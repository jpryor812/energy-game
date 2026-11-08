"""Nation Index, World Multiplier, bonuses, endings, Fallen Government. Fixture data."""

import pytest

from sim import runner, scoring
from sim.scenario import new_world


@pytest.fixture(scope="module")
def noop_world(cfg):
    return runner.play(cfg, 1, "AAA", "noop")


def test_world_multiplier_shape(cfg):
    good, bad = cfg.tune("scoring.world_good"), cfg.tune("scoring.world_bad")
    floor = cfg.tune("scoring.world_floor")
    assert scoring.world_multiplier(cfg, good - 0.5) == 1.0
    assert scoring.world_multiplier(cfg, good) == 1.0
    assert scoring.world_multiplier(cfg, bad) == pytest.approx(floor)
    assert scoring.world_multiplier(cfg, bad + 1) == pytest.approx(floor)
    temps = [good + i * (bad - good) / 10 for i in range(11)]
    values = [scoring.world_multiplier(cfg, t) for t in temps]
    assert all(b < a for a, b in zip(values, values[1:], strict=False))


@pytest.mark.parametrize(
    ("rank", "warming", "fallen", "expected"),
    [
        (1, 1.5, False, scoring.CHAMPION),
        (1, 3.0, False, scoring.PROSPEROUS_BUT_DOOMED),
        (16, 1.5, False, scoring.GREEN_BUT_POOR),
        (16, 3.0, False, scoring.SHARED_FAILURE),
        (1, 1.5, True, scoring.FALLEN_GOVERNMENT),
    ],
)
def test_endings(cfg, rank, warming, fallen, expected):
    assert scoring.ending(cfg, rank, warming, fallen) == expected


def test_components_in_range_and_index_bounded(cfg, noop_world):
    for nid in noop_world.nations:
        comps = scoring.components(cfg, noop_world, nid)
        assert set(comps) == {"income", "security", "welfare", "clean", "climate"}
        assert all(0.0 <= v <= 1.0 for v in comps.values())
        assert 0.0 <= scoring.nation_index(cfg, comps) <= 100.0


def test_income_component_is_relative_to_baseline(cfg, noop_world):
    """Doing nothing keeps income near the baseline path, so near 0.5."""
    assert scoring.components(cfg, noop_world, "AAA")["income"] == pytest.approx(0.5, abs=0.15)


def test_components_move_the_right_way(cfg, noop_world):
    import copy

    w = copy.deepcopy(noop_world)
    base = scoring.components(cfg, w, "AAA")
    w.nations["AAA"].gdp *= 1.2
    w.nations["AAA"].energy_price *= 0.5
    w.nations["AAA"].clean_built += 10.0
    better = scoring.components(cfg, w, "AAA")
    assert better["income"] > base["income"]
    assert better["welfare"] > base["welfare"]
    assert better["clean"] > base["clean"]
    for h in w.history:
        h["nations"]["AAA"]["shortfall"] = 0.1 * h["nations"]["AAA"]["demand"]
    assert scoring.components(cfg, w, "AAA")["security"] < better["security"]


def test_bonuses(cfg, noop_world):
    import copy

    w = copy.deepcopy(noop_world)
    w.history[10]["nations"]["BBB"]["emissions"] = 0.0
    w.history[20]["nations"]["AAA"]["emissions"] = 0.0
    w.nations["BBB"].emissions = 0.5 * w.nations["BBB"].base["emissions"]
    w.nations["AAA"].emissions = 0.9 * w.nations["AAA"].base["emissions"]
    b = scoring.bonuses(cfg, w)
    assert "first_net_zero" in b["BBB"] and "first_net_zero" not in b["AAA"]
    assert "largest_reduction" in b["BBB"]


def test_score_combines_index_multiplier_and_bonuses(cfg, noop_world):
    result = scoring.score(cfg, noop_world, "AAA")
    expected = result["nation_index"] * result["world_multiplier"] + sum(result["bonuses"].values())
    assert result["score"] == pytest.approx(expected)
    assert sorted(r["rank"] for r in result["all_nations"].values()) == [1, 2]


def test_fallen_government_stops_the_run(cfg):
    w = new_world(cfg, seed=1)
    w = runner.play(cfg, 1, "AAA", "noop", world=w, until=8)
    w.nations["AAA"].stability = 0.05  # e.g. after a run of blackouts
    w = runner.play(cfg, 1, "AAA", "noop", world=w)
    assert w.t == 8
    summary = runner.summarize(cfg, w, "AAA", "noop", 1)
    assert summary["ending"] == scoring.FALLEN_GOVERNMENT
