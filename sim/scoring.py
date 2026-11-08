"""Nation Index, World Multiplier, bonuses and endings.

Score = (w_abs x A + w_rel x N x difficulty) x M(T) + absolute bonuses + relative bonuses x
difficulty (decided 2026-11-08). A, the absolute index (0-100), compares where nations end up:
income per person against the 16-nation average (a straight line in log income from
`abs_income_low` to `abs_income_high` times the average, so a given percentage loss costs every
nation the same; M6), clean share of energy, emissions per person
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

M(T) is 1 at or below `world_good` warming and falls in a straight line to `world_floor` at
`world_bad` (M6; it was quadratic, which left 1.6-1.7 degC worlds almost unpenalised).

Bonuses (flat points). Absolute: first nation to reach net zero (emissions at or below
`net_zero_share` of 2025), largest cut in tonnes, and the deal that cut the most emissions (both
parties). Relative, x difficulty: largest percentage cut, largest gain in clean share.

Endings, for the player: Fallen Government if stability fell below the threshold, or Voted Out
if they lost an election; both end the game early and score `loss_score` (M7). Otherwise a
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
VOTED_OUT = "Voted Out"
LOSSES = (FALLEN_GOVERNMENT, VOTED_OUT)


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
    return 1.0 - (1.0 - floor) * x


def annual_emissions(world: World, nid: str) -> float:
    """Net emissions averaged over the last four quarters, MtCO2/yr (current rate before any
    quarter has been played)."""
    recs = [h["nations"][nid]["emissions"] for h in world.history[-4:]]
    return sum(recs) / len(recs) if recs else world.nations[nid].emissions


def first_net_zero(cfg: Config, world: World) -> tuple[str, str] | None:
    """(nation, quarter label) of the first nation to reach net zero, if any has."""
    share = _sc(cfg, "net_zero_share")
    for h in world.history:
        reached = sorted(
            nid
            for nid, r in h["nations"].items()
            if r["emissions"] <= share * world.nations[nid].base["emissions"]
        )
        if reached:
            return reached[0], h["label"]
    return None


def race_metrics(cfg: Config, world: World) -> dict[str, dict[str, float]]:
    """What each end-of-game bonus race is decided on, per nation (higher is better). Emissions
    and clean share are four-quarter averages (M8), so seasons do not flip the lead."""
    nations = world.nations
    out = {
        "largest_reduction": {
            nid: 1 - annual_emissions(world, nid) / n.base["emissions"]
            for nid, n in nations.items()
            if n.base["emissions"] > 0
        },
        "largest_cut_tonnes": {
            nid: n.base["emissions"] - annual_emissions(world, nid) for nid, n in nations.items()
        },
        "largest_clean_gain": {
            nid: annual_clean_share(cfg, world, nid) - n.base.get("clean_share", 0.0)
            for nid, n in nations.items()
        },
        "best_deal": {nid: 0.0 for nid in nations},
    }
    for d in world.deals.values():
        c = d.terms.get("credited", 0.0)
        for nid in (d.financier, d.host):
            out["best_deal"][nid] = max(out["best_deal"][nid], c)
    return out


BONUS_KEYS = {
    "largest_reduction": "bonus_largest_reduction",
    "largest_cut_tonnes": "bonus_largest_cut",
    "largest_clean_gain": "bonus_clean_gain",
}


def bonuses(cfg: Config, world: World) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {nid: {} for nid in world.nations}
    first = first_net_zero(cfg, world)
    if first:
        out[first[0]]["first_net_zero"] = _sc(cfg, "bonus_first_net_zero")
    metrics = race_metrics(cfg, world)
    for race, key in BONUS_KEYS.items():
        vals = metrics[race]
        if vals:
            best = min(vals, key=lambda nid: (-vals[nid], nid))
            if vals[best] > 0:
                out[best][race] = _sc(cfg, key)
    credited = [(d.terms.get("credited", 0.0), d.id) for d in world.deals.values()]
    credited = [c for c in credited if c[0] > 0]
    if credited:
        _, did = sorted(credited, key=lambda c: (-c[0], c[1]))[0]
        deal = world.deals[did]
        for nid in (deal.financier, deal.host):
            out[nid]["best_deal"] = _sc(cfg, "bonus_best_deal")
    return out


def races(cfg: Config, world: World, me: str) -> list[dict[str, Any]]:
    """Each bonus race as the player sees it: who leads (or has claimed it), on what, and where
    the player stands."""
    out = []
    first = first_net_zero(cfg, world)
    share = _sc(cfg, "net_zero_share")
    mine = annual_emissions(world, me) / max(world.nations[me].base["emissions"], 1e-9)
    out.append(
        {
            "race": "first_net_zero",
            "leader": first[0] if first else None,
            "claimed": first[1] if first else None,
            "measure": f"net emissions at or below {share:.0%} of 2025",
            "you": mine,
        }
    )
    metrics = race_metrics(cfg, world)
    measures = {
        "largest_reduction": "share of 2025 emissions cut",
        "largest_cut_tonnes": "MtCO2/yr cut from 2025",
        "largest_clean_gain": "clean share gained since 2025",
        "best_deal": "MtCO2 credited to one deal",
    }
    for race, vals in metrics.items():
        best = min(vals, key=lambda nid: (-vals[nid], nid)) if vals else None
        out.append(
            {
                "race": race,
                "leader": best if best and vals[best] > 0 else None,
                "lead": vals.get(best, 0.0) if best else 0.0,
                "measure": measures[race],
                "you": vals.get(me, 0.0),
            }
        )
    return out


RELATIVE_BONUSES = ("largest_reduction", "largest_clean_gain")  # x country difficulty


def _clean(cfg: Config, supply: dict[str, float]) -> tuple[float, float]:
    return sum(v for s, v in supply.items() if cfg.category(s) != "fossil"), sum(supply.values())


def clean_share(cfg: Config, n) -> float:
    """Clean share of this quarter's supply."""
    clean, delivered = _clean(cfg, n.supply)
    return clean / delivered if delivered > 0 else 0.0


def annual_clean_share(cfg: Config, world: World, nid: str) -> float:
    """Clean share of supply over the last four quarters (M8), so seasonal swings in demand do
    not flip scores or bonuses from one quarter to the next. Falls back to this quarter's supply
    before any quarter has been played."""
    recs = [h["nations"][nid]["supply"] for h in world.history[-4:]]
    if not recs:
        return clean_share(cfg, world.nations[nid])
    parts = [_clean(cfg, r) for r in recs]
    delivered = sum(d for _, d in parts)
    return sum(c for c, _ in parts) / delivered if delivered > 0 else 0.0


def warming_falling(cfg: Config, world: World) -> bool | None:
    """Whether warming is lower now than `falling_years` ago (None before that much history)."""
    back = int(_sc(cfg, "falling_years") * 4)
    if len(world.history) <= back:
        return None
    return world.warming < world.history[-1 - back]["warming"]


def ending(
    cfg: Config, rank: int, warming: float, loss: str | None = None, falling: bool | None = True
) -> str:
    """Endings. A good world (M8) ends at or below `good_world_warming` with warming falling
    over the last `falling_years` (`falling` None = not enough history, counted as falling)."""
    if loss:
        return loss
    top = rank <= _sc(cfg, "top_rank")
    good = warming <= _sc(cfg, "good_world_warming") and falling is not False
    if top and good:
        return CHAMPION
    if top:
        return PROSPEROUS_BUT_DOOMED
    if good:
        return GREEN_BUT_POOR
    return SHARED_FAILURE


def is_fallen(cfg: Config, world: World, nid: str) -> bool:
    return world.nations[nid].stability < _sc(cfg, "fallen_stability")


def loss(cfg: Config, world: World, nid: str) -> str | None:
    """How the player lost, if they did: their government fell, or they lost an election. Either
    ends the game (M7)."""
    if is_fallen(cfg, world, nid):
        return FALLEN_GOVERNMENT
    if world.player == nid and world.voted_out_at >= 0:
        return VOTED_OUT
    return None


def absolute_components(cfg: Config, world: World, nid: str) -> dict[str, float]:
    """Where the nation ends up, comparable across nations (each 0..1)."""
    n = world.nations[nid]
    nations = world.nations.values()
    avg_income = sum(m.gdp for m in nations) / sum(m.population for m in nations)
    low, high = math.log(_sc(cfg, "abs_income_low")), math.log(_sc(cfg, "abs_income_high"))
    ratio = math.log(max(n.gdp / n.population, 1e-12) / avg_income)
    income = min(1.0, max(0.0, (ratio - low) / (high - low)))
    clean_share = annual_clean_share(cfg, world, nid)
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


def score(cfg: Config, world: World, player: str, lost: str | None = None) -> dict[str, Any]:
    """Final (or running) score for every nation, the player's rank and ending.

    score = (w_abs x absolute index + w_rel x relative index x country difficulty) x World
    Multiplier + absolute bonuses + relative bonuses x country difficulty. Rank (for endings) is
    on the combined index before the World Multiplier. A lost game (`lost` is Fallen Government
    or Voted Out) scores `loss_score`; `score_at_exit` keeps what the formula gave.
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
        "score": _sc(cfg, "loss_score") if lost else totals[player],
        "score_at_exit": totals[player],
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
        "ending": ending(cfg, ranks[player], world.warming, lost, warming_falling(cfg, world)),
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
