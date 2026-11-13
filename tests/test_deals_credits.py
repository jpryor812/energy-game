"""Deals, emissions credit, the credit market, and the climate score. Fixture data."""

import copy
import dataclasses

import pytest

from sim import actions, ai, credits, deals, scoring, turn
from sim.scenario import new_world

OFFER = {
    "type": "propose_deal",
    "target": "BBB",
    "deal_type": "equipment_on_credit",
    "source": "solar",
    "amount": 1.0,
    "currency": "hard",
    "rate": 0.08,
    "duration": 8,
    "collateral": 0.5,
    "exit_penalty": 0.3,
}


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 50, "diplomatic": 50}
        n.capital = 5.0
    return w


def act(cfg, world, nid, *acts):
    return actions.resolve(cfg, world, nid, list(acts))


def signed(cfg, world, **changes):
    """Propose (AAA finances BBB) and accept a quarter later; return the deal."""
    act(cfg, world, "AAA", OFFER | changes)
    world.t += 1
    did = sorted(world.deals)[-1]
    [r] = act(cfg, world, "BBB", {"type": "respond_deal", "deal_id": did, "response": "accept"})
    assert r["ok"], r
    return world.deals[did]


def run_until(cfg, world, t):
    while world.t < t:
        world = turn.step(world, cfg)
    return world


def test_proposal_rules(cfg, world):
    act(cfg, world, "AAA", OFFER)
    did = sorted(world.deals)[-1]
    [r] = act(cfg, world, "BBB", {"type": "respond_deal", "deal_id": did, "response": "accept"})
    assert not r["ok"]  # same quarter
    world.t += 1
    [r] = act(cfg, world, "AAA", {"type": "respond_deal", "deal_id": did, "response": "accept"})
    assert not r["ok"]  # only the other side answers
    [r] = act(cfg, world, "AAA", OFFER | {"source": "coal"})
    assert not r["ok"]  # clean capacity only


def test_equipment_on_credit_flows(cfg, world):
    fin_before = world.nations["AAA"].capital
    debt_before = world.nations["BBB"].debt_hard
    deal = signed(cfg, world)
    cost = deal.terms["cost"]
    assert world.nations["AAA"].capital == pytest.approx(fin_before - cost)
    assert world.nations["BBB"].debt_hard == pytest.approx(debt_before + cost)
    assert world.nations["BBB"].pipeline[-1].source == "solar"
    w = run_until(cfg, world, deal.terms["end_turn"] + 1)
    d = w.deals[deal.id]
    assert d.status == "completed"
    assert d.terms["outstanding"] == pytest.approx(0.0, abs=1e-9)
    assert d.terms["paid"] > cost  # principal plus interest
    assert w.nations["AAA"].climate_credit["financed"] > 0


def test_counter_offer_goes_back_to_financier(cfg, world):
    act(cfg, world, "AAA", OFFER)
    world.t += 1
    did = sorted(world.deals)[-1]
    act(
        cfg,
        world,
        "BBB",
        {"type": "respond_deal", "deal_id": did, "response": "counter", "rate": 0.04},
    )
    assert world.deals[did].status == "countered"
    new = world.deals[sorted(world.deals)[-1]]
    assert new.terms["rate"] == 0.04 and deals.responder(new) == "AAA"


def test_hard_currency_default(cfg, world):
    tuning = copy.deepcopy(cfg.tuning)  # this test needs a deal far bigger than the host cap
    tuning["deals"]["host_capacity_cap"]["value"] = 100.0
    cfg = dataclasses.replace(cfg, tuning=tuning)
    deal = signed(cfg, world, collateral=0.5, amount=20.0)  # payments far above income
    host = world.nations["BBB"]
    w = run_until(cfg, world, deal.terms["online_turn"])
    w.nations["BBB"].capital = 0.0
    w.nations["BBB"].fx_reserves = 0.0
    w.nations["BBB"].base["fx_reserves"] = 0.0
    trust_before = w.trust["AAA"]["BBB"]
    w.nations["BBB"].capital = 0.0
    w = turn.step(w, cfg)
    w.nations["BBB"].capital = 0.0
    w = turn.step(w, cfg)
    d = w.deals[deal.id]
    assert d.status == "defaulted"
    assert w.trust["AAA"]["BBB"] < trust_before
    assert host is not w.nations["BBB"]  # steps are pure


def test_local_currency_never_defaults_but_loses_value(cfg, world):
    deal = signed(cfg, world, currency="local")
    w = run_until(cfg, world, deal.terms["online_turn"])
    host = w.nations["BBB"]
    host.fx_reserves = 0.25 * host.base["fx_reserves"]
    factor = deals._fx_factor(cfg, host, "BBB", "local")
    assert 0 < factor < 1
    w.nations["BBB"].capital = 0.0
    w = turn.step(w, cfg)
    assert w.deals[deal.id].status == "active"


def test_energy_as_a_service_and_exit(cfg, world):
    deal = signed(cfg, world, deal_type="energy_as_a_service", price=5.0)
    w = run_until(cfg, world, deal.terms["online_turn"] + 2)
    d = w.deals[deal.id]
    assert d.terms["paid"] == pytest.approx(5.0 * deals.output(cfg, d) * 1e-3 * 2 / 4, rel=1e-6)
    trust_before = w.trust["AAA"]["BBB"]
    [r] = act(cfg, w, "BBB", {"type": "exit_deal", "deal_id": deal.id})
    assert r["ok"] and w.deals[deal.id].status == "exited"
    assert w.trust["AAA"]["BBB"] < trust_before


def test_credit_never_changes_warming(cfg, world):
    signed(cfg, world)
    w = run_until(cfg, world, 12)
    inflated = copy.deepcopy(w)
    for n in inflated.nations.values():
        n.climate_credit = {"financed": 1e9, "exported": 1e9}
        n.credits_bought = 1e9
    a, b = run_until(cfg, w, 30), run_until(cfg, inflated, 30)
    assert a.warming == b.warming
    assert a.global_cumulative_emissions == b.global_cumulative_emissions


# --- credit market -------------------------------------------------------------------------------


def test_market_clears_at_midpoint(cfg, world):
    world.nations["BBB"].credit_balance = 10.0
    act(cfg, world, "AAA", {"type": "buy_credits", "amount": 10.0, "max_price": 50.0})
    act(cfg, world, "BBB", {"type": "sell_credits", "amount": 6.0, "min_price": 30.0})
    cap_a, cap_b = world.nations["AAA"].capital, world.nations["BBB"].capital
    log = credits.clear(cfg, world)
    assert log["traded"] == pytest.approx(6.0) and world.credit_price == pytest.approx(40.0)
    assert world.nations["AAA"].credit_balance == pytest.approx(6.0)
    assert world.nations["AAA"].capital == pytest.approx(cap_a - credits.cost(6.0, 40.0))
    assert world.nations["BBB"].capital == pytest.approx(cap_b + credits.cost(6.0, 40.0))
    assert world.credit_orders == []


def test_one_sided_market_drifts(cfg, world):
    start = world.credit_price
    act(cfg, world, "AAA", {"type": "buy_credits", "amount": 1.0, "max_price": 50.0})
    credits.clear(cfg, world)
    assert world.credit_price > start
    world.nations["BBB"].credit_balance = 1.0
    up = world.credit_price
    act(cfg, world, "BBB", {"type": "sell_credits", "amount": 1.0, "min_price": 90.0})
    credits.clear(cfg, world)
    assert world.credit_price < up


def test_order_rules(cfg, world):
    world.nations["AAA"].credit_balance = 1.0
    [r] = act(cfg, world, "AAA", {"type": "sell_credits", "amount": 5.0, "min_price": 10.0})
    assert not r["ok"]
    act(cfg, world, "AAA", {"type": "sell_credits", "amount": 1.0, "min_price": 10.0})
    [r] = act(cfg, world, "AAA", {"type": "buy_credits", "amount": 1.0, "max_price": 10.0})
    assert not r["ok"]


def test_beating_the_pathway_earns_credits(cfg, world):
    n = world.nations["AAA"]
    credits.issue(cfg, world, 1)
    assert n.credit_balance == 0  # at its 2025 level, on the pathway's start
    n.emissions = 0.5 * n.base["emissions"]
    credits.issue(cfg, world, 1)
    assert n.credit_balance == pytest.approx(0.5 * n.base["emissions"] / 4)


# --- scoring and AI ------------------------------------------------------------------------------


def test_climate_weights(cfg):
    from sim import runner

    w = runner.play(cfg, 1, "AAA", "noop", until=8)
    base = scoring.climate_contribution(cfg, w, "AAA")
    w.nations["AAA"].credits_bought = 100.0
    bought = scoring.climate_contribution(cfg, w, "AAA") - base
    assert bought == pytest.approx(100.0 * cfg.tune("credits.weight_purchased"))
    w.nations["AAA"].climate_credit["financed"] = 100.0
    assert scoring.climate_component(cfg, w, "AAA") > scoring.climate_component(
        cfg, runner.play(cfg, 1, "AAA", "noop", until=8), "AAA"
    )


def test_best_deal_honour_to_both_parties(cfg, world):
    deal = signed(cfg, world)
    deal.terms["credited"] = 10.0
    b = scoring.honours(cfg, world)
    assert "best_deal" in b["AAA"] and "best_deal" in b["BBB"]


def test_ai_host_bar_rises_with_currency_risk_and_falls_with_trust(cfg):
    from tests.test_ai import with_personalities

    acfg = with_personalities(cfg, BBB="opportunist")
    w = new_world(acfg, seed=1)
    for n in w.nations.values():
        n.capital = 5.0
        n.slots_banked = {"domestic": 5, "diplomatic": 5}
    act(acfg, w, "AAA", OFFER | {"amount": 0.01})
    w.t += 1
    d = w.deals[sorted(w.deals)[-1]]
    ctx = ai.context(acfg, w, "BBB")
    w_em = ai.emissions_weight(acfg, w, "BBB", "opportunist")
    income = (10.0, 4.0)

    def margin():
        return ai._value_deal_as_host(acfg, w, "BBB", d, "opportunist", ctx, w_em, income)

    base = margin()
    w.trust["BBB"]["AAA"] = 0.9
    trusted = margin()
    w.nations["BBB"].fx_reserves = 1e-7  # hard payments now dwarf reserves
    risky = margin()
    assert trusted > base > risky


def test_deals_change_outcomes(cfg, monkeypatch):
    from tests.test_ai import with_personalities

    acfg = with_personalities(cfg, AAA="green_leader", BBB="opportunist")
    with_deals = run_until(acfg, new_world(acfg, seed=1), 40)
    monkeypatch.setattr(ai, "_deal_offer", lambda *a, **k: None)
    without = run_until(acfg, new_world(acfg, seed=1), 40)
    assert with_deals.deals and not without.deals
    assert with_deals.hash() != without.hash()
