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

Panels from your own factories (W4 part 2, decided with the user 2026-11-12): when the financier
of a plant deal (equipment on credit, equity, or an equipment sale) has spare factory output for
the plant's equipment (solar panels, wind turbines), its factories make it: the sale counts as
its clean-tech export, not a share of the world market. Spare output is factory capacity x
`deals.panel_output_years`, less what its deals of the last four quarters already took.

Equipment sale (W4): the host buys the plant outright. The seller builds it at its own unit cost
from its own factories (required) and the host pays that cost plus a negotiated `markup` at
signing. The seller earns exported credit (`credits.weight_exported`) for the cut once it runs.

Factory partnership (W4): the financier funds `amount` T$/yr of clean-tech factory capacity
(`tech`: solar, wind or storage) in the host, paying `capital_share` of its cost (the host pays
the rest), and may also supply `power` EJ/yr of cheap clean power for the term, paid at its own
solar cost, which lowers the factory's running costs. In return it takes `share` of the
factory's earnings for `duration` quarters once it opens: the factory's slice of the host's sales
of that technology x `industry.factory_margin`, plus the power's value at the host's energy price.
Each quarter the factory may fail (seeded "deals" stream), more likely the smaller the
financier's stake (capital and power, as a share of the whole) and the less developed the host
(income per person against the 16-nation average), and when the host is unstable or distrusts
the financier. Credit follows the export credit the host's factories already earn (sim.trade):
the financier earns `credits.weight_exported` x its stake x the factory's slice of the rise in
the host's exported cut since the factory opened (an approximation: the plants its panels
equip would have been built anyway, so a factory moves who makes them, not how many).
"""

from __future__ import annotations

from typing import Any

from sim import construction, diplomacy, rng, tech, trade
from sim.config import Config
from sim.state import Construction, Deal, Nation, World

TYPES = (
    "equipment_on_credit", "energy_as_a_service", "equity_for_energy", "climate_loan",
    "equipment_sale", "factory_partnership",
)  # fmt: skip
LOANS = ("equipment_on_credit", "climate_loan")  # the host carries debt
# Plants the financier builds, from its own factories where it can.
PANELS = ("equipment_on_credit", "equity_for_energy", "equipment_sale")
SHARES = ("equity_for_energy", "factory_partnership")  # paid as a share of earnings
# The power source whose equipment each factory line makes, for the cuts its output enables.
LINE_SOURCE = {"solar": "solar", "wind": "onshore_wind"}
OPEN = "proposed"
ACTIVE = "active"


def _k(cfg: Config, name: str) -> Any:
    return cfg.tune(f"deals.{name}")


def new_id(world: World) -> str:
    return f"D{len(world.deals) + 1:04d}"


def build_cost(cfg: Config, world: World, deal: Deal) -> float:
    """What the financier pays: the plant at its own unit cost, the loan amount, or its share of
    a factory's cost (T$)."""
    if deal.type == "climate_loan":
        return deal.terms["amount"]
    if deal.type == "factory_partnership":
        return deal.terms["capital_share"] * factory_cost(cfg, deal)
    fin = world.nations[deal.financier]
    return tech.nation_unit_cost(cfg, world, fin, deal.terms["source"]) * deal.terms["amount"]


def deal_capacity(cfg: Config, world: World, deal: Deal) -> float:
    """EJ/yr of capacity a deal builds in its host (a climate loan's at the host's unit cost; a
    factory builds none)."""
    if deal.type == "factory_partnership":
        return 0.0
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


# --- panels from the financier's factories, sales and factory partnerships (W4) ---------------


def factory_cost(cfg: Config, deal: Deal) -> float:
    """Whole cost of a partnership's factory (T$)."""
    return cfg.tune("industry.factory_capital_cost") * deal.terms["amount"]


def equipment_value(cfg: Config, world: World, deal: Deal) -> float:
    """T$ of factory-made equipment in a plant deal (0 for sources no factory line makes)."""
    source = deal.terms.get("source")
    if deal.type not in PANELS or source not in trade.EQUIPMENT_OF:
        return 0.0
    fin = world.nations[deal.financier]
    unit = tech.nation_unit_cost(cfg, world, fin, source)
    return cfg.src(source, "equipment_share") * unit * deal.terms["amount"]


def spare_output(cfg: Config, world: World, nid: str, line: str) -> float:
    """T$ of equipment a nation's `line` factories can still supply to deals: capacity x
    `deals.panel_output_years`, less what its deals signed in the last four quarters took."""
    n = world.nations[nid]
    used = sum(
        d.terms.get("equipment_value", 0.0)
        for d in world.deals.values()
        if d.financier == nid and d.terms.get("supplied") and d.status != OPEN
        and world.t - d.start_turn < 4
        and trade.EQUIPMENT_OF.get(d.terms.get("source")) == line
    )  # fmt: skip
    return max(0.0, n.factory_capacity.get(line, 0.0) * _k(cfg, "panel_output_years") - used)


def self_supplied(cfg: Config, world: World, deal: Deal) -> bool:
    """Whether the financier's own factories can make this plant's equipment."""
    value = equipment_value(cfg, world, deal)
    if value <= 0:
        return False
    line = trade.EQUIPMENT_OF[deal.terms["source"]]
    return value <= spare_output(cfg, world, deal.financier, line) + 1e-12


def sale_price(cfg: Config, world: World, deal: Deal) -> float:
    """What the host pays for an equipment sale: the seller's cost plus the markup (T$)."""
    return build_cost(cfg, world, deal) * (1 + deal.terms["markup"])


def host_outlay(cfg: Config, world: World, deal: Deal) -> float:
    """What the host pays at signing (T$): the price of a sale, its share of a factory."""
    if deal.type == "equipment_sale":
        return sale_price(cfg, world, deal)
    if deal.type == "factory_partnership":
        return (1 - deal.terms["capital_share"]) * factory_cost(cfg, deal)
    return 0.0


def _power_cost(cfg: Config, world: World, deal: Deal) -> float:
    """What the financier's committed clean power costs it a year (T$), at its solar cost."""
    power = deal.terms.get("power", 0.0)
    if power <= 0:
        return 0.0
    fin = world.nations[deal.financier]
    return power * tech.lcoe(cfg, world, fin, "solar") * 1e-3


def stake(cfg: Config, world: World, deal: Deal) -> float:
    """The financier's share of what was put into a factory: its capital and the power it
    commits over the term, against the whole factory cost plus that power."""
    power = _power_cost(cfg, world, deal) * deal.terms["duration"] / 4
    mine = deal.terms["capital_share"] * factory_cost(cfg, deal) + power
    whole = factory_cost(cfg, deal) + power
    return mine / whole if whole > 0 else 0.0


def development(world: World, nid: str) -> float:
    """Income per person against the 16-nation average, capped at 1."""
    nations = world.nations.values()
    avg = sum(m.gdp for m in nations) / sum(m.population for m in nations)
    n = world.nations[nid]
    return min(1.0, (n.gdp / n.population) / avg) if avg > 0 else 1.0


def line_use(world: World, line: str) -> float:
    """Share of the 16 nations' factory capacity on a line that is selling now."""
    cap = sum(n.factory_capacity.get(line, 0.0) for n in world.nations.values())
    sales = sum(n.factory_sales.get(line, 0.0) for n in world.nations.values())
    return min(1.0, sales / cap) if cap > 0 else 0.0


def factory_profit(cfg: Config, world: World, deal: Deal) -> float:
    """A partnership factory's yearly earnings (T$): its slice of the host's sales of that
    technology once it runs (before then, its capacity at the world's current use of that line)
    x the factory margin, plus the committed power at the host's energy price."""
    host = world.nations[deal.host]
    line, amount = deal.terms["tech"], deal.terms["amount"]
    cap = host.factory_capacity.get(line, 0.0)
    sales = host.factory_sales.get(line, 0.0)
    built = world.t >= deal.terms.get("online_turn", world.t + 1)
    mine = sales * amount / cap if built and cap > 0 else line_use(world, line) * amount
    power = deal.terms.get("power", 0.0) * host.energy_price * 1e-3
    return cfg.tune("industry.factory_margin") * mine + power


def factory_failure_chance(cfg: Config, world: World, deal: Deal) -> float:
    """Chance per quarter that a partnership factory fails: higher the smaller the financier's
    stake and the less developed the host, and with the host risks equity deals face."""
    base = _k(cfg, "factory_hazard")
    low_stake = 1 + _k(cfg, "hazard_low_stake") * (1 - stake(cfg, world, deal))
    poor = 1 + _k(cfg, "hazard_development") * (1 - development(world, deal.host))
    host_risk = failure_chance(cfg, world, deal) / _k(cfg, "equity_hazard")
    return min(1.0, base * low_stake * poor * host_risk)


def line_cut(cfg: Config, world: World, deal: Deal, value: float) -> float:
    """Mt/yr of cuts the plants built with `value` T$ of a factory line's equipment make (at
    the host's displaced emission factor, as a stand-in for its buyers')."""
    source = LINE_SOURCE.get(deal.terms["tech"])
    if source is None or value <= 0:
        return 0.0  # batteries enable cuts rather than make them
    unit = tech.unit_cost(cfg, world, source)
    capacity = value / (cfg.src(source, "equipment_share") * unit)
    ef = trade.displaced_ef(cfg, world.nations[deal.host])
    return capacity / cfg.src(source, "headroom") * ef


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
    if deal.type == "factory_partnership":
        _activate_factory(cfg, world, deal, cost)
        return
    source = deal.terms["source"]
    supplier = None
    if deal.type in PANELS:
        supplied = self_supplied(cfg, world, deal)
        deal.terms["equipment_value"] = equipment_value(cfg, world, deal)
        deal.terms["supplied"] = supplied
        supplier = deal.financier if supplied else None
    online = world.t + construction.build_time(cfg, host, source)
    if deal.type == "climate_loan":
        # The loan pays for clean capacity built in the host at the host's unit cost (M9: it
        # used to be cash the host need not spend, while the lender was credited anyway);
        # repayments start next quarter.
        capacity = cost / tech.nation_unit_cost(cfg, world, host, source)
        construction.queue(cfg, host, source, capacity, world.t)
        pay_from = world.t + 1
    else:
        construction.queue(cfg, host, source, deal.terms["amount"], world.t, supplier)
        capacity = deal.terms["amount"]
        pay_from = online
    if deal.type == "equipment_sale":  # the host pays for the plant now
        price = sale_price(cfg, world, deal)
        host.capital -= price
        fin.capital += price
        deal.terms["price_paid"] = price
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


def _activate_factory(cfg: Config, world: World, deal: Deal, cost: float) -> None:
    host = world.nations[deal.host]
    host.capital -= host_outlay(cfg, world, deal)
    online = world.t + int(cfg.tune("industry.factory_build_time"))
    host.pipeline.append(
        Construction(construction.FACTORY + deal.terms["tech"], deal.terms["amount"], online)
    )
    deal.terms |= {
        "cost": cost,
        "online_turn": online,
        "pay_from": online,
        "end_turn": online + int(deal.terms["duration"]),
        "paid": 0.0,
        "credited": 0.0,
        "stake": stake(cfg, world, deal),
    }
    deal.status = ACTIVE
    deal.start_turn = world.t
    gain = _k(cfg, "signing_trust_gain")
    diplomacy.adjust(world, deal.financier, deal.host, gain)
    diplomacy.adjust(world, deal.host, deal.financier, gain)


def _service_factory(cfg: Config, world: World, deal: Deal, dt: int) -> None:
    """A partnership factory's quarter: failure roll, the financier's power, its share of the
    earnings, and credit for the cuts the factory's equipment makes."""
    host, fin = world.nations[deal.host], world.nations[deal.financier]
    roll = rng.stream(world.seed, "deals", world.t, deal.id).random()
    if roll < factory_failure_chance(cfg, world, deal):
        line = deal.terms["tech"]
        lost = min(host.factory_capacity.get(line, 0.0), deal.terms["amount"])
        host.factory_capacity[line] = host.factory_capacity.get(line, 0.0) - lost
        hit = _k(cfg, "failure_trust_hit")
        diplomacy.adjust(world, deal.financier, deal.host, -hit)
        diplomacy.adjust(world, deal.host, deal.financier, -hit)
        deal.terms["failed_turn"] = world.t
        deal.status = "failed"
        return
    fin.capital -= min(max(fin.capital, 0.0), _power_cost(cfg, world, deal) * dt / 4)
    due = deal.terms["share"] * factory_profit(cfg, world, deal) * dt / 4
    paid = _collect(cfg, host, deal.host, due, "local")
    fin.capital += paid * _fx_factor(cfg, host, deal.host, "local")
    deal.terms["paid"] += paid
    line = deal.terms["tech"]
    cap = host.factory_capacity.get(line, 0.0)
    slice_ = deal.terms["amount"] / cap if cap > 0 else 0.0
    if "export_base" not in deal.terms:
        deal.terms["export_base"] = host.exported_cut_rate
    rise = max(0.0, host.exported_cut_rate - deal.terms["export_base"])
    credit = deal.terms["stake"] * slice_ * rise * dt / 4
    deal.terms["credited"] += credit
    weight = cfg.tune("credits.weight_exported")
    fin.climate_credit["financed"] = fin.climate_credit.get("financed", 0.0) + weight * credit
    if world.t + dt >= deal.terms["end_turn"]:
        deal.status = "completed"
        gain = _k(cfg, "completion_trust_gain")
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
    """What the host pays per year on an active (or proposed) deal, T$ (an equipment sale is
    paid at signing)."""
    if deal.type == "equipment_sale":
        return 0.0
    if deal.type == "factory_partnership":
        return deal.terms["share"] * factory_profit(cfg, world, deal)
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
        if deal.type == "factory_partnership":
            _service_factory(cfg, world, deal, dt)
            continue
        if deal.type == "equipment_sale":  # paid at signing; the seller's credit starts now
            world.nations[deal.financier].exported_cut_rate += deal.terms["cut_rate"]
            deal.status = "completed"
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
