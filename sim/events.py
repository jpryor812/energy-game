"""Events hook. M5 plugs in seeded shocks (sim.shocks): climate disasters and factory
disruptions. The richer event system, with choices and chains, comes later.
"""

from __future__ import annotations

from typing import Any

from sim import shocks
from sim.config import Config
from sim.state import World


def on_turn(world: World, cfg: Config, dt: int = 1) -> list[dict[str, Any]]:
    """Called once per turn, after the scoring snapshot. Returns what happened."""
    return shocks.apply(world, cfg, dt)
