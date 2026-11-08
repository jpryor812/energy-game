"""GDP, income, population, energy intensity, FX, approval and stability.

Annual GDP growth:  g = g0 + I + P + T - S - E - R - D - C

- g0: baseline, interpolated from `trend.g0_start` (2025) to `trend.g0_end` (final turn).
- I, P, R: zero until actions exist (M2).
- T: trade, the change in fossil export value since 2025 as a share of GDP x elasticity.
- S: energy shortfall share x `shortfall_drag`.
- E: energy price rise above the 2025 level x `price_drag`.
- D: rise in hard-currency debt / GDP above the 2025 ratio x `debt_drag`.
- C: climate damage from warming since 2025 (computed by sim.climate the step before).

Every drag is measured against the nation's own 2025 state, because the baseline growth rate
already reflects 2025 conditions. GDP is in T$ (constant 2025 USD at market exchange rates).
"""

from __future__ import annotations

from sim import energy
from sim.config import Config
from sim.state import Nation, World


def baseline_growth(cfg: Config, nid: str, t: int) -> float:
    start = cfg.nat(nid, "trend.g0_start")
    end = cfg.nat(nid, "trend.g0_end")
    span = max(1, cfg.tune("time.turns") - 1)
    frac = min(1.0, max(0.0, t / span))
    return start + (end - start) * frac


def growth_terms(cfg: Config, nid: str, n: Nation, t: int) -> dict[str, float]:
    share_short = n.shortfall / n.demand if n.demand > 0 else 0.0
    base_price = n.base.get("energy_price", 0.0)
    price_rise = max(0.0, n.energy_price / base_price - 1.0) if base_price > 0 else 0.0
    export_change = (n.export_revenue - n.base.get("export_revenue", 0.0)) / n.gdp
    debt_rise = max(0.0, n.debt_hard / n.gdp - n.base.get("debt_hard_ratio", 0.0))
    return {
        "g0": baseline_growth(cfg, nid, t),
        "T": cfg.tune("economy.trade_elasticity") * export_change,
        "S": cfg.tune("economy.shortfall_drag") * share_short,
        "E": cfg.tune("economy.price_drag") * price_rise,
        "D": cfg.tune("economy.debt_drag") * debt_rise,
        "C": n.climate_damage,
    }


def annual_growth(terms: dict[str, float]) -> float:
    return terms["g0"] + terms["T"] - terms["S"] - terms["E"] - terms["D"] - terms["C"]


def apply_income(world: World, cfg: Config, dt: int) -> None:
    """Capital += discretionary share of GDP + government take on fossil exports - debt service.

    Debt service counts only debt above the 2025 level: servicing pre-existing public debt is
    part of the ordinary budget, not the discretionary capital the player spends.
    """
    share = cfg.tune("economy.capital_share_of_gdp")
    take = cfg.tune("economy.fossil_revenue_take")
    r_hard = cfg.tune("economy.interest_rate_hard")
    r_local = cfg.tune("economy.interest_rate_local")
    for nid in sorted(world.nations):
        n = world.nations[nid]
        new_hard = max(0.0, n.debt_hard - n.base.get("debt_hard", 0.0))
        new_local = max(0.0, n.debt_local - n.base.get("debt_local", 0.0))
        income = share * n.gdp + take * n.export_revenue - r_hard * new_hard - r_local * new_local
        n.capital += income * dt / 4


def apply_growth(world: World, cfg: Config, dt: int) -> None:
    pol = "politics."
    reversion = cfg.tune(pol + "approval_reversion")
    baseline = cfg.tune(pol + "approval_baseline")
    for nid in sorted(world.nations):
        n = world.nations[nid]
        terms = growth_terms(cfg, nid, n, world.t)
        g = annual_growth(terms)
        n.growth = g
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
        )
        pull = 1 - (1 - reversion) ** years
        n.approval = min(1.0, max(0.0, n.approval + pull * (baseline - n.approval) - hit * years))
        s_pull = 1 - (1 - cfg.tune(pol + "stability_reversion")) ** years
        n.stability = min(1.0, max(0.0, n.stability + s_pull * (n.approval - n.stability)))
