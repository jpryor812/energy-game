"""Player and AI actions: definitions, validation, slot accounting, effects.

An action is a plain dict, e.g. {"type": "build_capacity", "source": "solar", "amount": 1.0}.
Each type declares a slot (domestic or diplomatic), a check that validates parameters and returns
its resource costs, and an effect. `resolve` applies a nation's actions in order: an action that
is malformed or unaffordable is rejected and logged, never raised, so a bad action cannot crash a
run. Every action uses one slot of its type; unused slots are banked with no cap.

Units: amounts of capacity in EJ/yr, money in T$, carbon price in $/tCO2, shares in 0..1.
Diplomatic actions (M4): talks, tariffs, the carbon club, deals, and carbon credit orders.
Domestic economy (M4b): taxes, tax credits, factories, domestic content, retraining, and
electrification programmes. Climate levers (M4b): carbon removal, methane abatement, and the
global forest fund.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sim import construction, credits, deals, diplomacy, tech, trade
from sim.config import Config
from sim.state import Construction, Nation, Pledge, World

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


def _target(world, n, act) -> str:
    t = act.get("target")
    if t not in world.nations or t == n.id:
        raise Rejected("'target' must be another nation")
    return t


def _talks_check(cfg, world, n, act):
    _target(world, n, act)
    return {"influence": cfg.tune("diplomacy.talks_influence_cost")}


def _talks_apply(cfg, world, n, act):
    diplomacy.adjust(world, act["target"], n.id, cfg.tune("diplomacy.talks_trust_gain"))


def _tariff_check(cfg, world, n, act):
    t = _target(world, n, act)
    _num(act, "level", 0.0, cfg.tune("trade.tariff_max"))
    members = trade.club_members(world)
    if n.id in members and t in members:
        raise Rejected("carbon club members cannot tariff each other")
    return {}


def _tariff_apply(cfg, world, n, act):
    t, level = act["target"], float(act["level"])
    raised = max(0.0, level - n.tariffs.get(t, 0.0))
    if level > 0:
        n.tariffs[t] = level
    else:
        n.tariffs.pop(t, None)
    diplomacy.adjust(world, t, n.id, -cfg.tune("diplomacy.tariff_trust_hit") * raised)


def _lift_check(cfg, world, n, act):
    t = _target(world, n, act)
    if n.tariffs.get(t, 0.0) <= 0:
        raise Rejected(f"no tariff on {t} to lift")
    return {}


def _lift_apply(cfg, world, n, act):
    n.tariffs.pop(act["target"], None)


def _join_check(cfg, world, n, act):
    _choice(act, "bloc", [trade.CLUB])
    if n.id in trade.club_members(world):
        raise Rejected("already a member")
    if not diplomacy.club_eligible(cfg, world, n.id):
        need = cfg.tune("diplomacy.club_min_carbon_price")
        raise Rejected(f"carbon price must be at least {need}")
    return {}


def _join_apply(cfg, world, n, act):
    diplomacy.join_club(world, n.id)


def _leave_check(cfg, world, n, act):
    _choice(act, "bloc", [trade.CLUB])
    if n.id not in trade.club_members(world):
        raise Rejected("not a member")
    return {}


def _leave_apply(cfg, world, n, act):
    diplomacy.leave_club(world, n.id)


DEAL_PRICE_MAX = {"rate": 0.3, "price": 50.0}  # validation bounds, not tuning


def _deal_terms(cfg, act) -> dict:
    kind = _choice(act, "deal_type", list(deals.TYPES))
    clean = [s for s in cfg.energy_source_ids if cfg.category(s) != "fossil"]
    terms = {
        "source": _choice(act, "source", clean),
        "amount": _positive(act),
        "currency": _choice(act, "currency", ["hard", "local"]),
        "duration": int(_num(act, "duration", 4, cfg.tune("deals.max_duration"))),
        "collateral": _num(act, "collateral", 0.0, 1.0),
        "exit_penalty": _num(act, "exit_penalty", 0.0, 1.0),
    }
    key = "rate" if kind == "equipment_on_credit" else "price"
    terms[key] = _num(act, key, 0.0, DEAL_PRICE_MAX[key])
    return terms


def _propose_check(cfg, world, n, act):
    _target(world, n, act)
    terms = _deal_terms(cfg, act)
    cost = tech.nation_unit_cost(cfg, world, n, terms["source"]) * terms["amount"]
    if cost > n.capital + 1e-12:
        raise Rejected(f"needs {cost:.4g} capital to finance, has {n.capital:.4g}")
    return {}


def _propose_apply(cfg, world, n, act):
    deals.propose(world, n.id, act["target"], act["deal_type"], _deal_terms(cfg, act))


def _open_deal(world, n, act):
    deal = world.deals.get(act.get("deal_id"))
    if deal is None or deal.status != deals.OPEN:
        raise Rejected("no open proposal with that id")
    if deals.responder(deal) != n.id:
        raise Rejected("this proposal is not addressed to you")
    if deal.start_turn >= world.t:
        raise Rejected("a proposal can be answered from the next quarter")
    return deal


def _respond_check(cfg, world, n, act):
    deal = _open_deal(world, n, act)
    response = _choice(act, "response", ["accept", "refuse", "counter"])
    if response == "counter":
        key = "rate" if deal.type == "equipment_on_credit" else "price"
        _num(act, key, 0.0, DEAL_PRICE_MAX[key])
    return {}


def _respond_apply(cfg, world, n, act):
    deal = world.deals[act["deal_id"]]
    response = act["response"]
    if response == "refuse":
        deal.status = "refused"
    elif response == "counter":
        key = "rate" if deal.type == "equipment_on_credit" else "price"
        deal.status = "countered"
        terms = {k: v for k, v in deal.terms.items() if k != "proposer"}
        terms[key] = float(act[key])
        terms["proposer"] = n.id
        deals.propose(world, deal.financier, deal.host, deal.type, terms)
    elif deals.build_cost(cfg, world, deal) > world.nations[deal.financier].capital:
        deal.status = "lapsed"  # the financier can no longer pay
    else:
        deals.activate(cfg, world, deal)


def _exit_check(cfg, world, n, act):
    deal = world.deals.get(act.get("deal_id"))
    if deal is None or deal.status != deals.ACTIVE or deal.host != n.id:
        raise Rejected("no active deal of yours with that id")
    if deal.type != "energy_as_a_service":
        raise Rejected("only energy-as-a-service deals have an exit clause")
    return {}


def _exit_apply(cfg, world, n, act):
    deals.exit_deal(cfg, world, world.deals[act["deal_id"]])


def _orders(world, nid, side):
    return [o for o in world.credit_orders if o["nation"] == nid and o["side"] == side]


def _buy_check(cfg, world, n, act):
    amount = _positive(act)
    limit = _num(act, "max_price", cfg.tune("credits.min_price"), 1e4)
    if _orders(world, n.id, "sell"):
        raise Rejected("cannot buy and sell credits in the same quarter")
    committed = sum(credits.cost(o["amount"], o["limit"]) for o in _orders(world, n.id, "buy"))
    if credits.cost(amount, limit) + committed > n.capital + 1e-12:
        raise Rejected("not enough capital for this order at its price limit")
    return {}


def _buy_apply(cfg, world, n, act):
    world.credit_orders.append(
        {
            "nation": n.id,
            "side": "buy",
            "amount": float(act["amount"]),
            "limit": float(act["max_price"]),
        }
    )


def _sell_check(cfg, world, n, act):
    amount = _positive(act)
    _num(act, "min_price", 0.0, 1e4)
    if _orders(world, n.id, "buy"):
        raise Rejected("cannot buy and sell credits in the same quarter")
    offered = sum(o["amount"] for o in _orders(world, n.id, "sell"))
    if amount + offered > n.credit_balance + 1e-12:
        raise Rejected(f"only {n.credit_balance:.4g} Mt of credits to sell")
    return {}


def _sell_apply(cfg, world, n, act):
    world.credit_orders.append(
        {
            "nation": n.id,
            "side": "sell",
            "amount": float(act["amount"]),
            "limit": float(act["min_price"]),
        }
    )


# --- domestic economy (M4b) ----------------------------------------------------------------------


def _tax_check(cfg, world, n, act):
    level = _num(act, "level", cfg.tune("tax.min_change"), cfg.tune("tax.max_change"))
    raised = max(0.0, level - n.tax_change)
    return {"political_capital": cfg.tune("tax.pc_per_point") * raised * 100}


def _tax_apply(cfg, world, n, act):
    raised = max(0.0, act["level"] - n.tax_change)
    n.approval = max(0.0, n.approval - cfg.tune("tax.approval_hit") * raised)
    n.tax_change = float(act["level"])


def _credit_check(cfg, world, n, act):
    kind = _choice(act, "kind", ["generation", "manufacturing"])
    if kind == "generation":
        _choice(act, "tech", cfg.energy_source_ids)
        _num(act, "rate", 0.0, cfg.tune("tax.generation_credit_max"))
    else:
        _choice(act, "tech", list(trade.EQUIPMENT))
        _num(act, "rate", 0.0, cfg.tune("tax.manufacturing_credit_max"))
    return {}


def _credit_apply(cfg, world, n, act):
    key = f"{act['kind']}:{act['tech']}"
    if act["rate"] > 0:
        n.tax_credits[key] = float(act["rate"])
    else:
        n.tax_credits.pop(key, None)


def _factory_check(cfg, world, n, act):
    _choice(act, "tech", list(trade.EQUIPMENT))
    return {"capital": cfg.tune("industry.factory_capital_cost") * _positive(act)}


def _factory_apply(cfg, world, n, act):
    done = world.t + int(cfg.tune("industry.factory_build_time"))
    n.pipeline.append(Construction(construction.FACTORY + act["tech"], float(act["amount"]), done))


def _content_check(cfg, world, n, act):
    _choice(act, "tech", list(trade.EQUIPMENT))
    _num(act, "share", 0.0, 1.0)
    return {}


def _content_apply(cfg, world, n, act):
    if act["share"] > 0:
        n.domestic_content[act["tech"]] = float(act["share"])
    else:
        n.domestic_content.pop(act["tech"], None)


def _retraining_apply(cfg, world, n, act):
    n.retraining += act["amount"]


def _electrification_apply(cfg, world, n, act):
    n.electrification += act["amount"]


# --- climate levers (M4b) ------------------------------------------------------------------------


def _removal_check(cfg, world, n, act):
    if "carbon_removal" not in cfg.source_ids:
        raise Rejected("carbon removal is not in this game")
    return {"capital": tech.nation_unit_cost(cfg, world, n, "carbon_removal") * _positive(act)}


def _removal_apply(cfg, world, n, act):
    construction.queue(cfg, n, "carbon_removal", act["amount"], world.t)


def _methane_apply(cfg, world, n, act):
    n.methane_abatement += act["amount"]


def _forest_apply(cfg, world, n, act):
    world.forest_fund += act["amount"]
    n.forest_paid += act["amount"]


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
    "set_tax_rate": Spec(DOMESTIC, _tax_check, _tax_apply),
    "set_tax_credit": Spec(DOMESTIC, _credit_check, _credit_apply),
    "build_factory": Spec(DOMESTIC, _factory_check, _factory_apply),
    "set_domestic_content": Spec(DOMESTIC, _content_check, _content_apply),
    "fund_retraining": Spec(DOMESTIC, _spend_check, _retraining_apply),
    "electrification_program": Spec(DOMESTIC, _spend_check, _electrification_apply),
    "build_removal": Spec(DOMESTIC, _removal_check, _removal_apply),
    "methane_abatement": Spec(DOMESTIC, _spend_check, _methane_apply),
    "fund_forests": Spec(DIPLOMATIC, _spend_check, _forest_apply),
    "make_pledge": Spec(DIPLOMATIC, _pledge_check, _pledge_apply),
    "open_talks": Spec(DIPLOMATIC, _talks_check, _talks_apply),
    "set_tariff": Spec(DIPLOMATIC, _tariff_check, _tariff_apply),
    "lift_tariff": Spec(DIPLOMATIC, _lift_check, _lift_apply),
    "join_bloc": Spec(DIPLOMATIC, _join_check, _join_apply),
    "leave_bloc": Spec(DIPLOMATIC, _leave_check, _leave_apply),
    "propose_deal": Spec(DIPLOMATIC, _propose_check, _propose_apply),
    "respond_deal": Spec(DIPLOMATIC, _respond_check, _respond_apply),
    "exit_deal": Spec(DIPLOMATIC, _exit_check, _exit_apply),
    "buy_credits": Spec(DIPLOMATIC, _buy_check, _buy_apply),
    "sell_credits": Spec(DIPLOMATIC, _sell_check, _sell_apply),
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
