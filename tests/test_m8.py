"""M8 mechanics pass: fixes from the pilot playtest."""

import pytest

from sim import actions, ai, config, construction, elections, runner, scoring, tech, turn
from sim.scenario import new_world
from sim.state import Construction

# --- clean share and bonus races use four-quarter averages ---------------------------------------


def test_annual_clean_share_pools_the_last_four_quarters(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=6)
    recs = [h["nations"]["AAA"]["supply"] for h in w.history[-4:]]
    clean = sum(v for r in recs for s, v in r.items() if cfg.category(s) != "fossil")
    total = sum(v for r in recs for v in r.values())
    assert scoring.annual_clean_share(cfg, w, "AAA") == pytest.approx(clean / total)


def test_races_report_every_bonus_and_the_first_to_net_zero(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=4)
    races = {r["race"]: r for r in scoring.races(cfg, w, "AAA")}
    assert set(races) == {
        "first_net_zero",
        "largest_reduction",
        "largest_cut_tonnes",
        "largest_clean_gain",
        "best_deal",
    }
    assert races["first_net_zero"]["claimed"] is None
    base = w.nations["BBB"].base["emissions"]
    w.history[1]["nations"]["BBB"]["emissions"] = 0.0
    assert scoring.first_net_zero(cfg, w) is None  # M9: one low quarter is not enough
    for h in w.history[:4]:
        h["nations"]["BBB"]["emissions"] = 0.0
    assert scoring.first_net_zero(cfg, w) == ("BBB", w.history[3]["label"])
    assert scoring.bonuses(cfg, w)["BBB"]["first_net_zero"] > 0
    assert base > 0


# --- the fossil ban -------------------------------------------------------------------------------


def test_fossil_ban_cancels_projects_not_yet_started(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.slots_banked = {"domestic": 5, "diplomatic": 5}
    n.political_capital = 100.0
    coal_time = int(cfg.src("coal", "build_time"))
    n.pipeline = [
        Construction("coal", 1.0, w.t + 1),  # started long ago
        Construction("coal", 1.0, w.t + coal_time + 4),  # starts in a year
        Construction("solar", 1.0, w.t + 20),
    ]
    [r] = actions.resolve(cfg, w, "AAA", [{"type": "set_fossil_ban", "on": True}])
    assert r["ok"], r
    assert [(c.source, c.complete_turn) for c in n.pipeline] == [
        ("coal", w.t + 1),
        ("solar", w.t + 20),
    ]
    [r] = actions.resolve(
        cfg, w, "AAA", [{"type": "build_capacity", "source": "coal", "amount": 0.1}]
    )
    assert not r["ok"] and "fossil ban" in r["reason"]


def test_no_new_fossil_orders_under_a_ban(cfg):
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.fossil_ban = 1.0
    n.pipeline = []
    construction.market_build(cfg, w, "AAA", n)
    assert not any(cfg.category(c.source) == "fossil" for c in n.pipeline)


# --- elections average the tax rise over the term ------------------------------------------------


def test_a_tax_rise_reversed_before_the_vote_still_costs_votes(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=2)
    w.player = "AAA"
    elections.start_term(w)
    n = w.nations["AAA"]
    n.tax_change = 0.03
    for _ in range(3):
        elections.track(w)
    n.tax_change = 0.0
    elections.track(w)
    assert elections.term_tax_rise(w) == pytest.approx(0.03 * 3 / 4)
    assert elections.vote(cfg, w)["taxes"] < 0


# --- AI financiers refuse counter-offers far below their ask -------------------------------------


def _countered(rate_share):
    cfg = config.load()
    w = new_world(cfg, seed=1)
    usa, ind = w.nations["USA"], w.nations["IND"]
    for n in (usa, ind):
        n.slots_banked = {"domestic": 4, "diplomatic": 4}
        n.capital = 1.0
    offer = {
        "type": "propose_deal",
        "target": "IND",
        "deal_type": "equipment_on_credit",
        "source": "solar",
        "amount": 0.05,
        "currency": "hard",
        "rate": 0.1,
        "duration": 40,
        "collateral": 0.2,
        "exit_penalty": 0.2,
    }
    [r] = actions.resolve(cfg, w, "USA", [offer])
    assert r["ok"], r
    w.t += 1
    did = sorted(w.deals)[-1]
    counter = {"type": "respond_deal", "deal_id": did, "response": "counter"}
    [r] = actions.resolve(cfg, w, "IND", [counter | {"rate": 0.1 * rate_share}])
    assert r["ok"], r
    w.t += 1
    new = sorted(w.deals)[-1]
    assert w.deals[new].terms["asked"] == 0.1
    answers = [
        a["response"]
        for _, a, _ in ai.scored(cfg, w, "USA")
        if a["type"] == "respond_deal" and a["deal_id"] == new
    ]
    return answers


def test_ai_financier_refuses_a_lowball_counter():
    assert _countered(0.3) == ["refuse"]


def test_ai_financier_accepts_a_fair_counter():
    assert _countered(0.8) == ["accept"]


# --- banked slots, learning floors, endings -------------------------------------------------------


def test_bots_see_the_slot_cap(cfg):
    from sim import bots

    n = new_world(cfg, seed=1).nations["AAA"]
    n.slots_banked = {"domestic": 99, "diplomatic": 99}
    assert bots.slots(cfg, n, "domestic") == cfg.tune("slots.domestic_bank_cap")


def test_removal_cost_reports_its_floor(cfg):
    w = new_world(cfg, seed=1)
    assert not tech.at_floor(cfg, w, "carbon_removal")
    w.tech_state["carbon_removal"] = 1e6
    assert tech.at_floor(cfg, w, "carbon_removal")
    assert not tech.at_floor(cfg, w, "wind")  # no floor set


def test_warming_must_be_falling_for_a_good_world(cfg):
    w = runner.play(cfg, 1, "AAA", "noop", until=25)
    assert scoring.warming_falling(cfg, w) is not None
    w.warming = w.history[-21]["warming"] + 0.01
    assert scoring.warming_falling(cfg, w) is False
    w.warming = w.history[-21]["warming"] - 0.01
    assert scoring.warming_falling(cfg, w) is True


def test_turn_runs_with_capped_slots(cfg):
    w = new_world(cfg, seed=1)
    for _ in range(4):
        w = turn.step(w, cfg)
    assert w.nations["AAA"].slots_banked["domestic"] <= cfg.tune("slots.domestic_bank_cap")


def test_free_actions_work_with_negative_capital(cfg):
    """Playtest round 1 (VNM): capital at -0.0002 T$ crashed every action with a KeyError."""
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.capital = -0.001
    n.slots_banked = {"domestic": 4, "diplomatic": 4}
    free, paid = actions.resolve(
        cfg,
        w,
        "AAA",
        [
            {"type": "set_tax_rate", "level": 0.0},
            {"type": "build_capacity", "source": "wind", "amount": 0.1},
        ],
    )
    assert free["ok"], free
    assert not paid["ok"] and "capital" in paid["reason"]


def test_negative_income_is_borrowed_not_left_as_negative_capital(cfg):
    from sim import economy

    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.capital = -0.05
    debt = n.debt_local
    economy.apply_income(w, cfg, 1)
    assert n.capital >= 0
    assert n.debt_local > debt or n.capital > 0


def test_fossil_ban_with_a_factory_under_construction(cfg):
    """Playtest round 1 (exploit hunter): the ban crashed on factory entries in the pipeline."""
    w = new_world(cfg, seed=1)
    n = w.nations["AAA"]
    n.slots_banked = {"domestic": 4, "diplomatic": 4}
    n.political_capital = 100.0
    n.capital = 1.0
    build, ban = actions.resolve(
        cfg,
        w,
        "AAA",
        [
            {"type": "build_factory", "tech": "solar", "amount": 0.001},
            {"type": "set_fossil_ban", "on": True},
        ],
    )
    assert build["ok"] and ban["ok"], (build, ban)
    assert any(c.source.startswith(construction.FACTORY) for c in n.pipeline)
