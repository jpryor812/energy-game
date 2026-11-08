"""Nation Index, World Multiplier, bonuses and endings.

Score = N x M(T) + bonuses.

N (0-100) blends five components, each in 0..1 and each measured against the nation's own
starting point, so a poor country is not judged against a rich one:

- income: income per person vs. what baseline growth alone would have delivered
  (0.5 = on baseline), through a logistic on the log ratio.
- security: mean of (a) supply met, 1 at no shortfall falling to 0 at an average shortfall share
  of `shortfall_zero`, and (b) change in fossil import dependence since 2025 (0.5 = unchanged).
- welfare: mean of (a) average approval over the game and (b) the change in energy price since
  2025 (0.5 = unchanged, higher is worse).
- clean: the nation's share of clean capacity built by the 16 nations during the game vs. its
  share of their 2025 GDP (0.5 = fair share).
- climate: credit-weighted emissions cut per year, as a share of 2025 emissions (0.5 = no
  change): real domestic cuts count 1.0, cuts financed abroad 0.75, cuts made with exported
  equipment 0.6, purchased credits 0.25 (`credits.weight_*`; decided 2026-11-08).

M(T) is 1 at or below `world_good` warming and falls quadratically to `world_floor` at
`world_bad`.

Bonuses (flat points): first nation to reach net zero (emissions at or below `net_zero_share`
of 2025), the largest percentage cut in emissions from 2025 to the end, and the deal that cut the
most emissions (both parties). The breakthrough-technology bonus waits for M4b.

Endings, for the player: Fallen Government if stability fell below the threshold; otherwise a
top finish (rank on N at or above `top_rank`) and a good world (final warming at or below
`good_world_warming`) decide between Champion, Prosperous but Doomed, Green but Poor, and Shared
Failure.
"""

from __future__ import annotations

import math
from typing import Any

from sim import economy
from sim.config import Config
from sim.state import World

CHAMPION = "Champion"
PROSPEROUS_BUT_DOOMED = "Prosperous but Doomed"
GREEN_BUT_POOR = "Green but Poor"
SHARED_FAILURE = "Shared Failure"
FALLEN_GOVERNMENT = "Fallen Government"


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _sc(cfg: Config, name: str) -> Any:
    return cfg.tune(f"scoring.{name}")


def expected_income_ratio(cfg: Config, nid: str, turns: int) -> float:
    """Income-per-person growth baseline growth alone would deliver over `turns` quarters."""
    gdp = 1.0
    for t in range(turns):
        gdp *= (1 + economy.baseline_growth(cfg, nid, t)) ** 0.25
    pop = (1 + cfg.nat(nid, "trend.population_growth")) ** (turns / 4)
    return gdp / pop


def components(cfg: Config, world: World, nid: str) -> dict[str, float]:
    n = world.nations[nid]
    records = [h["nations"][nid] for h in world.history]

    actual = (n.gdp / n.population) / n.base["income_per_person"]
    expected = expected_income_ratio(cfg, nid, world.t)
    income = logistic(math.log(actual / expected) / _sc(cfg, "income_scale"))

    shortfall = sum(r["shortfall"] / r["demand"] for r in records) / max(1, len(records))
    supply = max(0.0, 1.0 - shortfall / _sc(cfg, "shortfall_zero"))
    imports = logistic(
        -(n.import_dependence - n.base["import_dependence"]) / _sc(cfg, "import_scale")
    )
    security = (supply + imports) / 2

    approval = sum(r["approval"] for r in records) / max(1, len(records))
    price_ratio = n.energy_price / n.base["energy_price"] if n.base["energy_price"] > 0 else 1.0
    price = logistic(-math.log(max(price_ratio, 1e-9)) / _sc(cfg, "price_scale"))
    welfare = (approval + price) / 2

    total_clean = sum(m.clean_built for m in world.nations.values())
    total_gdp = sum(m.base["gdp"] for m in world.nations.values())
    if total_clean > 0:
        ratio = (n.clean_built / total_clean) / (n.base["gdp"] / total_gdp)
        clean = logistic(math.log(max(ratio, 1e-9)) / _sc(cfg, "clean_scale"))
    else:
        clean = 0.5

    return {
        "income": income,
        "security": security,
        "welfare": welfare,
        "clean": clean,
        "climate": climate_component(cfg, world, nid),
    }


def climate_contribution(cfg: Config, world: World, nid: str) -> float:
    """Credit-weighted MtCO2 cut over the game (real cuts against the 2025 level, plus
    weighted credits)."""
    n = world.nations[nid]
    base = n.base["emissions"]
    real = sum(base - h["nations"][nid]["emissions"] for h in world.history) / 4
    w = lambda k: cfg.tune(f"credits.weight_{k}")  # noqa: E731
    return (
        w("real") * real
        + n.climate_credit.get("financed", 0.0)
        + n.climate_credit.get("exported", 0.0)
        + w("purchased") * n.credits_bought
    )


def climate_component(cfg: Config, world: World, nid: str) -> float:
    n = world.nations[nid]
    years = max(world.t / 4, 0.25)
    per_year = climate_contribution(cfg, world, nid) / (n.base["emissions"] * years)
    return logistic(per_year / _sc(cfg, "climate_scale"))


def nation_index(cfg: Config, comps: dict[str, float]) -> float:
    weights = {k: _sc(cfg, f"weight_{k}") for k in comps}
    return 100.0 * sum(weights[k] * comps[k] for k in comps) / sum(weights.values())


def world_multiplier(cfg: Config, warming: float) -> float:
    good, bad, floor = _sc(cfg, "world_good"), _sc(cfg, "world_bad"), _sc(cfg, "world_floor")
    x = min(1.0, max(0.0, (warming - good) / (bad - good)))
    return 1.0 - (1.0 - floor) * x**2


def bonuses(cfg: Config, world: World) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {nid: {} for nid in world.nations}
    share = _sc(cfg, "net_zero_share")
    for h in world.history:
        reached = sorted(
            nid
            for nid, r in h["nations"].items()
            if r["emissions"] <= share * world.nations[nid].base["emissions"]
        )
        if reached:
            out[reached[0]]["first_net_zero"] = _sc(cfg, "bonus_first_net_zero")
            break
    cuts = {
        nid: 1 - n.emissions / n.base["emissions"]
        for nid, n in world.nations.items()
        if n.base["emissions"] > 0
    }
    if cuts:
        best = min(cuts, key=lambda nid: (-cuts[nid], nid))
        if cuts[best] > 0:
            out[best]["largest_reduction"] = _sc(cfg, "bonus_largest_reduction")
    credited = [(d.terms.get("credited", 0.0), d.id) for d in world.deals.values()]
    credited = [c for c in credited if c[0] > 0]
    if credited:
        _, did = sorted(credited, key=lambda c: (-c[0], c[1]))[0]
        deal = world.deals[did]
        for nid in (deal.financier, deal.host):
            out[nid]["best_deal"] = _sc(cfg, "bonus_best_deal")
    return out


def ending(cfg: Config, rank: int, warming: float, fallen: bool) -> str:
    if fallen:
        return FALLEN_GOVERNMENT
    top = rank <= _sc(cfg, "top_rank")
    good = warming <= _sc(cfg, "good_world_warming")
    if top and good:
        return CHAMPION
    if top:
        return PROSPEROUS_BUT_DOOMED
    if good:
        return GREEN_BUT_POOR
    return SHARED_FAILURE


def is_fallen(cfg: Config, world: World, nid: str) -> bool:
    return world.nations[nid].stability < _sc(cfg, "fallen_stability")


def score(cfg: Config, world: World, player: str, fallen: bool = False) -> dict[str, Any]:
    """Final (or running) score for every nation, the player's rank and ending."""
    comps = {nid: components(cfg, world, nid) for nid in sorted(world.nations)}
    index = {nid: nation_index(cfg, c) for nid, c in comps.items()}
    order = sorted(index, key=lambda nid: (-index[nid], nid))
    ranks = {nid: i + 1 for i, nid in enumerate(order)}
    mult = world_multiplier(cfg, world.warming)
    bonus = bonuses(cfg, world)
    totals = {nid: index[nid] * mult + sum(bonus[nid].values()) for nid in index}
    return {
        "player": player,
        "score": totals[player],
        "nation_index": index[player],
        "components": comps[player],
        "world_multiplier": mult,
        "warming": world.warming,
        "rank": ranks[player],
        "bonuses": bonus[player],
        "ending": ending(cfg, ranks[player], world.warming, fallen),
        "all_nations": {
            nid: {"nation_index": index[nid], "rank": ranks[nid], "score": totals[nid]}
            for nid in order
        },
    }
