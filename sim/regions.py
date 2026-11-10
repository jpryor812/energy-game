"""The rest of the world as seven regions (M15).

Before M15 the rest of the world was one emissions number that fell only as fast as the 16
nations' carbon intensity. Now each region (data/regions.yaml: 2024 data, the modelled nations
left out) keeps a GDP, its clean and fossil energy use, and its trust in each nation:

- GDP grows at its 2025-2030 trend, less climate damage at its vulnerability (sim.climate).
- Energy use grows with GDP, less `intensity_decline`. New energy (growth plus the plants that
  retire) is clean at the region's 2019-2024 share, raised as world clean-tech costs fall
  (`cost_response`, from the solar and onshore wind learning curves), as the 16 nations cut
  their own carbon intensity (`spread`: practice, finance and supply chains follow the big
  economies; `spread_retire` also retires fossil plants early, stranded as the world moves on)
  and by the carbon club's share of world GDP (`club_pull`), up to the same clean ceiling the
  nations face (sim.energy.clean_max_share).
- Emissions = fossil energy x the region's emission factor, plus CO2 from events (M15b: an
  oil field developed).

Nations act on a region with `finance_region`: a concessional loan that builds clean capacity
there after the source's build time. The clean energy displaces fossil; the region repays at
`loan_rate` over `loan_years`, during which the lender earns financed climate credit for the cut.
The equipment is bought from the world's factories, tilted toward nations the region trusts, and
financing raises that trust. A region can take only so much financed energy (`absorb_share` of
its energy use a year, over a rolling `absorb_years`, shared by all lenders, first come first
served), and never past its clean ceiling. The international shipping and aviation CO2 the
regions leave out stays a separate term in sim.climate.

Regions have no elections, score, or actions of their own.
"""

from __future__ import annotations

from typing import Any

from sim import climate, energy, tech, trade
from sim.config import Config
from sim.state import Region, World


def _r(cfg: Config, name: str) -> Any:
    return cfg.tune(f"regions.{name}")


def init(cfg: Config, world: World) -> None:
    for rid in cfg.region_ids:
        r = Region(
            id=rid,
            gdp=cfg.reg(rid, "gdp"),
            population=cfg.reg(rid, "population"),
            clean=cfg.reg(rid, "clean"),
            fossil=cfg.reg(rid, "fossil"),
            fossil_production=cfg.reg(rid, "fossil_production"),
            growth=cfg.reg(rid, "growth"),
            clean_additions=cfg.reg(rid, "clean_additions"),
            trust={nid: _r(cfg, "trust_start") for nid in sorted(world.nations)},
        )
        r.emissions = r.fossil * cfg.reg(rid, "fossil_ef")
        world.regions[rid] = r
    world.base["clean_cost_index"] = clean_cost(cfg, world)
    world.base["regions_co2"] = total_emissions(world)


def total_emissions(world: World) -> float:
    return sum(world.regions[rid].emissions for rid in sorted(world.regions))


def clean_cost(cfg: Config, world: World) -> float:
    """Mean world unit cost of the sources regions mostly build clean energy with."""
    sources = cfg.tuning["regions"]["cost_sources"]
    return sum(tech.unit_cost(cfg, world, s) for s in sources) / len(sources)


def club_share(world: World) -> float:
    """The carbon club's share of world GDP (regions included)."""
    members = trade.club_members(world)
    club = sum(world.nations[m].gdp for m in members if m in world.nations)
    total = sum(n.gdp for n in world.nations.values()) + sum(r.gdp for r in world.regions.values())
    return club / total if total > 0 else 0.0


def clean_additions(cfg: Config, world: World, rid: str) -> float:
    """Share of a region's new energy that is clean this quarter."""
    base = world.base.get("clean_cost_index", 0.0)
    now = clean_cost(cfg, world)
    cost = (base / now) ** _r(cfg, "cost_response") if now > 0 and base > 0 else 1.0
    share = cfg.reg(rid, "clean_additions") * cost + _r(cfg, "club_pull") * club_share(world)
    share += _r(cfg, "spread") * max(0.0, 1 - intensity_ratio(world))
    return min(ceiling(cfg, world), share)


def ceiling(cfg: Config, world: World) -> float:
    """Most of a region's energy that can be clean now: the nations' clean ceiling (end-use
    conversion), without electrification bonuses."""
    return energy.clean_max_share(cfg, world.t)


def intensity_ratio(world: World) -> float:
    """The 16 nations' carbon intensity of energy against 2025 (1 = no change)."""
    base = world.base.get("carbon_intensity", 0.0)
    return climate.carbon_intensity(world) / base if base > 0 else 1.0


def unit_cost(cfg: Config, world: World, source: str) -> float:
    """T$ per EJ/yr of capacity built in a region."""
    return tech.unit_cost(cfg, world, source) * (1 + _r(cfg, "cost_premium"))


def payment_rate(cfg: Config) -> float:
    """Yearly repayment per T$ lent (an annuity at the concessional rate)."""
    return tech.crf(_r(cfg, "loan_rate"), _r(cfg, "loan_years"))


# --- financing (the finance_region action) -------------------------------------------------------


def window(cfg: Config) -> int:
    return int(round(_r(cfg, "absorb_years") * 4))


def room(cfg: Config, world: World, rid: str) -> float:
    """Financed clean energy (EJ/yr delivered) the region can still take: `absorb_share` of its
    energy use per year over the last `absorb_years`, less what nations financed there in that
    time, and never past its clean ceiling counting projects not yet built."""
    r = world.regions[rid]
    demand = r.clean + r.fossil
    since = world.t - window(cfg)
    recent = sum(
        p["delivered"] for p in world.region_projects
        if p["region"] == rid and p["signed"] > since
    )  # fmt: skip
    pending = sum(
        p["delivered"] for p in world.region_projects if p["region"] == rid and not p["built"]
    )
    absorb = _r(cfg, "absorb_share") * demand * _r(cfg, "absorb_years") - recent
    headroom = ceiling(cfg, world) * demand - r.clean - pending
    return max(0.0, min(absorb, headroom))


def delivered_per_trillion(cfg: Config, world: World, source: str) -> float:
    return 1 / unit_cost(cfg, world, source) / cfg.src(source, "headroom")


def finance(cfg: Config, world: World, nid: str, rid: str, source: str, amount: float) -> None:
    """Lend `amount` T$ to region `rid` to build `source`; it comes online after the build time."""
    capacity = amount / unit_cost(cfg, world, source)
    online = world.t + tech.build_quarters(cfg, None, source)
    world.region_projects.append(
        {
            "financier": nid,
            "region": rid,
            "source": source,
            "amount": amount,
            "capacity": capacity,
            "delivered": capacity / cfg.src(source, "headroom"),
            "signed": world.t,
            "online": online,
            "end": online + int(round(_r(cfg, "loan_years") * 4)),
            "built": False,
        }
    )
    r = world.regions[rid]
    r.financed[nid] = r.financed.get(nid, 0.0) + amount
    r.trust[nid] = min(1.0, r.trust.get(nid, 0.5) + _r(cfg, "trust_per_trillion") * amount)


def complete(cfg: Config, world: World) -> list[tuple[str, str, float]]:
    """Bring financed projects online: the clean energy displaces fossil in the region. Returns
    (region, source, capacity) for each, for the equipment purchases (sim.trade)."""
    done = []
    for p in world.region_projects:
        if p["built"] or p["online"] > world.t:
            continue
        p["built"] = True
        r = world.regions[p["region"]]
        p["delivered"] = min(p["delivered"], r.fossil)  # nothing left to displace beyond this
        r.clean += p["delivered"]
        r.fossil -= p["delivered"]
        done.append((p["region"], p["source"], p["capacity"]))
    return done


def supplier_weights(cfg: Config, world: World, rid: str, tech_: str) -> dict[str, float]:
    """Where a region buys equipment: world market shares, tilted toward the nations it trusts.
    Regions set no tariffs or content rules."""
    pull = _r(cfg, "trust_pull")
    trust = world.regions[rid].trust
    raw = {
        s: share * max(0.0, 1 + pull * (trust.get(s, 0.5) - 0.5))
        for s, share in trade.capacity_shares(cfg, world, tech_).items()
    }
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else raw


# --- the quarterly step --------------------------------------------------------------------------


def apply(world: World, cfg: Config, dt: int) -> None:
    """Grow each region, add its new energy, and service the loans. Runs before sim.climate."""
    years = dt / 4
    for rid in sorted(world.regions):
        r = world.regions[rid]
        vuln = cfg.reg(rid, "vulnerability")
        r.growth = cfg.reg(rid, "growth") - climate.damage(cfg, vuln, world.warming)
        grow = (1 + r.growth) ** years
        r.gdp *= grow
        demand = r.clean + r.fossil
        new_demand = demand * grow * (1 - _r(cfg, "intensity_decline")) ** years
        early = _r(cfg, "spread_retire") * max(0.0, 1 - intensity_ratio(world))
        retire_f = r.fossil * (1 - (1 - 1 / _r(cfg, "fossil_lifespan") - early) ** years)
        retire_c = r.clean * (1 - (1 - 1 / _r(cfg, "clean_lifespan")) ** years)
        needed = max(0.0, new_demand - demand + retire_f + retire_c)
        r.clean_additions = clean_additions(cfg, world, rid)
        clean = r.clean - retire_c + r.clean_additions * needed
        clean = min(clean, ceiling(cfg, world) * new_demand)
        r.clean, r.fossil = clean, max(0.0, new_demand - clean)
        r.emissions = r.fossil * cfg.reg(rid, "fossil_ef") + r.extra_co2
        base_fossil = cfg.reg(rid, "fossil")
        r.fossil_production = cfg.reg(rid, "fossil_production") * (
            r.fossil / base_fossil if base_fossil > 0 else 1.0
        ) + r.extra_co2 / cfg.reg(rid, "fossil_ef")

    rate = payment_rate(cfg) * years
    weight = cfg.tune("credits.weight_financed")
    for p in world.region_projects:
        if not p["built"] or world.t >= p["end"]:
            continue
        n = world.nations[p["financier"]]
        n.capital += p["amount"] * rate
        cut = p["delivered"] * cfg.reg(p["region"], "fossil_ef")
        n.climate_credit["financed"] = n.climate_credit.get("financed", 0.0) + weight * cut * years


def projects_of(world: World, nid: str) -> list[dict[str, Any]]:
    return [p for p in world.region_projects if p["financier"] == nid]
