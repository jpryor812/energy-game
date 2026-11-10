"""M9 mechanics pass: fixes from playtest round 1."""

import copy
import dataclasses

import pytest

from sim import actions, construction, deals, diplomacy, elections, runner, scoring, trade, turn
from sim.scenario import new_world


def retune(cfg, **values):
    tuning = copy.deepcopy(cfg.tuning)
    for key, value in values.items():
        *path, last = key.split("__")
        node = tuning
        for p in path:
            node = node[p]
        node[last]["value"] = value
    return dataclasses.replace(cfg, tuning=tuning)


# --- factories ------------------------------------------------------------------------------------


def test_factories_age_out_everywhere(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.factory_capacity["solar"] = 1.0
    row = {k: v for k, v in w.base.items() if k.startswith("row_capacity_")}
    w = turn.step(w, cfg)
    keep = (1 - 1 / cfg.tune("industry.factory_lifespan")) ** 0.25
    assert w.nations["AAA"].factory_capacity["solar"] == pytest.approx(keep)
    for k, v in row.items():
        assert w.base[k] == pytest.approx(v * keep)


def test_clean_score_counts_sales_not_idle_capacity(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=6)
    before = scoring.clean_competitiveness(cfg, w, "AAA")
    w.nations["AAA"].factory_capacity["storage"] = 100.0  # idle: nobody buys from it
    assert scoring.clean_competitiveness(cfg, w, "AAA") == pytest.approx(before)
    for h in w.history[-4:]:
        h["nations"]["AAA"]["factory_sales"] = {"solar": 1.0}
        h["nations"]["AAA"]["equipment_demand"] = {"solar": 1.0}
    assert scoring.clean_competitiveness(cfg, w, "AAA") > before


def test_exported_cut_winds_down(cfg):
    w = new_world(cfg, seed=1)
    w.nations["AAA"].exported_cut_rate = 100.0
    w = turn.step(w, cfg)
    assert w.nations["AAA"].exported_cut_rate < 100.0


# --- deals ----------------------------------------------------------------------------------------


def test_host_cannot_accept_more_than_its_cap(cfg):
    w = new_world(cfg, seed=1)
    for n in w.nations.values():
        n.slots_banked = {"domestic": 4, "diplomatic": 4}
        n.capital = 50.0
    room = deals.host_room(cfg, w, "BBB")
    offer = {
        "type": "propose_deal", "target": "BBB", "deal_type": "equipment_on_credit",
        "source": "solar", "amount": room * 1.5, "currency": "hard", "rate": 0.08,
        "duration": 8, "collateral": 0.5, "exit_penalty": 0.3,
    }  # fmt: skip
    actions.resolve(cfg, w, "AAA", [offer])
    w.t += 1
    did = sorted(w.deals)[-1]
    accept = {"type": "respond_deal", "deal_id": did, "response": "accept"}
    [r] = actions.resolve(cfg, w, "BBB", [accept])
    assert not r["ok"] and "host only" in r["reason"]


# --- elections average prices and jobs over the term ----------------------------------------------


def test_price_cut_before_the_vote_counts_only_for_its_quarter(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=2)
    w.player = "AAA"
    elections.start_term(w)
    n = w.nations["AAA"]
    start = w.term_start["price"]
    n.energy_price = start * 1.2
    for _ in range(3):
        elections.track(cfg, w)
    n.energy_price = start * 0.9
    elections.track(cfg, w)
    assert elections.term_price_rise(w) == pytest.approx((0.2 * 3 - 0.1) / 4)


def test_jobs_vote_compares_term_averages(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=2)
    w.player = "AAA"
    elections.start_term(w)
    n = w.nations["AAA"]
    base = dict(n.jobs)
    for _ in range(3):
        elections.track(cfg, w)
    n.jobs = {k: v * 3 for k, v in base.items()}  # one quarter's spike
    elections.track(cfg, w)
    avg = elections.term_jobs(w)
    for k, v in base.items():
        assert avg[k] == pytest.approx(v * 1.5)
    elections.start_term(w)  # the next term starts from this term's average
    assert w.term_start["jobs_" + next(iter(base))] == pytest.approx(
        next(iter(base.values())) * 1.5
    )


# --- the carbon club, rank -----------------------------------------------------------------------


def test_members_below_the_club_minimum_leave(cfg):
    w = new_world(cfg, seed=1)
    w.blocs[trade.CLUB] = ["AAA", "BBB"]
    w.nations["AAA"].carbon_price = cfg.tune("diplomacy.club_min_carbon_price")
    w.nations["BBB"].carbon_price = 0.0
    assert diplomacy.enforce_club(cfg, w) == ["BBB"]
    assert trade.club_members(w) == ["AAA"]


def test_rank_follows_the_final_score(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=8)
    result = scoring.score(cfg, w, "AAA")
    nations = result["all_nations"]
    by_score = sorted(nations, key=lambda nid: -nations[nid]["score"])
    assert [nations[nid]["rank"] for nid in by_score] == list(range(1, len(nations) + 1))


# --- the market fills near-term gaps -------------------------------------------------------------


def test_fast_orders_use_only_sources_that_build_in_time(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.pipeline = []
    n.energy_intensity *= 1.3
    fast = int(cfg.tune("market.fast_horizon"))
    construction.order(cfg, w, "AAA", n, w.t, w.t + fast, fast=True)
    assert n.pipeline
    assert all(cfg.src(c.source, "build_time") <= fast for c in n.pipeline)
