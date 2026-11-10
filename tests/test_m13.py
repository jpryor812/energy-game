"""M13: technology licensing."""

import pytest

from sim import actions, diplomacy, research
from sim.scenario import new_world


@pytest.fixture
def w(cfg):
    world = new_world(cfg, seed=1)
    world.player = "AAA"
    for n in world.nations.values():
        n.slots_banked = {"domestic": 6, "diplomatic": 4}
        n.capital = 10.0
    world.nations["AAA"].techs = ["next_gen_solar"]
    world.tech_firsts["next_gen_solar"] = ["AAA", 0]
    return world


def act(cfg, w, nid, *acts):
    return actions.resolve(cfg, w, nid, list(acts))


def test_player_tech_is_not_for_sale_until_priced(cfg, w):
    assert research.license_price(cfg, w, "AAA", "BBB", "next_gen_solar") is None
    [r] = act(cfg, w, "AAA", {"type": "set_license_price", "tech": "next_gen_solar", "price": 0.2})
    assert r["ok"], r
    assert research.license_price(cfg, w, "AAA", "BBB", "next_gen_solar") == pytest.approx(0.2)


def test_buying_pays_the_seller_and_grants_the_tech(cfg, w):
    act(cfg, w, "AAA", {"type": "set_license_price", "tech": "next_gen_solar", "price": 0.2})
    seller, buyer = w.nations["AAA"].capital, w.nations["BBB"].capital
    buy = {"type": "buy_license", "tech": "next_gen_solar", "seller": "AAA"}
    [r] = act(cfg, w, "BBB", buy)
    assert r["ok"], r
    assert w.nations["AAA"].capital == pytest.approx(seller + 0.2)
    assert w.nations["BBB"].capital == pytest.approx(buyer - 0.2)
    assert research.has(w.nations["BBB"], "next_gen_solar")
    assert not research.researched(w.nations["BBB"], "next_gen_solar")  # cannot resell
    [r] = act(cfg, w, "BBB", {"type": "set_license_price", "tech": "next_gen_solar", "price": 0.1})
    assert not r["ok"]


def test_exclusion_refuses_and_costs_trust(cfg, w):
    trust = diplomacy.trust(w, "BBB", "AAA")
    setting = {"type": "set_license_price", "tech": "next_gen_solar", "price": 0.2}
    act(cfg, w, "AAA", setting | {"exclude": ["BBB"]})
    assert research.license_price(cfg, w, "AAA", "BBB", "next_gen_solar") is None
    assert diplomacy.trust(w, "BBB", "AAA") < trust
    [r] = act(cfg, w, "BBB", {"type": "buy_license", "tech": "next_gen_solar", "seller": "AAA"})
    assert not r["ok"] and "will not sell" in r["reason"]


def test_patents_expire_into_free_licences(cfg, w):
    act(cfg, w, "AAA", {"type": "set_license_price", "tech": "next_gen_solar", "price": None,
                        "exclude": ["BBB"]})  # fmt: skip
    w.t = int(cfg.tune("license.patent_years") * 4)
    assert research.patent_expired(cfg, w, "next_gen_solar")
    assert research.license_price(cfg, w, "AAA", "BBB", "next_gen_solar") == 0.0


def test_ai_seller_prices_below_research_and_refuses_the_distrusted(cfg, w):
    w.player = None
    price = research.license_price(cfg, w, "AAA", "BBB", "next_gen_solar")
    full = research.research_cost_for(cfg, w, w.nations["BBB"], "next_gen_solar")
    assert 0 < price < full
    diplomacy.adjust(w, "AAA", "BBB", -1.0)  # AAA no longer trusts BBB
    assert research.license_price(cfg, w, "AAA", "BBB", "next_gen_solar") is None


def test_buyer_needs_the_prerequisites(cfg, w):
    a = w.nations["AAA"]
    a.techs = ["advanced_batteries", "long_duration_storage"]
    a.license_prices["long_duration_storage"] = 0.1
    buy = {"type": "buy_license", "tech": "long_duration_storage", "seller": "AAA"}
    [r] = act(cfg, w, "BBB", buy)
    assert not r["ok"] and "advanced_batteries" in r["reason"]
