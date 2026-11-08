"""Construction: retirements, completions, and the business-as-usual (BAU) builder.

Capacity retires at a constant annual rate: 1 / lifespan, or faster where the nation's own
2019-2024 data shows a faster decline (`bau.retire_rate`). There is no plant-age data, so this is
an approximation.

The market builder is the private sector, and runs for every nation. It keeps the nation's
*normal* output (capacity / headroom) on track to meet demand plus a reserve margin, after
expected retirements and counting everything already under construction (including public builds
from actions). New capacity is split by a blend of the nation's recent build mix (`bau.mix`) and a
cost-driven choice among the sources it can build (see `market_mix`). It also builds grid so wind
and solar are not curtailed. Orders are delivered after the slowest build time among the sources
it may build, so the mix arrives together; at t=0 the pipeline is seeded with the projects
already under way. Market builds cost the government nothing except any subsidy it has set.
"""

from __future__ import annotations

import math
from collections import defaultdict

from sim import economy, energy, tech
from sim.config import Config
from sim.energy import base_demand
from sim.state import Construction, Nation, World


def retire_rate(cfg: Config, nid: str, source: str) -> float:
    """Annual retirement fraction for one source in one nation."""
    rate = 1.0 / cfg.src(source, "lifespan")
    overrides = cfg.nat_spec(nid).get("bau", {}).get("retire_rate") or {}
    if source in overrides:
        rate = max(rate, overrides[source]["value"])
    return rate


def retire(cfg: Config, nid: str, n: Nation, dt: int) -> None:
    for s in sorted(n.capacity):
        n.capacity[s] *= (1.0 - retire_rate(cfg, nid, s)) ** (dt / 4)


def complete(n: Nation, t: int) -> dict[str, float]:
    """Bring finished projects online; return capacity completed per source."""
    done: dict[str, float] = defaultdict(float)
    remaining = []
    for c in n.pipeline:
        if c.complete_turn <= t:
            n.capacity[c.source] = n.capacity.get(c.source, 0.0) + c.amount
            done[c.source] += c.amount
        else:
            remaining.append(c)
    n.pipeline = remaining
    return dict(done)


def queue(cfg: Config, n: Nation, source: str, amount: float, t: int) -> None:
    if amount > 0:
        n.pipeline.append(Construction(source, amount, t + int(cfg.src(source, "build_time"))))


COST_DRIVEN = ("coal", "gas", "oil", "other_renewables", "solar", "wind")


def cost_candidates(cfg: Config, nid: str) -> list[str]:
    """Sources the market may pick on cost. Nuclear and hydro are policy-driven and appear only
    through the trend mix; coal only where the nation already uses it."""
    out = []
    for s in COST_DRIVEN:
        if s not in cfg.energy_source_ids:
            continue
        if s == "coal" and cfg.nat(nid, "start.energy.coal") <= 0:
            continue
        out.append(s)
    return out


def market_sources(cfg: Config, nid: str) -> list[str]:
    return sorted(set(cfg.nat_spec(nid)["bau"]["mix"]) | set(cost_candidates(cfg, nid)))


def horizon_quarters(cfg: Config, nid: str) -> int:
    """Market orders are delivered this many quarters after they are placed: the slowest build
    time among the sources it may build. Faster sources start later, so the mix arrives together."""
    return max(int(cfg.src(s, "build_time")) for s in market_sources(cfg, nid))


def market_mix(cfg: Config, world: World, nid: str, n: Nation) -> dict[str, float]:
    """(1 - w) x recent trend mix + w x logit of levelized cost, w = `market.cost_weight`.

    Levelized cost includes the carbon price, the nation's subsidy and research, learning-curve
    costs, and a system cost for wind and solar that grows with their share.
    """
    w = cfg.tune("market.cost_weight")
    temp = cfg.tune("market.cost_temperature")
    trend = {s: v["value"] for s, v in cfg.nat_spec(nid)["bau"]["mix"].items()}
    cands = cost_candidates(cfg, nid)
    costs = {s: tech.lcoe(cfg, world, n, s) for s in cands}
    low = min(costs.values())
    weights = {s: math.exp(-(costs[s] - low) / temp) for s in cands}
    total = sum(weights.values())
    mix = {s: (1 - w) * trend.get(s, 0.0) for s in market_sources(cfg, nid)}
    for s in cands:
        mix[s] += w * weights[s] / total
    return mix


def future_capacity(cfg: Config, nid: str, n: Nation, source: str, t: int, at: int) -> float:
    """Capacity of `source` expected at turn `at`: survivors plus projects finished by then."""
    years = (at - t) / 4
    kept = n.capacity.get(source, 0.0) * (1 - retire_rate(cfg, nid, source)) ** years
    arriving = sum(c.amount for c in n.pipeline if c.source == source and c.complete_turn <= at)
    return kept + arriving


def order(cfg: Config, world: World, nid: str, n: Nation, t: int, at: int) -> None:
    """Place market orders so that, at turn `at`, normal output covers projected demand plus the
    reserve margin, split by `market_mix`; add grid for the wind and solar. Subsidies are paid
    from capital when ordered (borrowed locally if capital runs out)."""
    growth = economy.baseline_growth(cfg, nid, t)
    decline = cfg.nat(nid, "trend.intensity_decline")
    demand_growth = (1 + growth) * (1 - decline) - 1
    target = base_demand(n) * (1 + demand_growth) ** ((at - t) / 4)
    target *= 1 + cfg.tune("market.reserve_margin")
    normal = sum(
        future_capacity(cfg, nid, n, s, t, at) / cfg.src(s, "headroom")
        for s in cfg.energy_source_ids
    )
    gap = target - normal
    if gap > 0:
        mix = market_mix(cfg, world, nid, n)
        for s in sorted(mix):
            amount = gap * mix[s] * cfg.src(s, "headroom")
            if amount <= 0:
                continue
            n.pipeline.append(Construction(s, amount, at))
            subsidy = n.subsidies.get(s, 0.0)
            if subsidy > 0:
                pay(n, subsidy * tech.nation_unit_cost(cfg, world, n, s) * amount)

    if "grid" in cfg.source_ids:
        enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
        vre = sum(future_capacity(cfg, nid, n, s, t, at) for s in cfg.vre_ids)
        absorb = cfg.tune("energy.vre_base_absorb_share") * target + sum(
            future_capacity(cfg, nid, n, s, t, at) for s in enablers
        )
        useful = min(vre, energy.vre_max_share(cfg, at) * target)
        if useful > absorb:
            n.pipeline.append(Construction("grid", useful - absorb, at))


def pay(n: Nation, amount: float) -> None:
    """Spend capital; any part capital cannot cover becomes local-currency debt."""
    from_capital = min(amount, max(0.0, n.capital))
    n.capital -= from_capital
    n.debt_local += amount - from_capital


def market_build(cfg: Config, world: World, nid: str, n: Nation) -> None:
    order(cfg, world, nid, n, world.t, world.t + horizon_quarters(cfg, nid))


def seed_pipeline(cfg: Config, world: World, nid: str, n: Nation) -> None:
    """At t=0, fill the pipeline with the projects the market would already have under way,
    one delivery per quarter up to the horizon."""
    for at in range(1, horizon_quarters(cfg, nid) + 1):
        order(cfg, world, nid, n, 0, at)


def apply(world: World, cfg: Config, dt: int) -> dict[str, float]:
    """Run construction for every nation; return capacity completed per source (all nations)."""
    completed: dict[str, float] = defaultdict(float)
    clean = [s for s in cfg.source_ids if cfg.category(s) != "fossil"]
    for nid in sorted(world.nations):
        n = world.nations[nid]
        retire(cfg, nid, n, dt)
        for s, amount in complete(n, world.t).items():
            completed[s] += amount
            if s in clean:
                n.clean_built += amount
        market_build(cfg, world, nid, n)
    return dict(completed)
