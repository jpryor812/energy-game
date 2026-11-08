"""Cumulative emissions -> warming -> damage.

Global CO2 each step = the modelled nations' energy CO2 + rest of world energy CO2 + land-use CO2
+ other fossil CO2 (cement, flaring). The last three are exogenous paths.

Warming = warming at the start of 2025 + TCRE x (1 + non-CO2 multiplier) x cumulative CO2 since
2025. Damage, as a drag on annual GDP growth, = vulnerability x coefficient x (warming rise since
2025)^2, because baseline growth already reflects 2025 damages.

Units: MtCO2/yr and MtCO2; TCRE is stated in degC per 1000 GtCO2.
"""

from __future__ import annotations

from sim.config import Config
from sim.state import World

MT_PER_1000_GT = 1e6


def exogenous_co2(cfg: Config, t: int) -> dict[str, float]:
    years = t / 4
    c = "climate."
    return {
        "rest_of_world": cfg.tune(c + "rest_of_world_co2")
        * (1 + cfg.tune(c + "rest_of_world_growth")) ** years,
        "land_use": cfg.tune(c + "land_use_co2") * (1 + cfg.tune(c + "land_use_trend")) ** years,
        "other_fossil": cfg.tune(c + "other_fossil_co2"),
    }


def warming_from(cfg: Config, cumulative_mt: float) -> float:
    per_mt = cfg.tune("climate.tcre") * (1 + cfg.tune("climate.nonco2_multiplier")) / MT_PER_1000_GT
    return cfg.tune("climate.warming_start") + per_mt * cumulative_mt


def damage(cfg: Config, vulnerability: float, warming: float) -> float:
    rise = max(0.0, warming - cfg.tune("climate.warming_start"))
    return vulnerability * cfg.tune("climate.damage_coefficient") * rise**2


def apply(world: World, cfg: Config, dt: int) -> None:
    nations = sum(world.nations[nid].emissions for nid in sorted(world.nations))
    total = nations + sum(exogenous_co2(cfg, world.t).values())
    world.global_emissions = total
    world.global_cumulative_emissions += total * dt / 4
    world.warming = warming_from(cfg, world.global_cumulative_emissions)
    for nid in sorted(world.nations):
        vuln = cfg.nat(nid, "climate.vulnerability")
        world.nations[nid].climate_damage = damage(cfg, vuln, world.warming)
