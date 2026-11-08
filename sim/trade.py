"""Goods trade and clean-tech equipment trade, and how tariffs act on them.

Goods (non-fossil exports): each nation exports `goods_openness` x GDP, split across the other
15 nations and the rest of the world in proportion to their GDP (a gravity model). A partner's
tariff cuts exports to it by `tariff_elasticity` x the tariff. The growth effect is the change in
exports against their no-tariff level; the imposer pays the tariff on its imports (a price drag)
and collects it as revenue. Trade relations start from a clean slate: no real-world restrictions.

Clean-tech equipment (solar, wind, batteries): every completed build buys `equipment_share` of its
cost from manufacturers in proportion to their world share (data/countries.yaml), shifted away
from suppliers the buyer has tariffed. A tariff also raises the buyer's cost of that technology.
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
    """World manufacturing shares for one technology, the rest of the world taking the rest."""
    shares = {}
    for nid in cfg.nation_ids:
        spec = cfg.nat_spec(nid)["start"].get("manufacturing_share") or {}
        if tech in spec:
            shares[nid] = spec[tech]["value"]
    shares[ROW] = max(0.0, 1.0 - sum(shares.values()))
    return shares


def supplier_weights(cfg: Config, world: World, buyer: str, tech: str) -> dict[str, float]:
    """Where `buyer` sources equipment: base shares shifted away from suppliers it tariffs."""
    switching = cfg.tune("trade.supplier_switching")
    raw = {}
    for supplier, share in base_shares(cfg, tech).items():
        rate = 0.0 if supplier in (buyer, ROW) else tariff(world, buyer, supplier)
        raw[supplier] = share * (1 + rate) ** -switching
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else raw


def tariff_premium(cfg: Config, world: World, buyer: str, tech: str) -> float:
    """Extra share of build cost `buyer` pays because of its own tariffs on equipment."""
    if tech not in EQUIPMENT:
        return 0.0
    weights = supplier_weights(cfg, world, buyer, tech)
    paid = sum(w * tariff(world, buyer, s) for s, w in weights.items() if s not in (buyer, ROW))
    return cfg.src(tech, "equipment_share") * paid


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
    per source. Sets each nation's clean-tech export rate (T$/yr), its no-tariff baseline, and
    adds to suppliers' exported-cut rate (Mt/yr displaced abroad by their equipment).
    """
    sales = {nid: 0.0 for nid in world.nations}
    expected = {nid: 0.0 for nid in world.nations}
    for buyer in sorted(completed):
        b = world.nations[buyer]
        for tech, amount in sorted(completed[buyer].items()):
            if tech not in EQUIPMENT or amount <= 0:
                continue
            value = cfg.src(tech, "equipment_share") * unit_cost[tech] * amount
            cut = 0.0
            if tech in cfg.vre_ids:
                cut = amount / cfg.src(tech, "headroom") * displaced_ef(cfg, b)
            weights = supplier_weights(cfg, world, buyer, tech)
            base = base_shares(cfg, tech)
            for supplier in sorted(weights):
                if supplier in (buyer, ROW):
                    continue
                sales[supplier] += weights[supplier] * value
                expected[supplier] += base[supplier] * value
                world.nations[supplier].exported_cut_rate += weights[supplier] * cut
    for nid, n in world.nations.items():
        n.cleantech_exports = sales[nid] * 4 / dt
        n.base["cleantech_expected"] = expected[nid] * 4 / dt
