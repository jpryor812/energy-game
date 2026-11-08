"""Emissions -> warming -> damage.

Global CO2 each step = the modelled nations' net CO2 (energy CO2 minus carbon removal) + rest of
world energy CO2 + land-use CO2 + other fossil CO2 (cement, flaring).

- The rest of the world decarbonises in step with the 16 nations: its energy CO2 grows at
  `rest_of_world_growth` but is scaled by the 16 nations' carbon intensity of energy relative to
  2025 (clean technology spreads).
- Land-use CO2 follows its trend, cut by the global forest fund (`fund_forests` actions): up to
  `forest_max_cut` of it (above 1, land turns into a net sink), half at `forest_half_fund` T$.
- Other fossil CO2 is held constant.

Warming (M4b) has two parts:

    warming = W_co2 + TCRE x cumulative CO2 since 2025               (long-lived)
            + W_ch4 x methane index - W_aer x aerosol index + W_other  (short-lived)

W_co2 is chosen so 2025 warming is `warming_start`. The methane index relaxes toward current
methane emissions (relative to 2025) with a `ch4_lifetime` e-folding time; fossil methane
(`ch4_fossil_share`) follows world fossil production, the rest follows population; both can be
cut by `methane_abatement`. The aerosol index follows coal and oil burning and a clean-air trend,
with no delay, so stopping coal briefly warms. Deep cuts lower warming within years; net-negative
CO2 (carbon removal, forests) lowers it for good.

Damage, as a drag on annual GDP growth, = vulnerability x coefficient x (warming rise since
2025)^2, because baseline growth already reflects 2025 damages; adaptation spending reduces it.

Units: MtCO2/yr and MtCO2; TCRE is stated in degC per 1000 GtCO2.
"""

from __future__ import annotations

from typing import Any

from sim.config import FUELS, Config
from sim.state import Nation, World

MT_PER_1000_GT = 1e6


def _c(cfg: Config, name: str) -> Any:
    return cfg.tune(f"climate.{name}")


def co2_per_mt(cfg: Config) -> float:
    """degC per MtCO2 (long-lived part only)."""
    return _c(cfg, "tcre") / MT_PER_1000_GT


def short_lived_2025(cfg: Config) -> float:
    return _c(cfg, "ch4_warming") - _c(cfg, "aerosol_warming") + _c(cfg, "other_warming")


def warming_from(
    cfg: Config, cumulative_mt: float, ch4: float = 1.0, aerosol: float = 1.0
) -> float:
    """Warming for a cumulative CO2 since 2025 and methane and aerosol indices (2025 = 1)."""
    co2 = _c(cfg, "warming_start") - short_lived_2025(cfg) + co2_per_mt(cfg) * cumulative_mt
    short = _c(cfg, "ch4_warming") * ch4 - _c(cfg, "aerosol_warming") * aerosol
    return co2 + short + _c(cfg, "other_warming")


# --- the rest of the world, land use, methane, aerosols ------------------------------------------


def carbon_intensity(world: World) -> float:
    """The 16 nations' gross energy CO2 (before removal) per unit of energy delivered (Mt/EJ)."""
    co2 = sum(n.emissions + n.removals for n in world.nations.values())
    delivered = sum(sum(n.supply.values()) for n in world.nations.values())
    return co2 / delivered if delivered > 0 else 0.0


def forest_cut(cfg: Config, world: World) -> float:
    """Share of land-use CO2 removed by the forest fund (can exceed 1: a net sink)."""
    fund = world.forest_fund
    if fund <= 0:
        return 0.0
    return _c(cfg, "forest_max_cut") * fund / (fund + _c(cfg, "forest_half_fund"))


def exogenous_co2(cfg: Config, world: World) -> dict[str, float]:
    years = world.t / 4
    base_ci = world.base.get("carbon_intensity", 0.0)
    ci_ratio = carbon_intensity(world) / base_ci if base_ci > 0 else 1.0
    land = _c(cfg, "land_use_co2") * (1 + _c(cfg, "land_use_trend")) ** years
    return {
        "rest_of_world": _c(cfg, "rest_of_world_co2")
        * (1 + _c(cfg, "rest_of_world_growth")) ** years
        * ci_ratio,
        "land_use": land * (1 - forest_cut(cfg, world)),
        "other_fossil": _c(cfg, "other_fossil_co2"),
    }


def abatement(cfg: Config, n: Nation, kind: str) -> float:
    """Share of a nation's fossil or other methane its abatement spending removes."""
    if n.methane_abatement <= 0:
        return 0.0
    half = _c(cfg, "abatement_half_spend") * n.gdp
    return _c(cfg, f"abatement_max_{kind}") * n.methane_abatement / (n.methane_abatement + half)


def methane_emissions_index(cfg: Config, world: World) -> float:
    """Current methane emissions relative to 2025 (the rest of the world moves with the 16)."""
    fossil_now = sum(
        sum(n.fossil_production.get(f, 0.0) for f in FUELS) * (1 - abatement(cfg, n, "fossil"))
        for n in world.nations.values()
    )
    pop = sum(n.population for n in world.nations.values())
    other_now = sum(n.population * (1 - abatement(cfg, n, "other")) for n in world.nations.values())
    years = world.t / 4
    fossil = fossil_now / world.base["fossil_production"]
    other = other_now / pop * (1 + _c(cfg, "other_methane_trend")) ** years
    share = _c(cfg, "ch4_fossil_share")
    return share * fossil + (1 - share) * other


def aerosol_index(cfg: Config, world: World) -> float:
    """Coal and oil burning relative to 2025, times the clean-air trend."""
    burning = sum(
        n.supply.get("coal", 0.0) + n.supply.get("oil", 0.0) for n in world.nations.values()
    )
    trend = (1 + _c(cfg, "aerosol_trend")) ** (world.t / 4)
    return burning / world.base["aerosol_burning"] * trend


def init(cfg: Config, world: World) -> None:
    """2025 reference values for the responsive paths."""
    world.base["carbon_intensity"] = carbon_intensity(world)
    world.base["fossil_production"] = sum(
        sum(n.fossil_production.get(f, 0.0) for f in FUELS) for n in world.nations.values()
    )
    world.base["aerosol_burning"] = sum(
        n.supply.get("coal", 0.0) + n.supply.get("oil", 0.0) for n in world.nations.values()
    )
    world.methane_index = 1.0


# --- the step ------------------------------------------------------------------------------------


def apply(world: World, cfg: Config, dt: int) -> None:
    nations = sum(world.nations[nid].emissions for nid in sorted(world.nations))
    exo = exogenous_co2(cfg, world)
    total = nations + sum(exo.values())
    world.global_emissions = total
    world.global_cumulative_emissions += total * dt / 4

    relax = 1 - (1 - 1 / _c(cfg, "ch4_lifetime")) ** (dt / 4)
    world.methane_index += relax * (methane_emissions_index(cfg, world) - world.methane_index)
    world.aerosol_index = aerosol_index(cfg, world)
    world.warming = warming_from(
        cfg, world.global_cumulative_emissions, world.methane_index, world.aerosol_index
    )

    if world.forest_fund > 0:
        avoided = (
            _c(cfg, "land_use_co2") * (1 + _c(cfg, "land_use_trend")) ** (world.t / 4)
        ) - exo["land_use"]
        weight = cfg.tune("credits.weight_financed")
        for n in world.nations.values():
            if n.forest_paid > 0:
                credit = weight * avoided * n.forest_paid / world.forest_fund * dt / 4
                n.climate_credit["financed"] = n.climate_credit.get("financed", 0.0) + credit

    for nid in sorted(world.nations):
        n = world.nations[nid]
        vuln = cfg.nat(nid, "climate.vulnerability")
        n.climate_damage = (
            damage(cfg, vuln, world.warming)
            * adaptation_factor(cfg, n)
            * cfg.level(world.difficulty, "damage")
        )


def damage(cfg: Config, vulnerability: float, warming: float) -> float:
    rise = max(0.0, warming - _c(cfg, "warming_start"))
    return vulnerability * _c(cfg, "damage_coefficient") * rise**2


def adaptation_factor(cfg: Config, n: Nation) -> float:
    """Share of damage left after adaptation: falls toward 1 - adaptation_max as the adaptation
    stock grows relative to GDP."""
    half = _c(cfg, "adaptation_half_spend") * n.gdp
    return 1 - _c(cfg, "adaptation_max") * n.adaptation / (n.adaptation + half)
