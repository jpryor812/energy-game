import json

import pytest

from sim.scenario import new_world
from sim.state import Construction, Deal, Pledge, World


@pytest.fixture
def world(cfg) -> World:
    w = new_world(cfg, seed=7)
    ind = w.nations["AAA"]
    ind.gdp = 1.25
    ind.pipeline.append(Construction(source="solar", amount=3.0, complete_turn=6))
    ind.pledge = Pledge(target_emissions=0.5, year=2070, made_turn=0)
    ind.tariffs["BBB"] = 0.1
    w.deals["d1"] = Deal(
        id="d1",
        type="climate_loan",
        financier="BBB",
        host="AAA",
        terms={"currency": "hard", "duration": 20},
        status="active",
        start_turn=0,
    )
    w.trust = {"AAA": {"BBB": 0.5}}
    w.blocs = {"carbon_club": ["BBB"]}
    w.history.append({"t": 0, "note": "x"})
    return w


def test_new_world_has_all_nations(cfg):
    w = new_world(cfg, seed=1)
    assert sorted(w.nations) == cfg.nation_ids
    assert w.nations["AAA"].playable and not w.nations["BBB"].playable
    assert set(w.nations["AAA"].capacity) == set(cfg.source_ids)


def test_round_trip_dict(world):
    assert World.from_dict(world.to_dict()) == world


def test_round_trip_json(world):
    text = world.to_json()
    again = World.from_json(text)
    assert again == world
    assert again.to_json() == text
    assert again.hash() == world.hash()


def test_hash_changes_with_state(world):
    before = world.hash()
    world.nations["AAA"].gdp += 0.01
    assert world.hash() != before


def test_rejects_nan(world):
    world.warming = float("nan")
    with pytest.raises(ValueError):
        world.to_json()


def test_rejects_unknown_version(world):
    d = json.loads(world.to_json())
    d["version"] = 999
    with pytest.raises(ValueError, match="version"):
        World.from_dict(d)
