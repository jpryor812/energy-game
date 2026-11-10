"""Energy dispatch and fossil-fuel trade.

Units: energy flows are rates in EJ/yr of primary energy (input-equivalent for non-fossil
sources); emissions are MtCO2/yr; prices are $/GJ; money is T$/yr.

Dispatch, per nation per step:

1. Demand = GDP x energy intensity x the seasonal factor for the quarter(s) covered.
2. Wind and solar run first. Output beyond what the grid can absorb (a base share of demand
   plus grid and storage capacity) is curtailed.
   Wind and solar can never serve more than the electrifiable share of demand, and all
   non-fossil sources together never more than the clean ceiling (end-use conversion limits).
3. Every other source has a *normal* output, capacity / headroom, which reproduces the
   2025 data mix at t=0. If normal output exceeds the remaining demand, the most expensive
   sources are cut first. If it falls short, headroom is used cheapest first. What is still
   unmet is shortfall. "Expensive" includes the carbon price, so carbon pricing shifts
   dispatch at the margin.

The `price` here is the variable (fuel + carbon) cost used for merit order; the nation's
reported energy price also includes capital costs (sim.tech.delivered_price).
"""

from __future__ import annotations

from dataclasses import dataclass

from sim import research
from sim.config import FUELS, Config
from sim.state import Nation, World

GJ_PER_EJ = 1e9
DOLLARS_PER_TRILLION = 1e12


@dataclass
class Dispatch:
    demand: float
    supply: dict[str, float]
    shortfall: float
    curtailment: float
    price: float
    emissions: float


def season_factor(cfg: Config, t: int, dt: int) -> float:
    factors = cfg.tune("seasonality.demand_factor")
    return sum(factors[q % 4] for q in range(t, t + dt)) / dt


def emission_factor(cfg: Config, nid: str, source: str) -> float:
    """MtCO2/EJ. Fossil fuels use the nation's own 2024 factor where the data gives one (oil
    feedstock shares and coal grades differ by country); otherwise the world factor."""
    own = cfg.nat_spec(nid).get("start", {}).get("emission_factor", {}).get(source)
    return own["value"] if own else cfg.src(source, "emission_factor")


def marginal_cost(cfg: Config, nid: str, source: str, carbon_price: float) -> float:
    """$/GJ: variable cost plus carbon price ($/t) x emission factor (Mt/EJ = kg/GJ)."""
    ef = emission_factor(cfg, nid, source)
    return cfg.src(source, "variable_cost") + carbon_price * ef / 1e3


def _ramp(cfg: Config, name: str, t: int) -> float:
    start = cfg.tune(f"energy.{name}_start")
    end = cfg.tune(f"energy.{name}_end")
    frac = min(1.0, max(0.0, t / max(1, cfg.tune("time.turns") - 1)))
    return start + (end - start) * frac


def electrification_bonus(cfg: Config, nation: Nation | None) -> float:
    """How far a nation's electrification programme has raised its ceilings."""
    if nation is None or nation.electrification <= 0:
        return 0.0
    half = cfg.tune("industrial_policy.electrification_half_spend") * nation.gdp
    top = cfg.tune("industrial_policy.electrification_max_bonus")
    return top * nation.electrification / (nation.electrification + half)


def vre_max_share(cfg: Config, t: int, nation: Nation | None = None) -> float:
    """Most of primary demand wind and solar can serve at turn t: the electrifiable share,
    rising linearly from 2025 to the final turn, plus the nation's electrification bonus."""
    bonus = electrification_bonus(cfg, nation) + research.hydrogen_bonus(cfg, nation)  # M12
    return min(1.0, _ramp(cfg, "vre_max_share", t) + bonus)


def clean_max_share(cfg: Config, t: int, nation: Nation | None = None) -> float:
    """Most of primary demand all non-fossil sources together can serve at turn t, standing in
    for end-use conversion (vehicles, heating, industry); rises linearly to the final turn, plus
    the nation's electrification bonus."""
    bonus = electrification_bonus(cfg, nation) + research.hydrogen_bonus(cfg, nation)  # M12
    return min(1.0, _ramp(cfg, "clean_max_share", t) + bonus)


def production_credit(nation: Nation, source: str) -> float:
    """The nation's production tax credit for a source, $/GJ."""
    return nation.tax_credits.get(f"generation:{source}", 0.0)


def is_fossil(cfg: Config, source: str) -> bool:
    return cfg.category(source) == "fossil"


def vre_absorb_limit(cfg: Config, nation: Nation, demand: float, t: int = 0) -> float:
    """EJ/yr of wind and solar the system can take without curtailment: a base share of demand
    plus grid and storage, never more than the electrifiable share."""
    enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
    limit = cfg.tune("energy.vre_base_absorb_share") * demand + sum(
        nation.capacity.get(s, 0.0) for s in enablers
    )
    return min(limit, vre_max_share(cfg, t, nation) * demand)


def dispatch(cfg: Config, nation: Nation, demand: float, t: int = 0) -> Dispatch:
    supply = {s: 0.0 for s in cfg.energy_source_ids}
    clean_cap = clean_max_share(cfg, t, nation) * demand

    vre = cfg.vre_ids
    vre_avail = sum(nation.capacity.get(s, 0.0) for s in vre)
    vre_used = min(vre_avail, vre_absorb_limit(cfg, nation, demand, t), demand, clean_cap)
    if vre_avail > 0:
        for s in vre:
            supply[s] = nation.capacity.get(s, 0.0) * vre_used / vre_avail
    curtailment = vre_avail - vre_used
    remaining = demand - vre_used

    others = [s for s in cfg.energy_source_ids if s not in vre]
    cost = {
        s: marginal_cost(cfg, nation.id, s, nation.carbon_price) - production_credit(nation, s)
        for s in others
    }
    by_cost = sorted(others, key=lambda s: (cost[s], s))
    normal = {s: nation.capacity.get(s, 0.0) / cfg.src(s, "headroom") for s in others}
    top = {s: nation.capacity.get(s, 0.0) for s in others}

    # Non-fossil dispatchables share what is left under the clean ceiling, cheapest first.
    room = max(0.0, clean_cap - vre_used)
    clean = [s for s in by_cost if not is_fossil(cfg, s)]
    for s in clean:
        normal[s] = min(normal[s], room)
        room -= normal[s]
    for s in clean:
        top[s] = normal[s] + min(top[s] - normal[s], room)
        room -= top[s] - normal[s]
    total_normal = sum(normal.values())

    if total_normal >= remaining:
        excess = total_normal - remaining
        for s in others:
            supply[s] = normal[s]
        for s in reversed(by_cost):
            cut = min(excess, supply[s])
            supply[s] -= cut
            excess -= cut
            if excess <= 0:
                break
        shortfall = 0.0
    else:
        need = remaining - total_normal
        for s in others:
            supply[s] = normal[s]
        for s in by_cost:
            extra = min(need, top[s] - normal[s])
            supply[s] += extra
            need -= extra
            if need <= 0:
                break
        shortfall = max(0.0, need)

    delivered = sum(supply.values())
    all_cost = {s: marginal_cost(cfg, nation.id, s, nation.carbon_price) for s in supply}
    price = sum(supply[s] * all_cost[s] for s in supply) / delivered if delivered > 0 else 0.0
    emissions = sum(
        supply[s] * emission_factor(cfg, nation.id, s) * research.capture_factor(cfg, nation, s)
        for s in supply
    )  # M12: carbon-capture retrofits
    return Dispatch(demand, supply, shortfall, curtailment, price, emissions)


def net_removal(cfg: Config, nation: Nation, d: Dispatch) -> float:
    """MtCO2/yr removed by the nation's carbon removal. Its energy is part of demand
    (`extra_demand`), so the CO2 from powering it is already in the nation's gross emissions."""
    if "carbon_removal" not in cfg.source_ids:
        return 0.0
    return nation.capacity.get("carbon_removal", 0.0)


def base_demand(nation: Nation) -> float:
    """Underlying demand rate before seasonality, EJ/yr: the economy's use plus energy for
    carbon removal."""
    return nation.gdp * nation.energy_intensity + nation.extra_demand


def apply_dispatch(world: World, cfg: Config, dt: int) -> None:
    """Dispatch every nation for the step and record emissions."""
    factor = season_factor(cfg, world.t, dt)
    for nid in sorted(world.nations):
        n = world.nations[nid]
        d = dispatch(cfg, n, base_demand(n) * factor, world.t)
        n.demand = d.demand
        n.supply = d.supply
        n.shortfall = d.shortfall
        n.curtailment = d.curtailment
        n.energy_price = d.price
        n.removals = net_removal(cfg, n, d)
        n.emissions = d.emissions - n.removals
        n.cumulative_emissions += d.emissions * dt / 4
        n.period_emissions += d.emissions * dt / 4


def global_fuel_use(world: World) -> dict[str, float]:
    return {f: sum(world.nations[nid].supply.get(f, 0.0) for nid in world.nations) for f in FUELS}


def apply_trade(world: World, cfg: Config) -> None:
    """Fossil trade.

    A base exporter (production above use in 2025) keeps its 2025 export volume scaled by world
    use of that fuel relative to 2025. A base importer keeps its 2025 self-sufficiency (domestic
    production / use) and imports the rest. Revenue and trade value use world fuel prices.
    """
    use = global_fuel_use(world)
    for nid in sorted(world.nations):
        n = world.nations[nid]
        revenue = 0.0
        for f in FUELS:
            consumed = n.supply.get(f, 0.0)
            base_exports = n.base.get(f"exports_{f}", 0.0)
            if base_exports > 0:
                ratio = use[f] / world.base[f"fuel_use_{f}"] if world.base[f"fuel_use_{f}"] else 0
                exports = base_exports * ratio
                n.fossil_exports[f] = exports
                n.fossil_imports[f] = 0.0
                n.fossil_production[f] = consumed + exports
            else:
                base_use = n.base.get(f"use_{f}", 0.0)
                share = n.base.get(f"production_{f}", 0.0) / base_use if base_use > 0 else 0.0
                production = consumed * min(1.0, share)
                n.fossil_production[f] = production
                n.fossil_exports[f] = 0.0
                n.fossil_imports[f] = consumed - production
            revenue += n.fossil_exports[f] * cfg.tune(f"energy.fuel_price.{f}")
        n.export_revenue = revenue * GJ_PER_EJ / DOLLARS_PER_TRILLION
        n.import_dependence = import_dependence(n)


def trade_balance(cfg: Config, nation: Nation) -> float:
    """Net fossil trade value, T$/yr (exports minus imports)."""
    value = sum(
        (nation.fossil_exports.get(f, 0.0) - nation.fossil_imports.get(f, 0.0))
        * cfg.tune(f"energy.fuel_price.{f}")
        for f in FUELS
    )
    return value * GJ_PER_EJ / DOLLARS_PER_TRILLION


def import_dependence(nation: Nation) -> float:
    delivered = sum(nation.supply.values())
    return sum(nation.fossil_imports.values()) / delivered if delivered > 0 else 0.0
