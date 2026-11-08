"""Scripted player policies for balance testing.

A bot is a deterministic function `(cfg, world, nation_id) -> list of actions`. Bots use no
randomness. They plan with the slots that will be available once this quarter's slots accrue,
and spend shares of current capital, so every action they send is normally affordable; anything
that is not is rejected and logged by sim.actions like any other action.

Shares and step sizes below are bot behaviour, not world tuning, so they live here.

- noop:       takes no actions.
- all_fossil: no carbon price, subsidises and builds the cheapest fossil fuel.
- all_clean:  rising carbon price with a rebate, subsidises solar and wind, builds the cheapest
              clean source, adds storage when output is curtailed, researches solar, retires
              coal as political capital allows.
- balanced:   moderate carbon price, builds gas and the cheapest clean source, invests in
              efficiency and adaptation.
- deal_maker: balanced, plus a pledge and influence buying. A stand-in until deals exist (M4).
- ai:         the AI plays the player's nation with its own personality (an AI-only world).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sim import tech
from sim.config import Config
from sim.state import Nation, World

Action = dict[str, Any]
Bot = Callable[[Config, World, str], list[Action]]


def noop(cfg: Config, world: World, nid: str) -> list[Action]:
    """Takes no actions."""
    return []


# --- helpers -------------------------------------------------------------------------------------


def slots(cfg: Config, n: Nation, kind: str) -> int:
    return n.slots_banked.get(kind, 0) + int(cfg.tune(f"slots.{kind}_per_quarter"))


def build(cfg: Config, world: World, n: Nation, source: str, share: float) -> Action | None:
    """Build `source` with `share` of current capital."""
    unit = tech.nation_unit_cost(cfg, world, n, source)
    amount = share * n.capital / unit if unit > 0 else 0.0
    if amount <= 0:
        return None
    key = "kind" if cfg.category(source) == "enabler" else "source"
    kind = "build_grid_storage" if key == "kind" else "build_capacity"
    return {"type": kind, key: source, "amount": amount}


def spend(kind: str, n: Nation, share: float) -> Action | None:
    amount = share * n.capital
    return {"type": kind, "amount": amount} if amount > 0 else None


def cheapest_fossil(cfg: Config, world: World, n: Nation) -> str:
    options = [f for f in ("coal", "gas") if n.capacity.get(f, 0.0) > 0] or ["gas"]
    return min(options, key=lambda f: (tech.lcoe(cfg, world, n, f), f))


def cheapest_clean(cfg: Config, world: World, n: Nation) -> str:
    """Cheapest clean source by levelized cost; wind and solar include their rising system cost,
    and are skipped once output is already being curtailed."""
    options = ["other_renewables"]
    if n.curtailment <= 0:
        options += ["solar", "wind"]
    if n.capacity.get("nuclear", 0.0) > 0:
        options.append("nuclear")
    return min(options, key=lambda s: (tech.lcoe(cfg, world, n, s), s))


def raise_carbon(n: Nation, step: float, cap: float) -> Action | None:
    if n.carbon_price >= cap:
        return None
    return {"type": "set_carbon_price", "level": min(cap, n.carbon_price + step)}


def pick(candidates: list[Action | None], limit: int) -> list[Action]:
    """The first `limit` real actions, in priority order."""
    return [a for a in candidates if a is not None][:limit]


# --- bots ----------------------------------------------------------------------------------------


def all_fossil(cfg: Config, world: World, nid: str) -> list[Action]:
    n = world.nations[nid]
    fuel = cheapest_fossil(cfg, world, n)
    wanted: list[Action | None] = []
    if world.t == 0:
        if n.carbon_price > 0:
            wanted.append({"type": "set_carbon_price", "level": 0.0})
        wanted.append({"type": "set_subsidy", "source": fuel, "share": 0.3})
    wanted.append(build(cfg, world, n, fuel, 0.4))
    return pick(wanted, slots(cfg, n, "domestic"))


def all_clean(cfg: Config, world: World, nid: str) -> list[Action]:
    n = world.nations[nid]
    q = world.t % 4
    wanted: list[Action | None] = []
    if world.t == 0:
        wanted += [
            {"type": "set_subsidy", "source": "solar", "share": 0.3},
            {"type": "rebate", "share": 0.5},
        ]
    elif world.t == 1:
        wanted.append({"type": "set_subsidy", "source": "wind", "share": 0.3})
    wanted.append(build(cfg, world, n, cheapest_clean(cfg, world, n), 0.5))
    if q == 0 and n.curtailment > 0:
        wanted.append(build(cfg, world, n, "storage", 0.2))
    if q == 1:
        research = spend("invest_research", n, 0.05)
        wanted.append(research | {"tech": "solar"} if research else None)
    if q == 2:
        wanted.append(raise_carbon(n, 15.0, 150.0))
    if q == 3:
        per_ej = cfg.tune("actions.retire_pc_per_ej") * cfg.tune("actions.retire_coal_multiplier")
        affordable = 0.5 * n.political_capital / per_ej
        coal = min(n.capacity.get("coal", 0.0), 0.04 * n.base.get("use_coal", 0.0), affordable)
        if coal > 0:
            wanted.append({"type": "retire_capacity", "source": "coal", "amount": coal})
    return pick(wanted, slots(cfg, n, "domestic"))


def _balanced_domestic(cfg: Config, world: World, n: Nation) -> list[Action | None]:
    q = world.t % 4
    clean = cheapest_clean(cfg, world, n)
    wanted: list[Action | None] = [build(cfg, world, n, "gas" if world.t % 2 else clean, 0.4)]
    if q == 0 and n.curtailment > 0:
        wanted.append(build(cfg, world, n, "storage", 0.2))
    if q == 1:
        wanted.append(spend("invest_efficiency", n, 0.1))
    if q == 2:
        wanted.append(raise_carbon(n, 5.0, 50.0))
    if q == 3 and n.climate_damage > 0:
        wanted.append(spend("adaptation_spend", n, 0.05))
    return wanted


def balanced(cfg: Config, world: World, nid: str) -> list[Action]:
    n = world.nations[nid]
    return pick(_balanced_domestic(cfg, world, n), slots(cfg, n, "domestic"))


def deal_maker(cfg: Config, world: World, nid: str) -> list[Action]:
    n = world.nations[nid]
    domestic = _balanced_domestic(cfg, world, n)
    if world.t % 4 == 0:
        domestic.insert(1, spend("buy_influence", n, 0.05))
    out = pick(domestic, slots(cfg, n, "domestic"))
    if world.t == 0 and slots(cfg, n, "diplomatic") > 0:
        out.append({"type": "make_pledge", "target": 0.5, "year": 2050})
    return out


def ai_player(cfg: Config, world: World, nid: str) -> list[Action]:
    """The AI plays the player's nation. sim.runner hands this nation to the turn's AI stage
    instead of calling this, so the AI sees the quarter's slots and income."""
    from sim import ai

    return ai.decide(cfg, world, nid)


BOTS: dict[str, Bot] = {
    "noop": noop,
    "ai": ai_player,
    "all_fossil": all_fossil,
    "all_clean": all_clean,
    "balanced": balanced,
    "deal_maker": deal_maker,
}


def get(name: str) -> Bot:
    if name not in BOTS:
        raise KeyError(f"unknown bot '{name}'; available: {sorted(BOTS)}")
    return BOTS[name]
