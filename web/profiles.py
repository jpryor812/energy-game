"""Nation profiles for the new-game screen: each playable nation's 2025 position as strengths,
weaknesses and key figures.

Read-only and derived: every statement comes from the 2025 world the game starts with (data in
data/countries.yaml and the world built from it) and is compared with the other 15 nations, so
the text stays true when the data changes. Nothing here changes the rules.

The display cut-offs below decide only which facts are worth a line on the screen; they are not
simulation tunables.
"""

from __future__ import annotations

from typing import Any

from sim import scoring
from sim.config import Config
from sim.scenario import new_world

TOP = 4  # a nation in the top (or bottom) 4 of the 16 on a measure gets a line about it
EQUIPMENT = {"solar": "solar panels", "wind": "wind turbines", "storage": "batteries"}
DIFFICULTY_ORDER = ["easy", "easy_to_medium", "medium", "hard"]


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _bn(x: float) -> str:
    return f"${x * 1000:,.0f} bn"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def profiles(cfg: Config) -> dict[str, dict[str, Any]]:
    """Profile of every playable nation, in difficulty order (easiest first)."""
    w = new_world(cfg, 0, None)
    ids = cfg.nation_ids
    spec = {nid: cfg.nat_spec(nid) for nid in ids}
    budget_share = cfg.tune("economy.capital_share_of_gdp")

    def energy(nid: str) -> dict[str, float]:
        return {k: v["value"] for k, v in spec[nid]["start"]["energy"].items()}

    def coal_share(nid: str) -> float:
        e = energy(nid)
        return e.get("coal", 0.0) / sum(e.values())

    def fossil_balance(nid: str) -> float:
        """Fossil production as a share of fossil use (above 1: a net exporter)."""
        b = w.nations[nid].base
        use = sum(b[f"use_{f}"] for f in ("coal", "oil", "gas"))
        prod = sum(b[f"production_{f}"] for f in ("coal", "oil", "gas"))
        return prod / use if use else 0.0

    measures = {
        "gdp": {nid: w.nations[nid].gdp for nid in ids},
        "growth": {nid: spec[nid]["trend"]["g0_start"]["value"] for nid in ids},
        "clean": {nid: w.nations[nid].base["clean_share"] for nid in ids},
        "coal": {nid: coal_share(nid) for nid in ids},
        "openness": {nid: spec[nid]["start"]["export_openness"]["value"] for nid in ids},
        "carbon_price": {nid: w.nations[nid].carbon_price for nid in ids},
    }

    def rank(measure: str, nid: str) -> int:
        """1 = highest of the 16."""
        vals = measures[measure]
        return 1 + sum(1 for o in ids if vals[o] > vals[nid])

    def top(measure: str, nid: str) -> bool:
        return rank(measure, nid) <= TOP

    def bottom(measure: str, nid: str) -> bool:
        return rank(measure, nid) > len(ids) - TOP

    def makers(kind: str) -> dict[str, float]:
        return {
            nid: (spec[nid]["start"].get("manufacturing_share") or {}).get(kind, {"value": 0.0})[
                "value"
            ]
            for nid in ids
        }

    lowest_mult = min(scoring.difficulty_multiplier(cfg, nid) for nid in cfg.playable_ids)
    out: dict[str, dict[str, Any]] = {}
    order = sorted(
        cfg.playable_ids,
        key=lambda nid: (DIFFICULTY_ORDER.index(spec[nid]["difficulty"]), spec[nid]["name"]),
    )
    for nid in order:
        s, n, b = spec[nid], w.nations[nid], w.nations[nid].base
        pros: list[str] = []
        cons: list[str] = []
        budget = n.gdp * budget_share
        growth = measures["growth"][nid]
        clean = measures["clean"][nid]
        coal = measures["coal"][nid]
        balance = fossil_balance(nid)
        vuln = s["climate"]["vulnerability"]["value"]
        permit = (s.get("permitting_opposition") or {}).get("value", 1.0)
        mult = scoring.difficulty_multiplier(cfg, nid)

        # money
        if top("gdp", nid):
            pros.append(
                f"Deep pockets: an energy budget of {_bn(budget)} a year to build and deal with."
            )
        elif bottom("gdp", nid) or rank("gdp", nid) > len(ids) // 2:
            cons.append(f"Small budget: {_bn(budget)} a year, so every plant and deal must count.")
        if s["hard_currency_issuer"]:
            pros.append(
                "Issues a reserve currency: foreign loans never drain reserves or weaken its money."
            )
        else:
            cons.append(
                f"No reserve currency: hard-currency loans draw on its "
                f"{_bn(n.fx_reserves)} of reserves, "
                "and rising foreign debt slows growth."
            )

        # growth and demand
        if top("growth", nid):
            pros.append(f"Fast growth, about {_pct(growth)} a year: prosperity rises quickly.")
            cons.append(
                "Demand climbs just as fast: new supply must keep pace or the lights go out."
            )
        elif bottom("growth", nid):
            cons.append(
                f"Slow growth, about {_pct(growth)} a year: little prosperity comes for free."
            )

        # the energy system
        if top("clean", nid):
            pros.append(f"A head start: {_pct(clean)} of supply is already clean.")
        elif bottom("clean", nid):
            cons.append(f"Only {_pct(clean)} of supply is clean: the longest road to net zero.")
        if top("coal", nid):
            cons.append(
                f"Coal-heavy: coal is {_pct(coal)} of primary energy, the dirtiest fuel to replace."
            )
        elif bottom("coal", nid):
            pros.append(
                f"Little coal ({_pct(coal)} of primary energy): "
                "fewer of the dirtiest plants to close."
            )

        # fuel trade
        if balance > 1:
            pros.append(
                f"Net fuel exporter (produces {balance:.1f}× what it burns): "
                "fuel sales add capital income."
            )
            cons.append(
                "That fuel income shrinks as the world decarbonises, and buyers can impose tariffs."
            )
        elif balance < 1 and n.import_dependence > 0:
            cons.append(
                f"Imports {_pct(n.import_dependence)} of its energy: "
                "exposed to fuel price shocks and suppliers."
            )

        # factories
        leads, holds = [], []
        for kind, label in EQUIPMENT.items():
            share = makers(kind)
            mine = share[nid]
            if mine > 0 and mine == max(share.values()):
                leads.append(f"{label} ({_pct(mine)})")
            elif mine > 1 / len(ids):
                holds.append(f"{_pct(mine)} of the world's {label}")
        if leads:
            pros.append(
                f"The world's workshop for {_join(leads)}: "
                "cheap equipment at home and exports to sell."
            )
        if holds:
            pros.append(f"Makes {_join(holds)}.")

        # trade exposure
        if top("openness", nid):
            cons.append(
                f"Lives by trade (exports are {_pct(measures['openness'][nid])} of GDP): "
                "others' tariffs and carbon border fees bite hard."
            )

        # policy and politics
        if top("carbon_price", nid) and n.carbon_price > 0:
            pros.append(
                f"A carbon price already in place (${n.carbon_price:.0f}/t): "
                "carbon revenue from day one."
            )
        elif n.carbon_price == 0:
            cons.append("No carbon price yet: raising one spends political capital.")
        if permit < 1:
            pros.append("Projects face little local opposition: permitting reform is cheap.")
        elif permit > 1:
            cons.append("Strong local opposition to new projects: permitting reform costs votes.")

        # climate
        if vuln > 1:
            cons.append(f"Exposed to climate damage ({vuln:.1f}× a typical nation).")
        elif vuln < 1:
            pros.append(f"Less exposed to climate damage ({vuln:.1f}× a typical nation).")

        if mult > lowest_mult:
            pros.append(f"Score multiplied by {mult:g} for the harder start.")
        else:
            cons.append(f"The easiest start, so no score bonus (×{mult:g}).")

        out[nid] = {
            "name": s["name"],
            "archetype": s["archetype"],
            "difficulty": s["difficulty"],
            "personality": s["personality"],
            "score_multiplier": mult,
            "pros": pros,
            "cons": cons,
            "figures": [
                ["GDP", f"${n.gdp:,.1f} tn"],
                ["Income per person", f"${n.gdp / n.population * 1e6:,.0f}"],
                ["Growth outlook", f"{growth * 100:.1f}% a year"],
                ["Energy budget", f"{_bn(budget)} a year"],
                ["Clean share of supply", _pct(clean)],
                ["Coal share of energy", _pct(coal)],
                ["Fuel production / use", f"{balance:.2f}×"],
                ["CO2 emissions", f"{b['emissions']:,.0f} Mt a year"],
                ["Carbon price", f"${n.carbon_price:.0f}/t"],
            ],
        }
    return out
