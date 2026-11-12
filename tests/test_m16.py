"""M16: fixes from playtest round 3."""

import importlib.util
from pathlib import Path

import pytest

from sim import actions, climate, economy, events, research, view
from sim.scenario import new_world
from sim.session import Game


@pytest.fixture
def w(cfg):
    world = new_world(cfg, seed=1)
    for n in world.nations.values():
        n.slots_banked = {"domestic": 6, "diplomatic": 4}
        n.political_capital = 100.0
        n.capital = 10.0
    return world


def test_tax_cut_is_mostly_borrowed(cfg, w):
    n = w.nations["AAA"]
    n.tax_change = -0.02
    parts = economy.income_parts(cfg, n)
    cut = 0.02 * n.gdp
    share = cfg.tune("tax.cut_capital_share")
    assert parts["tax"] == pytest.approx(-cut * share)
    assert parts["borrowed"] == pytest.approx(cut * (1 - share))
    debt, capital = n.debt_local, n.capital
    economy.apply_income(w, cfg, 1)
    assert n.debt_local == pytest.approx(debt + parts["borrowed"] / 4)
    assert n.capital > capital  # the budget still covers it at first
    assert economy.income_parts(cfg, n)["interest"] < 0  # and the debt now costs interest


def test_tax_rise_still_adds_in_full(cfg, w):
    n = w.nations["AAA"]
    n.tax_change = 0.01
    parts = economy.income_parts(cfg, n)
    assert parts["tax"] == pytest.approx(0.01 * n.gdp) and parts["borrowed"] == 0


def test_amounts_a_hair_over_the_limit_are_trimmed(cfg, w):
    n = w.nations["AAA"]
    tid = cfg.tech_ids[0]
    useful = research.useful_funding(cfg, w, n, tid)
    [r] = actions.resolve(cfg, w, "AAA", [{"type": "fund_research", "tech": tid,
                                          "amount": useful * 1.005}])  # fmt: skip
    assert r["ok"] and r["action"]["amount"] == pytest.approx(useful, rel=1e-6)
    [r] = actions.resolve(cfg, w, "AAA", [{"type": "fund_research", "tech": tid,
                                          "amount": useful * 2}])  # fmt: skip
    assert not r["ok"]  # a real overshoot is still refused


def test_fund_within_rounding_of_target_is_funded(cfg, w):
    e = {"id": "E1", "type": "rainforest", "region": "LAC", "target": 0.08, "opened": 0,
         "deadline": w.t, "status": events.OPEN, "closed": -1,
         "pledges": {"AAA": 0.07995}}  # fmt: skip
    w.minor_events.append(e)
    events.apply_minor(w, cfg, 1)
    assert e["status"] == events.FUNDED


def test_forest_payments_wear_off_and_credit_less(cfg, w):
    actions.resolve(cfg, w, "AAA", [{"type": "fund_forests", "amount": 0.1}])
    fund = w.forest_fund
    climate.apply(w, cfg, 4)
    keep = 1 - 1 / cfg.tune("climate.forest_lifespan")
    assert w.forest_fund == pytest.approx(fund * keep)
    assert w.nations["AAA"].forest_paid == pytest.approx(0.1 * keep)
    assert cfg.tune("credits.weight_forest") < cfg.tune("credits.weight_financed")


def test_screen_shows_income_and_borrowing(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    game.turn([{"type": "set_tax_rate", "level": -0.02}])
    text = view.render(view.observe(game))
    assert "capital income" in text and "your tax cut also borrows" in text


def test_runner_waits_as_openrouter_asks():
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("agent", root / "scripts" / "playtest_agent.py")
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    assert agent.retry_after("45", "") == 45
    assert agent.retry_after(None, '"headers":{"Retry-After":"120') == 120
    assert agent.retry_after(None, "no hint") == 120


def test_screen_has_no_unfilled_placeholders(cfg):
    """Round 4: an f-string split in M16 printed "{ec['approval']:.2f}" literally."""
    game = Game.new(cfg, "AAA", seed=1)
    game.wait(2)
    for brief in (False, True):
        text = view.render(view.observe(game), brief=brief)
        assert "{" not in text and "}" not in text
