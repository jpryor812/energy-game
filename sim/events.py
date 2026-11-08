"""Events hook. A no-op in v0; v1 plugs the event system in here.

Events will draw from `sim.rng.stream(world.seed, "events", world.t, ...)`.
"""

from __future__ import annotations

from sim.config import Config
from sim.state import World


def on_turn(world: World, cfg: Config) -> None:
    """Called once per turn, after the scoring snapshot. Does nothing in v0."""
    return None
