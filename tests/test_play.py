"""M7 text interface: sessions, saves, the game screen, the action catalogue and the CLI."""

import copy
import dataclasses
import json
import math

import pytest

from sim import actions, bots, catalogue, play, runner, view
from sim.session import Game, SaveError


def test_session_driven_by_a_bot_matches_runner(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    while game.world.t < 20 and not game.over:
        game.turn(bots.balanced(cfg, game.world, "AAA"))
    assert game.world.hash() == runner.play(cfg, 1, "AAA", "balanced", until=20).hash()


def test_save_load_and_replay_round_trip(cfg, tmp_path):
    game = Game.new(cfg, "AAA", seed=3)
    game.turn([{"type": "set_carbon_price", "level": 10}])
    game.wait(5)
    game.save(tmp_path / "g")
    loaded = Game.load(cfg, tmp_path / "g")
    assert loaded.world.hash() == game.world.hash()
    assert loaded.replay().hash() == game.world.hash()
    assert len(loaded.moves) == 6


def test_load_refuses_a_save_from_different_data(cfg, tmp_path):
    game = Game.new(cfg, "AAA", seed=1)
    game.save(tmp_path / "g")
    meta = json.loads((tmp_path / "g" / "game.json").read_text())
    meta["config_hash"] = "0" * 64
    (tmp_path / "g" / "game.json").write_text(json.dumps(meta))
    with pytest.raises(SaveError):
        Game.load(cfg, tmp_path / "g")


def test_check_matches_the_turn_and_changes_nothing(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    acts = [{"type": "set_carbon_price", "level": 5}, {"type": "set_carbon_price", "level": 1e9}]
    before = game.world.hash()
    checked = game.check(acts)
    assert game.world.hash() == before
    played = game.turn(acts)["results"]
    assert [r["ok"] for r in checked] == [r["ok"] for r in played] == [True, False]


def test_every_action_has_a_catalogue_entry_with_a_valid_example(cfg):
    cat = catalogue.catalogue(cfg)
    assert set(cat) == set(actions.SPECS)
    for name, entry in cat.items():
        assert entry["example"]["type"] == name
        assert entry["slot"] == actions.SPECS[name].slot
        assert entry["summary"] and entry["params"] is not None and entry["cost"]


def _finite(x):
    if isinstance(x, dict):
        return all(_finite(v) for v in x.values())
    if isinstance(x, list):
        return all(_finite(v) for v in x)
    return not isinstance(x, float) or math.isfinite(x)


def test_view_is_finite_and_hides_the_swing(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    assert _finite(view.observe(game)) and view.render(view.observe(game))
    game.wait(8)
    obs = view.observe(game)
    assert _finite(obs)
    assert obs["election"]["expected_vote"] is not None
    assert "swing" not in obs["election"]["parts"]
    assert "personality" not in json.dumps(obs)
    assert "SCORE now" in view.render(obs)


def test_a_lost_election_ends_the_session(cfg):
    harsh = copy.deepcopy(cfg.tuning)
    harsh["elections"]["incumbency"]["value"] = 0.0
    hcfg = dataclasses.replace(cfg, tuning=harsh)
    game = Game.new(hcfg, "AAA", seed=1)
    game.wait(40)
    assert game.over and game.lost == "Voted Out" and game.world.t == 16
    assert "GAME OVER: Voted Out" in view.render(view.observe(game))
    with pytest.raises(RuntimeError):
        game.turn([])


def test_cli_plays_a_game(fixture_dir, tmp_path, capsys):
    save = str(tmp_path / "g")
    base = ["--data-dir", str(fixture_dir)]
    assert play.main([*base, "new", "--country", "AAA", "--save", save]) == 0
    assert play.main([*base, "new", "--country", "AAA", "--save", save]) == 1  # no overwrite
    assert play.main([*base, "turn", save, '[{"type": "set_carbon_price", "level": 5}]']) == 0
    assert "ok        set_carbon_price" in capsys.readouterr().out
    assert play.main([*base, "check", save, '[{"type": "nope"}]']) == 0
    assert "REJECTED" in capsys.readouterr().out
    assert play.main([*base, "wait", save, "3"]) == 0
    capsys.readouterr()
    assert play.main([*base, "show", save, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["turn"] == 4
    assert play.main([*base, "turn", save, "not json"]) == 1
    assert play.main([*base, "actions"]) == 0
    assert "propose_deal" in capsys.readouterr().out
