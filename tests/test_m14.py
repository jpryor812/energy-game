"""M14: fixes from playtest round 2."""

import pytest

from sim import actions, economy, tech, view
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


# --- permitting -----------------------------------------------------------------------------------


def test_raising_reform_restarts_the_backlash_and_it_fades_after_a_term(cfg, w):
    n = w.nations["AAA"]
    w.t = 5
    [r] = actions.resolve(cfg, w, "AAA", [{"type": "set_permitting", "level": 1.0}])
    assert r["ok"] and n.permitting_since == 5
    full = economy.permitting_backlash(cfg, w, n)
    w.t = 5 + int(cfg.tune("permitting.habituation_quarters"))
    assert economy.permitting_backlash(cfg, w, n) == pytest.approx(
        full * cfg.tune("permitting.habituation_factor")
    )
    [r] = actions.resolve(cfg, w, "AAA", [{"type": "set_permitting", "level": 0.5}])
    assert n.permitting_since == 5  # lowering does not restart it


def test_faster_builds_are_cheaper(cfg, w):
    n = w.nations["AAA"]
    before = tech.nation_unit_cost(cfg, w, n, "onshore_wind")
    assert tech.permitting_saving(cfg, n, "onshore_wind") == 0.0
    n.permitting = 1.0
    saving = tech.permitting_saving(cfg, n, "onshore_wind")
    assert saving > 0
    assert tech.nation_unit_cost(cfg, w, n, "onshore_wind") == pytest.approx(before * (1 - saving))


# --- the election line and the screen -------------------------------------------------------------


def test_forecast_shows_early_with_swing_range_and_growth_gap(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    game.wait(1)
    obs = view.observe(game)
    e = obs["election"]
    assert e["expected_vote"] is not None
    assert e["swing_range"] == pytest.approx(1.96 * cfg.tune("elections.swing_sd"), abs=1e-3)
    text = view.render(obs)
    assert "random swing" in text and "levers:" in text
    assert "behind by" in text or "ahead by" in text


def test_score_change_notice(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    game.wait(2)
    assert any(x.startswith("Score ") for x in game.notices)


def test_two_point_tax_cut_allowed(cfg, w):
    [r] = actions.resolve(cfg, w, "AAA", [{"type": "set_tax_rate", "level": -0.02}])
    assert r["ok"], r


def test_election_result_has_its_own_block():
    from sim import play

    rep = {
        "quarter": "2028Q4",
        "results": [],
        "election": {"event": "won", "vote": 0.553},
        "notices": [],
    }
    lines = play._quarter(rep)
    assert any("===== ELECTION 2028Q4: WON with 0.553" in x for x in lines)
