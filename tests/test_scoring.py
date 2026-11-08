"""Nation Index, World Multiplier, bonuses, endings, Fallen Government. Fixture data."""

import pytest

from sim import report, runner, scoring
from sim.scenario import new_world


@pytest.fixture(scope="module")
def noop_world(cfg):
    return runner.play(report.without_shocks(cfg), 1, "AAA", "noop")


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
    ("rank", "warming", "loss", "expected"),
    [
        (1, 1.5, None, scoring.CHAMPION),
        (1, 1.6, None, scoring.CHAMPION),
        (1, 1.65, None, scoring.PROSPEROUS_BUT_DOOMED),
        (1, 3.0, None, scoring.PROSPEROUS_BUT_DOOMED),
        (16, 1.5, None, scoring.GREEN_BUT_POOR),
        (16, 3.0, None, scoring.SHARED_FAILURE),
        (1, 1.5, scoring.FALLEN_GOVERNMENT, scoring.FALLEN_GOVERNMENT),
        (1, 1.5, scoring.VOTED_OUT, scoring.VOTED_OUT),
    ],
)
def test_endings(cfg, rank, warming, loss, expected):
    assert scoring.ending(cfg, rank, warming, loss) == expected


def test_good_world_needs_warming_to_be_falling(cfg):
    assert scoring.ending(cfg, 1, 1.55, None, falling=False) == scoring.PROSPEROUS_BUT_DOOMED
    assert scoring.ending(cfg, 16, 1.55, None, falling=False) == scoring.SHARED_FAILURE
    assert scoring.ending(cfg, 1, 1.55, None, falling=None) == scoring.CHAMPION


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
    w.nations["AAA"].factory_capacity["solar"] = 1.0  # a big share of world clean-tech making
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
    mult = result["difficulty_multiplier"]
    combined = 0.5 * result["absolute_index"] + 0.5 * result["nation_index"] * mult
    assert result["combined_index"] == pytest.approx(combined)
    bonus = sum(
        v * (mult if k in scoring.RELATIVE_BONUSES else 1) for k, v in result["bonuses"].items()
    )
    assert result["score"] == pytest.approx(combined * result["world_multiplier"] + bonus)
    assert sorted(r["rank"] for r in result["all_nations"].values()) == [1, 2]


def test_fallen_government_stops_the_run(cfg):
    w = new_world(cfg, seed=1)
    w = runner.play(cfg, 1, "AAA", "noop", world=w, until=8)
    w.nations["AAA"].stability = 0.05  # e.g. after a run of blackouts
    w = runner.play(cfg, 1, "AAA", "noop", world=w)
    assert w.t == 8
    summary = runner.summarize(cfg, w, "AAA", "noop", 1)
    assert summary["ending"] == scoring.FALLEN_GOVERNMENT
