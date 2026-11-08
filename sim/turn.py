"""The quarterly pipeline.

`step` is pure: it deep-copies the world, runs the twelve stages in order, and returns the new
world. `t` counts quarters; `dt` is the number of quarters one call covers (1 now; 4 for the
planned annual mode), so annual mode can reuse the same rules.

Income, AI decisions, actions, construction (with the market builder for every nation),
dispatch and trade, economy (with goods trade), climate, technology, diplomacy (trust, deals,
credit market), the five-yearly stocktake and the snapshot all run.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sim import actions as acts
from sim import ai, credits, deals, energy, events, tech, trade
from sim import climate as climate_model
from sim import construction as build
from sim import diplomacy as diplo
from sim import economy as econ
from sim.config import Config
from sim.state import World

QUARTERS_PER_YEAR = 4  # definitional, not a tunable


@dataclass
class TurnContext:
    dt: int
    actions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    stocktake: bool = False
    results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    completed: dict[str, float] = field(default_factory=dict)
    ai: bool = True
    logs: dict[str, Any] = field(default_factory=dict)


Stage = Callable[[World, Config, TurnContext], None]


def quarter_label(t: int, start_year: int) -> str:
    return f"{start_year + t // QUARTERS_PER_YEAR}Q{t % QUARTERS_PER_YEAR + 1}"


def stocktake_due(t: int, dt: int, interval: int) -> bool:
    """True if any quarter covered by this step ends a stocktake period (t % 20 == 19)."""
    return any(q % interval == interval - 1 for q in range(t, t + dt))


# --- stages (order matters; see docs/BUILD_SIM_V0.md) -------------------------------------------


def income_and_slots(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Capital, political capital and action slots for the quarter."""
    econ.apply_income(world, cfg, ctx.dt)


def collect_actions(world: World, cfg: Config, ctx: TurnContext) -> None:
    """AI nations decide, all from the same start-of-quarter state, so moves are simultaneous.
    Nations whose actions arrived pre-filled (the player or a bot) are not touched."""
    if not ctx.ai:
        return
    for nid in sorted(world.nations):
        if nid not in ctx.actions:
            ctx.actions[nid] = ai.decide(cfg, world, nid)


def resolve_actions(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Validate and apply each nation's actions; rejected actions are logged, not raised."""
    for nid in sorted(ctx.actions):
        if nid not in world.nations:
            raise ValueError(f"actions submitted for unknown nation '{nid}'")
        ctx.results[nid] = acts.resolve(cfg, world, nid, ctx.actions[nid])


def construction(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Retire plants, bring finished capacity online, run the market builder."""
    ctx.completed = build.apply(world, cfg, ctx.dt)


def energy_dispatch(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Dispatch (shortfall, curtailment, emissions), then fossil trade."""
    energy.apply_dispatch(world, cfg, ctx.dt)
    energy.apply_trade(world, cfg)
    for nid in sorted(world.nations):
        world.nations[nid].energy_price = tech.delivered_price(cfg, world, world.nations[nid])


def economy(world: World, cfg: Config, ctx: TurnContext) -> None:
    """GDP growth, population, energy intensity, FX, approval, stability."""
    econ.apply_growth(world, cfg, ctx.dt)


def climate(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Global emissions -> warming -> damage per nation."""
    climate_model.apply(world, cfg, ctx.dt)


def technology(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Cumulative global deployment for learning curves. Research arrives in M2."""
    tech.apply(world, cfg, ctx.completed)


def diplomacy(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Trust drifts back toward neutral, deals pay and earn credit, the credit market clears."""
    diplo.revert_trust(world, cfg, ctx.dt)
    deals.service(cfg, world, ctx.dt)
    issued = credits.issue(cfg, world, ctx.dt)
    ctx.logs["credit_market"] = credits.clear(cfg, world) | {"issued": issued}
    for n in world.nations.values():
        stock = n.exported_cut_rate * ctx.dt / 4 * cfg.tune("credits.weight_exported")
        n.climate_credit["exported"] = n.climate_credit.get("exported", 0.0) + stock


def stocktake(world: World, cfg: Config, ctx: TurnContext) -> None:
    """Compare each nation's emissions with its fair share and apply consequences. Runs every
    five years."""
    if not ctx.stocktake:
        return
    ctx.logs["stocktake"] = diplo.run_stocktake(cfg, world)


def scoring_snapshot(world: World, cfg: Config, ctx: TurnContext) -> None:
    start_year = cfg.value("tuning", "time.start_year")
    world.history.append(
        {
            "t": world.t,
            "label": quarter_label(world.t, start_year),
            "stocktake": ctx.logs.get("stocktake") if ctx.stocktake else None,
            "credit_market": ctx.logs.get("credit_market"),
            "club": list(trade.club_members(world)),
            "coalition_tariffs": dict(world.coalition_tariffs),
            "global_emissions": world.global_emissions,
            "global_cumulative_emissions": world.global_cumulative_emissions,
            "warming": world.warming,
            "nations": {
                nid: _nation_record(n, ctx.results.get(nid, []))
                for nid, n in sorted(world.nations.items())
            },
        }
    )


def _nation_record(n, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "actions": results,
        "political_capital": n.political_capital,
        "influence": n.influence,
        "carbon_price": n.carbon_price,
        "import_dependence": n.import_dependence,
        "clean_built": n.clean_built,
        "tariffs": dict(n.tariffs),
        "goods_exports": n.goods_exports,
        "cleantech_exports": n.cleantech_exports,
        "credit_balance": n.credit_balance,
        "climate_credit": dict(n.climate_credit),
        "fair_share_budget": n.fair_share_budget,
        "period_emissions": n.period_emissions,
        "gdp": n.gdp,
        "population": n.population,
        "growth": n.growth,
        "capital": n.capital,
        "demand": n.demand,
        "supply": dict(n.supply),
        "shortfall": n.shortfall,
        "curtailment": n.curtailment,
        "energy_price": n.energy_price,
        "emissions": n.emissions,
        "export_revenue": n.export_revenue,
        "fx_reserves": n.fx_reserves,
        "approval": n.approval,
        "stability": n.stability,
        "climate_damage": n.climate_damage,
    }


def events_hook(world: World, cfg: Config, ctx: TurnContext) -> None:
    events.on_turn(world, cfg)


STAGES: tuple[tuple[str, Stage], ...] = (
    ("income_and_slots", income_and_slots),
    ("actions", collect_actions),
    ("resolve_actions", resolve_actions),
    ("construction", construction),
    ("energy_dispatch", energy_dispatch),
    ("economy", economy),
    ("climate", climate),
    ("technology", technology),
    ("diplomacy", diplomacy),
    ("stocktake", stocktake),
    ("scoring_snapshot", scoring_snapshot),
    ("events", events_hook),
)


def step(
    world: World,
    cfg: Config,
    actions: dict[str, list[dict[str, Any]]] | None = None,
    dt: int = 1,
    ai: bool = True,
) -> World:
    """Advance the world by `dt` quarters and return the new world. The input is not modified.

    Nations without entries in `actions` are played by the AI unless `ai` is False (the
    business-as-usual reference, where only the market builds)."""
    if dt < 1:
        raise ValueError("dt must be a positive number of quarters")
    new = copy.deepcopy(world)
    interval = cfg.value("tuning", "time.stocktake_interval")
    ctx = TurnContext(
        dt=dt,
        actions=copy.deepcopy(actions or {}),
        stocktake=stocktake_due(new.t, dt, interval),
        ai=ai,
    )
    for _name, stage in STAGES:
        stage(new, cfg, ctx)
    new.t += dt
    return new
