"""W4: trade-table previews (sim/negotiation.py) and the AI host's sense of a fair price."""

import copy

import pytest

from sim import ai, negotiation, runner
from tests.test_ai import with_personalities


@pytest.fixture
def setup(cfg):
    acfg = with_personalities(cfg, BBB="opportunist")
    w = runner.play(acfg, 1, "AAA", "noop", until=4)
    w.nations["AAA"].capital = 5.0
    return acfg, w


def offer(cfg, w, **terms):
    act = {
        "type": "propose_deal", "target": "BBB", "deal_type": "equipment_on_credit",
        "source": "solar", "amount": 0.01, "duration": 20, "collateral": 0.2,
        "exit_penalty": 0.3, "currency": "hard", "rate": 0.08,
    } | terms  # fmt: skip
    return negotiation.draft(cfg, w, "AAA", act)


def test_overpriced_terms_lower_the_hosts_margin(setup):
    cfg, w = setup
    fair = negotiation.host_margin(cfg, w, offer(cfg, w))
    steep = negotiation.host_margin(cfg, w, offer(cfg, w, rate=0.29))
    assert steep < fair
    assert ai.overprice(cfg, w, offer(cfg, w, rate=0.0)) == 0.0


def test_ai_financier_terms_are_fair(setup):
    """AI financiers ask exactly fair terms, so deals between AIs are unchanged by haggling."""
    cfg, w = setup
    rate = ai.fair_rate(cfg, w, "AAA", "BBB", "equipment_on_credit")
    assert ai.overprice(cfg, w, offer(cfg, w, rate=rate)) == 0.0


def test_what_it_takes_is_accepted(setup):
    cfg, w = setup
    deal = offer(cfg, w, rate=0.3)
    if negotiation.answer(cfg, negotiation.host_margin(cfg, w, deal)) == negotiation.ACCEPT:
        pytest.skip("this host accepts even the steepest rate")
    terms = negotiation.what_it_takes(cfg, w, deal)
    assert terms is not None and terms["rate"] < 0.3
    better = offer(cfg, w, rate=terms["rate"], amount=terms["amount"])
    assert negotiation.host_margin(cfg, w, better) > 0


def test_preview_is_read_only_and_reports_impact(setup):
    cfg, w = setup
    before = copy.deepcopy(w).hash()
    p = negotiation.preview(cfg, w, offer(cfg, w))
    assert w.hash() == before
    assert p["answer"] in (negotiation.ACCEPT, negotiation.COUNTER, negotiation.REFUSE)
    assert p["impact"]["BBB"] > 0 and p["impact"]["AAA"] > 0
    assert p["impact"]["BBB"] > p["impact"]["AAA"]  # real cuts count more than financed credit


def test_equity_preview_shows_the_chance_the_plant_lasts(setup):
    cfg, w = setup
    p = negotiation.preview(cfg, w, offer(cfg, w, deal_type="equity_for_energy", share=0.5))
    assert 0 < p["survival"] <= 1


def test_negotiate_endpoint(setup, tmp_path):
    from web.server import Server

    cfg, _ = setup
    server = Server(cfg, saves=tmp_path)
    server.new({"country": "AAA", "seed": 1})
    server.turn({"actions": []})
    act = {
        "type": "propose_deal", "target": "BBB", "deal_type": "equipment_on_credit",
        "source": "solar", "amount": 0.001, "duration": 20, "currency": "hard", "rate": 0.08,
        "collateral": 0.2, "exit_penalty": 0.3,
    }  # fmt: skip
    out = server.negotiate({"action": act})
    assert out["ok"], out
    assert "impact" in out and out["answer"] in ("accept", "counter", "refuse")
    bad = server.negotiate({"action": act | {"amount": 1e6}})
    assert not bad["ok"] and bad["reason"]
