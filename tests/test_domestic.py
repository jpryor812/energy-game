"""Domestic economy and elections (M4b part 1). Fixture data."""

import copy
import dataclasses

import pytest

from sim import actions, economy, elections, energy, jobs, runner, tech, trade, turn
from sim.scenario import new_world


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 20, "diplomatic": 20}
        n.capital = 5.0
        n.political_capital = 100.0
    return w


def act(cfg, world, nid, *acts):
    results = actions.resolve(cfg, world, nid, list(acts))
    assert all(r["ok"] for r in results), results
    return results


# --- taxes and credits ---------------------------------------------------------------------------


def test_tax_rise_brings_capital_costs_growth_and_approval(cfg, world):
    base = turn.step(world, cfg).nations["AAA"]
    approval = world.nations["AAA"].approval
    act(cfg, world, "AAA", {"type": "set_tax_rate", "level": 0.02})
    assert world.nations["AAA"].approval < approval
    assert world.nations["AAA"].political_capital < 100.0
    taxed = turn.step(world, cfg).nations["AAA"]
    assert taxed.capital > base.capital
    assert taxed.growth < base.growth
    [r] = actions.resolve(cfg, world, "AAA", [{"type": "set_tax_rate", "level": 0.05}])
    assert not r["ok"]


def test_production_credit_cuts_price_and_costs_revenue(cfg, world):
    n = world.nations["AAA"]
    price = tech.delivered_price(cfg, world, n)
    act(
        cfg,
        world,
        "AAA",
        {"type": "set_tax_credit", "kind": "generation", "tech": "solar", "rate": 2.0},
    )
    assert tech.delivered_price(cfg, world, n) < price
    assert economy.tax_credit_cost(n) == pytest.approx(2.0 * n.supply["solar"] * 1e-3)


def test_production_credit_changes_merit_order(cfg, world):
    n = world.nations["AAA"]
    demand = energy.base_demand(n) * 0.9
    gas = energy.dispatch(cfg, n, demand).supply["gas"]
    n.tax_credits["generation:gas"] = 5.0  # gas now cheaper than oil... and coal
    assert energy.dispatch(cfg, n, demand).supply["gas"] >= gas


# --- factories and supply chains -----------------------------------------------------------------


def test_factory_raises_share_after_build_time(cfg, world):
    share = trade.capacity_shares(cfg, world, "solar").get("AAA", 0.0)
    act(cfg, world, "AAA", {"type": "build_factory", "tech": "solar", "amount": 0.05})
    w = world
    for _ in range(int(cfg.tune("industry.factory_build_time")) + 1):
        w = turn.step(w, cfg)
    assert w.nations["AAA"].factory_capacity["solar"] == pytest.approx(0.05)
    assert trade.capacity_shares(cfg, w, "solar")["AAA"] > share


def test_manufacturing_credit_raises_share(cfg, world):
    world.nations["AAA"].factory_capacity["solar"] = 0.02
    share = trade.capacity_shares(cfg, world, "solar")["AAA"]
    world.nations["AAA"].tax_credits["manufacturing:solar"] = 0.3
    assert trade.capacity_shares(cfg, world, "solar")["AAA"] > share


def test_domestic_content_forces_share_and_costs_when_short(cfg, world):
    n = world.nations["AAA"]
    n.equipment_demand["solar"] = 0.1
    cost = tech.nation_unit_cost(cfg, world, n, "solar")
    act(cfg, world, "AAA", {"type": "set_domestic_content", "tech": "solar", "share": 0.5})
    assert trade.supplier_weights(cfg, world, "AAA", "solar")["AAA"] == pytest.approx(0.5)
    assert tech.nation_unit_cost(cfg, world, n, "solar") > cost  # no factories to meet it
    n.factory_capacity["solar"] = 1.0
    assert tech.nation_unit_cost(cfg, world, n, "solar") == pytest.approx(cost)


# --- jobs, retraining, electrification -----------------------------------------------------------


def test_fossil_losses_weigh_more_and_retraining_softens(cfg, world):
    n = world.nations["AAA"]
    before = {"fossil": 1.0, "clean_ops": 1.0}
    lost = jobs.weighted_change(cfg, n, before, {"fossil": 0.9, "clean_ops": 1.1})
    assert lost < 0  # 0.1 fossil lost outweighs 0.1 clean gained
    n.retraining = 10.0
    softened = jobs.weighted_change(cfg, n, before, {"fossil": 0.9, "clean_ops": 1.1})
    assert lost < softened


def test_job_loss_lowers_approval(cfg, world):
    n = world.nations["AAA"]
    n.jobs = {**n.jobs, "fossil": n.jobs["fossil"] + 5.0}  # pretend 5 million jobs just went
    approval = n.approval
    jobs.apply(world, cfg)
    assert n.approval < approval


def test_electrification_raises_ceilings(cfg, world):
    n = world.nations["AAA"]
    vre, clean = energy.vre_max_share(cfg, 0, n), energy.clean_max_share(cfg, 0, n)
    act(cfg, world, "AAA", {"type": "electrification_program", "amount": 0.5})
    assert energy.vre_max_share(cfg, 0, n) > vre
    assert energy.clean_max_share(cfg, 0, n) > clean


# --- elections -----------------------------------------------------------------------------------


def test_election_schedule(cfg):
    due = [t for t in range(100) if elections.due(cfg, t)]
    assert due == [15, 31, 47, 63, 79, 95]


def test_elections_are_seeded_and_deterministic(cfg):
    a = runner.play(cfg, 1, "AAA", "balanced", until=20).elections
    b = runner.play(cfg, 1, "AAA", "balanced", until=20).elections
    assert a == b and a[0]["t"] == 15
    assert set(a[0]["parts"]) == {"incumbency", "growth", "jobs", "prices", "taxes", "swing"}
    other = runner.play(cfg, 7, "AAA", "balanced", until=20).elections
    assert other[0]["parts"]["swing"] != a[0]["parts"]["swing"]


def test_vote_is_purely_economic(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=15)
    w.player = "AAA"
    base = sum(elections.vote(cfg, w).values())
    w.nations["AAA"].approval = 0.0  # approval does not enter the vote
    assert sum(elections.vote(cfg, w).values()) == pytest.approx(base)
    w.nations["AAA"].gdp *= 0.9  # a weaker economy does
    assert sum(elections.vote(cfg, w).values()) < base


def test_losing_hands_one_term_to_the_opposition(cfg):
    harsh = copy.deepcopy(cfg.tuning)
    harsh["elections"]["incumbency"]["value"] = 0.0  # every election is lost
    hcfg = dataclasses.replace(cfg, tuning=harsh)
    w = runner.play(hcfg, 1, "AAA", "balanced", until=40)
    events = [(e["t"], e["event"]) for e in w.elections]
    assert events == [(15, "lost"), (31, "player_returns")]
    log = {h["t"]: h for h in w.history}
    assert all(not log[t]["player_in_power"] for t in range(16, 32))
    assert all(log[t]["nations"]["AAA"]["actions"] == [] for t in range(17, 32))
    assert log[32]["player_in_power"] and log[33]["nations"]["AAA"]["actions"]
