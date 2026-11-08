"""Construction: retirements, completions, and the business-as-usual (BAU) builder.

Capacity retires at a constant annual rate: 1 / lifespan, or faster where the nation's own
2019-2024 data shows a faster decline (`bau.retire_rate`). There is no plant-age data, so this is
an approximation.

The BAU builder stands in for decisions nobody is making yet. It keeps the nation's *normal*
output (capacity / headroom) on track to meet demand plus a reserve margin, after expected
retirements and counting what is already under construction, and splits new capacity by the
nation's recent build mix (`bau.mix`). It also builds grid so wind and solar are not curtailed
once built. Orders are delivered after the slowest build time in the mix, so the whole mix arrives
together; at t=0 the pipeline is seeded with the projects already under way. BAU builds cost no
capital: baseline growth already includes this investment. AI nations replace the builder with
their own choices in M3.
"""

from __future__ import annotations

from collections import defaultdict

from sim import economy
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


def horizon_quarters(cfg: Config, nid: str) -> int:
    """BAU orders are delivered this many quarters after they are placed: the slowest build
    time in the nation's mix. Faster sources simply start later, so the mix arrives together."""
    mix = cfg.nat_spec(nid)["bau"]["mix"]
    return max(int(cfg.src(s, "build_time")) for s in mix)


def future_capacity(cfg: Config, nid: str, n: Nation, source: str, t: int, at: int) -> float:
    """Capacity of `source` expected at turn `at`: survivors plus projects finished by then."""
    years = (at - t) / 4
    kept = n.capacity.get(source, 0.0) * (1 - retire_rate(cfg, nid, source)) ** years
    arriving = sum(c.amount for c in n.pipeline if c.source == source and c.complete_turn <= at)
    return kept + arriving


def order(cfg: Config, nid: str, n: Nation, t: int, at: int) -> None:
    """Place BAU orders so that, at turn `at`, normal output covers projected demand plus the
    reserve margin, split by the nation's build mix; add grid for the wind and solar."""
    growth = economy.baseline_growth(cfg, nid, t)
    decline = cfg.nat(nid, "trend.intensity_decline")
    demand_growth = (1 + growth) * (1 - decline) - 1
    target = base_demand(n) * (1 + demand_growth) ** ((at - t) / 4)
    target *= 1 + cfg.tune("bau.reserve_margin")
    normal = sum(
        future_capacity(cfg, nid, n, s, t, at) / cfg.src(s, "headroom")
        for s in cfg.energy_source_ids
    )
    gap = target - normal
    if gap > 0:
        mix = cfg.nat_spec(nid)["bau"]["mix"]
        for s in sorted(mix):
            amount = gap * mix[s]["value"] * cfg.src(s, "headroom")
            n.pipeline.append(Construction(s, amount, at))

    if "grid" in cfg.source_ids:
        enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
        vre = sum(future_capacity(cfg, nid, n, s, t, at) for s in cfg.vre_ids)
        absorb = cfg.tune("energy.vre_base_absorb_share") * target + sum(
            future_capacity(cfg, nid, n, s, t, at) for s in enablers
        )
        if vre > absorb:
            n.pipeline.append(Construction("grid", vre - absorb, at))


def bau_build(cfg: Config, nid: str, n: Nation, t: int) -> None:
    order(cfg, nid, n, t, t + horizon_quarters(cfg, nid))


def seed_pipeline(cfg: Config, nid: str, n: Nation) -> None:
    """At t=0, fill the pipeline with the projects the BAU builder would already have under way,
    one delivery per quarter up to the horizon."""
    for at in range(1, horizon_quarters(cfg, nid) + 1):
        order(cfg, nid, n, 0, at)


def apply(world: World, cfg: Config, dt: int, bau_nations: set[str]) -> dict[str, float]:
    """Run construction for every nation; return capacity completed per source (all nations)."""
    completed: dict[str, float] = defaultdict(float)
    for nid in sorted(world.nations):
        n = world.nations[nid]
        retire(cfg, nid, n, dt)
        for s, amount in complete(n, world.t).items():
            completed[s] += amount
        if nid in bau_nations:
            bau_build(cfg, nid, n, world.t)
    return dict(completed)
