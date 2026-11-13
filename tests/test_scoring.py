"""Impact, prosperity, endings, honours, Climate Collapse, Fallen Government. Fixture data."""

import pytest

from sim import report, runner, scoring
from sim.scenario import new_world


@pytest.fixture(scope="module")
def noop_world(cfg):
    return runner.play(report.without_shocks(cfg), 1, "AAA", "noop")


@pytest.mark.parametrize(
    ("rank", "loss", "expected"),
    [
        (1, None, scoring.CHAMPION),
        (2, None, scoring.SHARED_VICTORY),
        (16, None, scoring.SHARED_VICTORY),
        (1, scoring.CLIMATE_COLLAPSE, scoring.CLIMATE_COLLAPSE),
        (1, scoring.FALLEN_GOVERNMENT, scoring.FALLEN_GOVERNMENT),
        (1, scoring.VOTED_OUT, scoring.VOTED_OUT),
    ],
)
def test_endings(cfg, rank, loss, expected):
    """Only first place is Champion (no top-four rule since 2026-11-12)."""
    assert scoring.ending(cfg, rank, loss) == expected


def test_climate_collapse_ends_the_game_for_everyone(cfg):
    line = cfg.tune("scoring.collapse_warming")
    w = runner.play(cfg, 1, "AAA", "noop", until=8)
    assert scoring.loss(cfg, w, "AAA") is None
    for h in w.history[-4:]:
        h["warming"] = line - 0.001
    assert scoring.loss(cfg, w, "AAA") is None
    w.history[-1]["warming"] = line + 0.002  # one hot quarter is not enough
    assert scoring.loss(cfg, w, "AAA") is None
    for h in w.history[-4:]:
        h["warming"] = line
    for nid in w.nations:
        assert scoring.loss(cfg, w, nid) == scoring.CLIMATE_COLLAPSE
    w = runner.play(cfg, 1, "AAA", "noop", world=w)  # the runner stops at once
    assert w.t == 8
    summary = runner.summarize(cfg, w, "AAA", "noop", 1)
    assert summary["ending"] == scoring.CLIMATE_COLLAPSE
    assert summary["score"] == cfg.tune("scoring.loss_score")


def test_collapse_is_checked_every_quarter(cfg):
    """Warming crossing the line mid-game ends it, even if it would fall back later."""
    from sim import climate

    real = climate.warming_from
    line = cfg.tune("scoring.collapse_warming")
    try:
        climate.warming_from = lambda *a, **k: line + 0.01
        w = runner.play(cfg, 1, "AAA", "noop", until=6)
    finally:
        climate.warming_from = real
    assert w.t == 1
    assert scoring.loss(cfg, w, "AAA") == scoring.CLIMATE_COLLAPSE


def test_components_in_range_and_index_bounded(cfg, noop_world):
    for nid in noop_world.nations:
        comps = scoring.components(cfg, noop_world, nid)
        assert set(comps) == {"income", "security", "welfare", "clean"}
        assert all(0.0 <= v <= 1.0 for v in comps.values())
        assert 0.0 <= scoring.prosperity_index(cfg, comps) <= 100.0
        assert 0.0 <= scoring.impact(cfg, noop_world, nid) <= 100.0


def test_income_component_is_relative_to_baseline(cfg, noop_world):
    """Doing nothing keeps income near the baseline path, so near 0.5."""
    assert scoring.components(cfg, noop_world, "AAA")["income"] == pytest.approx(0.5, abs=0.15)


def test_components_move_the_right_way(cfg, noop_world):
    import copy

    w = copy.deepcopy(noop_world)
    base = scoring.components(cfg, w, "AAA")
    w.nations["AAA"].gdp *= 1.2
    w.nations["AAA"].energy_price *= 0.5
    for h in w.history[-4:]:  # M9: the clean component reads a year of equipment sales
        h["nations"]["AAA"]["factory_sales"] = {"solar": 1.0}
        h["nations"]["AAA"]["equipment_demand"] = {"solar": 1.0}
    better = scoring.components(cfg, w, "AAA")
    assert better["income"] > base["income"]
    assert better["welfare"] > base["welfare"]
    assert better["clean"] > base["clean"]
    for h in w.history:
        h["nations"]["AAA"]["shortfall"] = 0.1 * h["nations"]["AAA"]["demand"]
    assert scoring.components(cfg, w, "AAA")["security"] < better["security"]


def test_honours(cfg, noop_world):
    import copy

    w = copy.deepcopy(noop_world)
    for i in range(10, 14):  # net zero is judged on four-quarter averages (M9)
        w.history[i]["nations"]["BBB"]["emissions"] = 0.0
    for i in range(20, 24):
        w.history[i]["nations"]["AAA"]["emissions"] = 0.0
    for h in w.history[-4:]:  # the reduction race reads the last four quarters (M8)
        h["nations"]["BBB"]["emissions"] = 0.5 * w.nations["BBB"].base["emissions"]
        h["nations"]["AAA"]["emissions"] = 0.9 * w.nations["AAA"].base["emissions"]
    b = scoring.honours(cfg, w)
    assert "first_net_zero" in b["BBB"] and "first_net_zero" not in b["AAA"]
    assert "largest_reduction" in b["BBB"]


def test_score_is_difficulty_times_impact_and_prosperity(cfg, noop_world):
    result = scoring.score(cfg, noop_world, "AAA")
    w_i, w_p = cfg.tune("scoring.weight_impact"), cfg.tune("scoring.weight_prosperity")
    expected = (
        result["difficulty_multiplier"]
        * (w_i * result["impact"] + w_p * result["prosperity"])
        / (w_i + w_p)
    )
    assert result["score"] == pytest.approx(expected)
    assert sorted(r["rank"] for r in result["all_nations"].values()) == [1, 2]
    assert "world_multiplier" not in result and "bonuses" not in result


def test_impact_is_relative_to_own_emissions(cfg, noop_world):
    """The same share cut scores the same impact whatever the nation's size."""
    import copy

    w = copy.deepcopy(noop_world)
    for nid in ("AAA", "BBB"):
        base = w.nations[nid].base["emissions"]
        for h in w.history:
            h["nations"][nid]["emissions"] = 0.6 * base
        w.nations[nid].climate_credit = {}
        w.nations[nid].credits_bought = 0.0
    assert w.nations["AAA"].base["emissions"] != w.nations["BBB"].base["emissions"]
    assert scoring.yearly_cut(cfg, w, "AAA") == pytest.approx(0.4)
    assert scoring.impact(cfg, w, "AAA") == pytest.approx(scoring.impact(cfg, w, "BBB"))
    assert scoring.impact(cfg, w, "AAA") > 50.0


def test_impact_outweighs_prosperity(cfg, noop_world):
    """A nation that cuts more ranks above one that grew more, at the default weights."""
    import copy

    w = copy.deepcopy(noop_world)
    for h in w.history:
        h["nations"]["AAA"]["emissions"] = 0.5 * w.nations["AAA"].base["emissions"]
    cut = scoring.score(cfg, w, "AAA")
    w2 = copy.deepcopy(noop_world)
    w2.nations["AAA"].gdp *= 1.2
    grew = scoring.score(cfg, w2, "AAA")
    assert cut["impact"] > grew["impact"]
    assert grew["prosperity"] > cut["prosperity"]
    assert cut["score"] > grew["score"]


def test_fallen_government_stops_the_run(cfg):
    w = new_world(cfg, seed=1)
    w = runner.play(cfg, 1, "AAA", "noop", world=w, until=8)
    w.nations["AAA"].stability = 0.05  # e.g. after a run of blackouts
    w = runner.play(cfg, 1, "AAA", "noop", world=w)
    assert w.t == 8
    summary = runner.summarize(cfg, w, "AAA", "noop", 1)
    assert summary["ending"] == scoring.FALLEN_GOVERNMENT


def test_notices_warn_before_the_collapse_line(cfg):
    import copy

    from sim import session

    warn, line = cfg.tune("scoring.collapse_warning"), cfg.tune("scoring.collapse_warming")
    before = runner.play(cfg, 1, "AAA", "noop", until=4)
    for h in before.history[-4:]:
        h["warming"] = warn - 0.01
    after = copy.deepcopy(before)
    for h in after.history[-4:]:
        h["warming"] = warn + 0.01
    assert any(
        m.startswith("WARNING: warming passed") for m in session.notices(cfg, before, after, "AAA")
    )
    for h in after.history[-4:]:
        h["warming"] = line
    assert any(m.startswith("CLIMATE COLLAPSE") for m in session.notices(cfg, before, after, "AAA"))
