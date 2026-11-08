"""Deterministic utility AI for non-player nations.

Each quarter an AI nation:

1. lists a fixed menu of concrete candidate actions from its state (`candidates`);
2. estimates each candidate's annual effects with closed-form proxies (`estimate`), not by
   simulating it: growth (pp/yr), energy security (pp of demand), emissions (% of 2025
   emissions/yr, negative = cut), and costs (years of capital and political-capital income);
3. scores it as personality-weighted effects minus costs (`utility`). The emissions weight
   rises with the gap between actual emissions and the nation's assumed target path
   (data/targets.yaml) and, for followers, with how much more its peers have cut;
4. picks the best-scoring affordable candidates, at most one per action type, up to its slots.
   Ties break by action type, then target. No randomness: this module never uses sim.rng.

A public build displaces what the market would otherwise have built, so its emissions and
price effects are measured against the market's current mix.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sim import actions, climate, construction, energy, tech
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
    margin = normal / demand - 1 if demand > 0 else 0.0
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
    buildable = set(construction.market_sources(cfg, nid))
    if n.capacity.get("nuclear", 0.0) > 0:
        buildable.add("nuclear")
    for s in sorted(buildable):
        unit = tech.nation_unit_cost(cfg, world, n, s)
        for share in _ai(cfg, "build_shares"):
            amount = share * n.capital / unit
            if amount > 0:
                out.append({"type": "build_capacity", "source": s, "amount": amount})
    if n.curtailment > 0:
        out.append({"type": "build_grid_storage", "kind": "storage", "amount": n.curtailment})
    cap = _p(cfg, personality, "carbon_price_max")
    for step in _ai(cfg, "carbon_steps"):
        if n.carbon_price < cap:
            level = min(cap, n.carbon_price + step)
            out.append({"type": "set_carbon_price", "level": level})
    coal = n.capacity.get("coal", 0.0)
    for share in _ai(cfg, "retire_shares"):
        if coal > 0:
            out.append({"type": "retire_capacity", "source": "coal", "amount": share * coal})
    clean = [s for s in ("solar", "wind", "other_renewables") if s in buildable]
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
    cost = actions.cost(cfg, world, n, act)
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
    elif kind == "adaptation_spend":
        before = climate.adaptation_factor(cfg, n)
        n.adaptation += act["amount"]
        try:
            after = climate.adaptation_factor(cfg, n)
        finally:
            n.adaptation -= act["amount"]
        eff.growth = n.climate_damage / before * (before - after) * 100 if before > 0 else 0.0
    return eff


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
    return str(act.get("source") or act.get("kind") or act.get("tech") or "")


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
    out.sort(key=lambda x: (-x[0], x[1]["type"], _target(x[1])))
    return out


def decide(cfg: Config, world: World, nid: str) -> list[Action]:
    """This quarter's actions for an AI nation (none if it has no personality)."""
    n = world.nations[nid]
    if cfg.nat_spec(nid).get("personality") is None:
        return []
    slots = dict(n.slots_banked)
    capital, pc = n.capital, n.political_capital
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
