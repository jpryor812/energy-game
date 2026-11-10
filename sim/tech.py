"""Learning curves, research, and levelized cost.

Unit cost C(n) = C0 x (n / n0)^(-b), where n is global cumulative deployment of the technology,
n0 its 2025 level (`global_installed`), and b = -log2(1 - learning_rate), so each doubling of
deployment cuts cost by `learning_rate`, never below `cost_floor` x C0 where a source sets one.

Global deployment grows by what the modelled nations build divided by their share of world
deployment (`coverage_share`), so the rest of the world builds in proportion. Enablers have no
coverage share and count only what the modelled nations build.

Research: a nation's cumulative research spending on a technology (T$) cuts its own unit cost for
it by up to `research.max_cost_cut`, with half of that at `research.half_effect_spend`.

Levelized cost ($/GJ of primary energy) = annualized capital cost per GJ of normal output
(after subsidy) + variable cost + carbon cost, plus a system cost for wind and solar that grows
with the square of their share of the nation's supply.
"""

from __future__ import annotations

import math

from sim import energy, research, trade
from sim.config import Config
from sim.state import Nation, World

DOLLARS_PER_GJ_YR_PER_UNIT = 1000.0  # 1 T$ per EJ/yr = $1000 per GJ/yr


def exponent(learning_rate: float) -> float:
    return -math.log2(1.0 - learning_rate)


def unit_cost(cfg: Config, world: World, source: str) -> float:
    """World unit cost, T$ per EJ/yr of capacity."""
    n0 = cfg.src(source, "global_installed")
    n = world.tech_state.get(source, n0)
    c0 = cfg.src(source, "capital_cost")
    if n0 <= 0 or n <= 0:
        return c0
    cost = c0 * (n / n0) ** (-exponent(cfg.src(source, "learning_rate")))
    floor = cfg.techs["sources"][source].get("cost_floor")
    return max(cost, floor["value"] * c0) if floor else cost


def at_floor(cfg: Config, world: World, source: str) -> bool:
    """Whether learning has pushed the world cost down to the source's floor (no further falls
    from deployment)."""
    floor = cfg.techs["sources"][source].get("cost_floor")
    if not floor:
        return False
    return unit_cost(cfg, world, source) <= floor["value"] * cfg.src(source, "capital_cost") + 1e-15


def research_multiplier(cfg: Config, nation: Nation, source: str) -> float:
    spent = nation.research.get(source, 0.0)
    half = cfg.tune("research.half_effect_spend")
    return 1.0 - cfg.tune("research.max_cost_cut") * spent / (spent + half)


def nation_unit_cost(cfg: Config, world: World, nation: Nation, source: str) -> float:
    """The nation's build cost: world cost, less its research, plus its tariff and content
    premiums."""
    premium = trade.cost_premium(cfg, world, nation.id, source)
    return (
        unit_cost(cfg, world, source)
        * research_multiplier(cfg, nation, source)
        * research.cost_multiplier(cfg, nation, source)  # M12 tech tree
        * (1 + premium)
    )


def crf(rate: float, years: float) -> float:
    """Capital recovery factor: annual payment per unit of capital over `years`."""
    return rate / (1 - (1 + rate) ** -years)


def capital_charge(cfg: Config, world: World, nation: Nation, source: str) -> float:
    """$/GJ of normal output to repay the build cost over the plant's life."""
    rate = cfg.tune("market.discount_rate")
    per_gj_yr = nation_unit_cost(cfg, world, nation, source) * DOLLARS_PER_GJ_YR_PER_UNIT
    headroom = cfg.src(source, "headroom") if cfg.category(source) != "enabler" else 1.0
    return per_gj_yr * crf(rate, cfg.src(source, "lifespan")) * headroom


def lcoe(cfg: Config, world: World, nation: Nation, source: str) -> float:
    subsidy = nation.subsidies.get(source, 0.0)
    cost = capital_charge(cfg, world, nation, source) * (1 - subsidy)
    cost += energy.marginal_cost(cfg, nation.id, source, nation.carbon_price)
    cost -= energy.production_credit(nation, source)
    if cfg.category(source) == "variable_renewable" and "grid" in cfg.source_ids:
        delivered = sum(nation.supply.values())
        vre = sum(nation.supply.get(s, 0.0) for s in cfg.vre_ids)
        share = vre / delivered if delivered > 0 else 0.0
        base = cfg.tune("energy.vre_base_absorb_share")
        cost += capital_charge(cfg, world, nation, "grid") * (share / base) ** 2
    return cost


def delivered_price(cfg: Config, world: World, nation: Nation) -> float:
    """Average cost of delivered energy, $/GJ: capital charge at today's unit costs plus fuel
    and carbon, less production tax credits, for each source dispatched, plus the grid and
    storage that support them."""
    delivered = sum(nation.supply.values())
    if delivered <= 0:
        return 0.0
    total = sum(
        q
        * (
            capital_charge(cfg, world, nation, s)
            + energy.marginal_cost(cfg, nation.id, s, nation.carbon_price)
            - energy.production_credit(nation, s)
        )
        for s, q in nation.supply.items()
    )
    for s in cfg.source_ids:
        if cfg.category(s) == "enabler":
            total += nation.capacity.get(s, 0.0) * capital_charge(cfg, world, nation, s)
    return total / delivered


def apply(world: World, cfg: Config, completed: dict[str, float]) -> None:
    for s in sorted(completed):
        coverage = 1.0
        if cfg.category(s) not in ("enabler", "removal"):
            coverage = cfg.src(s, "coverage_share")
        world.tech_state[s] = world.tech_state.get(s, 0.0) + completed[s] / coverage
