"""M12: the tech tree."""

import pytest

from sim import actions, config, construction, research, tech, turn
from sim.scenario import new_world


@pytest.fixture
def w(cfg):
    world = new_world(cfg, seed=1)
    for n in world.nations.values():
        n.slots_banked = {"domestic": 6, "diplomatic": 4}
        n.capital = 10.0
        n.political_capital = 100.0
    return world


def act(cfg, w, nid, *acts):
    return actions.resolve(cfg, w, nid, list(acts))


def test_funding_is_capped_at_the_minimum_time(cfg, w):
    n = w.nations["AAA"]
    cap = research.useful_funding(cfg, w, n, "next_gen_solar")
    spec = cfg.rtech("next_gen_solar")
    assert cap == pytest.approx(spec["cost"]["value"] / spec["min_quarters"]["value"])
    [r] = act(cfg, w, "AAA", {"type": "fund_research", "tech": "next_gen_solar", "amount": 1.0})
    assert not r["ok"] and "max" in r["reason"]
    [r] = act(cfg, w, "AAA", {"type": "fund_research", "tech": "next_gen_solar", "amount": "max"})
    assert r["ok"] and r["action"]["amount"] == pytest.approx(cap)
    assert n.research_progress["next_gen_solar"] == pytest.approx(1 / spec["min_quarters"]["value"])


def test_research_completes_after_the_minimum_time_and_unlocks(cfg, w):
    n = w.nations["AAA"]
    q = cfg.rtech("small_modular_reactors")["min_quarters"]["value"]
    for _ in range(q):
        n.slots_banked["domestic"] = 6
        n.capital = 10.0
        [r] = act(
            cfg,
            w,
            "AAA",
            {"type": "fund_research", "tech": "small_modular_reactors", "amount": "max"},
        )
        assert r["ok"], r
        w = turn.step(w, cfg)
        n = w.nations["AAA"]
    assert research.has(n, "small_modular_reactors")
    assert w.tech_firsts["small_modular_reactors"][0] == "AAA"
    assert "smr" in construction.cost_candidates(cfg, "AAA", n)
    assert "smr" not in construction.cost_candidates(cfg, "BBB", w.nations["BBB"])


def test_locked_sources_and_prerequisites(cfg, w):
    [r] = act(cfg, w, "AAA", {"type": "build_capacity", "source": "smr", "amount": 0.1})
    assert not r["ok"] and "research it first" in r["reason"]
    [r] = act(cfg, w, "AAA", {"type": "fund_research", "tech": "fusion", "amount": 0.01})
    assert not r["ok"] and "first" in r["reason"]
    [r] = act(cfg, w, "AAA", {"type": "retrofit_ccs", "fuel": "coal", "amount": 0.1})
    assert not r["ok"] and "ccs" in r["reason"]


def test_spillover_makes_followers_cheaper(cfg, w):
    before = research.cost_now(cfg, w, "advanced_batteries")
    w.tech_firsts["advanced_batteries"] = ["BBB", 4]
    after = research.cost_now(cfg, w, "advanced_batteries")
    assert after == pytest.approx(before * (1 - cfg.research["spillover"]["value"]))


def test_upgrades_cut_cost_and_build_time_for_the_owner_only(cfg, w):
    a, b = w.nations["AAA"], w.nations["BBB"]
    solar = tech.nation_unit_cost(cfg, w, a, "solar")
    grid = construction.build_time(cfg, a, "grid")
    a.techs = ["hvdc_supergrid", "next_gen_solar"]
    assert tech.nation_unit_cost(cfg, w, a, "solar") == pytest.approx(solar * 0.8)
    assert construction.build_time(cfg, a, "grid") < grid
    assert construction.build_time(cfg, b, "grid") == grid


def test_fusion_waits_for_its_earliest_year(cfg, w):
    n = w.nations["AAA"]
    n.techs = ["small_modular_reactors", "advanced_fission"]
    n.research_progress["fusion"] = 1.0
    assert research.complete(cfg, w) == []
    w.t = research.earliest_turn(cfg, "fusion")
    assert research.complete(cfg, w) == [("AAA", "fusion")]


def test_ccs_retrofit_cuts_emissions(cfg, w):
    n = w.nations["AAA"]
    n.techs = ["ccs"]
    base = turn.step(w, cfg).nations["AAA"].emissions
    [r] = act(cfg, w, "AAA", {"type": "retrofit_ccs", "fuel": "coal", "amount": "max"})
    assert r["ok"], r
    assert n.ccs["coal"] == pytest.approx(n.capacity["coal"], rel=1e-6)
    assert turn.step(w, cfg).nations["AAA"].emissions < base


def test_electrolysers_raise_the_clean_ceiling(cfg, w):
    from sim import energy

    n = w.nations["AAA"]
    before = energy.clean_max_share(cfg, w.t, n)
    n.capacity["electrolysers"] = 0.1 * n.demand
    assert energy.clean_max_share(cfg, w.t, n) > before


def test_tree_is_valid_and_reaches_fusion():
    cfg = config.load()
    assert "fusion" in cfg.tech_ids
    chain, tid = [], "fusion"
    while tid:
        chain.append(tid)
        pre = cfg.rtech(tid).get("requires", [])
        tid = pre[0] if pre else None
    assert chain[-1] == "small_modular_reactors"
    total = sum(cfg.rtech(t)["min_quarters"]["value"] for t in chain)
    assert total <= 100  # a determined player can reach fusion within the game
