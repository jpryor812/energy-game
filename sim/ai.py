"""Deterministic utility AI for non-player nations.

Each quarter an AI nation:

1. lists a fixed menu of concrete candidate actions from its state (`candidates`);
2. estimates each candidate's annual effects with closed-form proxies (`estimate`), not by
   simulating it: growth (pp/yr), energy security (pp of demand), emissions (% of 2025
   emissions/yr, negative = cut), and costs (years of capital and political-capital income);
3. scores it as personality-weighted effects minus costs (`utility`). The emissions weight
   rises with the gap between actual emissions and the nation's assumed target path
   (data/targets.yaml) and, for followers, with how much more its peers have cut;
4. adds diplomatic candidates (`diplomatic`): answering deal proposals, matching or lifting
   tariffs, joining the carbon club, offering a deal once a year, and trading carbon credits;
5. picks the best-scoring affordable candidates, at most one per action type, up to its slots.
   Ties break by action type, then target. No randomness: this module never uses sim.rng.

A public build displaces what the market would otherwise have built, so its emissions and
price effects are measured against the market's current mix.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sim import (
    actions,
    climate,
    construction,
    credits,
    deals,
    diplomacy,
    economy,
    energy,
    regions,
    research,
    tech,
    trade,
)
from sim.config import Config
from sim.state import Nation, World

Action = dict[str, Any]


@dataclass
class Effects:
    growth: float = 0.0  # pp/yr
    security: float = 0.0  # pp of demand
    emissions: float = 0.0  # % of 2025 emissions per year (negative is a cut)
    capital: float = 0.0  # T$ spent (negative = income)
    political: float = 0.0  # political capital spent


def _ai(cfg: Config, name: str) -> Any:
    return cfg.tune(f"ai.{name}")


def _p(cfg: Config, personality: str, name: str) -> float:
    return cfg.tune(f"ai.personalities.{personality}.{name}")


# --- context shared by the estimates -------------------------------------------------------------


@dataclass
class Context:
    n: Nation
    mix: dict[str, float]
    ef_market: float
    lcoe: dict[str, float]
    lcoe_market: float
    imports_market: float
    demand: float
    delivered: float
    security_need: float
    margin: float
    ef_marginal: float
    annual_builds: float
    clean_room: float
    vre_room: float


def _ef(cfg: Config, nid: str, s: str) -> float:
    return energy.emission_factor(cfg, nid, s) if cfg.category(s) != "enabler" else 0.0


def _import_share(n: Nation, s: str) -> float:
    supplied = n.supply.get(s, 0.0)
    return n.fossil_imports.get(s, 0.0) / supplied if supplied > 0 else 0.0


def context(cfg: Config, world: World, nid: str) -> Context:
    n = world.nations[nid]
    mix = construction.market_mix(cfg, world, nid, n)
    lcoe = {s: tech.lcoe(cfg, world, n, s) for s in cfg.energy_source_ids}
    demand = energy.base_demand(n)
    absorb = energy.vre_absorb_limit(cfg, n, demand, world.t)
    normal = sum(
        construction.future_capacity(cfg, nid, n, s, world.t, world.t + 4) / cfg.src(s, "headroom")
        for s in cfg.energy_source_ids
        if s not in cfg.vre_ids
    )
    vre_future = sum(
        construction.future_capacity(cfg, nid, n, s, world.t, world.t + 4) for s in cfg.vre_ids
    )
    normal += min(vre_future, absorb)  # wind and solar count only as far as the grid takes them
    # M9: all clean output together is capped too (sim.energy.dispatch), so count it only up to
    # that cap; otherwise an AI retires fossil plants it still needs at the seasonal peak.
    clean_future = min(vre_future, absorb) + sum(
        construction.future_capacity(cfg, nid, n, s, world.t, world.t + 4) / cfg.src(s, "headroom")
        for s in cfg.energy_source_ids
        if s not in cfg.vre_ids and not energy.is_fossil(cfg, s)
    )
    normal -= max(0.0, clean_future - energy.clean_max_share(cfg, world.t, n) * demand)
    peak = demand * max(cfg.tune("seasonality.demand_factor"))  # judge spare capacity at the peak
    margin = normal / peak - 1 if peak > 0 else 0.0
    target_margin = _ai(cfg, "security_margin")
    need = max(0.0, target_margin - margin) / target_margin
    growth = (1 + n.growth) * (1 - cfg.nat(nid, "trend.intensity_decline")) - 1
    retiring = sum(
        n.capacity.get(s, 0.0) / cfg.src(s, "headroom") * construction.retire_rate(cfg, nid, s)
        for s in cfg.energy_source_ids
    )
    clean_supply = sum(v for s, v in n.supply.items() if not energy.is_fossil(cfg, s))
    vre_supply = sum(n.supply.get(s, 0.0) for s in cfg.vre_ids)
    running = [s for s in cfg.energy_source_ids if energy.is_fossil(cfg, s) and n.supply[s] > 0]
    marginal = max(
        running,
        key=lambda s: (energy.marginal_cost(cfg, nid, s, n.carbon_price), s),
        default=None,
    )
    return Context(
        n=n,
        margin=margin,
        ef_marginal=_ef(cfg, nid, marginal) if marginal else 0.0,
        clean_room=max(0.0, energy.clean_max_share(cfg, world.t) * demand - clean_supply),
        vre_room=max(0.0, min(energy.vre_max_share(cfg, world.t) * demand, absorb) - vre_supply),
        mix=mix,
        ef_market=sum(w * _ef(cfg, nid, s) for s, w in mix.items()),
        lcoe=lcoe,
        lcoe_market=sum(w * lcoe[s] for s, w in mix.items()),
        imports_market=sum(w * _import_share(n, s) for s, w in mix.items()),
        demand=demand,
        delivered=max(sum(n.supply.values()), 1e-9),
        security_need=need,
        annual_builds=max(0.0, demand * growth) + retiring,
    )


# --- candidates ----------------------------------------------------------------------------------


def candidates(cfg: Config, world: World, nid: str, personality: str) -> list[Action]:
    n = world.nations[nid]
    out: list[Action] = []
    buildable = set(construction.market_sources(cfg, nid, n))
    if n.capacity.get("nuclear", 0.0) > 0:
        buildable.add("nuclear")
    for s in sorted(buildable):
        unit = tech.nation_unit_cost(cfg, world, n, s)
        for share in _ai(cfg, "build_shares"):
            amount = share * n.capital / unit
            if amount > 0:
                out.append({"type": "build_capacity", "source": s, "amount": amount})
    if n.curtailment > 0:  # M12: any storage-like enabler it has researched
        for kind in ("storage", "long_duration_storage", "electrolysers"):
            if kind in cfg.source_ids and research.can_build(cfg, n, kind):
                out.append({"type": "build_grid_storage", "kind": kind, "amount": n.curtailment})
    if research.can(cfg, n, "ccs_retrofit"):  # M12: carbon capture on its coal and gas plants
        unit = cfg.tune("research.ccs_capital_cost")
        for fuel in research.CCS_FUELS:
            room = n.capacity.get(fuel, 0.0) - n.ccs.get(fuel, 0.0)
            amount = min(room, _ai(cfg, "factory_share") * max(0.0, n.capital) / unit)
            if amount > 1e-6:
                out.append({"type": "retrofit_ccs", "fuel": fuel, "amount": amount})
    cap = _p(cfg, personality, "carbon_price_max")
    for step in _ai(cfg, "carbon_steps"):
        if n.carbon_price < cap:
            level = min(cap, n.carbon_price + step)
            out.append({"type": "set_carbon_price", "level": level})
    coal = n.capacity.get("coal", 0.0)
    for share in _ai(cfg, "retire_shares"):
        if coal > 0:
            out.append({"type": "retire_capacity", "source": "coal", "amount": share * coal})
    clean = [
        s for s in ("solar", "onshore_wind", "offshore_wind", "bioenergy", "geothermal")
        if s in buildable and construction.has_resource(cfg, nid, s)
    ]  # fmt: skip
    if clean:
        best = min(clean, key=lambda s: (tech.lcoe(cfg, world, n, s), s))
        if n.subsidies.get(best, 0.0) < _ai(cfg, "subsidy_share"):
            out.append({"type": "set_subsidy", "source": best, "share": _ai(cfg, "subsidy_share")})
        out.append(
            {
                "type": "invest_research",
                "tech": best,
                "amount": _ai(cfg, "research_share") * n.capital,
            }
        )
    out.append({"type": "invest_efficiency", "amount": _ai(cfg, "efficiency_share") * n.capital})
    for t in trade.EQUIPMENT:
        cost = cfg.tune("industry.factory_capital_cost")
        out.append(
            {
                "type": "build_factory",
                "tech": t,
                "amount": _ai(cfg, "factory_share") * n.capital / cost,
            }
        )
    out.append({"type": "methane_abatement", "amount": _ai(cfg, "methane_share") * n.capital})
    if "carbon_removal" in cfg.source_ids:
        unit = tech.nation_unit_cost(cfg, world, n, "carbon_removal")
        use = cfg.src("carbon_removal", "energy_use")
        planned = n.capacity.get("carbon_removal", 0.0) + sum(
            c.amount for c in n.pipeline if c.source == "carbon_removal"
        )
        room = _ai(cfg, "removal_energy_cap") * n.gdp * n.energy_intensity / use - planned
        amount = min(_ai(cfg, "removal_share") * n.capital / unit, max(0.0, room))
        if amount > 0:
            out.append({"type": "build_removal", "amount": amount})
    out.append({"type": "fund_forests", "amount": _ai(cfg, "forest_share") * n.capital})
    if ctx_clean_room_tight(cfg, world, nid):
        out.append(
            {
                "type": "electrification_program",
                "amount": _ai(cfg, "electrification_share") * n.capital,
            }
        )
    if n.climate_damage > 0:
        out.append({"type": "adaptation_spend", "amount": _ai(cfg, "adaptation_share") * n.capital})
    if n.carbon_price > n.base.get("carbon_price", 0.0) and n.rebate < _ai(cfg, "rebate_share"):
        out.append({"type": "rebate", "share": _ai(cfg, "rebate_share")})
    if n.pledge is None:
        spec = cfg.targets["targets"][nid]
        out.append(
            {
                "type": "make_pledge",
                "target": spec["levels"]["value"][0],
                "year": spec["years"]["value"][0],
            }
        )
    return [a for a in out if all(v > 0 for k, v in a.items() if k in ("amount",))]


def ctx_clean_room_tight(cfg: Config, world: World, nid: str) -> bool:
    """Whether the nation's clean ceiling is nearly reached (electrification would pay)."""
    n = world.nations[nid]
    demand = max(sum(n.supply.values()), 1e-9)
    clean = sum(v for s, v in n.supply.items() if not energy.is_fossil(cfg, s))
    return clean / demand > energy.clean_max_share(cfg, world.t, n) - _ai(cfg, "ceiling_margin")


# --- estimates -----------------------------------------------------------------------------------


def _price_growth(cfg: Config, n: Nation, price_change: float) -> float:
    """pp/yr of growth from a change in the energy price ($/GJ)."""
    if n.energy_price <= 0:
        return 0.0
    relief = 1 - n.rebate * cfg.tune("economy.rebate_price_relief")
    return -cfg.tune("economy.price_drag") * price_change / n.energy_price * relief * 100


def estimate(cfg: Config, world: World, nid: str, act: Action, ctx: Context) -> Effects:
    n = ctx.n
    base_em = max(n.base.get("emissions", n.emissions), 1e-9)
    try:
        cost = actions.cost(cfg, world, n, act)
    except actions.Rejected:  # e.g. a deal plant of a technology the host lacks (M12)
        cost = {}
    eff = Effects(capital=cost.get("capital", 0.0), political=cost.get("political_capital", 0.0))
    kind = act["type"]

    if kind == "build_capacity":
        s = act["source"]
        normal = act["amount"] / cfg.src(s, "headroom")
        if not energy.is_fossil(cfg, s):  # clean output beyond the ceilings is wasted
            normal = min(normal, ctx.clean_room)
            if s in cfg.vre_ids:
                normal = min(normal, ctx.vre_room)
        # The build replaces what the market would build over the next year; any surplus pushes
        # out the most expensive fossil source now running.
        via_market = min(1.0, ctx.annual_builds / normal) if normal > 0 else 1.0
        displaced = via_market * ctx.ef_market + (1 - via_market) * ctx.ef_marginal
        eff.emissions = normal * (_ef(cfg, nid, s) - displaced) / base_em * 100
        eff.growth = _price_growth(cfg, n, normal / ctx.delivered * (ctx.lcoe[s] - ctx.lcoe_market))
        eff.security = (
            normal / ctx.demand * 100 * ctx.security_need
            + normal / ctx.demand * (ctx.imports_market - _import_share(n, s)) * 100
        )
    elif kind == "build_grid_storage":
        used = min(act["amount"], n.curtailment)
        eff.emissions = -used * ctx.ef_market / base_em * 100
    elif kind == "retrofit_ccs":  # M12: the captured share of the plants' current CO2
        fuel = act["fuel"]
        cap = n.capacity.get(fuel, 0.0)
        share = act["amount"] / cap if cap > 0 else 0.0
        cut = (
            cfg.tune("research.ccs_capture") * share * n.supply.get(fuel, 0.0) * _ef(cfg, nid, fuel)
        )
        eff.emissions = -cut / base_em * 100
    elif kind == "retire_capacity":
        s = act["source"]
        normal = act["amount"] / cfg.src(s, "headroom")
        eff.emissions = -normal * (_ef(cfg, nid, s) - ctx.ef_market) / base_em * 100
        writeoff = tech.unit_cost(cfg, world, s) * act["amount"]
        writeoff *= cfg.tune("actions.stranded_value_share")
        eff.growth = -cfg.tune("economy.stranded_drag") * writeoff / n.gdp * 100
        after = ctx.margin - normal / ctx.demand
        # Expected shortfall if spare capacity goes negative, as lost growth.
        eff.growth -= cfg.tune("economy.shortfall_drag") * max(0.0, -after) * 100
        tight = after < _ai(cfg, "security_margin")
        eff.security = -normal / ctx.demand * 100 * (1.0 if tight else 0.1)
    elif kind == "set_carbon_price":
        step = act["level"] - n.carbon_price
        eff.emissions = -_ai(cfg, "carbon_response") * step * 100
        fossil_ef = n.emissions / ctx.delivered  # Mt/EJ = kg/GJ across delivered energy
        eff.growth = _price_growth(cfg, n, step * fossil_ef / 1000)
        eff.capital -= step * n.emissions * 1e-6 * (1 - n.rebate)  # extra revenue per year
    elif kind == "rebate":
        price_rise = max(0.0, n.energy_price / n.base["energy_price"] - 1)
        change = act["share"] - n.rebate
        eff.growth = (
            cfg.tune("economy.price_drag") * price_rise * change
            * cfg.tune("economy.rebate_price_relief") * 100
        )  # fmt: skip
        extra = max(0.0, n.carbon_price - n.base.get("carbon_price", 0.0))
        eff.capital += extra * n.emissions * 1e-6 * change  # revenue given back per year
    elif kind == "set_subsidy":
        s = act["source"]
        old = n.subsidies.get(s, 0.0)
        n.subsidies[s] = act["share"]
        try:
            new_mix = construction.market_mix(cfg, world, nid, n)
        finally:
            n.subsidies[s] = old
        new_ef = sum(w * _ef(cfg, nid, x) for x, w in new_mix.items())
        eff.emissions = ctx.annual_builds * (new_ef - ctx.ef_market) / base_em * 100
        unit = tech.nation_unit_cost(cfg, world, n, s) * cfg.src(s, "headroom")
        eff.capital = act["share"] * unit * ctx.annual_builds * new_mix.get(s, 0.0)
    elif kind == "invest_research":
        cap = cfg.tune("research.productivity_cap") * 100
        eff.growth = min(cap, cfg.tune("research.productivity") * act["amount"] / n.gdp * 100)
    elif kind == "invest_efficiency":
        gain = actions.efficiency_gain(cfg, n, act["amount"])
        eff.emissions = -gain * n.emissions / base_em * 100
        eff.security = gain * n.import_dependence * 100
    elif kind == "build_factory":
        t = act["tech"]
        shares = trade.capacity_shares(cfg, world, t)
        total_capacity = sum(m.factory_capacity.get(t, 0.0) for m in world.nations.values())
        total_capacity += world.base.get(f"row_capacity_{t}", 0.0)
        gain = act["amount"] / (total_capacity + act["amount"]) * (1 - shares.get(nid, 0.0))
        abroad = sum(
            m.equipment_demand.get(t, 0.0) for mid, m in world.nations.items() if mid != nid
        )
        eff.growth = cfg.tune("trade.cleantech_growth_elasticity") * gain * abroad / n.gdp * 100
    elif kind == "methane_abatement":
        eff.emissions = -_methane_co2e(cfg, world, n, act["amount"]) / base_em * 100
    elif kind == "build_removal":
        grid_ef = n.emissions / ctx.delivered if ctx.delivered > 0 else 0.0
        energy_use = cfg.src("carbon_removal", "energy_use")
        eff.emissions = -act["amount"] * max(0.0, 1 - energy_use * grid_ef) / base_em * 100
    elif kind == "fund_forests":
        before = climate.forest_cut(cfg, world)
        world.forest_fund += act["amount"]
        try:
            after = climate.forest_cut(cfg, world)
        finally:
            world.forest_fund -= act["amount"]
        land = climate.exogenous_co2(cfg, world)["land_use"] / max(1e-9, 1 - before)
        credit = cfg.tune("credits.weight_forest") * (after - before) * land
        eff.emissions = -credit / base_em * 100
    elif kind == "electrification_program":
        before = energy.electrification_bonus(cfg, n)
        n.electrification += act["amount"]
        try:
            after = energy.electrification_bonus(cfg, n)
        finally:
            n.electrification -= act["amount"]
        room = (after - before) * ctx.demand
        eff.emissions = -room * ctx.ef_marginal / base_em * 100
    elif kind == "adaptation_spend":
        before = climate.adaptation_factor(cfg, n)
        n.adaptation += act["amount"]
        try:
            after = climate.adaptation_factor(cfg, n)
        finally:
            n.adaptation -= act["amount"]
        eff.growth = n.climate_damage / before * (before - after) * 100 if before > 0 else 0.0
    return eff


def _methane_co2e(cfg: Config, world: World, n: Nation, amount: float) -> float:
    """CO2-equivalent MtCO2/yr of spending `amount` on methane abatement: the steady-state
    warming avoided, spread over `ai.methane_horizon` years at the TCRE rate."""
    share = cfg.tune("climate.ch4_fossil_share")
    fossil = sum(n.fossil_production.values()) / max(world.base["fossil_production"], 1e-9)
    people = n.population / sum(m.population for m in world.nations.values())
    before = (climate.abatement(cfg, n, "fossil"), climate.abatement(cfg, n, "other"))
    n.methane_abatement += amount
    try:
        after = (climate.abatement(cfg, n, "fossil"), climate.abatement(cfg, n, "other"))
    finally:
        n.methane_abatement -= amount
    index_cut = share * fossil * (after[0] - before[0]) + (1 - share) * people * (
        after[1] - before[1]
    )
    warming = cfg.tune("climate.ch4_warming") * index_cut
    return warming / climate.co2_per_mt(cfg) / _ai(cfg, "methane_horizon")


# --- scoring and choice --------------------------------------------------------------------------


def emissions_weight(cfg: Config, world: World, nid: str, personality: str) -> float:
    n = world.nations[nid]
    base = _p(cfg, personality, "w_emissions")
    base_em = max(n.base.get("emissions", n.emissions), 1e-9)
    year = cfg.tune("time.start_year") + world.t / 4
    gap = n.emissions / base_em - cfg.target_level(nid, year)
    scale = _ai(cfg, "gap_scale")
    mult = 1 + _p(cfg, personality, "target_adherence") * gap / scale
    follow = _p(cfg, personality, "follow_strength")
    if follow > 0:
        own_cut = 1 - n.emissions / base_em
        peers = [
            1 - m.emissions / m.base["emissions"]
            for pid, m in sorted(world.nations.items())
            if pid != nid and m.base.get("emissions", 0) > 0
        ]
        if peers:
            mult += follow * (sum(peers) / len(peers) - own_cut) / scale
    return base * max(_ai(cfg, "emissions_weight_floor"), mult)


def income_per_year(cfg: Config, n: Nation) -> tuple[float, float]:
    capital = cfg.tune("economy.capital_share_of_gdp") * n.gdp
    capital += cfg.tune("economy.fossil_revenue_take") * n.export_revenue + n.carbon_revenue
    return max(capital, 1e-9), max(cfg.tune("politics.pc_income_base"), 1e-9)


def utility(cfg: Config, personality: str, eff: Effects, w_em: float, income) -> float:
    cap_income, pc_income = income
    cap_weight = _ai(cfg, "capital_cost_weight") / _p(cfg, personality, "budget_appetite")
    return (
        _p(cfg, personality, "w_growth") * eff.growth
        + _p(cfg, personality, "w_security") * eff.security
        - w_em * eff.emissions
        - cap_weight * eff.capital / cap_income
        - _ai(cfg, "pc_cost_weight") * eff.political / pc_income
    )


def _target(act: Action) -> str:
    keys = ("region", "event_id", "source", "kind", "tech", "target", "deal_id", "bloc")
    return str(next((act[k] for k in keys if k in act), ""))


# --- diplomacy -----------------------------------------------------------------------------------


def _imports_from(world: World, buyer: str, seller: str) -> float:
    """Goods `buyer` imports from `seller` (T$/yr) under the gravity split, before tariffs."""
    s = world.nations[seller]
    others = sum(n.gdp for nid, n in world.nations.items() if nid != seller)
    total = others + trade.row_gdp(world)
    return s.base["goods_openness"] * s.gdp * world.nations[buyer].gdp / total


def _tariff_cost_pp(cfg: Config, world: World, nid: str, partner: str, level: float) -> float:
    """Growth (pp/yr) a nation loses paying its own tariff on a partner's goods."""
    n = world.nations[nid]
    paid = level * _imports_from(world, nid, partner)
    return cfg.tune("trade.tariff_price_drag") * paid / n.gdp * 100


def fair_rate(cfg: Config, world: World, financier: str, host: str, kind: str) -> float:
    """The interest an AI financier asks: the discount rate plus a premium for low trust, less
    a concession on climate loans. Also the rate an AI host judges an offer against (W4)."""
    trust = diplomacy.trust(world, financier, host)
    rate = cfg.tune("market.discount_rate") + _ai(cfg, "deal_rate_premium") * (1 - trust)
    if kind == "climate_loan":
        rate = max(0.0, rate - _ai(cfg, "climate_loan_discount"))  # concessional
    return rate


def fair_term(cfg: Config, world: World, deal) -> float:
    """What an AI host thinks is a fair rate, equity share or price for `deal` (W4): what an AI
    financier would ask, or for energy as a service (which AIs do not offer) the plant's
    levelized cost in the host; for an equipment sale the usual markup, and for a factory
    partnership a share of earnings equal to the financier's stake."""
    if deal.type == "equity_for_energy":
        return _ai(cfg, "equity_share_offer")
    if deal.type == "equipment_sale":
        return cfg.tune("deals.fair_markup")
    if deal.type == "factory_partnership":
        return deals.stake(cfg, world, deal)
    if deal.type == "energy_as_a_service":
        return tech.lcoe(cfg, world, world.nations[deal.host], deal.terms["source"])
    return fair_rate(cfg, world, deal.financier, deal.host, deal.type)


def overprice(cfg: Config, world: World, deal) -> float:
    """How far a deal's terms are above fair, as a share (0 at or below fair)."""
    key = actions._price_key(deal)
    fair = fair_term(cfg, world, deal)
    if fair <= 0:
        return math.inf if deal.terms[key] > 0 else 0.0  # asking for something for nothing
    return max(0.0, deal.terms[key] / fair - 1)


def _value_deal_as_host(cfg, world, nid, deal, personality, ctx, w_em, income) -> float:
    """Utility to the host of accepting `deal`, net of its payments, minus the bar to accept."""
    n = ctx.n
    if deal.type == "factory_partnership":  # W4: a factory line, not a plant
        build = {
            "type": "build_factory",
            "tech": deal.terms["tech"],
            "amount": deal.terms["amount"],
        }
    else:
        capacity = deal.terms["amount"]
        if deal.type == "climate_loan":  # cash: value the capacity it buys at the host's cost
            unit = tech.nation_unit_cost(cfg, world, n, deal.terms["source"])
            capacity = deal.terms["amount"] / unit
        build = {"type": "build_capacity", "source": deal.terms["source"], "amount": capacity}
    eff = estimate(cfg, world, nid, build, ctx)
    outlay = deals.host_outlay(cfg, world, deal)  # W4: paid at signing (a sale, a factory share)
    if outlay > n.capital:
        return -math.inf
    benefit = (
        _p(cfg, personality, "w_growth") * eff.growth
        + _p(cfg, personality, "w_security") * eff.security
        - w_em * eff.emissions
    )
    payment = deals.annual_payment(cfg, world, deal)
    committed = deals.obligations(cfg, world, nid)
    if payment + committed > _ai(cfg, "max_payment_share") * income[0]:
        return -math.inf  # cannot afford the payments
    cap_weight = _ai(cfg, "capital_cost_weight") / _p(cfg, personality, "budget_appetite")
    cost = payment + outlay  # M9: a climate loan builds the plant, so principal is a real cost
    value = benefit - cap_weight * cost / income[0]
    bar = -_p(cfg, personality, "w_deals") * _p(cfg, personality, "deal_affinity")
    bar -= _ai(cfg, "trust_weight") * (diplomacy.trust(world, nid, deal.financier) - 0.5)
    bar += _ai(cfg, "overprice_weight") * overprice(cfg, world, deal)  # W4: haggling
    if deal.terms["currency"] == "hard" and not cfg.nat_spec(nid)["hard_currency_issuer"]:
        bar += _ai(cfg, "currency_risk_weight") * payment / max(n.fx_reserves, 1e-9)
    return value - bar


def _deal_offer(cfg, world, nid, personality, w_em, income) -> tuple[float, Action] | None:
    """One deal this AI would offer as financier this quarter, if any."""
    n = world.nations[nid]
    if (world.t + sorted(world.nations).index(nid)) % 4:
        return None  # each AI considers offering once a year, staggered across nations
    if n.capital <= _ai(cfg, "deal_reserve_years") * income[0]:
        return None
    busy = {
        d.host
        for d in world.deals.values()
        if d.financier == nid and (d.status == deals.OPEN or world.t - d.start_turn < 4)
    }
    # Rank hosts by trust x need: emissions intensity and baseline growth, each relative to the
    # 16-nation average (M8: growth too, so clean but fast-growing nations still get offers).
    ids = sorted(world.nations)
    intensity = {i: max(0.0, world.nations[i].emissions) / world.nations[i].gdp for i in ids}
    growth = {i: max(0.0, economy.baseline_growth(cfg, i, world.t)) for i in ids}
    avg_i = max(sum(intensity.values()) / len(ids), 1e-12)
    avg_g = max(sum(growth.values()) / len(ids), 1e-12)
    hosts = []
    for hid in ids:
        if hid == nid or hid in busy or deals.host_room(cfg, world, hid) <= 0:
            continue
        need = intensity[hid] / avg_i + _ai(cfg, "host_growth_weight") * growth[hid] / avg_g
        if need > 0:
            hosts.append((diplomacy.trust(world, nid, hid) * need, hid))
    if not hosts:
        return None
    _, hid = max(hosts)
    host = world.nations[hid]
    options = [  # M12: plus any researched source the financier can supply
        s for s in construction.COST_DRIVEN
        if s in cfg.energy_source_ids and not energy.is_fossil(cfg, s)
        and construction.has_resource(cfg, hid, s) and research.can_build(cfg, n, s)
    ]  # fmt: skip
    source = min(options, key=lambda s: (tech.lcoe(cfg, world, host, s), s))
    kind = cfg.tuning["ai"]["personalities"][personality]["preferred_deal"]
    unit = tech.nation_unit_cost(cfg, world, n, source)
    rate = fair_rate(cfg, world, nid, hid, kind)
    years = _ai(cfg, "deal_duration") / 4
    host_income = income_per_year(cfg, host)[0]
    room = _ai(cfg, "max_payment_share") * host_income - deals.obligations(cfg, world, hid)
    budget = _ai(cfg, "deal_share") * n.capital
    if kind != "equity_for_energy":  # fixed repayments must fit the host's budget
        budget = min(budget, max(0.0, room) / (1 / years + rate))
    # M9: no bigger than the host can take (capacity at the host's own cost for a loan)
    budget = min(
        budget,
        deals.host_room(cfg, world, hid) * tech.nation_unit_cost(cfg, world, host, source)
        if kind == "climate_loan"
        else deals.host_room(cfg, world, hid) * unit,
    )
    if budget <= 0:
        return None
    act = {
        "type": "propose_deal",
        "target": hid,
        "deal_type": kind,
        "source": source,
        "amount": budget if kind == "climate_loan" else budget / unit,
        "duration": _ai(cfg, "deal_duration"),
        "collateral": _ai(cfg, "deal_collateral"),
        "exit_penalty": _ai(cfg, "deal_exit_penalty"),
    }
    if kind == "equity_for_energy":
        act["share"] = _ai(cfg, "equity_share_offer")
    else:
        act["currency"] = "hard"
        act["rate" if kind != "energy_as_a_service" else "price"] = rate
    capacity = budget / unit
    cut = capacity / cfg.src(source, "headroom") * trade.displaced_ef(cfg, host)
    credit = cfg.tune("credits.weight_financed") * cut / max(n.base["emissions"], 1e-9) * 100
    u = _p(cfg, personality, "w_deals") * _p(cfg, personality, "deal_affinity") + w_em * credit
    return u, act


def diplomatic(cfg, world, nid, personality, ctx, w_em, income) -> list[tuple[float, Action]]:
    """Diplomatic candidates with their utilities."""
    n = ctx.n
    p = lambda k: _p(cfg, personality, k)  # noqa: E731
    out: list[tuple[float, Action]] = []
    members = set(trade.club_members(world))

    for did in sorted(world.deals):
        d = world.deals[did]
        if d.status != deals.OPEN or deals.responder(d) != nid or d.start_turn >= world.t:
            continue
        if nid == d.host:
            margin = _value_deal_as_host(cfg, world, nid, d, personality, ctx, w_em, income)
            if margin > 0:
                out.append(
                    (margin + 1, {"type": "respond_deal", "deal_id": did, "response": "accept"})
                )
            elif margin > -_ai(cfg, "counter_margin") and d.terms["proposer"] == d.financier:
                key = actions._price_key(d)
                counter = d.terms[key] * _ai(cfg, "counter_rate_factor")
                act = {"type": "respond_deal", "deal_id": did, "response": "counter", key: counter}
                out.append((1.0, act))
        else:  # a counter-offer back to us as financier: accept one round if affordable and
            # not below our floor on what we first asked (M8); refuse otherwise
            key = actions._price_key(d)
            floor = _ai(cfg, "counter_accept_share") * d.terms.get("asked", d.terms[key])
            ok = d.terms[key] >= floor - 1e-12 and deals.build_cost(cfg, world, d) <= n.capital
            response = "accept" if ok else "refuse"
            out.append((1.0, {"type": "respond_deal", "deal_id": did, "response": response}))

    for pid in sorted(world.nations):
        if pid == nid or (nid in members and pid in members):
            continue
        theirs = world.nations[pid].tariffs.get(nid, 0.0)
        mine = n.tariffs.get(pid, 0.0)
        if theirs > mine and p("retaliation") > 0:
            u = p("retaliation") * theirs * 10
            u -= p("w_growth") * _tariff_cost_pp(cfg, world, nid, pid, theirs)
            out.append((u, {"type": "set_tariff", "target": pid, "level": theirs}))
        elif mine > theirs:
            u = p("w_growth") * _tariff_cost_pp(cfg, world, nid, pid, mine - theirs) + p("w_trust")
            act = {"type": "set_tariff", "target": pid, "level": theirs}
            out.append((u, act if theirs > 0 else {"type": "lift_tariff", "target": pid}))

    if nid not in members and diplomacy.club_eligible(cfg, world, nid):
        level = world.coalition_tariffs.get(nid, 0.0)
        to_members = sum(_imports_from(world, m, nid) for m in members)
        avoided = (
            cfg.tune("trade.export_growth_elasticity") * cfg.tune("trade.tariff_elasticity")
            * level * to_members / n.gdp * 100
        )  # fmt: skip
        u = p("w_growth") * avoided + p("w_trust") * _ai(cfg, "club_affinity")
        out.append((u, {"type": "join_bloc", "bloc": trade.CLUB}))

    offer = _deal_offer(cfg, world, nid, personality, w_em, income)
    if offer:
        out.append(offer)
    region = region_candidate(cfg, world, nid, personality, w_em, income)
    if region:
        out.append(region)
    pledge = event_candidate(cfg, world, nid, personality)
    if pledge:
        out.append(pledge)

    value, price = p("credit_value"), world.credit_price
    if n.credit_balance > 0 and price >= value:
        act = {"type": "sell_credits", "amount": n.credit_balance, "min_price": value}
        out.append(((price - value) / value + 0.1, act))
    interval = cfg.tune("time.stocktake_interval")
    quarters_left = interval - world.t % interval
    projected = n.period_emissions + n.emissions * quarters_left / 4
    short = projected - n.fair_share_budget - n.credit_balance
    if short > 0 and price < value:
        amount = _ai(cfg, "credit_cover_share") * short
        amount = min(amount, 0.1 * n.capital / max(credits.cost(1.0, value), 1e-18))
        if amount > 0:
            u = w_em * (value - price) / value
            out.append((u, {"type": "buy_credits", "amount": amount, "max_price": value}))
    return out


def region_candidate(cfg, world, nid, personality, w_em, income) -> tuple[float, Action] | None:
    """Concessional clean-energy finance for a region (M15), considered once a year (staggered
    like deal offers): the region where a T$ cuts the most (highest emission factor, weighted by
    how fossil it still is), with the cheaper source there. Utility: the financed credit plus
    `region_affinity`, less the cost of lending below the discount rate."""
    n = world.nations[nid]
    if (world.t + sorted(world.nations).index(nid) + 2) % 4 or not world.regions:
        return None
    if n.capital <= _ai(cfg, "deal_reserve_years") * income[0]:
        return None

    def need(rid: str) -> float:
        r = world.regions[rid]
        return cfg.reg(rid, "fossil_ef") * r.fossil / max(r.clean + r.fossil, 1e-9)

    open_ = [rid for rid in sorted(world.regions) if regions.room(cfg, world, rid) > 0]
    if not open_:
        return None
    rid = max(open_, key=need)
    sources = list(cfg.tuning["regions"]["finance_sources"])
    per_tn = {s: regions.delivered_per_trillion(cfg, world, s) for s in sources}
    source = max(sources, key=lambda s: (per_tn[s], s))
    most = regions.room(cfg, world, rid) / per_tn[source] * (1 - 1e-9)
    amount = min(_ai(cfg, "region_share") * n.capital, most)
    if amount <= 0:
        return None
    cut = amount * per_tn[source] * cfg.reg(rid, "fossil_ef")
    years = cfg.tune("regions.loan_years")
    credit = cfg.tune("credits.weight_financed") * cut / max(n.base["emissions"], 1e-9) * 100
    # Share of the loan lost by lending below the discount rate (present value of repayments).
    pv = regions.payment_rate(cfg) / tech.crf(cfg.tune("market.discount_rate"), years)
    cap_weight = _ai(cfg, "capital_cost_weight") / _p(cfg, personality, "budget_appetite")
    u = (
        _p(cfg, personality, "w_deals") * _ai(cfg, "region_affinity")
        + w_em * credit
        - cap_weight * amount * max(0.0, 1 - pv) / income[0]
    )
    return u, {"type": "finance_region", "region": rid, "source": source, "amount": amount}


def event_candidate(cfg, world, nid, personality) -> tuple[float, Action] | None:
    """A pledge to a minor-nation event's fund (M15b): this nation's fair share (its share of the
    16 nations' GDP) x its personality's `event_propensity`, to the first open event it has not
    pledged to. Cautious followers wait until others have pledged `event_follow_share`."""
    from sim import events

    n = world.nations[nid]
    propensity = _p(cfg, personality, "event_propensity")
    if propensity <= 0:
        return None
    gdp = sum(m.gdp for m in world.nations.values())
    for event in events.open_events(world):
        if nid in event["pledges"]:
            continue
        given = events.pledged(event) / event["target"]
        if personality == "cautious_follower" and given < _ai(cfg, "event_follow_share"):
            continue
        amount = min(
            event["target"] * n.gdp / gdp * propensity,
            events.remaining(event),
            max(0.0, n.capital),
        )
        if amount <= 1e-9:
            continue
        act = {"type": "pledge_to_event", "event_id": event["id"], "amount": amount}
        return _ai(cfg, "event_utility") * propensity, act
    return None


def research_candidate(cfg: Config, world: World, nid: str, personality: str):
    """The tech-tree research this AI would fund this quarter (M12): the first technology in its
    personality's priority list it can research (cautious followers only research what someone
    already has), funded with a share of capital up to what speeds it. None if nothing fits."""
    n = world.nations[nid]
    spec = cfg.tuning["ai"]["personalities"][personality]
    follower = personality == "cautious_follower"
    for tid in spec.get("research_priority", []):
        if research.blocked(cfg, n, tid) or (follower and tid not in world.tech_firsts):
            continue
        amount = min(
            _ai(cfg, "tech_research_share") * max(0.0, n.capital),
            research.useful_funding(cfg, world, n, tid),
        )
        if amount <= 0:
            return None
        act = {"type": "fund_research", "tech": tid, "amount": amount}
        return _p(cfg, personality, "research_utility"), act
    return None


def license_candidate(cfg: Config, world: World, nid: str, personality: str):
    """A licence this AI would buy (M13): the first technology in its priority list whose
    cheapest offer costs less than finishing the research itself and fits its budget."""
    n = world.nations[nid]
    budget = cfg.tune("license.ai_license_share") * max(0.0, n.capital)
    for tid in cfg.tuning["ai"]["personalities"][personality].get("research_priority", []):
        if research.has(n, tid) or research.missing_prerequisites(cfg, n, tid):
            continue
        found = research.offers(cfg, world, nid, tid)
        if not found:
            continue
        price, seller = found[0]
        if price < research.research_cost_for(cfg, world, n, tid) and price <= budget:
            act = {"type": "buy_license", "tech": tid, "seller": seller}
            return _p(cfg, personality, "research_utility") + 0.1, act
    return None


def scored(cfg: Config, world: World, nid: str) -> list[tuple[float, Action, dict[str, float]]]:
    """Every valid candidate with its utility and resource cost, best first."""
    personality = cfg.nat_spec(nid)["personality"]
    ctx = context(cfg, world, nid)
    w_em = emissions_weight(cfg, world, nid, personality)
    income = income_per_year(cfg, ctx.n)
    out = []
    for act in candidates(cfg, world, nid, personality):
        try:
            cost = actions.cost(cfg, world, ctx.n, act)
        except actions.Rejected:
            continue
        if act["type"] == "make_pledge":
            u = math.inf  # free, and states the nation's direction
        else:
            u = utility(cfg, personality, estimate(cfg, world, nid, act, ctx), w_em, income)
        out.append((u, act, cost))
    extra = diplomatic(cfg, world, nid, personality, ctx, w_em, income)
    for pick in (research_candidate, license_candidate):
        found = pick(cfg, world, nid, personality)
        if found:
            extra.append(found)
    for u, act in extra:
        try:
            cost = actions.cost(cfg, world, ctx.n, act)
        except actions.Rejected:
            continue
        out.append((u, act, cost))
    out.sort(key=lambda x: (-x[0], x[1]["type"], _target(x[1])))
    return out


def decide(cfg: Config, world: World, nid: str) -> list[Action]:
    """This quarter's actions for an AI nation (none if it has no personality)."""
    n = world.nations[nid]
    if cfg.nat_spec(nid).get("personality") is None:
        return []
    slots = dict(n.slots_banked)
    # Keep the next six months of deal payments in hand before spending.
    reserve = deals.obligations(cfg, world, nid) / 2
    capital, pc = n.capital - reserve, n.political_capital
    chosen: list[Action] = []
    used_types: set[str] = set()
    for u, act, cost in scored(cfg, world, nid):
        if u <= _ai(cfg, "min_utility"):
            break
        slot = actions.SPECS[act["type"]].slot
        if act["type"] in used_types or slots.get(slot, 0) < 1:
            continue
        if cost.get("capital", 0.0) > capital or cost.get("political_capital", 0.0) > pc:
            continue
        chosen.append(act)
        used_types.add(act["type"])
        slots[slot] -= 1
        capital -= cost.get("capital", 0.0)
        pc -= cost.get("political_capital", 0.0)
    return chosen
