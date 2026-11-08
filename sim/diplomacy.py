"""Trust, tariffs, the carbon club, and the global stocktake.

Trust is directional: `world.trust[a][b]` is how much `a` trusts `b`, in 0..1. Every pair starts
at `diplomacy.trust_start` (a clean slate, no real-world restrictions) and drifts back toward it.

The carbon club is the one bloc. Members need an effective carbon price of at least
`diplomacy.club_min_carbon_price`; they never tariff each other, get cheaper deal finance with
each other, and jointly apply coalition tariffs to non-members that overshoot at a stocktake.

Stocktake (every five years): the remaining carbon budget for `stocktake.target_warming` is
split across nations by their share of current global emissions and spread evenly over the
years to `budget_horizon_year`. Each nation's emissions over the past period are compared with
its allowance. Overshooters first surrender carbon credits; any remaining overshoot (as a share
of their 2025 emissions over the period) costs trust with everyone and brings coalition tariffs.
Nations under their allowance earn the surplus as sellable credits and gain trust. Pledges are
checked against a straight line from 2025 emissions to the pledged level.
"""

from __future__ import annotations

from typing import Any

from sim import climate, trade
from sim.config import Config
from sim.state import World


def _d(cfg: Config, name: str) -> Any:
    return cfg.tune(f"diplomacy.{name}")


def _s(cfg: Config, name: str) -> Any:
    return cfg.tune(f"stocktake.{name}")


# --- trust ---------------------------------------------------------------------------------------


def init_trust(world: World, cfg: Config) -> None:
    start = _d(cfg, "trust_start")
    ids = sorted(world.nations)
    world.trust = {a: {b: start for b in ids if b != a} for a in ids}


def trust(world: World, a: str, b: str) -> float:
    """How much `a` trusts `b`."""
    return world.trust[a][b]


def adjust(world: World, a: str, b: str, delta: float) -> None:
    if a != b:
        world.trust[a][b] = min(1.0, max(0.0, world.trust[a][b] + delta))


def adjust_all(world: World, b: str, delta: float) -> None:
    """Every other nation's trust in `b` changes by `delta`."""
    for a in sorted(world.nations):
        adjust(world, a, b, delta)


def revert_trust(world: World, cfg: Config, dt: int) -> None:
    start = _d(cfg, "trust_start")
    pull = 1 - (1 - _d(cfg, "trust_reversion")) ** (dt / 4)
    for a in sorted(world.trust):
        for b in sorted(world.trust[a]):
            world.trust[a][b] += pull * (start - world.trust[a][b])


# --- carbon club ---------------------------------------------------------------------------------


def club_eligible(cfg: Config, world: World, nid: str) -> bool:
    return world.nations[nid].carbon_price >= _d(cfg, "club_min_carbon_price")


def init_club(world: World, cfg: Config, founders: list[str]) -> None:
    world.blocs[trade.CLUB] = sorted(
        f for f in founders if f in world.nations and club_eligible(cfg, world, f)
    )


def join_club(world: World, nid: str) -> None:
    members = set(world.blocs.get(trade.CLUB, []))
    members.add(nid)
    world.blocs[trade.CLUB] = sorted(members)
    for other in members - {nid}:
        world.nations[other].tariffs.pop(nid, None)
        world.nations[nid].tariffs.pop(other, None)


def leave_club(world: World, nid: str) -> None:
    world.blocs[trade.CLUB] = sorted(set(world.blocs.get(trade.CLUB, [])) - {nid})


# --- stocktake -----------------------------------------------------------------------------------


def remaining_budget(cfg: Config, world: World) -> float:
    """MtCO2 left before `target_warming`, under the model's own warming rule."""
    per_mt = climate.warming_from(cfg, 1.0) - climate.warming_from(cfg, 0.0)
    total = (_s(cfg, "target_warming") - cfg.tune("climate.warming_start")) / per_mt
    return total - world.global_cumulative_emissions


def set_allowances(cfg: Config, world: World) -> None:
    """Each nation's allowance (MtCO2) for the next five-year period."""
    year = cfg.tune("time.start_year") + world.t / 4
    years_left = max(1.0, _s(cfg, "budget_horizon_year") - year)
    interval_years = cfg.tune("time.stocktake_interval") / 4
    budget = max(0.0, remaining_budget(cfg, world))
    global_rate = max(world.global_emissions, 1e-9)
    if world.t == 0:
        global_rate = max(
            sum(n.emissions for n in world.nations.values())
            + sum(climate.exogenous_co2(cfg, 0).values()),
            1e-9,
        )
    for nid in sorted(world.nations):
        n = world.nations[nid]
        share = n.emissions / global_rate
        n.fair_share_budget = budget * share * min(1.0, interval_years / years_left)
        n.period_emissions = 0.0


def pledge_on_track(cfg: Config, world: World, nid: str) -> bool | None:
    n = world.nations[nid]
    if n.pledge is None:
        return None
    start_year = cfg.tune("time.start_year")
    year = start_year + world.t / 4
    frac = min(1.0, (year - start_year) / max(1e-9, n.pledge.year - start_year))
    base = n.base["emissions"]
    path = base + (n.pledge.target_emissions - base) * frac
    return n.emissions <= path * (1 + _s(cfg, "tolerance"))


def run_stocktake(cfg: Config, world: World) -> dict[str, Any]:
    """Judge the past period, apply consequences, set the next allowances; return a log."""
    interval_years = cfg.tune("time.stocktake_interval") / 4
    tolerance = _s(cfg, "tolerance")
    members = set(trade.club_members(world))
    log: dict[str, Any] = {"nations": {}}

    for nid in sorted(world.nations):
        n = world.nations[nid]
        over = n.period_emissions - n.fair_share_budget
        surrendered = 0.0
        if over > 0 and n.credit_balance > 0:
            surrendered = min(over, n.credit_balance)
            n.credit_balance -= surrendered
            over -= surrendered
        share = over / max(n.base["emissions"] * interval_years, 1e-9)
        entry: dict[str, Any] = {
            "emissions": n.period_emissions,
            "allowance": n.fair_share_budget,
            "credits_surrendered": surrendered,
            "overshoot_share": share,
        }
        if share > tolerance:
            adjust_all(world, nid, -_s(cfg, "overshoot_trust_hit") * share)
            if nid not in members:
                level = min(
                    _s(cfg, "coalition_tariff_max"),
                    _s(cfg, "coalition_tariff_per_overshoot") * share,
                )
                world.coalition_tariffs[nid] = level
                entry["coalition_tariff"] = level
            else:
                world.coalition_tariffs.pop(nid, None)
        else:
            world.coalition_tariffs.pop(nid, None)
            if over < 0:
                n.credit_balance += -over
                entry["credits_issued"] = -over
                adjust_all(world, nid, _s(cfg, "undershoot_trust_gain"))
        on_track = pledge_on_track(cfg, world, nid)
        if on_track is not None:
            delta = _s(cfg, "pledge_trust") * (1 if on_track else -1)
            adjust_all(world, nid, delta)
            entry["pledge_on_track"] = on_track
        log["nations"][nid] = entry

    for nid in sorted(members):
        if not club_eligible(cfg, world, nid):
            leave_club(world, nid)
            log.setdefault("left_club", []).append(nid)
    log["remaining_budget"] = remaining_budget(cfg, world)
    set_allowances(cfg, world)
    return log
