import pytest

from sim import turn
from sim.scenario import new_world


def test_quarter_labels():
    assert turn.quarter_label(0, 2025) == "2025Q1"
    assert turn.quarter_label(3, 2025) == "2025Q4"
    assert turn.quarter_label(99, 2025) == "2049Q4"


def test_stocktake_turns():
    due = [t for t in range(100) if turn.stocktake_due(t, 1, 20)]
    assert due == [19, 39, 59, 79, 99]


def test_stocktake_annual_mode_hits_same_years():
    due = [t for t in range(0, 100, 4) if turn.stocktake_due(t, 4, 20)]
    assert due == [16, 36, 56, 76, 96]


def test_step_is_pure_and_advances(cfg):
    w0 = new_world(cfg, seed=1)
    before = w0.hash()
    w1 = turn.step(w0, cfg)
    assert w0.hash() == before
    assert w1.t == 1 and len(w1.history) == 1
    assert w1.history[0]["label"] == "2025Q1"


def test_step_dt(cfg):
    w = turn.step(new_world(cfg, seed=1), cfg, dt=4)
    assert w.t == 4
    with pytest.raises(ValueError):
        turn.step(w, cfg, dt=0)


def test_actions_are_resolved_and_logged(cfg):
    acts = [{"type": "rebate", "share": 0.5}, {"type": "no_such_action"}]
    w = turn.step(new_world(cfg, seed=1), cfg, actions={"AAA": acts})
    log = w.history[-1]["nations"]["AAA"]["actions"]
    assert [r["ok"] for r in log] == [True, False]
    assert w.nations["AAA"].rebate == 0.5


def test_actions_for_unknown_nation_raise(cfg):
    with pytest.raises(ValueError):
        turn.step(new_world(cfg, seed=1), cfg, actions={"ZZZ": []})


def test_stage_order_matches_build_doc():
    assert [name for name, _ in turn.STAGES] == [
        "income_and_slots",
        "actions",
        "resolve_actions",
        "construction",
        "energy_dispatch",
        "economy",
        "climate",
        "technology",
        "diplomacy",
        "stocktake",
        "elections",
        "scoring_snapshot",
        "events",
    ]
