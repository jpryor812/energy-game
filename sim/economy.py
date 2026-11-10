"""GDP, income, population, energy intensity, FX, approval and stability.

Annual GDP growth:  g = g0 + I + P + T - S - E - R - D - C - F - H

- g0: baseline, interpolated from `trend.g0_start` (2025) to `trend.g0_end` (final turn).
- I: zero; investment is already in g0, and public builds act through energy supply.
- P: productivity from cumulative research spending / GDP, capped.
- R: stranded-asset write-offs from early retirements, a one-off loss in the step after.
- T: trade: the change in fossil export value since 2025 as a share of GDP x elasticity, plus
  the goods-trade effect of tariffs (sim.trade) and clean-tech exports against their baseline.
- S: energy shortfall share x `shortfall_drag`.
- E: energy price rise above the 2025 level x `price_drag`, softened by carbon-revenue rebates.
- D: rise in hard-currency debt / GDP above the 2025 ratio x `debt_drag`.
- F: discretionary tax change x `tax.growth_drag` (negative when taxes are cut).
- H: one-off GDP loss from climate disasters (sim.shocks).
- C: climate damage from warming since 2025 (computed by sim.climate the step before).

Every drag is measured against the nation's own 2025 state, because the baseline growth rate
already reflects 2025 conditions. GDP is in T$ (constant 2025 USD at market exchange rates).
"""

from __future__ import annotations

from sim import energy, trade
from sim.config import Config
from sim.state import Nation, World


def baseline_growth(cfg: Config, nid: str, t: int) -> float:
    start = cfg.nat(nid, "trend.g0_start")
    end = cfg.nat(nid, "trend.g0_end")
    span = max(1, cfg.tune("time.turns") - 1)
    frac = min(1.0, max(0.0, t / span))
    return start + (end - start) * frac


def baseline_disaster_loss(cfg: Config, nid: str) -> float:
    """Expected annual GDP loss from disasters at 2025 warming on normal difficulty (mean
    severity 1, no adaptation). Baseline growth already includes it, so the growth term H only
    counts losses above it: more warming, or a harder world."""
    s = "shocks."
    above = max(0.0, cfg.tune("climate.warming_start") - cfg.tune(s + "disaster_threshold"))
    chance = cfg.tune(s + "disaster_rate") * above * cfg.nat(nid, "climate.vulnerability")
    return min(1.0, chance) * 4 * cfg.tune(s + "disaster_gdp_loss")


def permitting_opposition(cfg: Config, nid: str) -> float:
    """How strongly a nation's public pushes back on permitting reform (M10)."""
    spec = cfg.nat_spec(nid).get("permitting_opposition")
    return spec["value"] if spec else cfg.tune("permitting.default_opposition")


def permitting_backlash(cfg: Config, world: World, n: Nation) -> float:
    """Opposition to the nation's permitting reform now (M14): its permitting opposition, cut
    by `permitting.habituation_factor` once the current level has held for
    `permitting.habituation_quarters` (people get used to it)."""
    opp = permitting_opposition(cfg, n.id)
    if world.t - n.permitting_since >= cfg.tune("permitting.habituation_quarters"):
        opp *= cfg.tune("permitting.habituation_factor")
    return opp


def growth_terms(cfg: Config, nid: str, n: Nation, t: int, dt: int = 1) -> dict[str, float]:
    share_short = n.shortfall / n.demand if n.demand > 0 else 0.0
    base_price = n.base.get("energy_price", 0.0)
    price_rise = max(0.0, n.energy_price / base_price - 1.0) if base_price > 0 else 0.0
    relief = 1 - n.rebate * cfg.tune("economy.rebate_price_relief")
    export_change = (n.export_revenue - n.base.get("export_revenue", 0.0)) / n.gdp
    debt_rise = max(0.0, n.debt_hard / n.gdp - n.base.get("debt_hard_ratio", 0.0))
    research = sum(n.research.values()) / n.gdp
    return {
        "g0": baseline_growth(cfg, nid, t),
        "P": min(
            cfg.tune("research.productivity_cap"), cfg.tune("research.productivity") * research
        ),
        "T": cfg.tune("economy.trade_elasticity") * export_change
        + n.trade_drag
        + trade.cleantech_effect(cfg, n),
        "S": cfg.tune("economy.shortfall_drag") * share_short,
        "E": cfg.tune("economy.price_drag") * price_rise * relief,
        # A one-off level loss spread over this step, expressed as an annual rate.
        "R": cfg.tune("economy.stranded_drag") * n.pending_writeoff / n.gdp * 4 / dt,
        "D": cfg.tune("economy.debt_drag") * debt_rise,
        # Fiscal: discretionary tax above (or below) 2025 slows (or speeds) growth.
        "F": cfg.tune("tax.growth_drag") * n.tax_change,
        # Hazards: one-off GDP loss from climate disasters last quarter, as an annual rate, less
        # the average loss at 2025 warming, which baseline growth already reflects.
        "H": n.disaster_loss * 4 / dt - baseline_disaster_loss(cfg, nid),
        "C": n.climate_damage,
    }


def annual_growth(terms: dict[str, float]) -> float:
    gains = terms["g0"] + terms["P"] + terms["T"]
    losses = (
        terms["S"] + terms["E"] + terms["R"] + terms["D"] + terms["C"] + terms["F"] + terms["H"]
    )
    return gains - losses


def carbon_revenue(n: Nation) -> float:
    """Discretionary carbon revenue, T$/yr: only the price above its 2025 level counts (2025
    revenue is already in the ordinary budget), charged on CO2 emitted before carbon removal,
    minus the share rebated to households."""
    extra = max(0.0, n.carbon_price - n.base.get("carbon_price", 0.0))
    emitted = max(0.0, n.emissions + n.removals)  # charged on CO2 emitted, before removals
    return extra * emitted * 1e-6 * (1 - n.rebate)


def tax_credit_cost(n: Nation) -> float:
    """Revenue given up to tax credits, T$/yr: production credits ($/GJ x output) plus
    manufacturing credits (share x factory sales)."""
    cost = 0.0
    for key, rate in n.tax_credits.items():
        kind, tech = key.split(":", 1)
        if kind == "generation":
            cost += rate * n.supply.get(tech, 0.0) * 1e-3
        else:
            cost += rate * n.factory_sales.get(tech, 0.0)
    return cost


def apply_income(world: World, cfg: Config, dt: int) -> None:
    """Capital += discretionary share of GDP + government take on fossil exports + carbon
    revenue - interest on debt taken on during the game. Political capital and action slots
    accrue too.

    Debt service counts only debt above the 2025 level: servicing pre-existing public debt is
    part of the ordinary budget, not the discretionary capital the player spends.
    """
    share = cfg.tune("economy.capital_share_of_gdp")
    take = cfg.tune("economy.fossil_revenue_take")
    r_hard = cfg.tune("economy.interest_rate_hard")
    r_local = cfg.tune("economy.interest_rate_local")
    years = dt / 4
    for nid in sorted(world.nations):
        n = world.nations[nid]
        new_hard = max(0.0, n.debt_hard - n.base.get("debt_hard", 0.0))
        new_local = max(0.0, n.debt_local - n.base.get("debt_local", 0.0))
        n.carbon_revenue = carbon_revenue(n)
        income = share * n.gdp + take * n.export_revenue + n.carbon_revenue + n.tariff_revenue
        income += n.tax_change * n.gdp - tax_credit_cost(n)
        income -= r_hard * new_hard + r_local * new_local
        n.capital += income * years
        if n.capital < 0:  # a shortfall is borrowed locally, as for any spending (M8)
            n.debt_local -= n.capital
            n.capital = 0.0

        pc = cfg.tune("politics.pc_income_base") + cfg.tune("politics.pc_income_approval") * (
            n.approval - cfg.tune("politics.approval_baseline")
        )
        n.political_capital = max(0.0, n.political_capital + pc * years)
        for slot in ("domestic", "diplomatic"):
            per_quarter = cfg.tune(f"slots.{slot}_per_quarter")
            cap = cfg.tune(f"slots.{slot}_bank_cap")  # M8: unused slots bank only up to a cap
            n.slots_banked[slot] = min(cap, n.slots_banked.get(slot, 0) + per_quarter * dt)


def apply_growth(world: World, cfg: Config, dt: int) -> None:
    trade.apply_goods(world, cfg)
    pol = "politics."
    reversion = cfg.tune(pol + "approval_reversion")
    baseline = cfg.tune(pol + "approval_baseline")
    for nid in sorted(world.nations):
        n = world.nations[nid]
        terms = growth_terms(cfg, nid, n, world.t, dt)
        g = annual_growth(terms)
        n.growth = g
        n.pending_writeoff = 0.0
        n.disaster_loss = 0.0
        years = dt / 4
        n.gdp *= (1 + g) ** years
        n.population *= (1 + cfg.nat(nid, "trend.population_growth")) ** years
        n.energy_intensity *= (1 - cfg.nat(nid, "trend.intensity_decline")) ** years

        if not cfg.nat_spec(nid)["hard_currency_issuer"]:
            # Other trade is not modelled. An energy importer's 2025 deficit is assumed to be
            # financed by other exports that grow with GDP; an exporter's surplus is compared
            # with its 2025 level. Only deviations move reserves.
            base_balance = n.base.get("trade_balance", 0.0)
            expected = base_balance * n.gdp / n.base["gdp"] if base_balance < 0 else base_balance
            change = energy.trade_balance(cfg, n) - expected
            passthrough = cfg.tune("economy.fx_passthrough")
            n.fx_reserves = max(0.0, n.fx_reserves + passthrough * change * years)

        hit = (
            cfg.tune(pol + "approval_shortfall_hit") * terms["S"]
            + cfg.tune(pol + "approval_price_hit") * terms["E"]
            + cfg.tune(pol + "approval_damage_hit") * terms["C"]
            + cfg.tune("actions.activity_approval_hit") * n.activity_cap
            + cfg.tune("permitting.approval_hit")
            * n.permitting
            * permitting_backlash(cfg, world, n)
        )
        pull = 1 - (1 - reversion) ** years
        n.approval = min(1.0, max(0.0, n.approval + pull * (baseline - n.approval) - hit * years))
        s_pull = 1 - (1 - cfg.tune(pol + "stability_reversion")) ** years
        # Blackouts erode stability directly (unrest), on top of the pull toward approval, so
        # a government that cannot keep the lights on can fall between elections.
        unrest = cfg.tune(pol + "stability_shortfall_hit") * terms["S"] * years
        n.stability = min(1.0, max(0.0, n.stability + s_pull * (n.approval - n.stability) - unrest))
