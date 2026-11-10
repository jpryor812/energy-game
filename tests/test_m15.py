"""M15: the rest of the world as regions, and financing clean energy there."""

import pytest

from sim import actions, climate, config, regions, turn, view
from sim.scenario import new_world
from sim.session import Game


@pytest.fixture
def w(cfg):
    world = new_world(cfg, seed=1)
    for n in world.nations.values():
        n.slots_banked = {"domestic": 6, "diplomatic": 4}
        n.capital = 10.0
    return world


def act(cfg, w, nid, *acts):
    return actions.resolve(cfg, w, nid, list(acts))


# --- the data -------------------------------------------------------------------------------------


def test_regions_and_transport_add_up_to_the_old_rest_of_world():
    real = config.load()
    world = new_world(real, seed=1)
    exo = climate.exogenous_co2(real, world)
    assert len(world.regions) == 7
    assert exo["regions"] + exo["transport"] == pytest.approx(
        real.tune("climate.rest_of_world_co2"), rel=1e-6
    )
    assert exo["transport"] > 0  # international shipping and aviation


def test_region_ids_do_not_clash_with_nations():
    real = config.load()
    assert not set(real.region_ids) & set(real.nation_ids)


# --- the dynamics ---------------------------------------------------------------------------------


def test_regions_grow_and_their_new_energy_gets_cleaner_as_costs_fall(cfg, w):
    rid = "MEA"
    before = regions.clean_additions(cfg, w, rid)
    gdp = w.regions[rid].gdp
    regions.apply(w, cfg, 1)
    assert w.regions[rid].gdp > gdp
    for s in cfg.tuning["regions"]["cost_sources"]:
        w.tech_state[s] *= 8  # three doublings of world deployment
    assert regions.clean_additions(cfg, w, rid) > before


def test_the_carbon_club_pulls_regions_toward_clean(cfg, w):
    rid = "SEA"
    w.blocs["carbon_club"] = []
    alone = regions.clean_additions(cfg, w, rid)
    w.blocs["carbon_club"] = sorted(w.nations)
    assert regions.clean_additions(cfg, w, rid) > alone


def test_clean_share_never_passes_the_ceiling(cfg, w):
    r = w.regions["EUR"]
    r.clean, r.fossil = 100.0, 1.0
    regions.apply(w, cfg, 1)
    assert r.clean / (r.clean + r.fossil) <= regions.ceiling(cfg, w) + 1e-9


# --- financing ------------------------------------------------------------------------------------


def test_finance_builds_displaces_fossil_repays_and_earns_credit(cfg, w):
    rid, n = "SEA", w.nations["AAA"]
    most = regions.room(cfg, w, rid) / regions.delivered_per_trillion(cfg, w, "solar")
    amount = most / 2
    trust = w.regions[rid].trust["AAA"]
    [r] = act(cfg, w, "AAA", {"type": "finance_region", "region": rid, "source": "solar",
                              "amount": amount})  # fmt: skip
    assert r["ok"], r
    assert w.regions[rid].trust["AAA"] > trust
    assert w.regions[rid].financed["AAA"] == pytest.approx(amount)
    [p] = w.region_projects
    fossil = w.regions[rid].fossil
    w.t = p["online"]
    regions.complete(cfg, w)
    assert w.regions[rid].fossil == pytest.approx(fossil - p["delivered"])
    capital, credit = n.capital, n.climate_credit.get("financed", 0.0)
    regions.apply(w, cfg, 1)
    assert n.capital == pytest.approx(capital + amount * regions.payment_rate(cfg) / 4)
    assert n.climate_credit["financed"] > credit
    w.t = p["end"]
    capital = n.capital
    regions.apply(w, cfg, 1)
    assert n.capital == capital  # repaid in full


def test_regions_absorb_only_so_much_and_max_takes_the_rest(cfg, w):
    rid = "CAS"
    [r] = act(cfg, w, "AAA", {"type": "finance_region", "region": rid, "source": "solar",
                              "amount": "max"})  # fmt: skip
    assert r["ok"], r
    assert regions.room(cfg, w, rid) == pytest.approx(0.0, abs=1e-9)
    [r] = act(cfg, w, "BBB", {"type": "finance_region", "region": rid, "source": "solar",
                              "amount": 0.01})  # fmt: skip
    assert not r["ok"] and "can take only" in r["reason"]
    w.t += regions.window(cfg) + 1
    assert regions.room(cfg, w, rid) > 0  # the window rolls on


def test_bad_parameters_are_rejected(cfg, w):
    for bad in ({"region": "XXX", "source": "solar"}, {"region": "SEA", "source": "coal"}):
        [r] = act(cfg, w, "AAA", {"type": "finance_region", "amount": 0.001} | bad)
        assert not r["ok"]


def test_trusted_lenders_sell_more_equipment(cfg, w):
    rid = "SEA"
    neutral = regions.supplier_weights(cfg, w, rid, "solar")
    w.regions[rid].trust["AAA"] = 1.0
    tilted = regions.supplier_weights(cfg, w, rid, "solar")
    if neutral.get("AAA", 0.0) > 0:
        assert tilted["AAA"] > neutral["AAA"]
    assert sum(tilted.values()) == pytest.approx(1.0)


def test_financed_equipment_counts_as_exports(cfg, w):
    w.nations["AAA"].factory_capacity["solar"] = 1.0  # a big solar maker
    act(cfg, w, "BBB", {"type": "finance_region", "region": "SEA", "source": "solar",
                        "amount": "max"})  # fmt: skip
    p = w.region_projects[0]
    while w.t < p["online"]:
        w = turn.step(w, cfg, ai=False)
    w = turn.step(w, cfg, ai=False)
    assert p["online"] <= w.t
    assert w.nations["AAA"].cleantech_exports > 0


# --- AI and screen --------------------------------------------------------------------------------


def test_ai_nations_finance_regions_within_limits():
    real = config.load()
    world = new_world(real, seed=1)
    for _ in range(12):
        world = turn.step(world, real)
    assert world.region_projects
    for rid in world.regions:
        assert regions.room(real, world, rid) >= -1e-9


def test_screen_shows_regions(cfg):
    game = Game.new(cfg, "AAA", seed=1)
    game.wait(1)
    obs = view.observe(game)
    assert len(obs["regions"]) == 7
    text = view.render(obs)
    assert "REGIONS" in text and "room now" in text
    assert "can still finance now" in view.render(obs, brief=True)


# --- M15b: minor-nation events --------------------------------------------------------------------


def _open(w, kind, region, target=0.1):
    from sim import events

    event = {
        "id": f"E{len(w.minor_events) + 1}", "type": kind, "region": region, "target": target,
        "opened": w.t, "deadline": w.t + 8, "status": events.OPEN, "closed": -1, "pledges": {},
    }  # fmt: skip
    w.minor_events.append(event)
    return event


def test_events_are_seeded_and_replay():
    real = config.load()
    a, b = new_world(real, seed=3), new_world(real, seed=3)
    for _ in range(40):
        a, b = turn.step(a, real), turn.step(b, real)
    assert a.minor_events and a.minor_events == b.minor_events
    assert a.hash() == b.hash()


def test_full_pledges_fund_the_event_and_reward_contributors(cfg, w):
    from sim import events

    e = _open(w, "oil_discovery", "LAC")
    trust = w.regions["LAC"].trust["AAA"]
    [r] = act(cfg, w, "AAA", {"type": "pledge_to_event", "event_id": e["id"], "amount": "max"})
    assert r["ok"] and r["action"]["amount"] == pytest.approx(e["target"])
    [r] = act(cfg, w, "BBB", {"type": "pledge_to_event", "event_id": e["id"], "amount": 0.01})
    assert not r["ok"] and "needs only" in r["reason"]
    emissions = w.regions["LAC"].extra_co2
    events.apply_minor(w, cfg, 1)
    assert e["status"] == events.FUNDED
    assert w.regions["LAC"].trust["AAA"] > trust
    assert w.regions["LAC"].extra_co2 == emissions
    credit = w.nations["AAA"].climate_credit.get("financed", 0.0)
    events.apply_minor(w, cfg, 1)
    assert w.nations["AAA"].climate_credit["financed"] > credit  # credit keeps flowing


def test_short_funds_are_refunded_and_the_outcome_happens(cfg, w):
    from sim import events

    e = _open(w, "oil_discovery", "SSA")
    capital = w.nations["AAA"].capital
    act(cfg, w, "AAA", {"type": "pledge_to_event", "event_id": e["id"], "amount": 0.02})
    gdp = w.regions["SSA"].gdp
    w.t = e["deadline"]
    events.apply_minor(w, cfg, 1)
    assert e["status"] == events.FAILED
    assert w.nations["AAA"].capital == pytest.approx(capital)  # refunded
    assert w.regions["SSA"].extra_co2 > 0 and w.regions["SSA"].gdp > gdp
    regions.apply(w, cfg, 1)
    r = w.regions["SSA"]
    assert r.emissions == pytest.approx(r.fossil * cfg.reg("SSA", "fossil_ef") + r.extra_co2)


def test_each_outcome(cfg, w):
    from sim import events

    for kind, rid in (("rainforest", "LAC"), ("coal_pipeline", "SEA"),
                      ("adaptation_appeal", "SSA")):  # fmt: skip
        e = _open(w, kind, rid)
        before = (w.regions[rid].fossil, w.regions[rid].gdp, dict(w.regions[rid].trust))
        w.t = e["deadline"]
        events.apply_minor(w, cfg, 1)
        if kind == "coal_pipeline":
            assert w.regions[rid].fossil > before[0]
        if kind == "adaptation_appeal":
            assert w.regions[rid].gdp < before[1]
            assert all(w.regions[rid].trust[k] < v for k, v in before[2].items())
    extra = cfg.value("events", "events.types.rainforest.co2")
    assert w.base["land_use_extra"] == pytest.approx(extra)
    without = climate.exogenous_co2(cfg, w)["land_use"]
    w.base["land_use_extra"] = 0.0
    assert climate.exogenous_co2(cfg, w)["land_use"] == pytest.approx(without - extra)


def test_funded_coal_plan_builds_solar_instead(cfg, w):
    from sim import events

    e = _open(w, "coal_pipeline", "SEA", target=0.05)
    act(cfg, w, "AAA", {"type": "pledge_to_event", "event_id": e["id"], "amount": 0.05})
    clean, fossil = w.regions["SEA"].clean, w.regions["SEA"].fossil
    events.apply_minor(w, cfg, 1)
    assert w.regions["SEA"].clean > clean and w.regions["SEA"].fossil == fossil


def test_pledges_to_closed_or_unknown_events_are_rejected(cfg, w):
    [r] = act(cfg, w, "AAA", {"type": "pledge_to_event", "event_id": "E99", "amount": 0.01})
    assert not r["ok"]


def test_ai_pledges_by_personality_but_leaves_a_gap():
    """With every nation run by the AI, funds fall short of the target, so a player's pledge
    decides; fossil defenders give least."""
    from sim import events

    real = config.load()
    world = new_world(real, seed=2)
    while not any(e["status"] != events.OPEN for e in world.minor_events):
        world = turn.step(world, real)
    e = next(e for e in world.minor_events if e["status"] != events.OPEN)
    assert 0.5 < events.pledged(e) / e["target"] < 1.0
    assert e["pledges"]["EUU"] > e["pledges"].get("SAU", 0.0)


def test_screen_and_notices_show_events(cfg):
    from sim import events

    game = Game.new(cfg, "AAA", seed=1)
    game.wait(1)
    _open(game.world, "rainforest", "LAC")
    obs = view.observe(game)
    assert obs["events"]["open"][0]["id"] == "E1"
    assert "EVENTS" in view.render(obs) and "rainforest" in view.render(obs)
    game.world.minor_events[0]["deadline"] = game.world.t
    game.wait(1)
    assert any("Event E1 failed" in x for x in game.notices)
    assert events.find(game.world, "E1")["status"] == events.FAILED
