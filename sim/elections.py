"""Elections for the player's nation, every four years.

The vote is purely economic (decided with the user, 2026-11-08):

    vote = incumbency
         + growth_weight x (annual GDP growth over the term - baseline growth), in pp
         + jobs_weight x weighted energy-job change over the term / workforce (sim.jobs)
         - price_weight x energy-price rise over the term
         - tax_weight x tax raised over the term
         + a seeded swing (normal, `swing_sd`, from the "elections" RNG stream)

Win at `threshold` or more. Losing hands the nation to the AI (its default personality) for one
term; at the next election date the player returns without a vote. AI-led nations have no
elections. Approval does not enter the vote.
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
    """Whether the player governs this quarter."""
    return world.t > world.opposition_until


def start_term(world: World) -> None:
    p = world.nations[world.player]
    world.term_start = {
        "t": float(world.t + 1 if world.history else world.t),
        "gdp": p.gdp,
        "price": p.energy_price,
        "tax": p.tax_change,
    } | {f"jobs_{k}": v for k, v in p.jobs.items()}


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
        "jobs": _e(cfg, "jobs_weight") * jobs.weighted_change(cfg, p, before, p.jobs),
        "prices": -_e(cfg, "price_weight") * (p.energy_price / start["price"] - 1),
        "taxes": -_e(cfg, "tax_weight") * (p.tax_change - start["tax"]),
        "swing": rng.stream(world.seed, "elections", world.t, nid).gauss(0, _e(cfg, "swing_sd")),
    }
    return parts


def run(cfg: Config, world: World) -> dict[str, Any] | None:
    """Hold the election (or end the opposition's term) if one is due; return a log."""
    if world.player is None or not due(cfg, world.t):
        return None
    if world.t <= world.opposition_until:
        log: dict[str, Any] = {"t": world.t, "event": "player_returns"}
    else:
        parts = vote(cfg, world)
        share = sum(parts.values())
        won = share >= _e(cfg, "threshold")
        log = {"t": world.t, "event": "won" if won else "lost", "vote": share, "parts": parts}
        if not won:
            world.opposition_until = world.t + int(_e(cfg, "interval"))
    world.elections.append(log)
    start_term(world)
    return log
