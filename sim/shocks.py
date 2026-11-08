"""Seeded shocks (M5): climate disasters and clean-tech factory disruptions.

These are early forms of the event system; the richer events with choices and chains come later.
All randomness comes from the "shocks" and "supply" streams (sim.rng), keyed by turn and nation,
so a seed replays exactly. World difficulty scales how often both happen.

Climate disasters: each quarter a nation is hit with probability `disaster_rate` x (warming above
`disaster_threshold`) x vulnerability x the difficulty multiplier. Severity is 0.5-1.5, scaled up by
`disaster_warming_growth` per degC of warming since 2025. A
disaster costs a one-off share of GDP (cut by adaptation), destroys part of one energy source's
capacity, and costs approval.

Factory disruptions: each quarter each of a nation's clean-tech factory lines is disrupted with
probability `disruption_rate` x the difficulty multiplier, losing `disruption_severity` of its
output for 4-8 quarters, times the difficulty's `disruption_length`. Buyers shift to other
suppliers and pay more meanwhile (sim.trade).

Baseline growth already reflects the average disaster loss at 2025 warming, so the growth term
counts only losses above it (sim.economy.baseline_disaster_loss).
"""

from __future__ import annotations

from typing import Any

from sim import climate, rng, trade
from sim.config import Config
from sim.state import World


def _s(cfg: Config, name: str) -> Any:
    return cfg.tune(f"shocks.{name}")


def disaster_chance(cfg: Config, world: World, nid: str, dt: int = 1) -> float:
    above = max(0.0, world.warming - _s(cfg, "disaster_threshold"))
    vuln = cfg.nat(nid, "climate.vulnerability")
    mult = cfg.level(world.difficulty, "disasters")
    return min(1.0, _s(cfg, "disaster_rate") * above * vuln * mult * dt)


def disaster_scale(cfg: Config, world: World) -> float:
    """Disasters grow more severe as the world warms past 2025."""
    rise = max(0.0, world.warming - cfg.tune("climate.warming_start"))
    return 1 + _s(cfg, "disaster_warming_growth") * rise


def apply(world: World, cfg: Config, dt: int) -> list[dict[str, Any]]:
    """Roll this quarter's shocks; return a log of what happened."""
    log: list[dict[str, Any]] = []
    for nid in sorted(world.nations):
        n = world.nations[nid]
        draw = rng.stream(world.seed, "shocks", world.t, nid)
        if draw.random() < disaster_chance(cfg, world, nid, dt):
            severity = (0.5 + draw.random()) * disaster_scale(cfg, world)
            loss = _s(cfg, "disaster_gdp_loss") * severity * climate.adaptation_factor(cfg, n)
            n.disaster_loss += loss
            sources = sorted(s for s in cfg.energy_source_ids if n.capacity.get(s, 0.0) > 0)
            hit = sources[int(draw.random() * len(sources))] if sources else None
            if hit:
                n.capacity[hit] *= 1 - _s(cfg, "disaster_capacity_loss") * severity
            n.approval = max(0.0, n.approval - _s(cfg, "disaster_approval_hit") * severity)
            log.append(
                {
                    "type": "disaster",
                    "nation": nid,
                    "severity": severity,
                    "gdp_loss": loss,
                    "source": hit,
                }
            )

        for tech in trade.EQUIPMENT:
            if n.disruption_until.get(tech, -1) < world.t:
                n.disruption.pop(tech, None)
                n.disruption_until.pop(tech, None)
            if n.factory_capacity.get(tech, 0.0) <= 0 or tech in n.disruption:
                continue
            roll = rng.stream(world.seed, "supply", world.t, nid, tech)
            chance = _s(cfg, "disruption_rate") * cfg.level(world.difficulty, "disruptions") * dt
            if roll.random() < chance:
                base = _s(cfg, "disruption_min_quarters") + int(
                    roll.random() * (_s(cfg, "disruption_extra_quarters") + 1)
                )
                length = round(base * cfg.level(world.difficulty, "disruption_length"))
                n.disruption[tech] = _s(cfg, "disruption_severity")
                n.disruption_until[tech] = float(world.t + length)
                log.append({"type": "disruption", "nation": nid, "tech": tech, "quarters": length})
    return log
