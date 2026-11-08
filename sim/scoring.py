"""Nation Index, World Multiplier, bonuses and endings.

Score = (w_abs x A + w_rel x N x difficulty) x M(T) + absolute bonuses + relative bonuses x
difficulty (decided 2026-11-08). A, the absolute index (0-100), compares where nations end up:
income per person against the 16-nation average, clean share of energy, emissions per person
against twice the 2025 average, energy security, and average approval. Wealthy, cleaner nations
score higher on it. N, the relative index, is multiplied by the country's difficulty (easy 1.0,
easy-to-medium 1.1, medium 1.15, hard 1.3) so the same improvement is worth more for a harder
country.

N (0-100) blends five components, each in 0..1 and each measured against the nation's own
starting point, so a poor country is not judged against a rich one:

- income: income per person vs. what baseline growth alone would have delivered
  (0.5 = on baseline), through a logistic on the log ratio.
- security: mean of (a) supply met, 1 at no shortfall falling to 0 at an average shortfall share
  of `shortfall_zero`, and (b) change in fossil import dependence since 2025 (0.5 = unchanged).
- welfare: mean of (a) average approval over the game and (b) the change in energy price since
  2025 (0.5 = unchanged, higher is worse).
- clean: clean-tech competitiveness, the nation's share of world clean-tech factory capacity now
  against 2025 (0.5 = held its share; changed in M5 from clean capacity built at home, which
  double-counted the climate component).
- climate: credit-weighted emissions cut per year, as a share of 2025 emissions (0.5 = no
  change): real domestic cuts count 1.0, cuts financed abroad 0.75, cuts made with exported
  equipment 0.6, purchased credits 0.25 (`credits.weight_*`; decided 2026-11-08).

M(T) is 1 at or below `world_good` warming and falls quadratically to `world_floor` at
`world_bad`.

Bonuses (flat points). Absolute: first nation to reach net zero (emissions at or below
`net_zero_share` of 2025), largest cut in tonnes, and the deal that cut the most emissions (both
parties). Relative, x difficulty: largest percentage cut, largest gain in clean share.

Endings, for the player: Fallen Government if stability fell below the threshold; otherwise a
top finish (rank on the combined index at or above `top_rank`) and a good world (final warming
at or below `good_world_warming`) decide between Champion, Prosperous but Doomed, Green but Poor,
and Shared Failure.
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

    clean = clean_competitiveness(cfg, world, nid)

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


def manufacturing_share(world: World, nid: str, base: bool = False) -> float:
    """The nation's share of world clean-tech factory capacity (all technologies), now or in
    2025."""
    from sim import trade

    total = mine = 0.0
    for tech in trade.EQUIPMENT:
        key = f"factory_2025_{tech}" if base else None
        for oid, m in world.nations.items():
            cap = m.base.get(key, 0.0) if base else m.factory_capacity.get(tech, 0.0)
            total += cap
            if oid == nid:
                mine += cap
        total += world.base.get(f"row_capacity_{tech}", 0.0)
    return mine / total if total > 0 else 0.0


def clean_competitiveness(cfg: Config, world: World, nid: str) -> float:
    """Share of world clean-tech manufacturing now against 2025 (0.5 = held its share). A small
    floor lets nations with no factories in 2025 gain by building some."""
    floor = _sc(cfg, "clean_share_floor")
    now = manufacturing_share(world, nid) + floor
    then = manufacturing_share(world, nid, base=True) + floor
    return logistic(math.log(now / then) / _sc(cfg, "clean_scale"))


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
    tonnes = {nid: n.base["emissions"] - n.emissions for nid, n in world.nations.items()}
    best = min(tonnes, key=lambda nid: (-tonnes[nid], nid))
    if tonnes[best] > 0:
        out[best]["largest_cut_tonnes"] = _sc(cfg, "bonus_largest_cut")
    gains = {
        nid: clean_share(cfg, n) - n.base.get("clean_share", 0.0)
        for nid, n in world.nations.items()
    }
    best = min(gains, key=lambda nid: (-gains[nid], nid))
    if gains[best] > 0:
        out[best]["largest_clean_gain"] = _sc(cfg, "bonus_clean_gain")
    credited = [(d.terms.get("credited", 0.0), d.id) for d in world.deals.values()]
    credited = [c for c in credited if c[0] > 0]
    if credited:
        _, did = sorted(credited, key=lambda c: (-c[0], c[1]))[0]
        deal = world.deals[did]
        for nid in (deal.financier, deal.host):
            out[nid]["best_deal"] = _sc(cfg, "bonus_best_deal")
    return out


RELATIVE_BONUSES = ("largest_reduction", "largest_clean_gain")  # x country difficulty


def clean_share(cfg: Config, n) -> float:
    delivered = sum(n.supply.values())
    clean = sum(v for s, v in n.supply.items() if cfg.category(s) != "fossil")
    return clean / delivered if delivered > 0 else 0.0


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


def absolute_components(cfg: Config, world: World, nid: str) -> dict[str, float]:
    """Where the nation ends up, comparable across nations (each 0..1)."""
    n = world.nations[nid]
    nations = world.nations.values()
    avg_income = sum(m.gdp for m in nations) / sum(m.population for m in nations)
    income = logistic(
        math.log(max(n.gdp / n.population, 1e-12) / avg_income) / _sc(cfg, "abs_income_scale")
    )
    delivered = sum(n.supply.values())
    clean = sum(v for s, v in n.supply.items() if cfg.category(s) != "fossil")
    clean_share = clean / delivered if delivered > 0 else 0.0
    avg_em_2025 = sum(m.base["emissions"] for m in nations) / sum(
        m.base["population"] for m in nations
    )
    em_pc = n.emissions / n.population
    emissions = min(1.0, max(0.0, 1 - em_pc / (2 * avg_em_2025)))
    records = [h["nations"][nid] for h in world.history]
    shortfall = sum(r["shortfall"] / r["demand"] for r in records) / max(1, len(records))
    supply = max(0.0, 1.0 - shortfall / _sc(cfg, "shortfall_zero"))
    security = (supply + (1 - min(1.0, n.import_dependence))) / 2
    approval = sum(r["approval"] for r in records) / max(1, len(records))
    return {
        "income": income,
        "clean_share": clean_share,
        "emissions": emissions,
        "security": security,
        "approval": approval,
    }


def absolute_index(cfg: Config, comps: dict[str, float]) -> float:
    weights = {k: _sc(cfg, f"abs_weight_{k}") for k in comps}
    return 100.0 * sum(weights[k] * comps[k] for k in comps) / sum(weights.values())


def difficulty_multiplier(cfg: Config, nid: str) -> float:
    """Country difficulty multiplier on the relative index and relative bonuses."""
    return _sc(cfg, f"difficulty_{cfg.nat_spec(nid)['difficulty']}")


def combined_index(cfg: Config, absolute: float, relative: float, mult: float) -> float:
    return _sc(cfg, "weight_absolute") * absolute + _sc(cfg, "weight_relative") * relative * mult


def score(cfg: Config, world: World, player: str, fallen: bool = False) -> dict[str, Any]:
    """Final (or running) score for every nation, the player's rank and ending.

    score = (w_abs x absolute index + w_rel x relative index x country difficulty) x World
    Multiplier + absolute bonuses + relative bonuses x country difficulty. Rank (for endings) is
    on the combined index before the World Multiplier.
    """
    ids = sorted(world.nations)
    rel_comps = {nid: components(cfg, world, nid) for nid in ids}
    relative = {nid: nation_index(cfg, c) for nid, c in rel_comps.items()}
    abs_comps = {nid: absolute_components(cfg, world, nid) for nid in ids}
    absolute = {nid: absolute_index(cfg, c) for nid, c in abs_comps.items()}
    mults = {nid: difficulty_multiplier(cfg, nid) for nid in ids}
    combined = {nid: combined_index(cfg, absolute[nid], relative[nid], mults[nid]) for nid in ids}
    order = sorted(ids, key=lambda nid: (-combined[nid], nid))
    ranks = {nid: i + 1 for i, nid in enumerate(order)}
    world_mult = world_multiplier(cfg, world.warming)
    bonus = bonuses(cfg, world)

    def bonus_total(nid: str) -> float:
        return sum(
            v * (mults[nid] if k in RELATIVE_BONUSES else 1.0) for k, v in bonus[nid].items()
        )

    totals = {nid: combined[nid] * world_mult + bonus_total(nid) for nid in ids}
    return {
        "player": player,
        "score": totals[player],
        "nation_index": relative[player],
        "absolute_index": absolute[player],
        "difficulty_multiplier": mults[player],
        "combined_index": combined[player],
        "components": rel_comps[player],
        "absolute_components": abs_comps[player],
        "world_multiplier": world_mult,
        "warming": world.warming,
        "rank": ranks[player],
        "bonuses": bonus[player],
        "ending": ending(cfg, ranks[player], world.warming, fallen),
        "all_nations": {
            nid: {
                "nation_index": relative[nid],
                "absolute_index": absolute[nid],
                "combined_index": combined[nid],
                "rank": ranks[nid],
                "score": totals[nid],
            }
            for nid in order
        },
    }
