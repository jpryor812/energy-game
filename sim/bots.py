"""Scripted player policies for balance testing.

A bot is a deterministic function `(world, nation_id) -> list of actions`. M0 has only `noop`;
`all_fossil`, `all_clean`, `balanced` and `deal_maker` arrive in M2 with the action set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sim.state import World

Bot = Callable[[World, str], list[dict[str, Any]]]


def noop(world: World, nation_id: str) -> list[dict[str, Any]]:
    """Takes no actions."""
    return []


BOTS: dict[str, Bot] = {"noop": noop}


def get(name: str) -> Bot:
    if name not in BOTS:
        raise KeyError(f"unknown bot '{name}'; available: {sorted(BOTS)}")
    return BOTS[name]
