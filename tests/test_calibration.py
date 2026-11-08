"""Business-as-usual run on the real data, checked against published references.

The bands are deliberately loose: they catch a model that has drifted far from reality, not
small tuning changes. Each reference is listed in data/SOURCES.md.
"""

import pytest

from sim import climate, config, report

# GCB 2024 (via OWID): fossil CO2 38.6 Gt + land-use CO2 ~4.6 Gt.
GLOBAL_CO2_2025 = (41_000, 46_000)  # MtCO2/yr
# Forster et al. 2025: human-induced warming rate 0.27 [0.2-0.4] degC per decade.
WARMING_RATE = (0.20, 0.40)
# IEA WEO 2025 Current Policies Scenario: energy CO2 stays around 38 Gt to 2050 and warming
# passes 2 degC around 2050. BAU here is a frozen-trend baseline, so allow it to sit above.
ENERGY_CO2_2049 = (30_000, 48_000)
WARMING_2049 = (1.8, 2.4)


# AI-only world (M3): nations follow assumed target paths directionally, so it must land below
# the no-action baseline but not at a deep-cut path within 25 years.
AI_WARMING_2049 = (1.6, 2.0)


@pytest.fixture(scope="module")
def real():
    cfg = config.load()
    return cfg, report.bau_world(cfg)


def test_real_data_loads(real):
    cfg, _ = real
    assert len(cfg.nation_ids) == 16
    assert cfg.playable_ids == ["CHN", "EUU", "IND", "RUS", "USA", "VNM"]


def test_global_co2_2025(real):
    _, w = real
    total = report.annual(w.history, 2025, "global_emissions")
    assert GLOBAL_CO2_2025[0] < total < GLOBAL_CO2_2025[1]


def test_warming_rate(real):
    _, w = real
    end = {r["label"]: r["warming"] for r in w.history}
    rate = end["2035Q4"] - end["2025Q4"]
    assert WARMING_RATE[0] < rate < WARMING_RATE[1]


def test_2049_against_current_policies(real):
    cfg, w = real
    exo = climate.exogenous_co2(cfg, 99)
    energy_co2 = report.annual(w.history, 2049, "global_emissions") - exo["land_use"]
    energy_co2 -= exo["other_fossil"]
    assert ENERGY_CO2_2049[0] < energy_co2 < ENERGY_CO2_2049[1]
    assert WARMING_2049[0] < w.warming < WARMING_2049[1]


def test_bau_keeps_lights_on(real):
    _, w = real
    for r in w.history:
        for n in r["nations"].values():
            assert n["shortfall"] / n["demand"] < 0.01


def test_early_growth_tracks_imf(real):
    cfg, w = real
    for nid in cfg.nation_ids:
        g25 = report.annual(w.history, 2025, "gdp", nid)
        g30 = report.annual(w.history, 2030, "gdp", nid)
        realized = (g30 / g25) ** (1 / 5) - 1
        assert realized == pytest.approx(cfg.nat(nid, "trend.g0_start"), abs=0.005), nid


@pytest.fixture(scope="module")
def ai_real():
    cfg = config.load()
    return cfg, report.ai_world(cfg)


def test_ai_world_between_baseline_and_deep_cuts(real, ai_real):
    _, bau = real
    _, w = ai_real
    assert w.warming < bau.warming
    assert AI_WARMING_2049[0] < w.warming < AI_WARMING_2049[1]


def test_ai_world_keeps_lights_on(ai_real):
    _, w = ai_real
    worst = max(n["shortfall"] / n["demand"] for r in w.history for n in r["nations"].values())
    assert worst < 0.03


def test_ai_world_follows_targets_directionally(ai_real):
    """Ambitious-stance nations cut more than low-ambition ones."""
    _, w = ai_real

    def cut(nid):
        n = w.nations[nid]
        return 1 - n.emissions / n.base["emissions"]

    assert min(cut("EUU"), cut("GBR")) > max(cut("RUS"), cut("IND"))
