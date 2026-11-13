"""Negotiation previews for the trade table (W4, decided with the user 2026-11-12).

Read-only: nothing here changes the world. Given a deal the player is drafting, it says how the
other side's AI would answer (with the same valuation the AI uses when it answers next quarter),
what terms it would take, what the deal pays and risks, and how much each side's Impact would
move by the end of the game.

The verdict is a forecast on this quarter's state: the AI answers next quarter, when prices,
trust and its budget may have moved a little.
"""

from __future__ import annotations

import math
from typing import Any

from sim import actions, ai, construction, deals, scoring, tech, trade
from sim.config import Config
from sim.state import Deal, World

ACCEPT, COUNTER, REFUSE = "accept", "counter", "refuse"
SEARCH_STEPS = 30  # bisection steps for "what would it take" (a precision setting, not tuning)


def draft(cfg: Config, world: World, financier: str, act: dict[str, Any]) -> Deal:
    """An unsaved Deal from a propose_deal action (validated by the caller)."""
    terms = actions._deal_terms(cfg, act) | {"proposer": financier}
    return Deal(
        id="draft",
        type=act["deal_type"],
        financier=financier,
        host=act["target"],
        terms=terms,
        status=deals.OPEN,
        start_turn=world.t,
    )


def _with(deal: Deal, **terms: Any) -> Deal:
    return Deal(deal.id, deal.type, deal.financier, deal.host, deal.terms | terms, deal.status,
                deal.start_turn)  # fmt: skip


def host_margin(cfg: Config, world: World, deal: Deal) -> float:
    """The host AI's margin for accepting (above 0 accepts). -inf for a nation without an AI."""
    personality = cfg.nat_spec(deal.host).get("personality")
    if personality is None:
        return -math.inf
    ctx = ai.context(cfg, world, deal.host)
    w_em = ai.emissions_weight(cfg, world, deal.host, personality)
    income = ai.income_per_year(cfg, ctx.n)
    return ai._value_deal_as_host(cfg, world, deal.host, deal, personality, ctx, w_em, income)


def answer(cfg: Config, margin: float) -> str:
    if margin > 0:
        return ACCEPT
    if margin > -cfg.tune("ai.counter_margin"):
        return COUNTER
    return REFUSE


def what_it_takes(cfg: Config, world: World, deal: Deal) -> dict[str, float] | None:
    """The best terms for the financier that the host would accept: the highest rate, price or
    equity share with a positive margin (halving the size if even the lowest is refused), or
    None if nothing close works. Lower terms are always better for the host."""
    key = actions._price_key(deal)
    amount = deal.terms["amount"]
    for _ in range(4):
        trial = _with(deal, amount=amount)
        if host_margin(cfg, world, _with(trial, **{key: 0.0})) > 0:
            lo, hi = 0.0, max(deal.terms[key], 1e-9)
            if host_margin(cfg, world, trial) > 0:
                return {key: deal.terms[key], "amount": amount}
            for _ in range(SEARCH_STEPS):
                mid = (lo + hi) / 2
                if host_margin(cfg, world, _with(trial, **{key: mid})) > 0:
                    lo = mid
                else:
                    hi = mid
            return {key: lo, "amount": amount}
        amount /= 2
    return None


def financier_accepts_counter(cfg: Config, world: World, deal: Deal, value: float) -> bool:
    """How an AI financier answers the player's counter-offer on its own offer (the rule in
    ai.diplomatic): it keeps at least `ai.counter_accept_share` of what it first asked, and can
    still pay for the plant."""
    key = actions._price_key(deal)
    floor = cfg.tune("ai.counter_accept_share") * deal.terms.get("asked", deal.terms[key])
    fin = world.nations[deal.financier]
    return value >= floor - 1e-12 and deals.build_cost(cfg, world, deal) <= fin.capital


def _online(cfg: Config, world: World, deal: Deal) -> int:
    return world.t + construction.build_time(cfg, world.nations[deal.host], deal.terms["source"])


def capacity(cfg: Config, world: World, deal: Deal) -> float:
    """EJ/yr the deal builds in the host."""
    if deal.type == "climate_loan":
        host = world.nations[deal.host]
        return deal.terms["amount"] / tech.nation_unit_cost(cfg, world, host, deal.terms["source"])
    return deal.terms["amount"]


def projected_impact(cfg: Config, world: World, deal: Deal) -> dict[str, float]:
    """Change in each side's Impact (0-100) at the end of the game if the deal is signed and its
    plant runs: the host's real cut while the plant runs to the end, the financier's financed
    credit while the deal lasts. Each side's own yearly cut so far is held as it is."""
    turns = int(cfg.tune("time.turns"))
    host = world.nations[deal.host]
    out_ej = capacity(cfg, world, deal) / cfg.src(deal.terms["source"], "headroom")
    cut = out_ej * trade.displaced_ef(cfg, host)  # Mt/yr
    online = _online(cfg, world, deal)
    pay_from = world.t + 1 if deal.type == "climate_loan" else online
    end = min(turns, pay_from + int(deal.terms["duration"]))
    credited_years = max(0, end - online) / 4
    host_years = max(0, turns - online) / 4
    gains = {
        deal.financier: cfg.tune("credits.weight_financed") * cut * credited_years,
        deal.host: cfg.tune("credits.weight_real") * cut * host_years,
    }
    out = {}
    for nid, mt in gains.items():
        base = world.nations[nid].base["emissions"]
        now = scoring.yearly_cut(cfg, world, nid) if world.history else 0.0
        extra = mt / max(base * turns / 4, 1e-9)
        s = cfg.tune("scoring.climate_scale")
        out[nid] = 100 * (scoring.logistic((now + extra) / s) - scoring.logistic(now / s))
    return out


def preview(cfg: Config, world: World, deal: Deal) -> dict[str, Any]:
    """Everything the trade table shows about a drafted deal."""
    margin = host_margin(cfg, world, deal)
    key = actions._price_key(deal)
    yearly = deals.annual_payment(cfg, world, deal)
    years = int(deal.terms["duration"]) / 4
    out: dict[str, Any] = {
        "answer": answer(cfg, margin),
        "margin": None if math.isinf(margin) else margin,
        "price_key": key,
        "cost": deals.build_cost(cfg, world, deal),
        "capacity": capacity(cfg, world, deal),
        "online_turn": _online(cfg, world, deal),
        "payment_per_year": yearly,
        "years": years,
        "impact": projected_impact(cfg, world, deal),
    }
    if deal.type == "equity_for_energy":
        p = deals.failure_chance(cfg, world, deal)
        out["survival"] = (1 - p) ** int(deal.terms["duration"])
    if out["answer"] != ACCEPT:
        out["would_take"] = what_it_takes(cfg, world, deal)
    return out
