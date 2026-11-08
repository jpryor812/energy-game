"""Short-lived warming, carbon removal, forests, the responsive rest of world (M4b part 2)."""

import copy

import pytest

from sim import actions, bots, climate, config, economy, tech, turn
from sim.scenario import new_world


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 50, "diplomatic": 50}
        n.capital = 5.0
    return w


def run(cfg, w, turns):
    for _ in range(turns):
        w = turn.step(w, cfg)
    return w


def test_methane_abatement_cools_within_years(cfg, world):
    plain = run(cfg, copy.deepcopy(world), 20)
    actions.resolve(cfg, world, "AAA", [{"type": "methane_abatement", "amount": 1.0}])
    actions.resolve(cfg, world, "BBB", [{"type": "methane_abatement", "amount": 1.0}])
    abated = run(cfg, world, 20)
    assert abated.methane_index < plain.methane_index
    assert abated.warming < plain.warming


def test_less_coal_unmasks_aerosol_warming(cfg, world):
    index = climate.aerosol_index(cfg, world)
    world.nations["AAA"].supply["coal"] *= 0.5
    assert climate.aerosol_index(cfg, world) < index
    assert climate.warming_from(cfg, 0.0, aerosol=0.5) > climate.warming_from(cfg, 0.0)


def test_carbon_removal_goes_net_negative(cfg, world):
    n = world.nations["AAA"]
    [r] = actions.resolve(cfg, world, "AAA", [{"type": "build_removal", "amount": 10.0}])
    assert r["ok"] and n.pipeline[-1].source == "carbon_removal"
    n.capacity["carbon_removal"] = 1e4  # far more than AAA emits
    w = run(cfg, world, 2)
    aaa = w.nations["AAA"]
    removal = aaa.capacity["carbon_removal"]  # retires slowly, like any plant
    assert aaa.emissions < 0 and aaa.removals == pytest.approx(removal)
    assert aaa.extra_demand == pytest.approx(removal * cfg.src("carbon_removal", "energy_use"))
    assert economy.carbon_revenue(aaa) >= 0  # charged on CO2 emitted, not on removals


def test_net_negative_world_cools(cfg, world):
    for n in world.nations.values():
        n.capacity["carbon_removal"] = 2e5
    w = run(cfg, world, 8)
    assert w.global_emissions < 0
    assert (
        w.history[-1]["global_cumulative_emissions"] < w.history[0]["global_cumulative_emissions"]
    )


def test_removal_cost_has_a_floor(cfg, world):
    world.tech_state["carbon_removal"] = 1e9
    floor = cfg.techs["sources"]["carbon_removal"]["cost_floor"]["value"]
    assert tech.unit_cost(cfg, world, "carbon_removal") == pytest.approx(
        floor * cfg.src("carbon_removal", "capital_cost")
    )


def test_forest_fund_can_turn_land_into_a_sink(cfg, world):
    land = climate.exogenous_co2(cfg, world)["land_use"]
    [r] = actions.resolve(cfg, world, "AAA", [{"type": "fund_forests", "amount": 2.0}])
    assert r["ok"] and world.forest_fund == 2.0
    assert climate.exogenous_co2(cfg, world)["land_use"] < land
    world.forest_fund = 1e6
    assert climate.exogenous_co2(cfg, world)["land_use"] < 0
    w = run(cfg, world, 1)
    assert w.nations["AAA"].climate_credit["financed"] > 0


def test_rest_of_world_follows_the_16(cfg, world):
    row = climate.exogenous_co2(cfg, world)["rest_of_world"]
    for n in world.nations.values():
        n.emissions *= 0.5
    assert climate.exogenous_co2(cfg, world)["rest_of_world"] == pytest.approx(row * 0.5)


# --- the headline: colder than 2025 is reachable, but only with an all-out world ---------------


def all_out(cfg, w, nid):
    """Every nation, every quarter: tax to the maximum, build the cheapest clean source, abate
    methane, electrify, raise the carbon price, fund forests, and build carbon removal from 2032."""
    n = w.nations[nid]
    clean = bots.cheapest_clean(cfg, w, n)
    acts = [
        {
            "type": "build_capacity",
            "source": clean,
            "amount": 0.3 * n.capital / tech.nation_unit_cost(cfg, w, n, clean),
        }
    ]
    q = w.t % 4
    if w.t >= 30:
        unit = tech.nation_unit_cost(cfg, w, n, "carbon_removal")
        acts.append({"type": "build_removal", "amount": 0.4 * n.capital / unit})
    elif w.t == 0:
        acts.append({"type": "set_tax_rate", "level": cfg.tune("tax.max_change")})
    elif q == 0:
        acts.append({"type": "methane_abatement", "amount": 0.2 * n.capital})
    elif q == 1:
        acts.append({"type": "set_carbon_price", "level": min(300, n.carbon_price + 30)})
    elif q == 2:
        acts.append({"type": "electrification_program", "amount": 0.2 * n.capital})
    else:
        acts.append({"type": "invest_efficiency", "amount": 0.1 * n.capital})
    acts.append({"type": "fund_forests", "amount": 0.05 * n.capital})
    return [a for a in acts if a.get("amount", 1) > 0]


def test_all_out_world_ends_colder_than_2025():
    real = config.load()
    w = new_world(real, seed=1)
    while w.t < real.tune("time.turns"):
        w = turn.step(w, real, actions={nid: all_out(real, w, nid) for nid in w.nations}, ai=False)
    assert w.warming < real.tune("climate.warming_start")
