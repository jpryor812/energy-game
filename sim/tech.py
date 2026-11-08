"""Learning curves.

Unit cost C(n) = C0 x (n / n0)^(-b), where n is global cumulative deployment of the technology,
n0 its 2025 level (`global_installed`), and b = -log2(1 - learning_rate), so each doubling of
deployment cuts cost by `learning_rate`.

Global deployment grows by what the modelled nations build divided by their share of world
deployment (`coverage_share`), so the rest of the world builds in proportion. Enablers have no
coverage share and count only what the modelled nations build.

Research and tech points arrive with actions in M2.
"""

from __future__ import annotations

import math

from sim.config import Config
from sim.state import World


def exponent(learning_rate: float) -> float:
    return -math.log2(1.0 - learning_rate)


def unit_cost(cfg: Config, world: World, source: str) -> float:
    n0 = cfg.src(source, "global_installed")
    n = world.tech_state.get(source, n0)
    c0 = cfg.src(source, "capital_cost")
    if n0 <= 0 or n <= 0:
        return c0
    return c0 * (n / n0) ** (-exponent(cfg.src(source, "learning_rate")))


def apply(world: World, cfg: Config, completed: dict[str, float]) -> None:
    for s in sorted(completed):
        coverage = 1.0
        if cfg.category(s) != "enabler":
            coverage = cfg.src(s, "coverage_share")
        world.tech_state[s] = world.tech_state.get(s, 0.0) + completed[s] / coverage
