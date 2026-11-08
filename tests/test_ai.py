"""AI nations: deterministic, no randomness, valid actions, personalities pull the right way."""

import copy
import dataclasses

import pytest

from sim import actions, ai, config, rng, runner, turn
from sim.scenario import new_world


def with_personalities(cfg, **assign):
    countries = copy.deepcopy(cfg.countries)
    for nid, p in assign.items():
        countries["nations"][nid]["personality"] = p
    return dataclasses.replace(cfg, countries=countries)


@pytest.fixture(scope="module")
def ai_cfg(cfg):
    return with_personalities(cfg, AAA="opportunist", BBB="fossil_defender")


def emissions_after(cfg, turns=40):
    w = new_world(cfg, seed=1)
    for _ in range(turns):
        w = turn.step(w, cfg)
    return w


def test_ai_uses_no_randomness(ai_cfg, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("AI touched sim.rng")

    monkeypatch.setattr(rng, "stream", boom)
    monkeypatch.setattr(rng, "derive_seed", boom)
    emissions_after(ai_cfg, turns=12)


def test_ai_only_world_is_deterministic(ai_cfg):
    assert emissions_after(ai_cfg).hash() == emissions_after(ai_cfg).hash()


def test_ai_actions_are_valid(ai_cfg):
    w = emissions_after(ai_cfg)
    log = [r for h in w.history for n in h["nations"].values() for r in n["actions"]]
    assert log, "AI never acted"
    assert all(r["ok"] for r in log), [r for r in log if not r["ok"]][:3]


def test_decide_respects_slots_budget_and_one_per_type(ai_cfg):
    w = new_world(ai_cfg, seed=1)
    n = w.nations["AAA"]
    n.slots_banked = {"domestic": 1, "diplomatic": 1}
    n.capital, n.political_capital = 5.0, 50.0
    chosen = ai.decide(ai_cfg, w, "AAA")
    kinds = [actions.SPECS[a["type"]].slot for a in chosen]
    assert kinds.count("domestic") <= 1 and kinds.count("diplomatic") <= 1
    assert len({a["type"] for a in chosen}) == len(chosen)
    results = actions.resolve(ai_cfg, w, "AAA", chosen)
    assert all(r["ok"] for r in results)


def test_nation_without_personality_does_nothing(cfg):
    assert ai.decide(cfg, new_world(cfg, seed=1), "AAA") == []


def test_green_leader_cuts_more_than_fossil_defender(cfg):
    green = emissions_after(with_personalities(cfg, AAA="green_leader"))
    fossil = emissions_after(with_personalities(cfg, AAA="fossil_defender"))
    assert green.nations["AAA"].emissions < fossil.nations["AAA"].emissions


def test_gap_to_target_raises_emissions_weight(ai_cfg):
    w = new_world(ai_cfg, seed=1)
    w.t = 40
    on_path = ai.emissions_weight(ai_cfg, w, "AAA", "opportunist")
    w.nations["AAA"].emissions *= 1.3
    assert ai.emissions_weight(ai_cfg, w, "AAA", "opportunist") > on_path


def test_follower_responds_to_peers(cfg):
    fcfg = with_personalities(cfg, AAA="cautious_follower")
    w = new_world(fcfg, seed=1)
    alone = ai.emissions_weight(fcfg, w, "AAA", "cautious_follower")
    w.nations["BBB"].emissions *= 0.5  # peers have cut hard
    assert ai.emissions_weight(fcfg, w, "AAA", "cautious_follower") > alone


def test_bot_player_with_ai_others_on_real_data():
    real = config.load()
    w = runner.play(real, 1, "IND", "balanced", until=12)
    others = {nid for h in w.history for nid, r in h["nations"].items() if r["actions"]}
    assert "IND" in others and len(others) == 16
    again = runner.play(real, 1, "IND", "balanced", until=12)
    assert w.hash() == again.hash()
