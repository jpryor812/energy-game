"""M10: permitting and zoning reform."""

import pytest

from sim import actions, config, construction, economy, elections, runner, turn
from sim.scenario import new_world


def test_reform_shortens_build_times_most_where_permitting_is_slowest(cfg):
    n = new_world(cfg, seed=1).nations["AAA"]
    before = {s: construction.build_time(cfg, n, s) for s in ("grid", "onshore_wind", "storage")}
    n.permitting = 1.0
    after = {s: construction.build_time(cfg, n, s) for s in before}
    assert all(after[s] <= before[s] for s in before)
    assert after["grid"] < before["grid"] and after["onshore_wind"] < before["onshore_wind"]
    cut = {s: 1 - after[s] / before[s] for s in before}
    assert cut["grid"] > cut["storage"]
    assert min(after.values()) >= 1


def test_orders_placed_under_reform_arrive_sooner(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    construction.queue(cfg, n, "onshore_wind", 1.0, w.t)
    slow = n.pipeline[-1].complete_turn
    n.permitting = 1.0
    construction.queue(cfg, n, "onshore_wind", 1.0, w.t)
    assert n.pipeline[-1].complete_turn < slow
    assert construction.horizon_quarters(cfg, "AAA", n) <= construction.horizon_quarters(cfg, "AAA")


def test_raising_reform_costs_political_capital_and_lowering_is_free(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.slots_banked = {"domestic": 6, "diplomatic": 4}
    n.political_capital = 100.0
    [up] = actions.resolve(cfg, w, "AAA", [{"type": "set_permitting", "level": 0.5}])
    assert up["ok"] and up["cost"]["political_capital"] == pytest.approx(
        0.5 * cfg.tune("permitting.pc_per_level")
    )
    [down] = actions.resolve(cfg, w, "AAA", [{"type": "set_permitting", "level": 0.0}])
    assert down["ok"] and not down["cost"].get("political_capital")
    assert n.permitting == 0.0


def test_opposition_order_set_with_the_user():
    cfg = config.load()
    opp = {nid: economy.permitting_opposition(cfg, nid) for nid in ("EUU", "USA", "CHN", "RUS")}
    assert opp["EUU"] > opp["USA"] > opp["CHN"] > opp["RUS"]
    assert economy.permitting_opposition(cfg, "IND") == economy.permitting_opposition(cfg, "VNM")
    assert economy.permitting_opposition(cfg, "IND") < opp["CHN"]


def test_reform_costs_votes_and_approval_and_more_with_more_opposition(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=2)
    w.player = "AAA"
    elections.start_term(w)
    assert elections.local_opposition_now(cfg, w) == 0.0
    w.nations["AAA"].permitting = 1.0
    w.nations["AAA"].build_rate = 0.1 * w.nations["AAA"].demand
    for _ in range(4):
        elections.track(cfg, w)
    assert elections.vote(cfg, w)["local_opposition"] == pytest.approx(
        -cfg.tune("permitting.vote_weight") * 0.1 * economy.permitting_opposition(cfg, "AAA")
    )
    calm = turn.step(w, cfg)
    w.nations["AAA"].permitting = 0.0
    quiet = turn.step(w, cfg)
    assert calm.nations["AAA"].approval < quiet.nations["AAA"].approval
