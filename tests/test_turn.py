import pytest

from sim import config, turn
from sim.state import new_world


@pytest.fixture(scope="module")
def cfg():
    return config.load()


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


def test_actions_not_yet_supported(cfg):
    with pytest.raises(NotImplementedError):
        turn.step(new_world(cfg, seed=1), cfg, actions={"IND": [{"type": "build_capacity"}]})


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
        "scoring_snapshot",
        "events",
    ]
