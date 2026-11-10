"""Build the t=0 world (2025Q1) from the data files.

Starting capacity is sized so that, at t=0, dispatch reproduces each nation's 2025 energy mix
exactly: capacity = 2025 use x headroom. Grid starts just large enough that 2025 wind and solar
are not curtailed. The 2025 dispatch, trade and debt are stored in `Nation.base` / `World.base`
as the reference point for the growth drags.
"""

from __future__ import annotations

from sim import climate, construction, diplomacy, energy, jobs, tech, trade
from sim.config import FUELS, Config
from sim.state import Nation, World


def new_nation(cfg: Config, nid: str) -> Nation:
    spec = cfg.nat_spec(nid)
    use = {s: cfg.nat(nid, f"start.energy.{s}") for s in cfg.energy_source_ids}
    total = sum(use.values())
    gdp = cfg.nat(nid, "start.gdp")
    capacity = {s: 0.0 for s in cfg.source_ids}
    for s, amount in use.items():
        capacity[s] = amount * cfg.src(s, "headroom")
    vre = sum(use[s] for s in cfg.vre_ids)
    if "grid" in capacity:
        capacity["grid"] = max(0.0, vre - cfg.tune("energy.vre_base_absorb_share") * total)
    approval = cfg.tune("politics.approval_start")
    issuer = spec["hard_currency_issuer"]
    production = {f: cfg.nat(nid, f"start.production.{f}") for f in FUELS}
    base = {f"production_{f}": production[f] for f in FUELS}
    base.update({f"exports_{f}": max(0.0, production[f] - use[f]) for f in FUELS})
    base.update({f"use_{f}": use[f] for f in FUELS})
    return Nation(
        id=nid,
        playable=spec["playable"],
        personality=spec["personality"],
        gdp=gdp,
        population=cfg.nat(nid, "start.population"),
        fx_reserves=0.0 if issuer else cfg.nat(nid, "start.fx_reserves"),
        debt_hard=cfg.nat(nid, "start.debt_hard"),
        debt_local=cfg.nat(nid, "start.debt_local"),
        approval=approval,
        stability=approval,
        political_capital=cfg.tune("politics.political_capital_start"),
        energy_intensity=total / gdp,
        demand=total,
        capacity=capacity,
        carbon_price=cfg.nat(nid, "start.carbon_price"),
        slots_banked={"domestic": 0, "diplomatic": 0},
        base=base,
    )


def new_world(cfg: Config, seed: int, difficulty: str | None = None) -> World:
    nations = {nid: new_nation(cfg, nid) for nid in cfg.nation_ids}
    world = World(
        t=0,
        seed=seed,
        nations=nations,
        warming=cfg.tune("climate.warming_start"),
        tech_state={s: cfg.src(s, "global_installed") for s in cfg.source_ids},
        difficulty=difficulty or cfg.tuning["difficulty"]["default"],
    )
    if world.difficulty not in cfg.tuning["difficulty"]["levels"]:
        raise ValueError(f"unknown difficulty '{world.difficulty}'")
    for nid in sorted(nations):
        n = nations[nid]
        d = energy.dispatch(cfg, n, energy.base_demand(n))
        n.supply, n.energy_price, n.emissions = d.supply, d.price, d.emissions
    for nid in sorted(nations):
        construction.seed_pipeline(cfg, world, nid, nations[nid])
    world.base = {f"fuel_use_{f}": v for f, v in energy.global_fuel_use(world).items()}
    energy.apply_trade(world, cfg)
    for nid in sorted(nations):
        n = nations[nid]
        n.energy_price = tech.delivered_price(cfg, world, n)
        n.base.update(
            {
                "energy_price": n.energy_price,
                "export_revenue": n.export_revenue,
                "trade_balance": energy.trade_balance(cfg, n),
                "debt_hard": n.debt_hard,
                "debt_local": n.debt_local,
                "debt_hard_ratio": n.debt_hard / n.gdp,
                "emissions": n.emissions,
                "carbon_price": n.carbon_price,
                "import_dependence": n.import_dependence,
                "income_per_person": n.gdp / n.population,
                "clean_share": sum(v for k, v in n.supply.items() if cfg.category(k) != "fossil")
                / max(sum(n.supply.values()), 1e-9),
                "fx_reserves": n.fx_reserves,
                "goods_openness": max(
                    cfg.tune("trade.openness_floor"),
                    cfg.nat(nid, "start.export_openness") - n.export_revenue / n.gdp,
                ),
                "gdp": n.gdp,
                "population": n.population,
            }
        )
    gdp_16 = sum(n.gdp for n in nations.values())
    world.base["gdp_16"] = gdp_16
    world.base["row_gdp"] = max(0.0, cfg.tune("trade.world_gdp_2025") - gdp_16)
    climate.init(cfg, world)
    trade.init_factories(cfg, world)
    init_jobs(cfg, world)
    diplomacy.init_trust(world, cfg)
    diplomacy.init_club(world, cfg, FOUNDERS)
    world.credit_price = cfg.tune("credits.start_price")
    diplomacy.set_allowances(cfg, world)
    return world


FOUNDERS = ["EUU"]  # the carbon club's founder (decided 2026-11-08)


def init_jobs(cfg: Config, world: World) -> None:
    """Starting build rates, factory sales and jobs, from the projects already under way in the
    first year, so job counts do not jump in the first quarter."""
    first_year: dict[str, dict[str, float]] = {}
    for nid, n in world.nations.items():
        done: dict[str, float] = {}
        for c in n.pipeline:
            if c.complete_turn <= 4 and not c.source.startswith(construction.FACTORY):
                done[c.source] = done.get(c.source, 0.0) + c.amount
        first_year[nid] = done
        n.build_rate = sum(done.values())
    costs = {s: tech.unit_cost(cfg, world, s) for s in trade.EQUIPMENT_OF}
    trade.apply_equipment(cfg, world, first_year, costs, 4)
    for n in world.nations.values():
        n.exported_cut_rate = 0.0
        n.jobs = jobs.count(cfg, n)
        n.base["fossil_jobs"] = n.jobs["fossil"]
