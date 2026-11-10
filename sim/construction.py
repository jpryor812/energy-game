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

from sim import economy, energy, research, tech, trade
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
    research.retire_ccs(n)  # M12: capture retrofits go with their plants
    keep = (1.0 - 1.0 / cfg.tune("industry.factory_lifespan")) ** (dt / 4)
    for kind in sorted(n.factory_capacity):  # M9: factories age out too
        n.factory_capacity[kind] *= keep


def retire_world_factories(cfg: Config, world: World, dt: int) -> None:
    """The rest of the world's factories age at the same rate as the 16 nations' (M9), so
    shares hold steady unless someone builds."""
    keep = (1.0 - 1.0 / cfg.tune("industry.factory_lifespan")) ** (dt / 4)
    for key in sorted(world.base):
        if key.startswith("row_capacity_"):
            world.base[key] *= keep


FACTORY = "factory_"  # pipeline prefix for clean-tech factories, e.g. "factory_solar"


def complete(n: Nation, t: int) -> dict[str, float]:
    """Bring finished projects online; return energy capacity completed per source. Finished
    factories add to factory capacity instead."""
    done: dict[str, float] = defaultdict(float)
    remaining = []
    for c in n.pipeline:
        if c.complete_turn > t:
            remaining.append(c)
        elif c.source.startswith(FACTORY):
            tech = c.source[len(FACTORY) :]
            n.factory_capacity[tech] = n.factory_capacity.get(tech, 0.0) + c.amount
        else:
            n.capacity[c.source] = n.capacity.get(c.source, 0.0) + c.amount
            done[c.source] += c.amount
    n.pipeline = remaining
    return dict(done)


def build_time(cfg: Config, n: Nation | None, source: str) -> int:
    """Quarters to build `source` in nation `n`: the source's build time, less the part of its
    permitting time that the nation's permitting reform cuts (M10). At least one quarter."""
    return tech.build_quarters(cfg, n, source)


def queue(cfg: Config, n: Nation, source: str, amount: float, t: int) -> None:
    if amount > 0:
        n.pipeline.append(Construction(source, amount, t + build_time(cfg, n, source)))


COST_DRIVEN = (
    "coal", "gas", "oil", "bioenergy", "geothermal", "solar", "onshore_wind", "offshore_wind",
    "smr", "advanced_fission", "fusion", "enhanced_geothermal",  # M12: once researched
)  # fmt: skip


NEEDS_RESOURCE = ("geothermal",)  # M11: buildable only where the nation already uses it


def has_resource(cfg: Config, nid: str, source: str) -> bool:
    """Whether the nation can build `source` at all: conventional geothermal needs suitable
    ground, which we take as the nation already using some (M11)."""
    if source not in NEEDS_RESOURCE:
        return True
    return cfg.nat(nid, f"start.energy.{source}") > 0


def cost_candidates(cfg: Config, nid: str, n: Nation | None = None) -> list[str]:
    """Sources the market may pick on cost. Nuclear and hydro are policy-driven and appear only
    through the trend mix; coal only where the nation already uses it; geothermal only where it
    has the resource; sources that need research only once nation `n` has it (M12)."""
    out = []
    for s in COST_DRIVEN:
        if s not in cfg.energy_source_ids or not has_resource(cfg, nid, s):
            continue
        if cfg.requires(s) and (n is None or not research.can_build(cfg, n, s)):
            continue
        if s == "coal" and cfg.nat(nid, "start.energy.coal") <= 0:
            continue
        out.append(s)
    return out


def market_sources(cfg: Config, nid: str, n: Nation | None = None) -> list[str]:
    return sorted(set(cfg.nat_spec(nid)["bau"]["mix"]) | set(cost_candidates(cfg, nid, n)))


def horizon_quarters(cfg: Config, nid: str, n: Nation | None = None) -> int:
    """Market orders are delivered this many quarters after they are placed: the slowest build
    time among the sources it may build (after `n`'s permitting reform, if given). Faster
    sources start later, so the mix arrives together."""
    return max(build_time(cfg, n, s) for s in market_sources(cfg, nid, n))


def market_mix(cfg: Config, world: World, nid: str, n: Nation) -> dict[str, float]:
    """(1 - w) x recent trend mix + w x logit of levelized cost, w = `market.cost_weight`.

    Levelized cost includes the carbon price, the nation's subsidy and research, learning-curve
    costs, and a system cost for wind and solar that grows with their share.
    """
    w = cfg.tune("market.cost_weight")
    temp = cfg.tune("market.cost_temperature")
    trend = {s: v["value"] for s, v in cfg.nat_spec(nid)["bau"]["mix"].items()}
    cands = cost_candidates(cfg, nid, n)
    costs = {s: tech.lcoe(cfg, world, n, s) for s in cands}
    low = min(costs.values())
    weights = {s: math.exp(-(costs[s] - low) / temp) for s in cands}
    total = sum(weights.values())
    mix = {s: (1 - w) * trend.get(s, 0.0) for s in market_sources(cfg, nid, n)}
    for s in cands:
        mix[s] += w * weights[s] / total
    return mix


def future_capacity(cfg: Config, nid: str, n: Nation, source: str, t: int, at: int) -> float:
    """Capacity of `source` expected at turn `at`: survivors plus projects finished by then."""
    years = (at - t) / 4
    kept = n.capacity.get(source, 0.0) * (1 - retire_rate(cfg, nid, source)) ** years
    arriving = sum(c.amount for c in n.pipeline if c.source == source and c.complete_turn <= at)
    return kept + arriving


def order(
    cfg: Config, world: World, nid: str, n: Nation, t: int, at: int, fast: bool = False
) -> None:
    """Place market orders so that, at turn `at`, normal output covers projected demand plus the
    reserve margin, split by `market_mix`; add grid for the wind and solar. Subsidies are paid
    from capital when ordered (borrowed locally if capital runs out)."""
    growth = economy.baseline_growth(cfg, nid, t)
    decline = cfg.nat(nid, "trend.intensity_decline")
    demand_growth = (1 + growth) * (1 - decline) - 1
    economy_demand = (base_demand(n) - n.extra_demand) * (1 + demand_growth) ** ((at - t) / 4)
    removal_demand = 0.0
    if "carbon_removal" in cfg.source_ids:  # plan power for removal already being built
        removal = future_capacity(cfg, nid, n, "carbon_removal", t, at)
        removal_demand = removal * cfg.src("carbon_removal", "energy_use")
    target = (economy_demand + removal_demand) * (1 + cfg.tune("market.reserve_margin"))
    future = {s: future_capacity(cfg, nid, n, s, t, at) for s in cfg.energy_source_ids}
    normal = {s: future[s] / cfg.src(s, "headroom") for s in future}
    vre_cap = energy.vre_max_share(cfg, at, n) * target
    clean_cap = energy.clean_max_share(cfg, at, n) * target
    enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
    absorb = cfg.tune("energy.vre_base_absorb_share") * target + sum(
        future_capacity(cfg, nid, n, s, t, at) for s in enablers
    )
    # Count only wind and solar the grid will be able to take.
    vre_normal = min(sum(normal[s] for s in cfg.vre_ids), vre_cap, absorb)
    clean_normal = vre_normal + sum(
        v for s, v in normal.items() if not energy.is_fossil(cfg, s) and s not in cfg.vre_ids
    )
    clean_normal = min(clean_normal, clean_cap)
    fossil_normal = sum(v for s, v in normal.items() if energy.is_fossil(cfg, s))
    gap = target - clean_normal - fossil_normal
    if gap > 0:
        alloc = split_gap(
            cfg, world, nid, n, gap, vre_cap - vre_normal, clean_cap - clean_normal,
            lead=at - t if fast else None,
        )  # fmt: skip
        for s in sorted(alloc):
            amount = alloc[s] * cfg.src(s, "headroom")
            if amount <= 0:
                continue
            n.pipeline.append(Construction(s, amount, at))
            subsidy = n.subsidies.get(s, 0.0)
            if subsidy > 0:
                pay(n, subsidy * tech.nation_unit_cost(cfg, world, n, s) * amount)

    if "grid" in cfg.source_ids and not fast:  # grid is too slow for short-range orders
        enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
        vre = sum(future_capacity(cfg, nid, n, s, t, at) for s in cfg.vre_ids)
        absorb = cfg.tune("energy.vre_base_absorb_share") * target + sum(
            future_capacity(cfg, nid, n, s, t, at) for s in enablers
        )
        useful = min(
            vre,
            energy.vre_max_share(cfg, at, n) * target,
            energy.clean_max_share(cfg, at, n) * target,
        )
        if useful > absorb:
            n.pipeline.append(Construction("grid", useful - absorb, at))


def split_gap(
    cfg: Config,
    world: World,
    nid: str,
    n: Nation,
    gap: float,
    vre_room: float,
    clean_room: float,
    lead: int | None = None,
) -> dict[str, float]:
    """Split a gap in normal output by the market mix, keeping wind and solar within the
    electrifiable share and all clean sources within the clean ceiling; the rest goes to fossil
    sources by their mix weights (or the cheapest fossil source if the mix has none)."""
    mix = market_mix(cfg, world, nid, n)
    if lead is not None:  # only sources that can be built in time (M9 short-range orders)
        fast = {s: w for s, w in mix.items() if build_time(cfg, n, s) <= lead}
        total_w = sum(fast.values())
        mix = {s: w / total_w for s, w in fast.items()} if total_w > 0 else {}
    if n.fossil_ban:  # no new fossil plants: their share goes to clean sources
        clean_w = {s: w for s, w in mix.items() if not energy.is_fossil(cfg, s)}
        total_w = sum(clean_w.values())
        mix = {s: w / total_w for s, w in clean_w.items()} if total_w > 0 else {}
    alloc = {s: gap * w for s, w in mix.items()}
    vre = sum(alloc.get(s, 0.0) for s in cfg.vre_ids)
    if vre > max(0.0, vre_room):
        for s in cfg.vre_ids:
            if s in alloc:
                alloc[s] *= max(0.0, vre_room) / vre
    clean = [s for s in alloc if not energy.is_fossil(cfg, s)]
    total_clean = sum(alloc[s] for s in clean)
    if total_clean > max(0.0, clean_room):
        for s in clean:
            alloc[s] *= max(0.0, clean_room) / total_clean
    leftover = gap - sum(alloc.values())
    if leftover > 1e-12 and not n.fossil_ban:  # under a ban the gap stays unfilled
        fossil = {s: w for s, w in mix.items() if energy.is_fossil(cfg, s) and w > 0}
        if not fossil:
            options = [s for s in cost_candidates(cfg, nid, n) if energy.is_fossil(cfg, s)]
            if lead is not None:
                options = [s for s in options if build_time(cfg, n, s) <= lead]
            if not options:
                return alloc
            fossil = {min(options, key=lambda s: (tech.lcoe(cfg, world, n, s), s)): 1.0}
        total = sum(fossil.values())
        for s, w in fossil.items():
            alloc[s] = alloc.get(s, 0.0) + leftover * w / total
    return alloc


def pay(n: Nation, amount: float) -> None:
    """Spend capital; any part capital cannot cover becomes local-currency debt."""
    from_capital = min(amount, max(0.0, n.capital))
    n.capital -= from_capital
    n.debt_local += amount - from_capital


def market_build(cfg: Config, world: World, nid: str, n: Nation) -> None:
    """Order for delivery at the horizon, then (M9) fill any gap still expected within
    `market.fast_horizon` quarters with sources that can be built that quickly, so a sudden
    loss of capacity (a failed equity plant, retirements) does not leave years of blackouts."""
    horizon = horizon_quarters(cfg, nid, n)
    order(cfg, world, nid, n, world.t, world.t + horizon)
    fast = int(cfg.tune("market.fast_horizon"))
    if fast < horizon:
        order(cfg, world, nid, n, world.t, world.t + fast, fast=True)


def seed_pipeline(cfg: Config, world: World, nid: str, n: Nation) -> None:
    """At t=0, fill the pipeline with the projects the market would already have under way,
    one delivery per quarter up to the horizon."""
    for at in range(1, horizon_quarters(cfg, nid) + 1):
        order(cfg, world, nid, n, 0, at)


def apply(world: World, cfg: Config, dt: int) -> dict[str, float]:
    """Run construction for every nation; record clean-tech equipment trade; return capacity
    completed per source (all nations)."""
    completed: dict[str, float] = defaultdict(float)
    by_nation: dict[str, dict[str, float]] = {}
    retire_world_factories(cfg, world, dt)
    clean = [s for s in cfg.source_ids if cfg.category(s) != "fossil"]
    for nid in sorted(world.nations):
        n = world.nations[nid]
        retire(cfg, nid, n, dt)
        done = complete(n, world.t)
        by_nation[nid] = done
        alpha = 1 - (1 - cfg.tune("jobs.smoothing")) ** dt
        n.build_rate += alpha * (sum(done.values()) * 4 / dt - n.build_rate)
        if "carbon_removal" in cfg.source_ids:
            n.extra_demand = n.capacity.get("carbon_removal", 0.0) * cfg.src(
                "carbon_removal", "energy_use"
            )
        for s, amount in done.items():
            completed[s] += amount
            if s in clean:
                n.clean_built += amount
        market_build(cfg, world, nid, n)
    costs = {s: tech.unit_cost(cfg, world, s) for s in trade.EQUIPMENT_OF}
    trade.apply_equipment(cfg, world, by_nation, costs, dt)
    return dict(completed)
