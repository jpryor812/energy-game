"""The quarterly pipeline.

`step` is pure: it deep-copies the world, runs the twelve stages in order, and returns the new
world. `t` counts quarters; `dt` is the number of quarters one call covers (1 now; 4 for the
planned annual mode), so annual mode can reuse the same rules.

In M0 every stage is a no-op except the scoring snapshot, which appends a history record.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sim import events
from sim.config import Config
from sim.state import World

QUARTERS_PER_YEAR = 4  # definitional, not a tunable


@dataclass
class TurnContext:
    dt: int
    actions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    stocktake: bool = False


Stage = Callable[[World, Config, TurnContext], None]


def quarter_label(t: int, start_year: int) -> str:
    return f"{start_year + t // QUARTERS_PER_YEAR}Q{t % QUARTERS_PER_YEAR + 1}"


def stocktake_due(t: int, dt: int, interval: int) -> bool:
    """True if any quarter covered by this step ends a stocktake period (t % 20 == 19)."""
    return any(q % interval == interval - 1 for q in range(t, t + dt))


# --- stages (order matters; see docs/BUILD_SIM_V0.md) -------------------------------------------


def income_and_slots(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M2: capital from GDP, deals, exports minus debt service; bank action slots."""


def collect_actions(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M3: AI nations add their actions to ctx.actions (player/bot actions arrive pre-filled)."""


def resolve_actions(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M2: validate and apply actions; queue construction and research."""
    submitted = {nid: acts for nid, acts in ctx.actions.items() if acts}
    if submitted:
        raise NotImplementedError(f"actions are not implemented until M2: {sorted(submitted)}")


def construction(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M1: advance pipelines, bring capacity online, retire plants."""


def energy_dispatch(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M1: merit-order dispatch; shortfall, imports, curtailment, emissions."""


def economy(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M1: GDP growth, approval, stability."""


def climate(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M1: global emissions -> warming -> damage per nation."""


def technology(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M1: cumulative deployment, learning curves, research."""


def diplomacy(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M4: proposals, trust, deal flows, tariffs, blocs."""


def stocktake(world: World, cfg: Config, ctx: TurnContext) -> None:
    """M4: compare emissions with fair share and apply consequences. Runs only when due."""
    if not ctx.stocktake:
        return


def scoring_snapshot(world: World, cfg: Config, ctx: TurnContext) -> None:
    start_year = cfg.value("tuning", "time.start_year")
    world.history.append(
        {
            "t": world.t,
            "label": quarter_label(world.t, start_year),
            "stocktake": ctx.stocktake,
            "global_cumulative_emissions": world.global_cumulative_emissions,
            "warming": world.warming,
            "nations": {
                nid: {"gdp": n.gdp, "capital": n.capital, "emissions": n.emissions}
                for nid, n in sorted(world.nations.items())
            },
        }
    )


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
) -> World:
    """Advance the world by `dt` quarters and return the new world. The input is not modified."""
    if dt < 1:
        raise ValueError("dt must be a positive number of quarters")
    new = copy.deepcopy(world)
    interval = cfg.value("tuning", "time.stocktake_interval")
    ctx = TurnContext(
        dt=dt,
        actions=copy.deepcopy(actions or {}),
        stocktake=stocktake_due(new.t, dt, interval),
    )
    for _name, stage in STAGES:
        stage(new, cfg, ctx)
    new.t += dt
    return new
