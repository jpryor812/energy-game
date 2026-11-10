"""Player-facing description of every action: its slot, parameters with valid ranges, cost, and
an example. Ranges and costs are read from the tuning data, so the catalogue cannot drift from
the rules; a test fails if an action in sim.actions has no entry here.

Units: capital in T$ (trillion US dollars), energy capacity in EJ/yr, emissions in MtCO2,
carbon prices in $/tCO2, tax in points of GDP (0.01 = 1 point).
"""

from __future__ import annotations

from typing import Any

from sim import actions, deals, trade
from sim.config import Config


def _t(cfg: Config, key: str) -> Any:
    return cfg.tune(key)


def catalogue(cfg: Config) -> dict[str, dict[str, Any]]:
    """Every action type -> {slot, summary, params, cost, example}."""
    sources = list(cfg.energy_source_ids)
    clean = [s for s in sources if cfg.category(s) != "fossil"]
    enablers = [s for s in cfg.source_ids if cfg.category(s) == "enabler"]
    equipment = list(trade.EQUIPMENT)
    others = "another nation's id"
    pc = "political capital"
    from sim.session import LINEAR

    entries: dict[str, dict[str, Any]] = {
        "build_capacity": {
            "summary": "Order new generating capacity; it comes online after the source's build "
            "time (quarters: "
            + ", ".join(f"{x} {int(cfg.src(x, 'build_time'))}" for x in cfg.energy_source_ids)
            + "). Fossil sources are refused while your fossil ban is on; geothermal only where "
            "you already have the resource.",
            "params": {"source": sources, "amount": "EJ/yr of capacity, > 0"},
            "cost": "capital: unit cost x amount (see the cost table in `show`)",
            "example": {"type": "build_capacity", "source": "solar", "amount": 0.3},
        },
        "retire_capacity": {
            "summary": "Close plants now. Writes off book value; closing fossil plants costs "
            "approval and fossil jobs.",
            "params": {"source": sources, "amount": "EJ/yr, up to the capacity you have"},
            "cost": f"{pc}: {_t(cfg, 'actions.retire_pc_per_ej'):g} per EJ/yr "
            f"(x{_t(cfg, 'actions.retire_coal_multiplier'):g} for coal)",
            "example": {"type": "retire_capacity", "source": "coal", "amount": 0.1},
        },
        "set_carbon_price": {
            "summary": "Set the domestic carbon price. Raises revenue and shifts new building "
            "to clean sources; raises energy prices.",
            "params": {"level": f"$/t, 0 to {_t(cfg, 'actions.carbon_price_max'):g}"},
            "cost": f"{pc}: {_t(cfg, 'actions.carbon_pc_per_dollar'):g} per $ raised "
            "(lowering is free)",
            "example": {"type": "set_carbon_price", "level": 40},
        },
        "rebate": {
            "summary": "Return a share of carbon revenue to households, easing the price hit.",
            "params": {"share": "0 to 1"},
            "cost": "none (less revenue kept)",
            "example": {"type": "rebate", "share": 0.5},
        },
        "set_subsidy": {
            "summary": "Subsidise a share of a source's cost, so the market builds more of it.",
            "params": {
                "source": sources,
                "share": f"0 to {_t(cfg, 'actions.max_subsidy'):g}",
            },
            "cost": "none up front (the subsidy is paid as plants are built)",
            "example": {"type": "set_subsidy", "source": "wind", "share": 0.2},
        },
        "invest_research": {
            "summary": "Research a technology: lowers its cost for you and adds productivity.",
            "params": {"tech": list(cfg.source_ids), "amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "invest_research", "tech": "storage", "amount": 0.05},
        },
        "invest_efficiency": {
            "summary": "Cut energy intensity (diminishing returns).",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "invest_efficiency", "amount": 0.1},
        },
        "buy_influence": {
            "summary": "Convert capital into influence (spent on talks).",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "buy_influence", "amount": 0.02},
        },
        "build_grid_storage": {
            "summary": "Build grid or storage, letting more wind and solar be used (amount in "
            f"EJ/yr of wind and solar absorbed; grid takes {int(cfg.src('grid', 'build_time'))} "
            f"quarters, storage {int(cfg.src('storage', 'build_time'))}).",
            "params": {"kind": enablers, "amount": "EJ/yr equivalent, > 0"},
            "cost": "capital: unit cost x amount",
            "example": {"type": "build_grid_storage", "kind": "storage", "amount": 0.1},
        },
        "set_activity_cap": {
            "summary": "Cap energy-intensive output: cuts demand and emissions, and GDP and "
            "approval with them.",
            "params": {"level": f"share of output, 0 to {_t(cfg, 'actions.activity_cap_max'):g}"},
            "cost": f"{pc}: {_t(cfg, 'actions.activity_pc_cost'):g} per unit raised",
            "example": {"type": "set_activity_cap", "level": 0.05},
        },
        "adaptation_spend": {
            "summary": "Invest in adaptation: reduces losses from climate damage and disasters.",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "adaptation_spend", "amount": 0.05},
        },
        "set_tax_rate": {
            "summary": "Change taxes against 2025 (in points of GDP). Higher taxes raise capital "
            "and slow growth; voters dislike tax rises.",
            "params": {
                "level": f"{_t(cfg, 'tax.min_change'):g} to {_t(cfg, 'tax.max_change'):g} "
                "(0.01 = +1 point)"
            },
            "cost": f"{pc}: {_t(cfg, 'tax.pc_per_point'):g} per point raised (cuts are free)",
            "example": {"type": "set_tax_rate", "level": 0.01},
        },
        "set_tax_credit": {
            "summary": "Tax credit on a source's output ($/GJ generated) or on a clean-tech "
            "line's factory sales (share of sales).",
            "params": {
                "kind": ["generation", "manufacturing"],
                "tech": f"generation: {sources}; manufacturing: {equipment}",
                "rate": f"generation 0 to {_t(cfg, 'tax.generation_credit_max'):g} $/GJ; "
                f"manufacturing 0 to {_t(cfg, 'tax.manufacturing_credit_max'):g} of sales "
                "(0 removes the credit)",
            },
            "cost": "none up front (revenue given up as output happens)",
            "example": {
                "type": "set_tax_credit",
                "kind": "generation",
                "tech": "solar",
                "rate": 0.1,
            },  # fmt: skip
        },
        "build_factory": {
            "summary": "Build a clean-tech factory line: jobs, exports, and a cheaper home supply "
            f"(takes {int(_t(cfg, 'industry.factory_build_time'))} quarters; lines age out over "
            f"{_t(cfg, 'industry.factory_lifespan'):g} years; the clean score counts what they "
            "sell).",
            "params": {"tech": equipment, "amount": "factory units, > 0"},
            "cost": f"capital: {_t(cfg, 'industry.factory_capital_cost'):g} per unit",
            "example": {"type": "build_factory", "tech": "solar", "amount": 0.1},
        },
        "set_domestic_content": {
            "summary": "Require a share of equipment to be made at home (protects factories, "
            "raises costs).",
            "params": {"tech": equipment, "share": "0 to 1 (0 removes the rule)"},
            "cost": "none",
            "example": {"type": "set_domestic_content", "tech": "wind", "share": 0.3},
        },
        "fund_retraining": {
            "summary": "Retrain fossil workers: softens the jobs hit at elections.",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "fund_retraining", "amount": 0.02},
        },
        "set_fossil_ban": {
            "summary": "Ban (or unban) new fossil plants; the market stops building them, and "
            "fossil projects not yet under construction are cancelled (plants already being "
            "built still finish).",
            "params": {"on": [True, False]},
            "cost": f"{pc}: {_t(cfg, 'actions.fossil_ban_pc'):g} to switch on",
            "example": {"type": "set_fossil_ban", "on": True},
        },
        "set_permitting": {
            "summary": "Permitting and zoning reform: new plants, grid and storage (yours, the "
            "market's and deals') build faster, cutting part of each source's permitting time "
            "(grid and wind most). Local opposition costs approval and votes, more the more "
            "you build and the stronger your country's opposition (shown on the screen).",
            "params": {"level": "0 (none) to 1 (full reform)"},
            "cost": f"{pc}: {_t(cfg, 'permitting.pc_per_level'):g} per unit raised; lowering is "
            "free",
            "example": {"type": "set_permitting", "level": 0.5},
        },
        "electrification_program": {
            "summary": "Electrify transport, heat and industry: raises how much of demand wind, "
            "solar and other clean power can serve.",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "electrification_program", "amount": 0.1},
        },
        "build_removal": {
            "summary": "Build carbon removal capacity (uses energy; expensive early, cheaper with "
            f"learning; takes {int(cfg.src('carbon_removal', 'build_time'))} quarters).",
            "params": {"amount": "MtCO2/yr of removal, > 0"},
            "cost": "capital: unit cost x amount",
            "example": {"type": "build_removal", "amount": 5},
        },
        "methane_abatement": {
            "summary": "Cut methane leaks and other methane: lowers warming within years.",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "methane_abatement", "amount": 0.05},
        },
        "fund_forests": {
            "summary": "Pay into the global forest fund: cuts land-use CO2 and earns climate "
            "credit.",
            "params": {"amount": "T$, > 0"},
            "cost": "capital: amount",
            "example": {"type": "fund_forests", "amount": 0.02},
        },
        "make_pledge": {
            "summary": "Pledge emissions at a share of your 2025 level by a year. Breaking it "
            "costs trust with everyone.",
            "params": {
                "target": "share of 2025 emissions, 0 to 2",
                "year": f"{_t(cfg, 'time.start_year') + 1} to {_t(cfg, 'time.start_year') + 75}",
            },
            "cost": "none",
            "example": {"type": "make_pledge", "target": 0.5, "year": 2040},
        },
        "open_talks": {
            "summary": "Open talks with a nation: raises its trust in you.",
            "params": {"target": others},
            "cost": f"influence: {_t(cfg, 'diplomacy.talks_influence_cost'):g}",
            "example": {"type": "open_talks", "target": "CHN"},
        },
        "set_tariff": {
            "summary": "Tariff a nation's goods (not allowed between carbon-club members).",
            "params": {"target": others, "level": f"0 to {_t(cfg, 'trade.tariff_max'):g}"},
            "cost": "none (trade and trust suffer)",
            "example": {"type": "set_tariff", "target": "USA", "level": 0.1},
        },
        "lift_tariff": {
            "summary": "Remove a tariff you set.",
            "params": {"target": others},
            "cost": "none",
            "example": {"type": "lift_tariff", "target": "USA"},
        },
        "join_bloc": {
            "summary": "Join the carbon club (needs a carbon price of at least "
            f"{_t(cfg, 'diplomacy.club_min_carbon_price'):g} $/t): cheaper deal finance among "
            "members, coalition tariffs on laggards.",
            "params": {"bloc": [trade.CLUB]},
            "cost": "none",
            "example": {"type": "join_bloc", "bloc": trade.CLUB},
        },
        "leave_bloc": {
            "summary": "Leave the carbon club.",
            "params": {"bloc": [trade.CLUB]},
            "cost": "none",
            "example": {"type": "leave_bloc", "bloc": trade.CLUB},
        },
        "propose_deal": {
            "summary": "Offer a clean-energy deal to a host nation; it answers next quarter. "
            "equipment_on_credit lends the plant, climate_loan lends cash (T$) that builds it at "
            "the host's cost (rate); energy_as_a_service sells the "
            "power (price, $/GJ); equity_for_energy takes a share of the plant's margin (share; "
            "the plant can fail if the host becomes unreliable).",
            "params": {
                "target": others,
                "deal_type": list(deals.TYPES),
                "source": clean,
                "amount": "EJ/yr (a climate loan: T$), > 0",
                "duration": f"quarters, 4 to {_t(cfg, 'deals.max_duration'):g}",
                "collateral": "0 to 1",
                "exit_penalty": "0 to 1",
                "currency": ["hard", "local"],
                "rate | price | share": "rate 0 to 0.3; price 0 to 50; share 0 to 1",
            },
            "cost": "you must be able to finance it now (capital); paid when accepted",
            "example": {
                "type": "propose_deal",
                "target": "VNM",
                "deal_type": "equipment_on_credit",
                "source": "solar",
                "amount": 0.05,
                "duration": 40,
                "collateral": 0.2,
                "exit_penalty": 0.1,
                "currency": "hard",
                "rate": 0.05,
            },  # fmt: skip
        },
        "respond_deal": {
            "summary": "Answer a deal offered to you (see the inbox in `show`), from the quarter "
            "after it was made.",
            "params": {
                "deal_id": "id from the inbox",
                "response": ["accept", "refuse", "counter"],
                "rate | price | share": "for a counter: the new term",
            },
            "cost": "none",
            "example": {"type": "respond_deal", "deal_id": "D0001", "response": "accept"},
        },
        "exit_deal": {
            "summary": "Leave an energy-as-a-service deal, paying its exit penalty.",
            "params": {"deal_id": "id of one of your active deals"},
            "cost": "the deal's exit penalty",
            "example": {"type": "exit_deal", "deal_id": "D0001"},
        },
        "buy_credits": {
            "summary": "Bid for carbon credits (count 0.25 of a real cut). The market clears "
            "at one price each quarter.",
            "params": {"amount": "MtCO2, > 0", "max_price": f">= {_t(cfg, 'credits.min_price'):g}"},
            "cost": "capital: amount x clearing price (you must cover amount x max_price)",
            "example": {"type": "buy_credits", "amount": 10, "max_price": 30},
        },
        "sell_credits": {
            "summary": "Offer carbon credits you hold (earned by cutting below your 1.5 degC "
            "pathway).",
            "params": {"amount": "MtCO2, up to your balance", "min_price": ">= 0"},
            "cost": "none (you are paid the clearing price)",
            "example": {"type": "sell_credits", "amount": 10, "min_price": 20},
        },
    }
    for name, entry in entries.items():
        entry["slot"] = actions.SPECS[name].slot
        if name in LINEAR:
            base = entry["params"]["amount"]
            entry["params"]["amount"] = f'{base}, or "max" (all you can afford)'
    return {name: entries[name] for name in actions.SPECS}
