"""W4 part 2: panels from your own factories, equipment sales and factory partnerships."""

import pytest

from sim import actions, ai, deals, negotiation, trade
from sim.scenario import new_world

SALE = {
    "type": "propose_deal", "target": "BBB", "deal_type": "equipment_sale", "source": "solar",
    "amount": 0.2, "markup": 0.15,
}  # fmt: skip
FACTORY = {
    "type": "propose_deal", "target": "BBB", "deal_type": "factory_partnership", "tech": "solar",
    "amount": 0.05, "capital_share": 1.0, "power": 0.0, "share": 0.5, "duration": 20,
}  # fmt: skip


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 50, "diplomatic": 50}
        n.capital = 5.0
    return w


def act(cfg, world, nid, *acts):
    return actions.resolve(cfg, world, nid, list(acts))


def sign(cfg, world, offer):
    [r] = act(cfg, world, "AAA", offer)
    assert r["ok"], r
    world.t += 1
    did = sorted(world.deals)[-1]
    [r] = act(cfg, world, "BBB", {"type": "respond_deal", "deal_id": did, "response": "accept"})
    assert r["ok"], r
    return world.deals[did]


def test_a_sale_needs_your_own_factory_output(cfg, world):
    world.nations["AAA"].factory_capacity["solar"] = 0.0
    [r] = act(cfg, world, "AAA", SALE)
    assert not r["ok"] and "factories" in r["reason"]


def test_a_sale_is_paid_at_signing_and_built_from_your_factories(cfg, world):
    world.nations["AAA"].factory_capacity["solar"] = 1.0
    a0, b0 = world.nations["AAA"].capital, world.nations["BBB"].capital
    deal = sign(cfg, world, SALE)
    price, cost = deal.terms["price_paid"], deal.terms["cost"]
    assert price == pytest.approx(cost * 1.15)
    assert world.nations["AAA"].capital == pytest.approx(a0 - cost + price)
    assert world.nations["BBB"].capital == pytest.approx(b0 - price)
    built = [c for c in world.nations["BBB"].pipeline if c.source == "solar"]
    assert built and built[-1].supplier == "AAA"
    assert deal.terms["supplied"]


def test_supplied_plants_count_as_the_suppliers_sale(cfg, world):
    unit = {s: 1.0 for s in trade.EQUIPMENT_OF}
    sold = lambda w: w.nations["AAA"].factory_sales.get("solar", 0.0)  # noqa: E731
    trade.apply_equipment(cfg, world, {}, unit, 1, None, [("BBB", "AAA", "solar", 0.5)])
    assert sold(world) > 0
    assert world.nations["AAA"].cleantech_exports > 0
    assert world.nations["BBB"].equipment_demand["solar"] > 0


def test_credit_deals_use_your_factories_only_when_they_have_room(cfg, world):
    offer = SALE | {"deal_type": "equipment_on_credit", "rate": 0.08, "currency": "hard",
                    "duration": 8, "collateral": 0.2, "exit_penalty": 0.3}  # fmt: skip
    world.nations["AAA"].factory_capacity["solar"] = 0.0
    assert not sign(cfg, world, offer).terms["supplied"]  # bought on the world market
    world.nations["AAA"].factory_capacity["solar"] = 1.0
    assert sign(cfg, world, offer).terms["supplied"]


def test_factory_partnership_splits_the_cost_and_builds_a_factory(cfg, world):
    a0, b0 = world.nations["AAA"].capital, world.nations["BBB"].capital
    deal = sign(cfg, world, FACTORY | {"capital_share": 0.4})
    whole = cfg.tune("industry.factory_capital_cost") * FACTORY["amount"]
    assert world.nations["AAA"].capital == pytest.approx(a0 - 0.4 * whole)
    assert world.nations["BBB"].capital == pytest.approx(b0 - 0.6 * whole)
    assert any(c.source == "factory_solar" for c in world.nations["BBB"].pipeline)
    assert deal.terms["stake"] == pytest.approx(0.4)


def test_factory_partnership_pays_out_once_open(cfg, world):
    deal = sign(cfg, world, FACTORY)
    world.t = deal.terms["online_turn"]
    host = world.nations["BBB"]
    host.factory_capacity["solar"] = host.factory_capacity.get("solar", 0.0) + FACTORY["amount"]
    host.factory_sales["solar"] = host.factory_capacity["solar"] * 0.8
    before = world.nations["AAA"].capital
    deals.service(cfg, world, 1)
    if deal.status == "failed":
        pytest.skip("this seed's factory failed in its first quarter")
    assert deal.terms["paid"] > 0
    assert world.nations["AAA"].capital > before


def test_less_funding_and_less_development_raise_the_failure_chance(cfg, world):
    full = negotiation.draft(cfg, world, "AAA", FACTORY)
    thin = negotiation.draft(cfg, world, "AAA", FACTORY | {"capital_share": 0.2})
    assert deals.factory_failure_chance(cfg, world, thin) > deals.factory_failure_chance(
        cfg, world, full
    )
    host = world.nations["BBB"]
    rich = deals.factory_failure_chance(cfg, world, full)
    host.gdp *= 0.1
    assert deals.factory_failure_chance(cfg, world, full) > rich


def test_power_counts_toward_the_stake(cfg, world):
    no_power = negotiation.draft(cfg, world, "AAA", FACTORY | {"capital_share": 0.5})
    power = negotiation.draft(cfg, world, "AAA", FACTORY | {"capital_share": 0.5, "power": 0.2})
    assert deals.stake(cfg, world, power) > deals.stake(cfg, world, no_power)


def test_ai_wants_a_fair_share_for_a_factory(cfg, world):
    fair = negotiation.draft(cfg, world, "AAA", FACTORY | {"capital_share": 0.5, "share": 0.5})
    greedy = negotiation.draft(cfg, world, "AAA", FACTORY | {"capital_share": 0.5, "share": 0.9})
    free = negotiation.draft(cfg, world, "AAA", FACTORY | {"capital_share": 0.0, "share": 0.2})
    assert ai.overprice(cfg, world, fair) == pytest.approx(0.0)
    assert ai.overprice(cfg, world, greedy) > 0
    assert ai.overprice(cfg, world, free) == float("inf")


def test_preview_covers_the_new_deals(cfg, world):
    world.nations["AAA"].factory_capacity["solar"] = 1.0
    sale = negotiation.preview(cfg, world, negotiation.draft(cfg, world, "AAA", SALE))
    assert sale["price"] > sale["cost"] and sale["from_your_factories"]
    fac = negotiation.preview(cfg, world, negotiation.draft(cfg, world, "AAA", FACTORY))
    assert 0 < fac["survival"] < 1 and fac["stake"] == pytest.approx(1.0)
    assert fac["capacity"] == 0.0
