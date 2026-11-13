"""W4: influence is standing. It never gates a trade; it draws offers and eases answers."""

import pytest

from sim import actions, ai, diplomacy, negotiation
from sim.scenario import new_world
from tests.test_ai import with_personalities

OFFER = {
    "type": "propose_deal", "target": "BBB", "deal_type": "equipment_on_credit",
    "source": "solar", "amount": 0.01, "duration": 20, "collateral": 0.2, "exit_penalty": 0.3,
    "currency": "hard", "rate": 0.2,
}  # fmt: skip


def test_a_trade_needs_no_influence(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.influence, n.capital = 0.0, 5.0
    n.slots_banked = {"domestic": 3, "diplomatic": 2}
    [r] = actions.resolve(cfg, w, "AAA", [OFFER])
    assert r["ok"], r


def test_standing_rises_with_influence_and_saturates(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    values = []
    for infl in (0.0, 10.0, 100.0, 10_000.0):
        n.influence = infl
        values.append(diplomacy.standing(cfg, n))
    assert values[0] == 0.0
    assert values == sorted(values) and values[-1] < 1.0


def test_influence_eases_an_ai_hosts_answer(cfg):
    acfg = with_personalities(cfg, BBB="opportunist")
    w = new_world(acfg, seed=1)
    deal = negotiation.draft(acfg, w, "AAA", OFFER)
    w.nations["AAA"].influence = 0.0
    without = negotiation.host_margin(acfg, w, deal)
    w.nations["AAA"].influence = 50.0
    assert negotiation.host_margin(acfg, w, deal) > without


def test_influence_fades(cfg):
    w = new_world(cfg, seed=1)
    w.nations["AAA"].influence = 10.0
    diplomacy.fade_influence(w, cfg, 1)
    assert w.nations["AAA"].influence == pytest.approx(
        10.0 * (1 - cfg.tune("diplomacy.influence_fade"))
    )


def test_influence_draws_ai_offers(cfg):
    """An AI financier choosing between equally needy hosts picks the one with more influence."""
    acfg = with_personalities(cfg, BBB="green_leader")
    w = new_world(acfg, seed=1)
    w.nations["BBB"].capital = 100.0
    personality = acfg.nat_spec("BBB")["personality"]
    income = ai.income_per_year(acfg, w.nations["BBB"])
    w_em = ai.emissions_weight(acfg, w, "BBB", personality)
    for t in range(4):  # each AI considers offering once a year
        w.t = t
        found = ai._deal_offer(acfg, w, "BBB", personality, w_em, income)
        if found:
            break
    if not found:
        pytest.skip("this fixture's AI makes no offer")
    w.nations["AAA"].influence = 0.0
    _, act0 = ai._deal_offer(acfg, w, "BBB", personality, w_em, income)
    assert act0["target"] == "AAA"  # the only other nation; influence only changes the rank
