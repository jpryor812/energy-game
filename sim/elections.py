"""Elections for the player's nation, every four years.

The vote is purely economic (decided with the user, 2026-11-08):

    vote = incumbency
         + growth_weight x (annual GDP growth over the term - baseline growth), in pp
         + jobs_weight x weighted energy-job change / workforce (sim.jobs): M9, the term's
           average jobs against the previous term's average, so one quarter's completions
           cannot swing the vote
         - price_weight x energy-price rise over the term, averaged over its quarters (M9,
           like taxes: a price cut just before the vote counts only for its own quarters)
         - tax_weight x tax raised over the term, averaged over its quarters (M8: so a rise
           reversed just before the vote still counts for the quarters it was in force)
         + a seeded swing (normal, `swing_sd`, from the "elections" RNG stream)

Win at `threshold` or more. Losing ends the game: the player is voted out (decided with the user,
2026-11-08, replacing M4b's one opposition term). AI-led nations have no elections. Approval
does not enter the vote.
"""

from __future__ import annotations

from typing import Any

from sim import economy, jobs, rng
from sim.config import Config
from sim.state import World


def _e(cfg: Config, name: str) -> Any:
    return cfg.tune(f"elections.{name}")


def due(cfg: Config, t: int) -> bool:
    first, interval = _e(cfg, "first_turn"), _e(cfg, "interval")
    return t >= first and (t - first) % interval == 0


def in_power(world: World) -> bool:
    """Whether the player still governs (has not lost an election)."""
    return world.voted_out_at < 0


def term_jobs(world: World) -> dict[str, float]:
    """Average jobs over the term so far, by category (this quarter's if none recorded)."""
    start = world.term_start
    q = start.get("tax_quarters", 0.0)
    p = world.nations[world.player]
    if q <= 0:
        return dict(p.jobs)
    return {k: start.get(f"jobsum_{k}", v * q) / q for k, v in p.jobs.items()}


def start_term(world: World) -> None:
    p = world.nations[world.player]
    # M9: the new term's jobs baseline is the old term's average, not one quarter's count
    baseline = term_jobs(world) if world.term_start else dict(p.jobs)
    world.term_start = {
        "t": float(world.t + 1 if world.history else world.t),
        "gdp": p.gdp,
        "price": p.energy_price,
        "tax": p.tax_change,
        "tax_sum": 0.0,
        "tax_quarters": 0.0,
        "price_sum": 0.0,
    } | {f"jobs_{k}": v for k, v in baseline.items()}


def term_tax_rise(world: World) -> float:
    """Tax raised above the term's starting rate, averaged over the quarters of the term so far
    (this quarter's rate if none has been recorded yet)."""
    start = world.term_start
    if start.get("tax_quarters", 0.0) > 0:
        return start["tax_sum"] / start["tax_quarters"]
    return world.nations[world.player].tax_change - start["tax"]


def term_price_rise(world: World) -> float:
    """Energy-price rise over the term's starting price, averaged over the quarters of the term
    so far (this quarter's price if none has been recorded yet)."""
    start = world.term_start
    if start.get("tax_quarters", 0.0) > 0 and "price_sum" in start:
        return start["price_sum"] / start["tax_quarters"]
    return world.nations[world.player].energy_price / start["price"] - 1


def track(world: World) -> None:
    """Record this quarter's tax rate and energy price for the term averages."""
    start = world.term_start
    if "tax_sum" not in start:  # a save from before M8
        start["tax_sum"], start["tax_quarters"] = 0.0, 0.0
    start.setdefault("price_sum", 0.0)  # before M9
    p = world.nations[world.player]
    start["tax_sum"] += p.tax_change - start["tax"]
    start["price_sum"] += p.energy_price / start["price"] - 1
    for k, v in p.jobs.items():
        start[f"jobsum_{k}"] = start.get(f"jobsum_{k}", 0.0) + v
    start["tax_quarters"] += 1.0


def vote(cfg: Config, world: World) -> dict[str, float]:
    nid = world.player
    p = world.nations[nid]
    start = world.term_start
    t0 = int(start["t"])
    years = max(0.25, (world.t + 1 - t0) / 4)
    growth = (p.gdp / start["gdp"]) ** (1 / years) - 1
    baseline = sum(economy.baseline_growth(cfg, nid, t) for t in range(t0, world.t + 1))
    baseline /= max(1, world.t + 1 - t0)
    before = {k[5:]: v for k, v in start.items() if k.startswith("jobs_")}
    parts = {
        "incumbency": _e(cfg, "incumbency"),
        "growth": _e(cfg, "growth_weight") * (growth - baseline) * 100,
        "jobs": _e(cfg, "jobs_weight") * jobs.weighted_change(cfg, p, before, term_jobs(world)),
        "prices": -_e(cfg, "price_weight") * term_price_rise(world),
        "taxes": -_e(cfg, "tax_weight") * term_tax_rise(world),
        "swing": rng.stream(world.seed, "elections", world.t, nid).gauss(0, _e(cfg, "swing_sd")),
    }
    return parts


def run(cfg: Config, world: World) -> dict[str, Any] | None:
    """Record the quarter's tax for the term average; hold the election if one is due and the
    player is still in office; return a log."""
    if world.player is None or not in_power(world):
        return None
    track(world)
    if not due(cfg, world.t):
        return None
    parts = vote(cfg, world)
    share = sum(parts.values())
    won = share >= _e(cfg, "threshold")
    log: dict[str, Any] = {
        "t": world.t,
        "event": "won" if won else "lost",
        "vote": share,
        "parts": parts,
    }
    world.elections.append(log)
    if won:
        start_term(world)
    else:
        world.voted_out_at = world.t
    return log
