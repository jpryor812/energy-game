"""Each action: cost, slot use, validation, effect. Fixture data."""

import math

import pytest

from sim import actions, climate, energy, tech, turn
from sim.scenario import new_world


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.slots_banked = {"domestic": 10, "diplomatic": 10}
    n.capital = 10.0
    n.political_capital = 100.0
    return w


def run(cfg, world, *acts):
    return actions.resolve(cfg, world, "AAA", list(acts))


def test_build_capacity(cfg, world):
    n = world.nations["AAA"]
    unit = tech.nation_unit_cost(cfg, world, n, "solar")
    [r] = run(cfg, world, {"type": "build_capacity", "source": "solar", "amount": 2.0})
    assert r["ok"]
    assert n.capital == pytest.approx(10.0 - 2.0 * unit)
    assert n.slots_banked["domestic"] == 9
    item = n.pipeline[-1]
    assert (item.source, item.amount) == ("solar", 2.0)
    assert item.complete_turn == world.t + cfg.src("solar", "build_time")


def test_rejections_change_nothing(cfg, world):
    n = world.nations["AAA"]
    before = (n.capital, n.political_capital, dict(n.slots_banked), len(n.pipeline))
    bad = [
        {"type": "build_capacity", "source": "solar", "amount": 1e9},  # unaffordable
        {"type": "build_capacity", "source": "unobtainium", "amount": 1.0},
        {"type": "build_capacity", "source": "solar", "amount": -1.0},
        {"type": "build_capacity", "source": "solar", "amount": math.nan},
        {"type": "build_capacity", "source": "solar", "amount": True},
        {"type": "set_carbon_price", "level": 1e6},
        {"type": "teleport"},
        {"source": "solar"},
    ]
    results = run(cfg, world, *bad)
    assert not any(r["ok"] for r in results)
    assert all(r["reason"] for r in results)
    assert (n.capital, n.political_capital, dict(n.slots_banked), len(n.pipeline)) == before


def test_slots_run_out(cfg, world):
    n = world.nations["AAA"]
    n.slots_banked["domestic"] = 1
    results = run(cfg, world, {"type": "rebate", "share": 0.2}, {"type": "rebate", "share": 0.3})
    assert [r["ok"] for r in results] == [True, False]
    assert n.rebate == 0.2


def test_retire_capacity(cfg, world):
    n = world.nations["AAA"]
    coal, approval = n.capacity["coal"], n.approval
    [r] = run(cfg, world, {"type": "retire_capacity", "source": "coal", "amount": 1.0})
    assert r["ok"]
    assert n.capacity["coal"] == pytest.approx(coal - 1.0)
    expected_pc = cfg.tune("actions.retire_pc_per_ej") * cfg.tune("actions.retire_coal_multiplier")
    assert n.political_capital == pytest.approx(100.0 - expected_pc)
    assert n.pending_writeoff > 0
    assert n.approval < approval
    [r] = run(cfg, world, {"type": "retire_capacity", "source": "coal", "amount": 1e6})
    assert not r["ok"]


def test_writeoff_drags_growth_once(cfg, world):
    run(cfg, world, {"type": "retire_capacity", "source": "gas", "amount": 0.5})
    w1 = turn.step(world, cfg)
    assert w1.nations["AAA"].pending_writeoff == 0.0
    base = turn.step(new_world(cfg, seed=1), cfg)
    assert w1.nations["AAA"].growth < base.nations["AAA"].growth


def test_carbon_price_costs_only_increases(cfg, world):
    n = world.nations["AAA"]
    run(cfg, world, {"type": "set_carbon_price", "level": 50.0})
    assert n.carbon_price == 50.0
    assert n.political_capital == pytest.approx(
        100.0 - 50 * cfg.tune("actions.carbon_pc_per_dollar")
    )
    pc = n.political_capital
    run(cfg, world, {"type": "set_carbon_price", "level": 10.0})
    assert n.political_capital == pc


def test_carbon_revenue_and_rebate(cfg, world):
    run(cfg, world, {"type": "set_carbon_price", "level": 100.0})
    full = turn.step(world, cfg).nations["AAA"].carbon_revenue
    run(cfg, world, {"type": "rebate", "share": 0.5})
    half = turn.step(world, cfg).nations["AAA"].carbon_revenue
    assert full > 0
    assert half == pytest.approx(full / 2, rel=0.05)


def test_subsidy_and_research(cfg, world):
    n = world.nations["AAA"]
    cost_before = tech.nation_unit_cost(cfg, world, n, "solar")
    run(
        cfg,
        world,
        {"type": "set_subsidy", "source": "solar", "share": 0.4},
        {"type": "invest_research", "tech": "solar", "amount": 0.1},
    )
    assert n.subsidies["solar"] == 0.4
    assert n.research["solar"] == pytest.approx(0.1)
    assert n.tech_points > 0
    assert tech.nation_unit_cost(cfg, world, n, "solar") < cost_before
    [r] = run(cfg, world, {"type": "set_subsidy", "source": "solar", "share": 0.99})
    assert not r["ok"]


def test_efficiency_has_diminishing_returns(cfg, world):
    n = world.nations["AAA"]
    i0 = n.energy_intensity
    run(cfg, world, {"type": "invest_efficiency", "amount": 0.05})
    small = 1 - n.energy_intensity / i0
    n.energy_intensity = i0
    run(cfg, world, {"type": "invest_efficiency", "amount": 0.10})
    big = 1 - n.energy_intensity / i0
    assert 0 < small < big < 2 * small


def test_influence_grid_adaptation(cfg, world):
    n = world.nations["AAA"]
    run(
        cfg,
        world,
        {"type": "buy_influence", "amount": 0.1},
        {"type": "build_grid_storage", "kind": "storage", "amount": 0.5},
        {"type": "adaptation_spend", "amount": 0.2},
    )
    assert n.influence == pytest.approx(0.1 * cfg.tune("actions.influence_per_trillion"))
    assert n.pipeline[-1].source == "storage"
    assert climate.adaptation_factor(cfg, n) < 1.0


def test_activity_cap_cuts_demand_more_than_gdp(cfg, world):
    n = world.nations["AAA"]
    gdp, demand = n.gdp, energy.base_demand(n)
    run(cfg, world, {"type": "set_activity_cap", "level": 0.1})
    k = cfg.tune("actions.activity_gdp_ratio")
    assert n.gdp == pytest.approx(gdp * (1 - k * 0.1))
    assert energy.base_demand(n) == pytest.approx(demand * 0.9)
    run(cfg, world, {"type": "set_activity_cap", "level": 0.0})
    assert n.gdp == pytest.approx(gdp)
    assert energy.base_demand(n) == pytest.approx(demand)


def test_pledge_uses_diplomatic_slot(cfg, world):
    n = world.nations["AAA"]
    [r] = run(cfg, world, {"type": "make_pledge", "target": 0.5, "year": 2050})
    assert r["ok"]
    assert n.slots_banked == {"domestic": 10, "diplomatic": 9}
    assert n.pledge.target_emissions == pytest.approx(0.5 * n.base["emissions"])
    assert n.pledge.year == 2050


def test_capital_moves_only_by_income_and_spending(cfg, world):
    """Same world with and without a build: capital differs by exactly the build cost."""
    plain = turn.step(world, cfg)
    act = {"type": "build_capacity", "source": "wind", "amount": 1.0}
    cost = actions.cost(cfg, world, world.nations["AAA"], act)["capital"]
    built = turn.step(world, cfg, actions={"AAA": [act]})
    assert plain.nations["AAA"].capital - built.nations["AAA"].capital == pytest.approx(cost)


def test_slots_bank_each_quarter_up_to_a_cap(cfg):
    w = new_world(cfg, seed=1)
    for _ in range(3):
        w = turn.step(w, cfg)
    banked = {
        k: min(3 * cfg.tune(f"slots.{k}_per_quarter"), cfg.tune(f"slots.{k}_bank_cap"))
        for k in ("domestic", "diplomatic")
    }
    assert w.nations["AAA"].slots_banked == banked
    for _ in range(10):
        w = turn.step(w, cfg)
    caps = {k: cfg.tune(f"slots.{k}_bank_cap") for k in ("domestic", "diplomatic")}
    assert w.nations["AAA"].slots_banked == caps
