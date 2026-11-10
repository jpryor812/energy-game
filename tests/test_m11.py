"""M11: wind split into onshore and offshore; other renewables into bioenergy and geothermal."""

import sys
from pathlib import Path

import pytest
import yaml

from sim import actions, config, construction, trade
from sim.scenario import new_world

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "data_prep"))
from source_splits import GEOTHERMAL_SHARE, OFFSHORE_SHARE, split  # noqa: E402


def test_split_keeps_the_totals():
    values = {"wind": 2.0, "other_renewables": 1.0, "coal": 3.0}
    out = split("GBR", values)
    assert out["onshore_wind"] + out["offshore_wind"] == pytest.approx(2.0)
    assert out["offshore_wind"] == pytest.approx(2.0 * OFFSHORE_SHARE["GBR"])
    assert out["bioenergy"] + out["geothermal"] == pytest.approx(1.0)
    assert out["coal"] == 3.0 and "wind" not in out


def test_every_nation_has_the_new_sources_and_no_old_ones():
    cfg = config.load()
    for nid in cfg.nation_ids:
        energy = cfg.nat_spec(nid)["start"]["energy"]
        assert {"onshore_wind", "offshore_wind", "bioenergy", "geothermal"} <= set(energy)
        assert not {"wind", "other_renewables"} & set(energy)
        assert not {"wind", "other_renewables"} & set(cfg.nat_spec(nid)["bau"]["mix"])


def test_geothermal_needs_the_resource():
    cfg = config.load()
    have = {nid for nid in cfg.nation_ids if construction.has_resource(cfg, nid, "geothermal")}
    assert have == set(GEOTHERMAL_SHARE)
    assert "geothermal" not in construction.cost_candidates(cfg, "GBR")
    w = new_world(cfg, seed=1)
    n = w.nations["GBR"]
    n.slots_banked = {"domestic": 6, "diplomatic": 4}
    n.capital = 10.0
    [r] = actions.resolve(
        cfg, w, "GBR", [{"type": "build_capacity", "source": "geothermal", "amount": 0.1}]
    )
    assert not r["ok"] and "resource" in r["reason"]


def test_both_winds_buy_from_the_wind_factory_line():
    assert trade.EQUIPMENT_OF["onshore_wind"] == trade.EQUIPMENT_OF["offshore_wind"] == "wind"
    assert set(trade.EQUIPMENT_OF.values()) == set(trade.EQUIPMENT)


def test_offshore_wind_costs_more_and_builds_slower_than_onshore():
    cfg = config.load()
    assert cfg.src("offshore_wind", "capital_cost") > cfg.src("onshore_wind", "capital_cost")
    assert cfg.src("offshore_wind", "build_time") > cfg.src("onshore_wind", "build_time")
    assert set(cfg.vre_ids) == {"onshore_wind", "offshore_wind", "solar"}


def test_split_values_marked_placeholder_where_approximate():
    data = yaml.safe_load((ROOT / "data" / "countries.yaml").read_text())["nations"]
    gbr = data["GBR"]["start"]["energy"]
    assert gbr["offshore_wind"]["status"] == "placeholder"
    assert "M11 split" in gbr["offshore_wind"]["note"]
    usa = data["USA"]["start"]["energy"]
    assert usa["offshore_wind"]["value"] == 0.0
