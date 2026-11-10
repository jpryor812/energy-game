"""Shared fixtures.

`fixture_dir` / `cfg` use the real tuning, techs and events files with a small synthetic
`countries.yaml` (two nations: an importer and a fuel exporter), so model tests do not depend on
real-world country data. Tests that check the real data use `config.load()` directly.
"""

from pathlib import Path

import pytest
import yaml

from sim import config


def tun(value, note="test fixture"):
    return {"value": value, "status": "placeholder", "note": note}


def _nation(playable, issuer, energy, production, gdp, mix, retire=None):
    spec = {
        "name": "Test",
        "playable": playable,
        "archetype": "test",
        "difficulty": "medium",
        "personality": None,
        "hard_currency_issuer": issuer,
        "start": {
            "gdp": tun(gdp),
            "population": tun(100.0),
            "fx_reserves": tun(0.5),
            "debt_hard": tun(0.1 * gdp),
            "debt_local": tun(0.4 * gdp),
            "carbon_price": tun(0.0),
            "export_openness": tun(0.25),
            "energy": {s: tun(v) for s, v in energy.items()},
            "production": {f: tun(v) for f, v in production.items()},
        },
        "trend": {
            "g0_start": tun(0.04),
            "g0_end": tun(0.02),
            "population_growth": tun(0.01),
            "intensity_decline": tun(0.015),
        },
        "climate": {"vulnerability": tun(1.0)},
        "bau": {"mix": {s: tun(v) for s, v in mix.items()}},
    }
    if retire:
        spec["bau"]["retire_rate"] = {s: tun(v) for s, v in retire.items()}
    return spec


FIXTURE_COUNTRIES = {
    "nations": {
        "AAA": _nation(
            playable=True,
            issuer=False,
            energy={
                "coal": 10.0,
                "oil": 8.0,
                "gas": 4.0,
                "nuclear": 1.0,
                "hydro": 1.0,
                "onshore_wind": 1.2,
                "offshore_wind": 0.3,
                "solar": 2.0,
                "bioenergy": 0.4,
                "geothermal": 0.1,
            },
            production={"coal": 9.0, "oil": 1.0, "gas": 2.0},
            gdp=4.0,
            mix={"coal": 0.3, "solar": 0.5, "onshore_wind": 0.2},
            retire={"oil": 0.05},
        ),
        "BBB": _nation(
            playable=False,
            issuer=False,
            energy={
                "coal": 1.0,
                "oil": 6.0,
                "gas": 6.0,
                "nuclear": 0.5,
                "hydro": 0.5,
                "onshore_wind": 0.2,
                "offshore_wind": 0.0,
                "solar": 0.3,
                "bioenergy": 0.1,
                "geothermal": 0.0,
            },
            production={"coal": 1.0, "oil": 15.0, "gas": 9.0},
            gdp=2.0,
            mix={"gas": 0.6, "solar": 0.4},
        ),
    }
}


FIXTURE_TARGETS = {
    "targets": {
        "AAA": {"years": tun([2035, 2050]), "levels": tun([0.8, 0.2])},
        "BBB": {"years": tun([2040, 2060]), "levels": tun([1.1, 0.5])},
    }
}


@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("data")
    for name in ("tuning", "techs", "events", "research"):
        src = config.DEFAULT_DATA_DIR / f"{name}.yaml"
        (d / f"{name}.yaml").write_text(src.read_text())
    (d / "countries.yaml").write_text(yaml.safe_dump(FIXTURE_COUNTRIES, sort_keys=True))
    (d / "targets.yaml").write_text(yaml.safe_dump(FIXTURE_TARGETS, sort_keys=True))
    return d


@pytest.fixture(scope="session")
def cfg(fixture_dir):
    return config.load(fixture_dir)
