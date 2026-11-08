"""Player and AI actions: definitions, validation, slot accounting, effects.

An action is a plain dict, e.g. {"type": "build_capacity", "source": "solar", "amount": 1.0}.
Each type declares a slot (domestic or diplomatic), a check that validates parameters and returns
its resource costs, and an effect. `resolve` applies a nation's actions in order: an action that
is malformed or unaffordable is rejected and logged, never raised, so a bad action cannot crash a
run. Every action uses one slot of its type; unused slots are banked with no cap.

Units: amounts of capacity in EJ/yr, money in T$, carbon price in $/tCO2, shares in 0..1.
Tariffs, deals, talks and blocs arrive in M4.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sim import construction, tech
from sim.config import Config
from sim.state import Nation, Pledge, World

DOMESTIC, DIPLOMATIC = "domestic", "diplomatic"
RESOURCES = ("capital", "political_capital", "influence")


class Rejected(Exception):
    """An action failed validation; the message says why."""


Check = Callable[[Config, World, Nation, dict[str, Any]], dict[str, float]]
Apply = Callable[[Config, World, Nation, dict[str, Any]], None]


@dataclass(frozen=True)
class Spec:
    slot: str
    check: Check
    apply: Apply


# --- parameter helpers ---------------------------------------------------------------------------


def _num(act: dict[str, Any], key: str, lo: float, hi: float) -> float:
    v = act.get(key)
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise Rejected(f"'{key}' must be a number")
    if not lo <= v <= hi:
        raise Rejected(f"'{key}' must be between {lo} and {hi}")
    return float(v)


def _positive(act: dict[str, Any], key: str = "amount") -> float:
    v = _num(act, key, 0.0, math.inf)
    if v <= 0:
        raise Rejected(f"'{key}' must be positive")
    return v


def _choice(act: dict[str, Any], key: str, options: list[str]) -> str:
    v = act.get(key)
    if v not in options:
        raise Rejected(f"'{key}' must be one of {options}")
    return v


def _a(cfg: Config, name: str) -> Any:
    return cfg.tune(f"actions.{name}")


# --- domestic actions ----------------------------------------------------------------------------


def _build_check(cfg, world, n, act):
    s = _choice(act, "source", cfg.energy_source_ids)
    amount = _positive(act)
    return {"capital": tech.nation_unit_cost(cfg, world, n, s) * amount}


def _build_apply(cfg, world, n, act):
    construction.queue(cfg, n, act["source"], act["amount"], world.t)


def _grid_check(cfg, world, n, act):
    enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
    s = _choice(act, "kind", enablers)
    amount = _positive(act)
    return {"capital": tech.nation_unit_cost(cfg, world, n, s) * amount}


def _grid_apply(cfg, world, n, act):
    construction.queue(cfg, n, act["kind"], act["amount"], world.t)


def _retire_check(cfg, world, n, act):
    s = _choice(act, "source", cfg.energy_source_ids)
    amount = _positive(act)
    if amount > n.capacity.get(s, 0.0) + 1e-12:
        raise Rejected(f"only {n.capacity.get(s, 0.0):.3f} EJ/yr of {s} to retire")
    pc = _a(cfg, "retire_pc_per_ej") * amount
    if s == "coal":
        pc *= _a(cfg, "retire_coal_multiplier")
    return {"political_capital": pc}


def _retire_apply(cfg, world, n, act):
    s, amount = act["source"], min(act["amount"], n.capacity.get(act["source"], 0.0))
    n.capacity[s] -= amount
    # Book value lost: a share of today's replacement cost (no plant-age data).
    n.pending_writeoff += tech.unit_cost(cfg, world, s) * amount * _a(cfg, "stranded_value_share")
    if cfg.category(s) == "fossil":
        demand = max(n.demand, 1e-9)
        n.approval = max(0.0, n.approval - _a(cfg, "retire_approval_hit") * amount / demand)


def _carbon_check(cfg, world, n, act):
    level = _num(act, "level", 0.0, _a(cfg, "carbon_price_max"))
    return {"political_capital": _a(cfg, "carbon_pc_per_dollar") * max(0.0, level - n.carbon_price)}


def _carbon_apply(cfg, world, n, act):
    n.carbon_price = float(act["level"])


def _rebate_check(cfg, world, n, act):
    _num(act, "share", 0.0, 1.0)
    return {}


def _rebate_apply(cfg, world, n, act):
    n.rebate = float(act["share"])


def _subsidy_check(cfg, world, n, act):
    _choice(act, "source", cfg.energy_source_ids)
    _num(act, "share", 0.0, _a(cfg, "max_subsidy"))
    return {}


def _subsidy_apply(cfg, world, n, act):
    n.subsidies[act["source"]] = float(act["share"])


def _research_check(cfg, world, n, act):
    _choice(act, "tech", cfg.source_ids)
    return {"capital": _positive(act)}


def _research_apply(cfg, world, n, act):
    n.research[act["tech"]] = n.research.get(act["tech"], 0.0) + act["amount"]
    n.tech_points += act["amount"] * cfg.tune("research.points_per_trillion")


def _spend_check(cfg, world, n, act):
    return {"capital": _positive(act)}


def efficiency_factor(cfg: Config, n: Nation, spent: float) -> float:
    """Energy-intensity multiplier from cumulative efficiency spending (diminishing returns)."""
    return 1 - _a(cfg, "efficiency_max_gain") * (
        1 - math.exp(-spent / (n.gdp * _a(cfg, "efficiency_scale")))
    )


def efficiency_gain(cfg: Config, n: Nation, amount: float) -> float:
    """Share of energy intensity cut by spending `amount` more on efficiency."""
    old = efficiency_factor(cfg, n, n.efficiency_spent)
    return 1 - efficiency_factor(cfg, n, n.efficiency_spent + amount) / old


def _efficiency_apply(cfg, world, n, act):
    n.energy_intensity *= 1 - efficiency_gain(cfg, n, act["amount"])
    n.efficiency_spent += act["amount"]


def _influence_apply(cfg, world, n, act):
    n.influence += act["amount"] * _a(cfg, "influence_per_trillion")


def _adaptation_apply(cfg, world, n, act):
    n.adaptation += act["amount"]


def _cap_check(cfg, world, n, act):
    level = _num(act, "level", 0.0, _a(cfg, "activity_cap_max"))
    return {"political_capital": _a(cfg, "activity_pc_cost") * max(0.0, level - n.activity_cap)}


def _cap_apply(cfg, world, n, act):
    """Capping energy-intensive output cuts demand by the cap level and GDP by a smaller share."""
    k = _a(cfg, "activity_gdp_ratio")
    old, new = n.activity_cap, float(act["level"])
    gdp_factor = (1 - k * new) / (1 - k * old)
    demand_factor = (1 - new) / (1 - old)
    n.gdp *= gdp_factor
    n.energy_intensity *= demand_factor / gdp_factor
    n.activity_cap = new


# --- diplomatic actions --------------------------------------------------------------------------


def _pledge_check(cfg, world, n, act):
    _num(act, "target", 0.0, 2.0)
    start = cfg.tune("time.start_year")
    _num(act, "year", start + 1, start + 75)
    return {}


def _pledge_apply(cfg, world, n, act):
    target = act["target"] * n.base.get("emissions", n.emissions)
    n.pledge = Pledge(target_emissions=target, year=int(act["year"]), made_turn=world.t)


SPECS: dict[str, Spec] = {
    "build_capacity": Spec(DOMESTIC, _build_check, _build_apply),
    "retire_capacity": Spec(DOMESTIC, _retire_check, _retire_apply),
    "set_carbon_price": Spec(DOMESTIC, _carbon_check, _carbon_apply),
    "set_subsidy": Spec(DOMESTIC, _subsidy_check, _subsidy_apply),
    "invest_research": Spec(DOMESTIC, _research_check, _research_apply),
    "invest_efficiency": Spec(DOMESTIC, _spend_check, _efficiency_apply),
    "buy_influence": Spec(DOMESTIC, _spend_check, _influence_apply),
    "build_grid_storage": Spec(DOMESTIC, _grid_check, _grid_apply),
    "set_activity_cap": Spec(DOMESTIC, _cap_check, _cap_apply),
    "adaptation_spend": Spec(DOMESTIC, _spend_check, _adaptation_apply),
    "rebate": Spec(DOMESTIC, _rebate_check, _rebate_apply),
    "make_pledge": Spec(DIPLOMATIC, _pledge_check, _pledge_apply),
}


def cost(cfg: Config, world: World, n: Nation, act: dict[str, Any]) -> dict[str, float]:
    """Resource cost of an action, or Rejected if it is malformed."""
    spec = SPECS.get(act.get("type"))
    if spec is None:
        raise Rejected(f"unknown action type {act.get('type')!r}")
    return spec.check(cfg, world, n, act)


def resolve(cfg: Config, world: World, nid: str, acts: list[dict[str, Any]]) -> list[dict]:
    """Validate and apply a nation's actions in order; return one result per action."""
    n = world.nations[nid]
    results = []
    for act in acts:
        try:
            costs = cost(cfg, world, n, act)
            spec = SPECS[act["type"]]
            if n.slots_banked.get(spec.slot, 0) < 1:
                raise Rejected(f"no {spec.slot} slot left")
            for res in RESOURCES:
                if costs.get(res, 0.0) > getattr(n, res) + 1e-12:
                    raise Rejected(f"needs {costs[res]:.4g} {res}, has {getattr(n, res):.4g}")
            for res in RESOURCES:
                setattr(n, res, getattr(n, res) - costs.get(res, 0.0))
            n.slots_banked[spec.slot] -= 1
            spec.apply(cfg, world, n, act)
            results.append({"action": dict(act), "ok": True, "cost": costs})
        except Rejected as exc:
            results.append({"action": dict(act), "ok": False, "reason": str(exc)})
    return results
