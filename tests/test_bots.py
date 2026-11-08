"""Bots play every playable nation with valid actions, deterministically."""

import pytest

from sim import actions, bots, config, runner

PLAYING_BOTS = ["all_fossil", "all_clean", "balanced", "deal_maker"]


@pytest.mark.parametrize("bot", PLAYING_BOTS)
def test_bot_full_game_on_fixture(cfg, bot):
    w = runner.play(cfg, 1, "AAA", bot)
    assert w.t == cfg.tune("time.turns")
    log = [r for h in w.history for r in h["nations"]["AAA"]["actions"]]
    assert log, "bot never acted"
    assert all(r["action"]["type"] in actions.SPECS for r in log)
    assert all(r["ok"] for r in log), [r for r in log if not r["ok"]][:3]


@pytest.mark.parametrize("bot", PLAYING_BOTS)
def test_bot_is_deterministic(cfg, bot):
    assert runner.play(cfg, 1, "AAA", bot).hash() == runner.play(cfg, 1, "AAA", bot).hash()


def test_unknown_bot(cfg):
    with pytest.raises(KeyError):
        bots.get("nope")


@pytest.fixture(scope="module")
def real_cfg():
    return config.load()


@pytest.mark.parametrize("bot", PLAYING_BOTS)
def test_bots_play_every_playable_nation(real_cfg, bot):
    """The M2 done-criterion on the real data, over the first five years to keep tests fast;
    the full 100-turn grid runs in `python -m sim.runner batch`."""
    for nid in real_cfg.playable_ids:
        w = runner.play(real_cfg, 1, nid, bot, until=20)
        summary = runner.summarize(real_cfg, w, nid, bot, 1)
        assert summary["actions_rejected"] == 0, (nid, bot)
        assert summary["ending"] and summary["score"] > 0
