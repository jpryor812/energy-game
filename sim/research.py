"""The tech tree (M12).

Each technology in data/research.yaml has a total cost (T$), a minimum research time
(quarters), prerequisites and an optional earliest year. A nation funds research with
`fund_research`; each quarter its progress rises by funding / cost, and at most 1 /
`min_quarters` per quarter, so a richer nation can reach the minimum time and a poorer one takes
longer. Progress never decays. A technology completes in the research stage once progress
reaches 1 and its earliest year has come.

Once any nation has finished a technology, research on it costs everyone else `spillover` less
(knowledge spreads). A finished technology works only for the nation that has it: cheaper or
faster builds of a source (`effects.cost`, `effects.build_time`), new sources it may build
(`unlocks`, the sources marked `requires` in data/techs.yaml), or abilities (`enables`, e.g.
carbon-capture retrofits).
"""

from __future__ import annotations

import math
from typing import Any

from sim.config import Config
from sim.state import Nation, World

EPS = 1e-9


def _r(cfg: Config, tech: str, key: str) -> Any:
    return cfg.rtech(tech)[key]["value"]


def has(n: Nation, tech: str) -> bool:
    return tech in n.techs


def can_build(cfg: Config, n: Nation, source: str) -> bool:
    """Whether the nation has the technology a source needs (always, for 2025 sources)."""
    need = cfg.requires(source)
    return need is None or need in n.techs


def can(cfg: Config, n: Nation, ability: str) -> bool:
    """Whether one of the nation's technologies enables `ability` (e.g. "ccs_retrofit")."""
    return any(ability in cfg.rtech(t).get("enables", []) for t in n.techs)


def earliest_turn(cfg: Config, tech: str) -> int:
    spec = cfg.rtech(tech).get("earliest_year")
    if not spec:
        return 0
    return int((spec["value"] - cfg.tune("time.start_year")) * 4)


def cost_now(cfg: Config, world: World, tech: str) -> float:
    """Total research cost, less the spillover once anyone has the technology."""
    cost = _r(cfg, tech, "cost")
    if tech in world.tech_firsts:
        cost *= 1 - cfg.research["spillover"]["value"]
    return cost


def blocked(cfg: Config, n: Nation, tech: str) -> str | None:
    """Why the nation cannot research `tech` now, or None."""
    if tech not in cfg.research["techs"]:
        return f"unknown technology {tech}"
    if has(n, tech):
        return f"you already have {tech}"
    missing = [p for p in cfg.rtech(tech).get("requires", []) if not has(n, p)]
    if missing:
        return f"{tech} needs {', '.join(missing)} first"
    if n.research_progress.get(tech, 0.0) >= 1 - EPS:
        year = cfg.rtech(tech).get("earliest_year", {}).get("value", "its earliest year")
        return f"{tech} is fully funded and completes in {year}"
    return None


def useful_funding(cfg: Config, world: World, n: Nation, tech: str) -> float:
    """The most that speeds research this quarter (T$): the minimum-time cap, and no more than
    what is left."""
    cost = cost_now(cfg, world, tech)
    left = (1 - n.research_progress.get(tech, 0.0)) * cost
    return max(0.0, min(cost / _r(cfg, tech, "min_quarters"), left))


def fund(cfg: Config, world: World, n: Nation, tech: str, amount: float) -> None:
    progress = n.research_progress.get(tech, 0.0) + amount / cost_now(cfg, world, tech)
    n.research_progress[tech] = min(1.0, progress)


def quarters_left(cfg: Config, world: World, n: Nation, tech: str, per_quarter: float) -> int:
    """Quarters to finish at `per_quarter` T$ of funding (the minimum-time cap applies)."""
    rate = min(per_quarter, cost_now(cfg, world, tech) / _r(cfg, tech, "min_quarters"))
    if rate <= 0:
        return -1
    left = (1 - n.research_progress.get(tech, 0.0)) * cost_now(cfg, world, tech)
    return max(math.ceil(left / rate - EPS), earliest_turn(cfg, tech) - world.t, 0)


def complete(cfg: Config, world: World) -> list[tuple[str, str]]:
    """Finish fully funded technologies whose earliest year has come; return (nation, tech)."""
    done = []
    for nid in sorted(world.nations):
        n = world.nations[nid]
        for tech in sorted(n.research_progress):
            if has(n, tech) or n.research_progress[tech] < 1 - EPS:
                continue
            if world.t < earliest_turn(cfg, tech):
                continue
            n.techs.append(tech)
            n.techs.sort()
            world.tech_firsts.setdefault(tech, [nid, world.t])
            done.append((nid, tech))
    return done


# --- effects -------------------------------------------------------------------------------------


def _product(cfg: Config, n: Nation, kind: str, source: str) -> float:
    out = 1.0
    for tech in n.techs:
        spec = cfg.rtech(tech).get("effects", {}).get(kind, {}).get(source)
        if spec:
            out *= spec["value"]
    return out


def cost_multiplier(cfg: Config, n: Nation, source: str) -> float:
    return _product(cfg, n, "cost", source)


def build_time_multiplier(cfg: Config, n: Nation, source: str) -> float:
    return _product(cfg, n, "build_time", source)


def hydrogen_bonus(cfg: Config, n: Nation | None) -> float:
    """How far electrolysers raise the nation's clean and wind-and-solar ceilings: hydrogen
    serves demand that cannot be electrified directly (share of demand)."""
    if n is None or n.demand <= 0 or "electrolysers" not in n.capacity:
        return 0.0
    return cfg.tune("research.h2_cap_factor") * n.capacity["electrolysers"] / n.demand


def ccs_share(n: Nation, fuel: str) -> float:
    """Share of the nation's capacity burning `fuel` fitted with carbon capture."""
    cap = n.capacity.get(fuel, 0.0)
    return min(1.0, n.ccs.get(fuel, 0.0) / cap) if cap > 0 else 0.0


def capture_factor(cfg: Config, n: Nation, source: str) -> float:
    """Multiplier on the emission factor of a source from carbon-capture retrofits."""
    if source not in CCS_FUELS:
        return 1.0
    return 1.0 - cfg.tune("research.ccs_capture") * ccs_share(n, source)


CCS_FUELS = ("coal", "gas")


def retire_ccs(n: Nation) -> None:
    """Retrofits retire with the plants they are fitted to."""
    for fuel in CCS_FUELS:
        if fuel in n.ccs:
            n.ccs[fuel] = min(n.ccs[fuel], n.capacity.get(fuel, 0.0))
