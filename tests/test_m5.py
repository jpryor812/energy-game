"""M5: new deal types, plant failure, world difficulty, shocks, scoring layers, harness."""

import copy
import dataclasses

import pytest

from sim import actions, balance, bots, deals, diplomacy, runner, scoring, shocks, trade, turn
from sim.scenario import new_world

LOAN = {
    "type": "propose_deal",
    "target": "BBB",
    "deal_type": "climate_loan",
    "source": "solar",
    "amount": 0.2,
    "currency": "hard",
    "rate": 0.05,
    "duration": 8,
    "collateral": 0.2,
    "exit_penalty": 0.0,
}
EQUITY = {
    "type": "propose_deal",
    "target": "BBB",
    "deal_type": "equity_for_energy",
    "source": "solar",
    "amount": 1.0,
    "share": 0.5,
    "duration": 40,
    "collateral": 0.0,
    "exit_penalty": 0.0,
}


@pytest.fixture
def world(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 50, "diplomatic": 50}
        n.capital = 5.0
        n.political_capital = 100.0
    return w


def signed(cfg, w, offer):
    [r] = actions.resolve(cfg, w, "AAA", [offer])
    assert r["ok"], r
    w.t += 1
    did = sorted(w.deals)[-1]
    [r] = actions.resolve(
        cfg, w, "BBB", [{"type": "respond_deal", "deal_id": did, "response": "accept"}]
    )
    assert r["ok"], r
    return w.deals[did]


def run(cfg, w, turns):
    for _ in range(turns):
        w = turn.step(w, cfg)
    return w


# --- deals ---------------------------------------------------------------------------------------


def test_climate_loan_moves_cash_and_debt(cfg, world):
    host_cash, fin_cash = world.nations["BBB"].capital, world.nations["AAA"].capital
    deal = signed(cfg, world, LOAN)
    assert world.nations["AAA"].capital == pytest.approx(fin_cash - 0.2)
    assert world.nations["BBB"].capital == pytest.approx(host_cash + 0.2)
    assert deal.terms["outstanding"] == pytest.approx(0.2)
    assert deal.terms["pay_from"] == world.t + 1
    w = run(cfg, world, deal.terms["online_turn"] - world.t + 2)
    d = w.deals[deal.id]
    assert d.terms["paid"] > 0 and d.terms["credited"] > 0


def test_equity_dividends_follow_host_prices(cfg, world):
    deal = signed(cfg, world, EQUITY)
    world.t = deal.terms["online_turn"]
    high = deals.dividend(cfg, world, deal)
    world.nations["BBB"].energy_price *= 0.5
    assert 0 <= deals.dividend(cfg, world, deal) < high


def test_equity_failure_risk_rises_with_instability(cfg, world):
    deal = signed(cfg, world, EQUITY)
    calm = deals.failure_chance(cfg, world, deal)
    world.nations["BBB"].stability = 0.0
    shaky = deals.failure_chance(cfg, world, deal)
    world.trust["BBB"]["AAA"] = 0.0
    assert calm < shaky < deals.failure_chance(cfg, world, deal)


def test_failed_plant_loses_capacity_and_trust(cfg, world):
    deal = signed(cfg, world, EQUITY)
    w = run(cfg, world, deal.terms["online_turn"] - world.t + 1)
    host = w.nations["BBB"]
    before = host.capacity["solar"]
    trust = w.trust["AAA"]["BBB"]
    deals._fail(cfg, w, w.deals[deal.id])
    assert w.deals[deal.id].status == "failed"
    assert host.capacity["solar"] < before and w.trust["AAA"]["BBB"] < trust


# --- world difficulty and shocks -----------------------------------------------------------------


def test_difficulty_moves_the_pathway(cfg):
    easy = diplomacy.pathway_level(cfg, 2045, "easy")
    hard = diplomacy.pathway_level(cfg, 2045, "hard")
    assert hard == pytest.approx(0.0) and easy > diplomacy.pathway_level(cfg, 2045, "normal") > hard


def test_disasters_scale_with_warming_and_difficulty(cfg, world):
    assert shocks.disaster_chance(cfg, world, "AAA") == pytest.approx(
        cfg.tune("shocks.disaster_rate") * (world.warming - 1.0)
    )
    world.warming += 0.5
    normal = shocks.disaster_chance(cfg, world, "AAA")
    world.difficulty = "hard"
    assert shocks.disaster_chance(cfg, world, "AAA") > normal


def test_shocks_are_seeded(cfg):
    hot = copy.deepcopy(cfg.tuning)
    hot["shocks"]["disaster_rate"]["value"] = 1.0  # a disaster every quarter
    hcfg = dataclasses.replace(cfg, tuning=hot)

    def events(seed):
        w = run(hcfg, new_world(hcfg, seed=seed), 6)
        return [e for h in w.history for e in h.get("events", [])]

    assert events(1) == events(1)
    assert events(1) and events(1) != events(2)
    assert all(e["type"] in ("disaster", "disruption") for e in events(1))


def test_disruption_shifts_share_and_raises_cost(cfg, world):
    world.nations["AAA"].factory_capacity["solar"] = 0.1
    share = trade.capacity_shares(cfg, world, "solar")["AAA"]
    world.nations["AAA"].disruption["solar"] = 0.5
    assert trade.capacity_shares(cfg, world, "solar")["AAA"] < share
    assert trade.disruption_premium(cfg, world, "BBB", "solar") > 0
    assert trade.disruption_premium(cfg, world, "AAA", "solar") == 0  # its own factories


def test_fossil_ban_stops_new_fossil_plants(cfg, world):
    from sim import construction

    n = world.nations["AAA"]
    actions.resolve(cfg, world, "AAA", [{"type": "set_fossil_ban", "on": True}])
    alloc = construction.split_gap(cfg, world, "AAA", n, 5.0, 1e9, 1e9)
    assert all(not alloc.get(f) for f in ("coal", "oil", "gas"))


# --- scoring -------------------------------------------------------------------------------------


def test_absolute_and_relative_layers(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=12)
    result = scoring.score(cfg, w, "AAA")
    assert set(result["absolute_components"]) == {
        "income", "clean_share", "emissions", "security", "approval",
    }  # fmt: skip
    assert 0 <= result["absolute_index"] <= 100
    hard = copy.deepcopy(cfg.countries)
    hard["nations"]["AAA"]["difficulty"] = "hard"
    hcfg = dataclasses.replace(cfg, countries=hard)
    harder = scoring.score(hcfg, w, "AAA")
    assert harder["difficulty_multiplier"] == cfg.tune("scoring.difficulty_hard")
    assert harder["combined_index"] > result["combined_index"]  # same play, worth more


def test_relative_bonuses_scale_with_difficulty(cfg):
    assert "largest_reduction" in scoring.RELATIVE_BONUSES
    assert "first_net_zero" not in scoring.RELATIVE_BONUSES


# --- harness -------------------------------------------------------------------------------------


def test_parallel_grid_matches_serial(cfg):
    jobs = [(1, "AAA", "balanced", None, None), (2, "AAA", "noop", None, "hard")]
    serial = runner.run_grid(cfg, jobs, workers=1)
    parallel = runner.run_grid(cfg, jobs, workers=2)
    assert [r["state_hash"] for r in serial] == [r["state_hash"] for r in parallel]
    assert serial[1]["difficulty"] == "hard"


def test_reckless_bot_and_sanity(cfg):
    w = runner.play(cfg, 1, "AAA", "reckless", until=12)
    acts = [r["action"]["type"] for h in w.history for r in h["nations"]["AAA"]["actions"]]
    assert "retire_capacity" in acts and "set_carbon_price" in acts
    assert runner.sanity_issues(w) == []
    assert "reckless" in bots.BOTS


def test_balance_report_lists_all_criteria(cfg):
    summary = runner.summarize(cfg, runner.play(cfg, 1, "AAA", "noop", until=8), "AAA", "noop", 1)
    fake = {
        "main": [
            summary | {"bot": b, "country": c} for b in balance.BOTS for c in cfg.playable_ids
        ],
        "by_difficulty": [summary | {"difficulty": d} for d in ("easy", "normal", "hard")],
        "many_free": [summary | {"country": c} for c in cfg.playable_ids],
        "short": {(c, b): 50.0 for c in cfg.playable_ids for b in ("balanced", "all_fossil")},
        "determinism": ("a" * 64, "a" * 64),
        "seeds": [1],
    }
    text = balance.report(cfg, fake)
    for name in ("Determinism", "No dominant bot", "Viable strategies", "Difficulty ordering",
                 "Free-rider tension", "Sanity", "Game length"):  # fmt: skip
        assert name in text
