"""Deals: equipment on credit, energy-as-a-service, equity-for-energy and climate loans.

A financier offers a host clean capacity. Terms: `source`, `amount` (EJ/yr), `currency`
("hard" or "local"), `duration` (quarters of payments), `collateral` (share of what is owed the
financier can seize on default), `exit_penalty` (share of remaining payments owed on early exit),
and a price: `rate` (annual interest, equipment on credit) or `price` ($/GJ of output,
energy-as-a-service).

Lifecycle: proposed -> (accepted) active -> completed, or refused / lapsed / expired /
defaulted / exited. A counter-offer closes the proposal as "countered" and opens a new one with
the counter's terms, to be answered by the other side.

On acceptance the financier pays the build cost (at its own unit cost) and the capacity enters
the host's pipeline. With equipment on credit the host takes on the cost as debt and repays
principal plus interest each quarter once the plant is running. With energy-as-a-service the
host pays `price` for each GJ the plant can normally produce.

Payments: hard-currency payments come from the host's capital, then (for nations that do not
issue a reserve currency) its FX reserves; if both run out the host defaults. Local-currency
payments come from capital, then local borrowing, so never default, but lose value to the
financier as the host's FX reserves fall below their 2025 level (currency risk).

Equity-for-energy (M5): the financier builds a plant and takes `share` of its operating margin
(host energy price minus the plant's running cost) each quarter, paid in local currency. No
fixed payment, so no default, but returns fall with the host's prices, and each quarter the plant
may fail or be seized (seeded "deals" stream), more likely when the host is unstable, its FX
reserves have fallen, it distrusts the investor, or it defaulted recently; the investor loses the
stake and the capacity goes. Climate loan (M5): `amount` T$ lent to build `source` capacity in
the host at the host's own unit cost (M9: the plant enters the host's pipeline; before, the
host got cash it need not spend), repaid like equipment on credit from the next quarter.

Emissions credit: once running, a deal cuts the host's emissions by roughly the plant's output x
the host's average fossil emission factor at signing. The host's real emissions already show it;
the financier earns `credits.weight_financed` x that cut for its score. Credit never reaches the
atmosphere.
"""

from __future__ import annotations

from typing import Any

from sim import construction, diplomacy, rng, tech, trade
from sim.config import Config
from sim.state import Deal, Nation, World

TYPES = ("equipment_on_credit", "energy_as_a_service", "equity_for_energy", "climate_loan")
LOANS = ("equipment_on_credit", "climate_loan")  # the host carries debt
OPEN = "proposed"
ACTIVE = "active"


def _k(cfg: Config, name: str) -> Any:
    return cfg.tune(f"deals.{name}")


def new_id(world: World) -> str:
    return f"D{len(world.deals) + 1:04d}"


def build_cost(cfg: Config, world: World, deal: Deal) -> float:
    """What the financier pays: the plant at its own unit cost, or the loan amount (T$)."""
    if deal.type == "climate_loan":
        return deal.terms["amount"]
    fin = world.nations[deal.financier]
    return tech.nation_unit_cost(cfg, world, fin, deal.terms["source"]) * deal.terms["amount"]


def deal_capacity(cfg: Config, world: World, deal: Deal) -> float:
    """EJ/yr of capacity a deal builds in its host (a climate loan's at the host's unit cost)."""
    if "capacity" in deal.terms:
        return deal.terms["capacity"]
    if deal.type == "climate_loan":
        host = world.nations[deal.host]
        return deal.terms["amount"] / tech.nation_unit_cost(cfg, world, host, deal.terms["source"])
    return deal.terms["amount"]


def host_room(cfg: Config, world: World, nid: str) -> float:
    """EJ/yr of deal capacity a nation can still host (M9): active deals' capacity is capped
    at `deals.host_capacity_cap` x its energy demand, so offers cannot dwarf its economy."""
    n = world.nations[nid]
    hosted = sum(
        deal_capacity(cfg, world, d)
        for d in world.deals.values()
        if d.host == nid and d.status == ACTIVE
    )
    return max(0.0, _k(cfg, "host_capacity_cap") * n.demand - hosted)


def effective_rate(cfg: Config, world: World, deal: Deal) -> float:
    rate = deal.terms.get("rate", 0.0)
    members = trade.club_members(world)
    if deal.financier in members and deal.host in members:
        rate = max(0.0, rate - cfg.tune("diplomacy.club_rate_discount"))
    return rate


def output(cfg: Config, deal: Deal) -> float:
    """Normal output of the deal's plant (or of the plant a climate loan pays for), EJ/yr."""
    capacity = deal.terms.get("capacity", deal.terms["amount"])
    return capacity / cfg.src(deal.terms["source"], "headroom")


def propose(world: World, financier: str, host: str, kind: str, terms: dict) -> Deal:
    deal = Deal(
        id=new_id(world),
        type=kind,
        financier=financier,
        host=host,
        terms=dict(terms) | {"proposer": terms.get("proposer", financier)},
        status=OPEN,
        start_turn=world.t,
    )
    world.deals[deal.id] = deal
    return deal


def responder(deal: Deal) -> str:
    return deal.host if deal.terms["proposer"] == deal.financier else deal.financier


def activate(cfg: Config, world: World, deal: Deal) -> None:
    fin, host = world.nations[deal.financier], world.nations[deal.host]
    cost = build_cost(cfg, world, deal)
    fin.capital -= cost
    source = deal.terms["source"]
    online = world.t + int(cfg.src(source, "build_time"))
    if deal.type == "climate_loan":
        # The loan pays for clean capacity built in the host at the host's unit cost (M9: it
        # used to be cash the host need not spend, while the lender was credited anyway);
        # repayments start next quarter.
        capacity = cost / tech.nation_unit_cost(cfg, world, host, source)
        construction.queue(cfg, host, source, capacity, world.t)
        pay_from = world.t + 1
    else:
        construction.queue(cfg, host, source, deal.terms["amount"], world.t)
        capacity = deal.terms["amount"]
        pay_from = online
    deal.terms |= {
        "cost": cost,
        "capacity": capacity,
        "online_turn": online,
        "pay_from": pay_from,
        "end_turn": pay_from + int(deal.terms["duration"]),
        "paid": 0.0,
        "credited": 0.0,
    }
    deal.terms["cut_rate"] = output(cfg, deal) * trade.displaced_ef(cfg, host)
    if deal.type in LOANS:
        deal.terms["outstanding"] = cost
        if deal.terms["currency"] == "hard" and not _issuer(cfg, deal.host):
            host.debt_hard += cost
        else:
            host.debt_local += cost
    deal.status = ACTIVE
    deal.start_turn = world.t
    gain = _k(cfg, "signing_trust_gain")
    diplomacy.adjust(world, deal.financier, deal.host, gain)
    diplomacy.adjust(world, deal.host, deal.financier, gain)


def _issuer(cfg: Config, nid: str) -> bool:
    return bool(cfg.nat_spec(nid)["hard_currency_issuer"])


def _fx_factor(cfg: Config, host: Nation, nid: str, currency: str) -> float:
    """Share of a payment's value the financier keeps after currency moves."""
    if currency == "hard" or host.base.get("fx_reserves", 0.0) <= 0:
        return 1.0
    fall = max(0.0, 1 - host.fx_reserves / host.base["fx_reserves"])
    return max(0.0, 1 - _k(cfg, "currency_loss") * fall)


def _collect(cfg: Config, host: Nation, nid: str, due: float, currency: str) -> float:
    """Take `due` (T$) from the host; return what was actually paid."""
    from_capital = min(due, max(0.0, host.capital))
    host.capital -= from_capital
    left = due - from_capital
    if left <= 0:
        return due
    if currency == "hard" and not _issuer(cfg, nid):
        from_fx = min(left, host.fx_reserves)
        host.fx_reserves -= from_fx
        return from_capital + from_fx
    host.debt_local += left  # local currency: borrow to pay
    return due


def _default(cfg: Config, world: World, deal: Deal) -> None:
    host, fin = world.nations[deal.host], world.nations[deal.financier]
    owed = deal.terms.get("outstanding", 0.0)
    seized = min(max(0.0, host.capital), deal.terms.get("collateral", 0.0) * owed)
    host.capital -= seized
    fin.capital += seized
    if deal.type in LOANS:
        if deal.terms["currency"] == "hard" and not _issuer(cfg, deal.host):
            host.debt_hard = max(0.0, host.debt_hard - owed)
        else:
            host.debt_local = max(0.0, host.debt_local - owed)
    host.pending_writeoff += _k(cfg, "default_growth_hit") * max(0.0, owed - seized)
    hit = _k(cfg, "default_trust_hit")
    diplomacy.adjust_all(world, deal.host, -hit / 2)
    diplomacy.adjust(world, deal.financier, deal.host, -hit / 2)
    deal.terms["seized"] = seized
    deal.terms["defaulted_turn"] = world.t
    deal.status = "defaulted"


def failure_chance(cfg: Config, world: World, deal: Deal) -> float:
    """Chance per quarter that an equity-financed plant fails or is seized: higher when the
    host's government is unstable, its FX reserves have fallen, it distrusts the investor, or it
    has defaulted recently."""
    host = world.nations[deal.host]
    instability = max(0.0, 0.5 - host.stability) / 0.5
    fx_fall = 0.0
    if not _issuer(cfg, deal.host) and host.base.get("fx_reserves", 0.0) > 0:
        fx_fall = max(0.0, 1 - host.fx_reserves / host.base["fx_reserves"])
    distrust = max(0.0, 0.5 - diplomacy.trust(world, deal.host, deal.financier)) / 0.5
    recent = sum(
        1
        for d in world.deals.values()
        if d.host == deal.host
        and d.status == "defaulted"
        and world.t - d.terms.get("defaulted_turn", -1e9) < _k(cfg, "recent_default_quarters")
    )
    risk = (
        1
        + _k(cfg, "hazard_instability") * instability
        + _k(cfg, "hazard_fx") * fx_fall
        + _k(cfg, "hazard_distrust") * distrust
        + _k(cfg, "hazard_default") * recent
    )
    return min(1.0, _k(cfg, "equity_hazard") * risk)


def _fail(cfg: Config, world: World, deal: Deal) -> None:
    host = world.nations[deal.host]
    source = deal.terms["source"]
    lost = min(host.capacity.get(source, 0.0), deal.terms["capacity"])
    host.capacity[source] = host.capacity.get(source, 0.0) - lost
    hit = _k(cfg, "failure_trust_hit")
    diplomacy.adjust(world, deal.financier, deal.host, -hit)
    diplomacy.adjust(world, deal.host, deal.financier, -hit)
    deal.terms["failed_turn"] = world.t
    deal.status = "failed"


def exit_deal(cfg: Config, world: World, deal: Deal) -> None:
    """Host ends an energy-as-a-service deal early, paying the exit penalty."""
    host, fin = world.nations[deal.host], world.nations[deal.financier]
    remaining_q = max(0, deal.terms["end_turn"] - max(world.t, deal.terms["online_turn"]))
    remaining = deal.terms["price"] * output(cfg, deal) * 1e-3 * remaining_q / 4
    penalty = deal.terms.get("exit_penalty", 0.0) * remaining
    paid = _collect(cfg, host, deal.host, penalty, deal.terms["currency"])
    fin.capital += paid * _fx_factor(cfg, host, deal.host, deal.terms["currency"])
    diplomacy.adjust(world, deal.financier, deal.host, -_k(cfg, "exit_trust_hit"))
    deal.status = "exited"


def dividend(cfg: Config, world: World, deal: Deal) -> float:
    """Yearly equity dividend, T$: the investor's share of the plant's operating margin (host
    energy price minus the plant's running cost) on its normal output. Falls with prices."""
    host = world.nations[deal.host]
    margin = max(0.0, host.energy_price - cfg.src(deal.terms["source"], "variable_cost"))
    return deal.terms["share"] * output(cfg, deal) * margin * 1e-3


def annual_payment(cfg: Config, world: World, deal: Deal) -> float:
    """What the host pays per year on an active (or proposed) deal, T$."""
    if deal.type == "equity_for_energy":
        return dividend(cfg, world, deal)
    if deal.type in LOANS:
        owed = deal.terms.get("outstanding", build_cost(cfg, world, deal))
        years = max(
            0.25, (deal.terms.get("end_turn", world.t + deal.terms["duration"]) - world.t) / 4
        )
        return owed / years + owed * effective_rate(cfg, world, deal)
    return deal.terms["price"] * output(cfg, deal) * 1e-3


def obligations(cfg: Config, world: World, nid: str) -> float:
    """A host's yearly payments on all its active deals, T$."""
    return sum(
        annual_payment(cfg, world, d)
        for d in world.deals.values()
        if d.host == nid and d.status == ACTIVE
    )


def service(cfg: Config, world: World, dt: int) -> None:
    """Quarterly payments, credit, completion and expiry for every deal."""
    weight = cfg.tune("credits.weight_financed")
    for did in sorted(world.deals):
        deal = world.deals[did]
        if deal.status == OPEN:
            if world.t - deal.start_turn >= _k(cfg, "proposal_expiry"):
                deal.status = "expired"
            continue
        if deal.status != ACTIVE or world.t < deal.terms["pay_from"]:
            continue
        host, fin = world.nations[deal.host], world.nations[deal.financier]
        if deal.type == "equity_for_energy" and world.t >= deal.terms["online_turn"]:
            roll = rng.stream(world.seed, "deals", world.t, deal.id).random()
            if roll < failure_chance(cfg, world, deal):
                _fail(cfg, world, deal)
                continue
        currency = deal.terms["currency"]
        principal = 0.0
        if deal.type in LOANS:
            left_q = max(1, deal.terms["end_turn"] - world.t)
            principal = min(deal.terms["outstanding"], deal.terms["outstanding"] * dt / left_q)
            interest = deal.terms["outstanding"] * effective_rate(cfg, world, deal) * dt / 4
            due = principal + interest
        elif deal.type == "equity_for_energy":
            due = dividend(cfg, world, deal) * dt / 4
        else:
            due = deal.terms["price"] * output(cfg, deal) * 1e-3 * dt / 4
        paid = _collect(cfg, host, deal.host, due, currency)
        fin.capital += paid * _fx_factor(cfg, host, deal.host, currency)
        deal.terms["paid"] += paid
        if paid + 1e-12 < due:
            _default(cfg, world, deal)
            continue
        if deal.type in LOANS:
            deal.terms["outstanding"] -= principal
            if currency == "hard" and not _issuer(cfg, deal.host):
                host.debt_hard = max(0.0, host.debt_hard - principal)
            else:
                host.debt_local = max(0.0, host.debt_local - principal)
        if world.t < deal.terms["online_turn"]:
            continue  # a climate loan's plant is not running yet
        credit = deal.terms["cut_rate"] * dt / 4
        deal.terms["credited"] += credit
        fin.climate_credit["financed"] = fin.climate_credit.get("financed", 0.0) + weight * credit
        if world.t + dt >= deal.terms["end_turn"]:
            deal.status = "completed"
            gain = _k(cfg, "completion_trust_gain")
            diplomacy.adjust(world, deal.financier, deal.host, gain)
            diplomacy.adjust(world, deal.host, deal.financier, gain)
