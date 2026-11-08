"""Unit and property tests for the M1 world model, on the synthetic fixture data."""

import copy
import math

import pytest

from sim import climate, construction, energy, runner, tech, turn
from sim.scenario import new_world


@pytest.fixture
def world(cfg):
    return new_world(cfg, seed=1)


@pytest.fixture(scope="module")
def bau_run(cfg):
    w = new_world(cfg, seed=1)
    worlds = [w]
    for _ in range(cfg.tune("time.turns")):
        w = turn.step(w, cfg)
        worlds.append(w)
    return worlds


# --- t=0 calibration -----------------------------------------------------------------------------


def test_t0_dispatch_reproduces_data(cfg, world):
    n = world.nations["AAA"]
    for s in cfg.energy_source_ids:
        assert n.supply[s] == pytest.approx(cfg.nat("AAA", f"start.energy.{s}"))
    assert n.demand == pytest.approx(sum(n.supply.values()))


def test_t0_trade_matches_production(cfg, world):
    bbb = world.nations["BBB"]
    assert bbb.fossil_exports["oil"] == pytest.approx(15.0 - 6.0)
    aaa = world.nations["AAA"]
    assert aaa.fossil_imports["oil"] == pytest.approx(8.0 - 1.0)
    assert aaa.fossil_exports["coal"] == 0.0


# --- dispatch ------------------------------------------------------------------------------------


def test_excess_cuts_most_expensive_first(cfg, world):
    n = world.nations["AAA"]
    total = energy.base_demand(n)
    d = energy.dispatch(cfg, n, total * 0.9)
    normal_oil = n.capacity["oil"] / cfg.src("oil", "headroom")
    assert d.supply["oil"] < normal_oil  # oil is the most expensive
    assert d.supply["coal"] == pytest.approx(n.capacity["coal"] / cfg.src("coal", "headroom"))
    assert d.shortfall == 0


def test_carbon_price_changes_merit_order(cfg, world):
    n = world.nations["AAA"]
    demand = energy.base_demand(n) * 0.64  # excess larger than oil's whole output
    coal_normal = n.capacity["coal"] / cfg.src("coal", "headroom")
    assert energy.dispatch(cfg, n, demand).supply["coal"] == pytest.approx(coal_normal)
    n.carbon_price = 200.0  # coal now dearer than gas, so it is cut after oil
    assert energy.dispatch(cfg, n, demand).supply["coal"] < coal_normal


def test_shortfall_when_capacity_missing(cfg, world):
    n = world.nations["AAA"]
    n.capacity["coal"] = 0.0
    d = energy.dispatch(cfg, n, energy.base_demand(n))
    assert d.shortfall > 0
    assert sum(d.supply.values()) + d.shortfall == pytest.approx(d.demand)


def test_curtailment_beyond_absorb_limit(cfg, world):
    n = world.nations["AAA"]
    n.capacity["solar"] = 50.0
    d = energy.dispatch(cfg, n, energy.base_demand(n))
    assert d.curtailment > 0
    limit = energy.vre_absorb_limit(cfg, n, d.demand)
    assert d.supply["solar"] + d.supply["wind"] == pytest.approx(limit)


def test_season_factor_averages_to_one_over_a_year(cfg):
    assert energy.season_factor(cfg, 0, 4) == pytest.approx(1.0)


# --- construction --------------------------------------------------------------------------------


def test_retirement_rate_and_override(cfg, world):
    assert construction.retire_rate(cfg, "AAA", "coal") == pytest.approx(1 / 40)
    assert construction.retire_rate(cfg, "AAA", "oil") == pytest.approx(0.05)
    n = world.nations["AAA"]
    before = n.capacity["coal"]
    construction.retire(cfg, "AAA", n, dt=4)
    assert n.capacity["coal"] == pytest.approx(before * (1 - 1 / 40))


def test_completion_on_schedule(cfg, world):
    n = world.nations["AAA"]
    n.pipeline = []
    construction.queue(cfg, n, "solar", 1.0, t=0)
    assert n.pipeline[0].complete_turn == 4
    assert construction.complete(n, 3) == {}
    before = n.capacity["solar"]
    assert construction.complete(n, 4) == {"solar": 1.0}
    assert n.capacity["solar"] == pytest.approx(before + 1.0)


def test_market_mix_sums_to_one_and_respects_candidates(cfg, world):
    n = world.nations["AAA"]
    mix = construction.market_mix(cfg, world, "AAA", n)
    assert sum(mix.values()) == pytest.approx(1.0)
    assert set(mix) == set(construction.market_sources(cfg, "AAA"))
    assert "nuclear" not in mix  # policy-driven, and not in AAA's trend mix


def test_carbon_price_shifts_market_away_from_coal(cfg, world):
    n = world.nations["AAA"]
    before = construction.market_mix(cfg, world, "AAA", n)["coal"]
    n.carbon_price = 150.0
    assert construction.market_mix(cfg, world, "AAA", n)["coal"] < before


def test_subsidy_shifts_market_and_costs_capital(cfg, world):
    n = world.nations["AAA"]
    before = construction.market_mix(cfg, world, "AAA", n)["gas"]
    n.subsidies["gas"] = 0.9
    assert construction.market_mix(cfg, world, "AAA", n)["gas"] > before
    n.capital = 100.0
    n.energy_intensity *= 1.5  # force a large gap so the market orders now
    construction.market_build(cfg, world, "AAA", n)
    assert n.capital < 100.0


def test_market_orders_arrive_together(cfg, world):
    n = world.nations["AAA"]
    n.pipeline = []
    n.energy_intensity *= 1.2
    construction.market_build(cfg, world, "AAA", n)
    due = {c.complete_turn for c in n.pipeline}
    assert due == {construction.horizon_quarters(cfg, "AAA")}


# --- climate and tech ----------------------------------------------------------------------------


def test_warming_and_damage(cfg):
    start = cfg.tune("climate.warming_start")
    assert climate.warming_from(cfg, 0.0) == start
    expected = start + 0.45 * (1 + cfg.tune("climate.nonco2_multiplier"))
    assert climate.warming_from(cfg, 1e6) == pytest.approx(expected)
    assert climate.damage(cfg, 1.0, start) == 0.0
    assert climate.damage(cfg, 2.0, start + 1) == pytest.approx(
        2 * cfg.tune("climate.damage_coefficient")
    )


def test_learning_curve_doubling(cfg, world):
    n0 = cfg.src("solar", "global_installed")
    world.tech_state["solar"] = 2 * n0
    c0 = cfg.src("solar", "capital_cost")
    lr = cfg.src("solar", "learning_rate")
    assert tech.unit_cost(cfg, world, "solar") == pytest.approx(c0 * (1 - lr))


def test_deployment_scaled_by_coverage(cfg, world):
    before = world.tech_state["solar"]
    tech.apply(world, cfg, {"solar": 1.0})
    assert world.tech_state["solar"] == pytest.approx(
        before + 1.0 / cfg.src("solar", "coverage_share")
    )


# --- whole-run properties ------------------------------------------------------------------------


def test_energy_balance_every_turn(bau_run):
    for w in bau_run[1:]:
        for n in w.nations.values():
            assert sum(n.supply.values()) + n.shortfall == pytest.approx(n.demand, rel=1e-9)


def test_kaya_identity(cfg, bau_run):
    for w in bau_run[1:]:
        for n in w.nations.values():
            energy_used = sum(n.supply.values())
            direct = sum(n.supply[s] * energy.emission_factor(cfg, n.id, s) for s in n.supply)
            kaya = n.population * (n.gdp / n.population) * (energy_used / n.gdp)
            kaya *= direct / energy_used
            assert n.emissions == pytest.approx(kaya)


def test_sanity_no_nan_or_negative(bau_run):
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")
        elif isinstance(x, float):
            assert math.isfinite(x), path
            if not path.endswith((".growth", ".capital", "trade_balance")):
                assert x >= -1e-9, path

    walk(bau_run[-1].to_dict(), "world")


def test_warming_never_falls_while_emitting(bau_run):
    temps = [w.warming for w in bau_run]
    assert all(b >= a for a, b in zip(temps, temps[1:], strict=False))


def test_bau_keeps_lights_on(bau_run):
    for w in bau_run[1:]:
        for n in w.nations.values():
            assert n.shortfall / n.demand < 0.02


def test_falling_world_demand_cuts_exporter_revenue(cfg, world):
    w = copy.deepcopy(world)
    for n in w.nations.values():
        n.carbon_price = 0.0
        n.energy_intensity *= 0.7
    w2 = turn.step(w, cfg)
    assert w2.nations["BBB"].export_revenue < world.nations["BBB"].export_revenue


def test_resume_matches_full_run(cfg):
    full = runner.play(cfg, 5, "AAA", "noop")
    half = runner.play(cfg, 5, "AAA", "noop", until=50)
    from sim.state import World

    resumed = runner.play(cfg, 5, "AAA", "noop", world=World.from_json(half.to_json()))
    assert resumed.hash() == full.hash()
