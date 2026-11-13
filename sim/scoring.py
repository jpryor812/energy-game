"""Impact, prosperity, endings and honours (scoring redesign, decided with the user 2026-11-12).

There is no World Multiplier. The world wins together or loses together: if warming, averaged
over the last four quarters, reaches `collapse_warming` (2.0 degC), the game ends in Climate
Collapse and every nation scores `loss_score`. A world that reaches the last quarter below that
line has won, and nations are then ranked on

    score = country difficulty x (w_impact x Impact + w_prosperity x Prosperity)

Impact (0-100) is the nation's climate contribution relative to its own size: credit-weighted
tonnes cut over the game (real domestic cuts against the 2025 level at full weight, cuts financed
abroad, made with exported equipment or through the forest fund at lower weights, purchased
credits least; `credits.weight_*`), averaged per year and divided by the nation's 2025 emissions,
through a logistic (50 = no change). So a small nation that halves its emissions outranks a
large one that cuts a third.

Prosperity (0-100) blends four components, each in 0..1 and each measured against the nation's
own starting point, so a poor country is not judged against a rich one:

- income: income per person vs. what baseline growth alone would have delivered
  (0.5 = on baseline), through a logistic on the log ratio.
- security: mean of (a) supply met, 1 at no shortfall falling to 0 at an average shortfall share
  of `shortfall_zero`, and (b) change in fossil import dependence since 2025 (0.5 = unchanged).
- welfare: mean of (a) average approval over the game and (b) the change in energy price since
  2025 (0.5 = unchanged, higher is worse).
- clean: clean-tech competitiveness, the nation's share of world clean-tech equipment sales
  against its 2025 share of factory capacity (0.5 = held its share).

Country difficulty (easy 1.0, easy-to-medium 1.1, medium 1.15, hard 1.3) multiplies the whole
score, so the same achievement is worth more for a harder country.

Endings, for the player: Climate Collapse (warming reached the line), Fallen Government
(stability fell below the threshold) or Voted Out (lost an election) end the game early and score
`loss_score`. Otherwise, at the end, Champion if the player ranks first of the 16 nations and
Shared Victory if not.

Honours are unscored firsts and bests shown on screen: first to net zero, the largest cut in
percent and in tonnes, the largest gain in clean share, and the deal that cut the most.
"""

from __future__ import annotations

import math
from typing import Any

from sim import economy
from sim.config import Config
from sim.state import World

CHAMPION = "Champion"
SHARED_VICTORY = "Shared Victory"
CLIMATE_COLLAPSE = "Climate Collapse"
FALLEN_GOVERNMENT = "Fallen Government"
VOTED_OUT = "Voted Out"
LOSSES = (CLIMATE_COLLAPSE, FALLEN_GOVERNMENT, VOTED_OUT)


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
    """Impact as a share (0..1): the credit-weighted yearly cut as a share of 2025 emissions,
    through a logistic (0.5 = no change)."""
    return logistic(yearly_cut(cfg, world, nid) / _sc(cfg, "climate_scale"))


def yearly_cut(cfg: Config, world: World, nid: str) -> float:
    """Average credit-weighted cut so far as a share of the nation's 2025 emissions (MtCO2 cut
    over the game divided by 2025 emissions x years played)."""
    n = world.nations[nid]
    years = max(world.t / 4, 0.25)
    return climate_contribution(cfg, world, nid) / (n.base["emissions"] * years)


def impact(cfg: Config, world: World, nid: str) -> float:
    """Impact index, 0-100."""
    return 100.0 * climate_component(cfg, world, nid)


def sales_share(world: World, nid: str) -> float | None:
    """The nation's share of world clean-tech equipment purchases it supplied over the last four
    quarters (M9: sales, not capacity, so idle factories do not score). None if nobody bought
    equipment in that time."""
    recs = [h["nations"] for h in world.history[-4:]]
    total = sum(sum(r[o].get("equipment_demand", {}).values()) for r in recs for o in r)
    if total <= 0:
        return None
    return sum(sum(r[nid].get("factory_sales", {}).values()) for r in recs) / total


def manufacturing_share(world: World, nid: str, base: bool = False) -> float:
    """The nation's share of world clean-tech factory capacity (all technologies), now or in
    2025. Scoring uses `sales_share` for now and this for 2025."""
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
    """Share of world clean-tech equipment sales over the last year against the 2025 share of
    factory capacity (0.5 = held its share). A small floor lets nations with no factories in
    2025 gain by building some."""
    floor = _sc(cfg, "clean_share_floor")
    sold = sales_share(world, nid)
    now = (manufacturing_share(world, nid) if sold is None else sold) + floor
    then = manufacturing_share(world, nid, base=True) + floor
    return logistic(math.log(now / then) / _sc(cfg, "clean_scale"))


def prosperity_index(cfg: Config, comps: dict[str, float]) -> float:
    weights = {k: _sc(cfg, f"weight_{k}") for k in comps}
    return 100.0 * sum(weights[k] * comps[k] for k in comps) / sum(weights.values())


def annual_emissions(world: World, nid: str) -> float:
    """Net emissions averaged over the last four quarters, MtCO2/yr (current rate before any
    quarter has been played)."""
    recs = [h["nations"][nid]["emissions"] for h in world.history[-4:]]
    return sum(recs) / len(recs) if recs else world.nations[nid].emissions


def first_net_zero(cfg: Config, world: World) -> tuple[str, str] | None:
    """(nation, quarter label) of the first nation to reach net zero, judged on emissions
    averaged over four quarters (M9: one low-season quarter used to be enough), if any has."""
    share = _sc(cfg, "net_zero_share")
    hist = world.history
    for i in range(3, len(hist)):
        window = hist[i - 3 : i + 1]
        reached = sorted(
            nid
            for nid in world.nations
            if sum(h["nations"][nid]["emissions"] for h in window) / 4
            <= share * world.nations[nid].base["emissions"]
        )
        if reached:
            return reached[0], hist[i]["label"]
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


HONOUR_RACES = ("largest_reduction", "largest_cut_tonnes", "largest_clean_gain")


def honours(cfg: Config, world: World) -> dict[str, list[str]]:
    """Unscored honours each nation holds now: first to net zero, the lead in each race (when
    positive), and both parties to the deal that cut the most."""
    out: dict[str, list[str]] = {nid: [] for nid in world.nations}
    first = first_net_zero(cfg, world)
    if first:
        out[first[0]].append("first_net_zero")
    metrics = race_metrics(cfg, world)
    for race in HONOUR_RACES:
        vals = metrics[race]
        if vals:
            best = min(vals, key=lambda nid: (-vals[nid], nid))
            if vals[best] > 0:
                out[best].append(race)
    credited = [(d.terms.get("credited", 0.0), d.id) for d in world.deals.values()]
    credited = [c for c in credited if c[0] > 0]
    if credited:
        _, did = sorted(credited, key=lambda c: (-c[0], c[1]))[0]
        deal = world.deals[did]
        for nid in (deal.financier, deal.host):
            out[nid].append("best_deal")
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


def ending(cfg: Config, rank: int, loss: str | None = None) -> str:
    """Endings: a loss if there was one, otherwise Champion for first place and Shared Victory
    for the rest (the world stayed below the collapse line)."""
    if loss:
        return loss
    return CHAMPION if rank == 1 else SHARED_VICTORY


def is_fallen(cfg: Config, world: World, nid: str) -> bool:
    return world.nations[nid].stability < _sc(cfg, "fallen_stability")


def year_warming(world: World) -> float:
    """Warming averaged over the last four quarters (this quarter's before any is played).
    Warming swings about 0.03 degC with the seasons, so the collapse line is judged on the
    year, as clean share and net zero are (M8)."""
    recs = [h["warming"] for h in world.history[-4:]]
    return sum(recs) / len(recs) if recs else world.warming


def collapsed(cfg: Config, world: World) -> bool:
    """Whether warming, averaged over a year, has reached the collapse line, which ends the
    game for every nation."""
    return year_warming(world) >= _sc(cfg, "collapse_warming")


def loss(cfg: Config, world: World, nid: str) -> str | None:
    """How the player lost, if they did: warming reached the collapse line, their government
    fell, or they lost an election. Each ends the game (M7; collapse 2026-11-12)."""
    if collapsed(cfg, world):
        return CLIMATE_COLLAPSE
    if is_fallen(cfg, world, nid):
        return FALLEN_GOVERNMENT
    if world.player == nid and world.voted_out_at >= 0:
        return VOTED_OUT
    return None


def difficulty_multiplier(cfg: Config, nid: str) -> float:
    """Country difficulty multiplier on the relative index and relative bonuses."""
    return _sc(cfg, f"difficulty_{cfg.nat_spec(nid)['difficulty']}")


def total(cfg: Config, impact_index: float, prosperity: float, mult: float) -> float:
    """country difficulty x (w_impact x Impact + w_prosperity x Prosperity)."""
    w_i, w_p = _sc(cfg, "weight_impact"), _sc(cfg, "weight_prosperity")
    return mult * (w_i * impact_index + w_p * prosperity) / (w_i + w_p)


def score(cfg: Config, world: World, player: str, lost: str | None = None) -> dict[str, Any]:
    """Final (or running) score for every nation, the player's rank and ending.

    A lost game (`lost` is one of LOSSES) scores `loss_score`; `score_at_exit` keeps what the
    formula gave.
    """
    ids = sorted(world.nations)
    comps = {nid: components(cfg, world, nid) for nid in ids}
    prosperity = {nid: prosperity_index(cfg, c) for nid, c in comps.items()}
    impacts = {nid: impact(cfg, world, nid) for nid in ids}
    mults = {nid: difficulty_multiplier(cfg, nid) for nid in ids}
    totals = {nid: total(cfg, impacts[nid], prosperity[nid], mults[nid]) for nid in ids}
    order = sorted(ids, key=lambda nid: (-totals[nid], nid))
    ranks = {nid: i + 1 for i, nid in enumerate(order)}
    return {
        "player": player,
        "score": _sc(cfg, "loss_score") if lost else totals[player],
        "score_at_exit": totals[player],
        "impact": impacts[player],
        "yearly_cut": yearly_cut(cfg, world, player),
        "prosperity": prosperity[player],
        "difficulty_multiplier": mults[player],
        "components": comps[player],
        "warming": world.warming,
        "collapse_at": _sc(cfg, "collapse_warming"),
        "rank": ranks[player],
        "honours": honours(cfg, world)[player],
        "ending": ending(cfg, ranks[player], lost),
        "all_nations": {
            nid: {
                "impact": impacts[nid],
                "prosperity": prosperity[nid],
                "rank": ranks[nid],
                "score": totals[nid],
            }
            for nid in order
        },
    }
