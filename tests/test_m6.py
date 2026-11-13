"""M6 mechanics pass: blackouts, world difficulty, scoring curves, bot affordability."""

import copy
import dataclasses

import pytest

from sim import bots, climate, economy, runner, shocks
from sim.scenario import new_world


def retune(cfg, **values):
    """A copy of cfg with tuning values replaced; keys use '__' between levels, e.g.
    shocks__disaster_rate."""
    tuning = copy.deepcopy(cfg.tuning)
    for key, value in values.items():
        *path, last = key.split("__")
        node = tuning
        for p in path:
            node = node[p]
        node[last]["value"] = value
    return dataclasses.replace(cfg, tuning=tuning)


# --- blackouts erode stability directly ----------------------------------------------------------


def stability_after_blackout(cfg, quarters=8, share=0.3):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    for _ in range(quarters):
        n.shortfall = share * n.demand
        economy.apply_growth(w, cfg, 1)
    return n.stability


def test_blackouts_erode_stability_beyond_approval(cfg):
    calm = retune(cfg, politics__stability_shortfall_hit=0.0)
    assert stability_after_blackout(cfg) < stability_after_blackout(calm)


def test_a_sustained_blackout_can_topple_a_government(cfg):
    stability = stability_after_blackout(cfg, quarters=12, share=0.4)
    assert stability < cfg.tune("scoring.fallen_stability")


# --- world difficulty -----------------------------------------------------------------------------


def test_disasters_grow_with_warming(cfg):
    w = new_world(cfg, seed=1)
    w.warming = cfg.tune("climate.warming_start")
    assert shocks.disaster_scale(cfg, w) == pytest.approx(1.0)
    w.warming += 1.0
    assert shocks.disaster_scale(cfg, w) == pytest.approx(
        1.0 + cfg.tune("shocks.disaster_warming_growth")
    )


def test_hard_world_raises_climate_damage(cfg):
    damage = {}
    for level in ("easy", "hard"):
        w = new_world(cfg, seed=1, difficulty=level)
        w.global_cumulative_emissions = 5e5  # enough to warm well past 2025
        climate.apply(w, cfg, 1)
        damage[level] = w.nations["AAA"].climate_damage
    assert damage["hard"] > damage["easy"] > 0


def test_hard_world_lengthens_factory_disruptions(cfg):
    sure = retune(cfg, shocks__disruption_rate=10.0)  # certain at every level
    lengths = {}
    for level in ("easy", "hard"):
        w = new_world(sure, seed=1, difficulty=level)
        w.nations["AAA"].factory_capacity["solar"] = 1.0
        shocks.apply(w, sure, 1)
        lengths[level] = w.nations["AAA"].disruption_until["solar"] - w.t
    shortest = cfg.tune("shocks.disruption_min_quarters")
    assert lengths["hard"] >= round(shortest * cfg.level("hard", "disruption_length"))
    assert lengths["hard"] > lengths["easy"]


# --- bots only ask for what they can pay for -----------------------------------------------------


def test_affordable_drops_what_the_nation_cannot_pay_for(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.political_capital = 1.0
    cheap = {"type": "set_carbon_price", "level": n.carbon_price + 1.0}
    dear = {"type": "set_carbon_price", "level": n.carbon_price + 1e4}
    assert bots.affordable(cfg, w, n, [dear, None, cheap]) == [cheap]


def test_reckless_bot_has_no_rejected_actions(cfg):
    w = runner.play(cfg, 1, "AAA", "reckless", until=12)
    rejected = [r for h in w.history for r in h["nations"]["AAA"]["actions"] if not r["ok"]]
    assert rejected == []
