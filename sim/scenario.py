"""Build the t=0 world (2025Q1) from the data files.

Starting capacity is sized so that, at t=0, dispatch reproduces each nation's 2025 energy mix
exactly: capacity = 2025 use x headroom. Grid starts just large enough that 2025 wind and solar
are not curtailed. The 2025 dispatch, trade and debt are stored in `Nation.base` / `World.base`
as the reference point for the growth drags.
"""

from __future__ import annotations

from sim import construction, energy, tech
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


def new_world(cfg: Config, seed: int) -> World:
    nations = {nid: new_nation(cfg, nid) for nid in cfg.nation_ids}
    world = World(
        t=0,
        seed=seed,
        nations=nations,
        warming=cfg.tune("climate.warming_start"),
        tech_state={s: cfg.src(s, "global_installed") for s in cfg.source_ids},
    )
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
                "gdp": n.gdp,
                "population": n.population,
            }
        )
    return world
