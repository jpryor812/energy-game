"""Goods trade and clean-tech equipment trade, and how tariffs act on them.

Goods (non-fossil exports): each nation exports `goods_openness` x GDP, split across the other
15 nations and the rest of the world in proportion to their GDP (a gravity model). A partner's
tariff cuts exports to it by `tariff_elasticity` x the tariff. The growth effect is the change in
exports against their no-tariff level; the imposer pays the tariff on its imports (a price drag)
and collects it as revenue. Trade relations start from a clean slate: no real-world restrictions.

Clean-tech equipment (solar, wind, batteries): every completed build buys `equipment_share` of its
cost from manufacturers in proportion to their factory capacity (starting from 2025 world shares
in data/countries.yaml; nations add factories with actions, and manufacturing tax credits make
theirs more competitive), shifted away from suppliers the buyer has tariffed and toward its own
factories under a domestic-content rule. Tariffs and unmet content rules raise the buyer's cost.
Sales abroad are clean-tech exports; the supplier also earns credit for the emissions its
equipment displaces abroad (scored at `credits.weight_exported`).

Fossil-fuel trade stays in sim.energy.
"""

from __future__ import annotations

from sim import energy
from sim.config import Config
from sim.state import Nation, World

CLUB = "carbon_club"
ROW = "ROW"
EQUIPMENT = ("solar", "wind", "storage")


def club_members(world: World) -> list[str]:
    return world.blocs.get(CLUB, [])


def tariff(world: World, imposer: str, target: str) -> float:
    """Effective tariff `imposer` charges on goods from `target`: its own, or the coalition
    tariff if it is a club member and the target is not, whichever is higher."""
    own = world.nations[imposer].tariffs.get(target, 0.0)
    members = club_members(world)
    if imposer in members and target not in members:
        own = max(own, world.coalition_tariffs.get(target, 0.0))
    return own


# --- goods trade ---------------------------------------------------------------------------------


def row_gdp(world: World) -> float:
    """Rest-of-world GDP, growing with the 16 nations."""
    now = sum(n.gdp for n in world.nations.values())
    return world.base["row_gdp"] * now / world.base["gdp_16"]


def apply_goods(world: World, cfg: Config) -> None:
    """Exports, tariff revenue and the goods-trade growth effect for every nation."""
    elasticity = cfg.tune("trade.tariff_elasticity")
    gdp = {nid: n.gdp for nid, n in world.nations.items()}
    row = row_gdp(world)
    total = sum(gdp.values()) + row
    revenue = {nid: 0.0 for nid in world.nations}
    for nid in sorted(world.nations):
        n = world.nations[nid]
        planned = n.base["goods_openness"] * n.gdp
        partners = total - gdp[nid]
        actual = planned * row / partners
        for pid in sorted(world.nations):
            if pid == nid:
                continue
            flow = planned * gdp[pid] / partners
            rate = tariff(world, pid, nid)
            delivered = flow * max(0.0, 1 - elasticity * rate)
            actual += delivered
            revenue[pid] += rate * delivered
        n.goods_exports = actual
        n.trade_drag = cfg.tune("trade.export_growth_elasticity") * (actual - planned) / n.gdp
    for nid, n in world.nations.items():
        n.tariff_revenue = revenue[nid]
        n.trade_drag -= cfg.tune("trade.tariff_price_drag") * revenue[nid] / n.gdp


def cleantech_effect(cfg: Config, n: Nation) -> float:
    """Growth change from clean-tech exports above or below the no-tariff baseline share."""
    gap = n.cleantech_exports - n.base.get("cleantech_expected", 0.0)
    return cfg.tune("trade.cleantech_growth_elasticity") * gap / n.gdp


# --- clean-tech equipment ------------------------------------------------------------------------


def base_shares(cfg: Config, tech: str) -> dict[str, float]:
    """2025 world manufacturing shares from the data, the rest of the world taking the rest."""
    shares = {}
    for nid in cfg.nation_ids:
        spec = cfg.nat_spec(nid)["start"].get("manufacturing_share") or {}
        if tech in spec:
            shares[nid] = spec[tech]["value"]
    shares[ROW] = max(0.0, 1.0 - sum(shares.values()))
    return shares


def init_factories(cfg: Config, world: World) -> None:
    """2025 factory capacity (T$/yr of output) from world capacity x manufacturing shares."""
    for tech in EQUIPMENT:
        total = cfg.tune(f"industry.world_capacity_{tech}")
        shares = base_shares(cfg, tech)
        for nid, n in world.nations.items():
            n.factory_capacity[tech] = shares.get(nid, 0.0) * total
            n.base[f"factory_2025_{tech}"] = n.factory_capacity[tech]
        world.base[f"row_capacity_{tech}"] = shares[ROW] * total


def capacity_shares(cfg: Config, world: World, tech: str) -> dict[str, float]:
    """World market shares: factory capacity, boosted by manufacturing tax credits. The rest of
    the world keeps its 2025 capacity."""
    k = cfg.tune("industry.credit_competitiveness")
    raw = {
        nid: n.factory_capacity.get(tech, 0.0)
        * (1 - n.disruption.get(tech, 0.0))
        * (1 + n.tax_credits.get(f"manufacturing:{tech}", 0.0)) ** k
        for nid, n in world.nations.items()
    }
    raw[ROW] = world.base.get(f"row_capacity_{tech}", 0.0)
    total = sum(raw.values())
    return {k_: v / total for k_, v in raw.items()} if total > 0 else raw


def supplier_weights(cfg: Config, world: World, buyer: str, tech: str) -> dict[str, float]:
    """Where `buyer` sources equipment: market shares, shifted away from suppliers it tariffs,
    and toward its own factories if it sets a domestic-content rule."""
    switching = cfg.tune("trade.supplier_switching")
    raw = {}
    for supplier, share in capacity_shares(cfg, world, tech).items():
        rate = 0.0 if supplier in (buyer, ROW) else tariff(world, buyer, supplier)
        raw[supplier] = share * (1 + rate) ** -switching
    total = sum(raw.values())
    weights = {k: v / total for k, v in raw.items()} if total > 0 else raw
    required = world.nations[buyer].domestic_content.get(tech, 0.0)
    own = weights.get(buyer, 0.0)
    if required > own and own < 1:
        scale = (1 - required) / (1 - own)
        weights = {k: (required if k == buyer else v * scale) for k, v in weights.items()}
        weights.setdefault(buyer, required)
    return weights


def content_premium(cfg: Config, world: World, buyer: str, tech: str) -> float:
    """Extra share of build cost when a domestic-content rule asks for more than the nation's
    own factories can make."""
    n = world.nations[buyer]
    required = n.domestic_content.get(tech, 0.0)
    if required <= 0:
        return 0.0
    demand = n.equipment_demand.get(tech, 0.0)
    can_make = 1.0 if demand <= 0 else min(1.0, n.factory_capacity.get(tech, 0.0) / demand)
    return cfg.tune("industry.domestic_content_penalty") * max(0.0, required - can_make)


def cost_premium(cfg: Config, world: World, buyer: str, tech: str) -> float:
    """Extra share of build cost from the buyer's own equipment tariffs and content rules."""
    if tech not in EQUIPMENT:
        return 0.0
    weights = supplier_weights(cfg, world, buyer, tech)
    paid = sum(w * tariff(world, buyer, s) for s, w in weights.items() if s not in (buyer, ROW))
    tariffs = cfg.src(tech, "equipment_share") * paid
    return (
        tariffs
        + content_premium(cfg, world, buyer, tech)
        + disruption_premium(cfg, world, buyer, tech)
    )


def disruption_premium(cfg: Config, world: World, buyer: str, tech: str) -> float:
    """Extra equipment cost while factories abroad are disrupted: the share of world capacity
    knocked out (outside the buyer's own factories) x the penalty."""
    total = sum(n.factory_capacity.get(tech, 0.0) for n in world.nations.values())
    total += world.base.get(f"row_capacity_{tech}", 0.0)
    if total <= 0:
        return 0.0
    lost = sum(
        n.factory_capacity.get(tech, 0.0) * n.disruption.get(tech, 0.0)
        for nid, n in world.nations.items()
        if nid != buyer
    )
    return (
        cfg.src(tech, "equipment_share") * cfg.tune("shocks.disruption_cost_penalty") * lost / total
    )


def displaced_ef(cfg: Config, n: Nation) -> float:
    """Average emission factor of the fossil energy a nation burns now (Mt/EJ)."""
    fossil = {s: v for s, v in n.supply.items() if energy.is_fossil(cfg, s)}
    total = sum(fossil.values())
    if total <= 0:
        return 0.0
    return sum(v * energy.emission_factor(cfg, n.id, s) for s, v in fossil.items()) / total


def apply_equipment(
    cfg: Config,
    world: World,
    completed: dict[str, dict[str, float]],
    unit_cost: dict[str, float],
    dt: int,
) -> None:
    """Record clean-tech sales from this step's completed builds.

    `completed` is capacity finished per nation per source; `unit_cost` the world unit cost
    per source. Sets each nation's factory sales and equipment demand per technology, its
    clean-tech export rate (T$/yr) and no-tariff baseline (its 2025 share of others' purchases),
    and adds to suppliers' exported-cut rate (Mt/yr displaced abroad by their equipment).
    """
    per_year = 4 / dt
    exports = {nid: 0.0 for nid in world.nations}
    expected = {nid: 0.0 for nid in world.nations}
    sales = {nid: {t: 0.0 for t in EQUIPMENT} for nid in world.nations}
    demand = {nid: {t: 0.0 for t in EQUIPMENT} for nid in world.nations}
    for buyer in sorted(completed):
        b = world.nations[buyer]
        for tech, amount in sorted(completed[buyer].items()):
            if tech not in EQUIPMENT or amount <= 0:
                continue
            value = cfg.src(tech, "equipment_share") * unit_cost[tech] * amount
            demand[buyer][tech] += value
            cut = 0.0
            if tech in cfg.vre_ids:
                cut = amount / cfg.src(tech, "headroom") * displaced_ef(cfg, b)
            weights = supplier_weights(cfg, world, buyer, tech)
            base = base_shares(cfg, tech)
            for supplier in sorted(weights):
                if supplier == ROW:
                    continue
                sales[supplier][tech] += weights[supplier] * value
                if supplier == buyer:
                    continue
                exports[supplier] += weights[supplier] * value
                expected[supplier] += base.get(supplier, 0.0) * value
                world.nations[supplier].exported_cut_rate += weights[supplier] * cut
    for nid, n in world.nations.items():
        n.cleantech_exports = exports[nid] * per_year
        n.base["cleantech_expected"] = expected[nid] * per_year
        alpha = 1 - (1 - cfg.tune("jobs.smoothing")) ** dt
        for t, v in sales[nid].items():
            old = n.factory_sales.get(t, v * per_year)
            n.factory_sales[t] = old + alpha * (v * per_year - old)
        n.equipment_demand = {t: v * per_year for t, v in demand[nid].items()}
