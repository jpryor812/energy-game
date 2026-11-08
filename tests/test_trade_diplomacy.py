"""Trade, tariffs, trust, the carbon club and the stocktake. Fixture data."""

import copy
import dataclasses

import pytest

from sim import actions, diplomacy, tech, trade, turn
from sim.scenario import new_world


def with_spec(cfg, nid, path, value):
    countries = copy.deepcopy(cfg.countries)
    node = countries["nations"][nid]
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = {"value": value, "status": "placeholder", "note": "test"}
    return dataclasses.replace(cfg, countries=countries)


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 10, "diplomatic": 10}
        n.influence = 100.0
    return w


def act(cfg, world, nid, *acts):
    return actions.resolve(cfg, world, nid, list(acts))


# --- trade ---------------------------------------------------------------------------------------


def test_no_tariffs_no_trade_drag(cfg, world):
    trade.apply_goods(world, cfg)
    for n in world.nations.values():
        assert n.goods_exports == pytest.approx(n.base["goods_openness"] * n.gdp)
        assert n.trade_drag == pytest.approx(0.0)
        assert n.tariff_revenue == 0.0


def test_tariff_hurts_target_and_pays_imposer(cfg, world):
    act(cfg, world, "BBB", {"type": "set_tariff", "target": "AAA", "level": 0.2})
    trade.apply_goods(world, cfg)
    aaa, bbb = world.nations["AAA"], world.nations["BBB"]
    assert aaa.goods_exports < aaa.base["goods_openness"] * aaa.gdp
    assert aaa.trade_drag < 0
    assert bbb.tariff_revenue > 0
    assert bbb.trade_drag < 0  # the imposer pays the tariff on its imports


def test_equipment_tariff_raises_cost_and_shifts_suppliers(cfg):
    mcfg = with_spec(cfg, "AAA", ["start", "manufacturing_share", "solar"], 0.6)
    w = new_world(mcfg, seed=1)
    bbb = w.nations["BBB"]
    before = tech.nation_unit_cost(mcfg, w, bbb, "solar")
    share_before = trade.supplier_weights(mcfg, w, "BBB", "solar")["AAA"]
    bbb.tariffs["AAA"] = 0.3
    assert tech.nation_unit_cost(mcfg, w, bbb, "solar") > before
    assert trade.supplier_weights(mcfg, w, "BBB", "solar")["AAA"] < share_before


def test_equipment_sales_are_cleantech_exports(cfg):
    mcfg = with_spec(cfg, "AAA", ["start", "manufacturing_share", "solar"], 0.6)
    w = new_world(mcfg, seed=1)
    trade.apply_equipment(mcfg, w, {"BBB": {"solar": 1.0}, "AAA": {}}, {"solar": 0.06}, 1)
    aaa = w.nations["AAA"]
    assert aaa.cleantech_exports > 0
    assert aaa.exported_cut_rate > 0
    assert w.nations["BBB"].cleantech_exports == 0.0


# --- trust and tariffs ---------------------------------------------------------------------------


def test_trust_starts_neutral_and_reverts(cfg, world):
    start = cfg.tune("diplomacy.trust_start")
    assert all(v == start for row in world.trust.values() for v in row.values())
    diplomacy.adjust(world, "AAA", "BBB", 5.0)
    assert world.trust["AAA"]["BBB"] == 1.0
    diplomacy.revert_trust(world, cfg, 4)
    assert start < world.trust["AAA"]["BBB"] < 1.0


def test_talks_cost_influence_and_build_trust(cfg, world):
    [r] = act(cfg, world, "AAA", {"type": "open_talks", "target": "BBB"})
    assert r["ok"]
    assert world.nations["AAA"].influence == 100 - cfg.tune("diplomacy.talks_influence_cost")
    assert world.trust["BBB"]["AAA"] > cfg.tune("diplomacy.trust_start")


def test_tariff_costs_trust_and_can_be_lifted(cfg, world):
    act(cfg, world, "AAA", {"type": "set_tariff", "target": "BBB", "level": 0.2})
    assert world.trust["BBB"]["AAA"] < cfg.tune("diplomacy.trust_start")
    [r] = act(cfg, world, "AAA", {"type": "lift_tariff", "target": "BBB"})
    assert r["ok"] and "BBB" not in world.nations["AAA"].tariffs


def test_carbon_club_rules(cfg, world):
    [r] = act(cfg, world, "AAA", {"type": "join_bloc", "bloc": "carbon_club"})
    assert not r["ok"]  # carbon price too low
    for nid in ("AAA", "BBB"):
        world.nations[nid].carbon_price = 30.0
    world.nations["AAA"].tariffs["BBB"] = 0.1
    act(cfg, world, "AAA", {"type": "join_bloc", "bloc": "carbon_club"})
    act(cfg, world, "BBB", {"type": "join_bloc", "bloc": "carbon_club"})
    assert trade.club_members(world) == ["AAA", "BBB"]
    assert "BBB" not in world.nations["AAA"].tariffs
    [r] = act(cfg, world, "AAA", {"type": "set_tariff", "target": "BBB", "level": 0.1})
    assert not r["ok"]


def test_coalition_tariff_applies_only_from_members(cfg, world):
    world.blocs["carbon_club"] = ["AAA"]
    world.coalition_tariffs["BBB"] = 0.1
    assert trade.tariff(world, "AAA", "BBB") == 0.1
    assert trade.tariff(world, "BBB", "AAA") == 0.0


# --- stocktake -----------------------------------------------------------------------------------


def test_stocktake_fires_on_schedule_with_consequences(cfg):
    w = new_world(cfg, seed=1)
    w.blocs["carbon_club"] = ["BBB"]
    w.nations["BBB"].carbon_price = 30.0
    trust_before = w.trust["BBB"]["AAA"]
    for _ in range(20):
        w = turn.step(w, cfg)
    records = [h for h in w.history if h["stocktake"]]
    assert [h["t"] for h in records] == [19]
    log = records[0]["stocktake"]
    assert log["nations"]["AAA"]["overshoot_share"] > cfg.tune("stocktake.tolerance")
    assert w.coalition_tariffs.get("AAA", 0) > 0  # AAA is outside the club
    assert "BBB" not in w.coalition_tariffs  # members are exempt
    assert w.trust["BBB"]["AAA"] < trust_before


def test_credits_cover_overshoot_and_undershoot_gains_trust(cfg):
    w = new_world(cfg, seed=1)
    aaa, bbb = w.nations["AAA"], w.nations["BBB"]
    aaa.period_emissions = aaa.fair_share_budget + 50.0
    aaa.credit_balance = 1e6
    bbb.period_emissions = bbb.fair_share_budget - 30.0
    trust_before = w.trust["AAA"]["BBB"]
    log = diplomacy.run_stocktake(cfg, w)
    assert log["nations"]["AAA"]["credits_surrendered"] == pytest.approx(50.0)
    assert log["nations"]["AAA"]["overshoot_share"] == pytest.approx(0.0)
    assert log["nations"]["BBB"]["overshoot_share"] < 0
    assert w.trust["AAA"]["BBB"] > trust_before


def test_allowance_follows_the_pathway(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    first = n.fair_share_budget
    assert first < n.base["emissions"] * 5  # already cutting in 2025-2029
    assert diplomacy.pathway_level(cfg, 2025) == 1.0
    assert diplomacy.pathway_level(cfg, 2030) == pytest.approx(0.55)
    assert diplomacy.pathway_level(cfg, 2049) > 0  # never zero before 2050
    w.t = 80
    diplomacy.set_allowances(cfg, w)
    assert 0 < n.fair_share_budget < first


def test_club_member_below_price_is_removed(cfg, world):
    world.blocs["carbon_club"] = ["AAA"]
    world.nations["AAA"].carbon_price = 0.0
    log = diplomacy.run_stocktake(cfg, world)
    assert log["left_club"] == ["AAA"] and trade.club_members(world) == []
