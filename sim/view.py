"""What the player sees: a structured observation of the game and a compact text rendering.

Only information a real player would have is shown. AI personalities, other nations' plans,
and the seeded random draws (disasters, election swing) stay hidden. The expected vote leaves out
the swing.

Units: GDP and capital in T$ (trillion US dollars); energy in EJ/yr; emissions in MtCO2/yr;
prices in $/tCO2 and $/GJ; jobs in millions.
"""

from __future__ import annotations

import json
from typing import Any

from sim import (
    climate,
    construction,
    deals,
    diplomacy,
    economy,
    elections,
    energy,
    jobs,
    research,
    scoring,
    tech,
    trade,
    turn,
)
from sim.catalogue import catalogue
from sim.session import Game

FORECAST_AFTER = 1  # quarters into a term before the expected vote is shown (M14: was 4)
SWING_Z = 1.96  # the swing stays within this many standard deviations 95% of the time


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


def _label(game: Game, t: int) -> str:
    return turn.quarter_label(t, game.cfg.tune("time.start_year"))


def _next_election(game: Game) -> int | None:
    cfg, t = game.cfg, game.world.t
    for q in range(t, int(cfg.tune("time.turns"))):
        if elections.due(cfg, q):
            return q
    return None


def observe(game: Game) -> dict[str, Any]:
    cfg, w, me = game.cfg, game.world, game.country
    n = w.nations[me]
    ready = game.preview()  # after this quarter's income: what can be spent now
    p = ready.nations[me]
    year = cfg.tune("time.start_year") + w.t / 4

    # Election
    nxt = _next_election(game)
    election: dict[str, Any] = {"next": None}
    if nxt is not None and not game.over:
        election = {
            "next": _label(game, nxt),
            "quarters_away": nxt - w.t,
            "needed": cfg.tune("elections.threshold"),
            "expected_vote": None,
            "parts": {},
            "swing_range": _r(SWING_Z * cfg.tune("elections.swing_sd")),
        }
        if w.t - int(w.term_start["t"]) >= FORECAST_AFTER:
            parts = {k: v for k, v in elections.vote(cfg, w).items() if k != "swing"}
            weight = cfg.tune("elections.growth_weight")
            t0 = int(w.term_start["t"])
            years = max(0.25, (w.t + 1 - t0) / 4)
            growth = (n.gdp / w.term_start["gdp"]) ** (1 / years) - 1
            election["growth_this_term"] = _r(growth, 4)
            election["growth_expected"] = _r(growth - parts["growth"] / weight / 100, 4)
            election["expected_vote"] = _r(sum(parts.values()))
            election["parts"] = {k: _r(v) for k, v in parts.items()}
            election["note"] = "expected vote if held now, before a random swing"
            start = w.term_start
            election["jobs_baseline"] = {
                k[5:]: _r(v) for k, v in sorted(start.items()) if k.startswith("jobs_")
            }
            election["jobs_term_average"] = {
                k: _r(v) for k, v in sorted(elections.term_jobs(w).items())
            }

    # Energy
    delivered = sum(n.supply.values())
    supply = {s: _r(v) for s, v in sorted(n.supply.items()) if v > 1e-6}
    capacity = {s: _r(v) for s, v in sorted(n.capacity.items()) if v > 1e-6}
    arrivals: dict[str, dict[int, float]] = {}
    for c in n.pipeline:
        by_q = arrivals.setdefault(c.source, {})
        by_q[c.complete_turn] = by_q.get(c.complete_turn, 0.0) + c.amount
    pipeline = {
        s: {
            "total": _r(sum(q.values())),
            "arrivals": [
                {"online": _label(game, t), "amount": _r(v, 4)} for t, v in sorted(q.items())
            ],
        }
        for s, q in sorted(arrivals.items())
    }
    costs = {
        s: {
            "unit_cost": _r(tech.nation_unit_cost(cfg, w, n, s), 4),
            "lcoe": _r(tech.lcoe(cfg, w, n, s), 2) if s in cfg.energy_source_ids else None,
            "at_floor": tech.at_floor(cfg, w, s),
        }
        for s in cfg.source_ids
    }

    # Why clean power is curtailed: the limits dispatch applies (sim.energy).
    t_last = max(0, w.t - 1)
    base_absorb = cfg.tune("energy.vre_base_absorb_share") * n.demand
    enablers = {
        s: _r(n.capacity.get(s, 0.0)) for s in cfg.source_ids if cfg.category(s) == "enabler"
    }
    integration = {
        "wind_solar_available": _r(sum(n.capacity.get(s, 0.0) for s in cfg.vre_ids)),
        "wind_solar_usable": _r(energy.vre_absorb_limit(cfg, n, n.demand, t_last)),
        "base_absorb": _r(base_absorb),
        "enablers": enablers,
        "electrifiable_cap": _r(energy.vre_max_share(cfg, t_last, n) * n.demand),
        "clean_cap": _r(energy.clean_max_share(cfg, t_last, n) * n.demand),
        "electrification_bonus": _r(energy.electrification_bonus(cfg, n)),
    }

    # Emissions and targets
    base_em = n.base["emissions"]
    emissions = {
        "now": _r(n.emissions, 1),
        "vs_2025": _r(n.emissions / base_em - 1) if base_em else 0.0,
        "target_path_now": _r(cfg.target_level(me, year) * base_em, 1),
        "pathway_1_5c_now": _r(diplomacy.pathway_level(cfg, year, w.difficulty) * base_em, 1),
        "pledge": (
            {"target": _r(n.pledge.target_emissions, 1), "year": n.pledge.year}
            if n.pledge
            else None
        ),
        "removals": _r(n.removals, 1),
        "credit_balance": _r(n.credit_balance, 1),
    }

    # Relations
    club = trade.club_members(w)
    relations = {
        o: {
            "their_trust_in_you": _r(diplomacy.trust(w, o, me), 2),
            "your_tariff": _r(n.tariffs.get(o, 0.0), 2),
            "their_tariff": _r(w.nations[o].tariffs.get(me, 0.0), 2),
            "club": o in club,
        }
        for o in sorted(w.nations)
        if o != me
    }

    # Research (M12)
    tree = []
    for tid in cfg.tech_ids:
        spec = cfg.rtech(tid)
        first = w.tech_firsts.get(tid)
        row = {
            "tech": tid,
            "name": spec["name"],
            "progress": _r(n.research_progress.get(tid, 0.0)),
            "have": research.has(n, tid),
            "cost_now": _r(research.cost_now(cfg, w, tid), 3),
            "min_quarters": spec["min_quarters"]["value"],
            "useful_now": _r(research.useful_funding(cfg, w, p, tid), 4),
            "blocked": research.blocked(cfg, n, tid),
            "first": [first[0], _label(game, first[1])] if first else None,
            "owners": sorted(o for o, m in w.nations.items() if research.has(m, tid)),
            # M13 licensing
            "licensed": tid in n.licensed,
            "offers": [[s, _r(pr, 4)] for pr, s in research.offers(cfg, w, me, tid)][:3],
            "patent_expired": research.patent_expired(cfg, w, tid),
            "my_price": n.license_prices.get(tid) if research.researched(n, tid) else None,
            "excluded": n.license_excluded.get(tid, []),
            "gives": spec.get("unlocks", [])
            + spec.get("enables", [])
            + [
                f"{s} {kind.replace('_', ' ')} x{v['value']:g}"
                for kind in ("cost", "build_time")
                for s, v in spec.get("effects", {}).get(kind, {}).items()
            ],
        }  # fmt: skip
        tree.append(row)

    # Deals
    inbox, mine, sent = [], [], []
    expiry = int(cfg.tune("deals.proposal_expiry"))
    for d in sorted(w.deals.values(), key=lambda d: d.id):
        if me not in (d.host, d.financier):
            continue
        row = {
            "id": d.id,
            "type": d.type,
            "financier": d.financier,
            "host": d.host,
            "status": d.status,
            "terms": {k: (_r(v) if isinstance(v, float) else v) for k, v in d.terms.items()},
        }
        if "end_turn" in d.terms:
            row["terms"]["end_label"] = _label(game, int(d.terms["end_turn"]))
        if d.status == deals.OPEN:
            row["expires"] = _label(game, d.start_turn + expiry)
        if d.status == deals.OPEN and deals.responder(d) == me:
            row["can_answer"] = w.t > d.start_turn
            inbox.append(row)
        elif d.status == deals.OPEN:
            sent.append(row)  # M9: your own offers awaiting an answer
        elif d.status == deals.ACTIVE:
            mine.append(row)

    # Recent events and last results
    last = w.history[-1] if w.history else None
    events = []
    if last:
        for e in last.get("events", []):
            if e.get("nation") == me:
                events.append(e)
        others = [e for e in last.get("events", []) if e.get("nation") != me]
        if others:
            events.append({"type": "elsewhere", "count": len(others)})
        if last.get("election"):
            events.append({"type": "election"} | last["election"])

    lost = game.lost
    result = scoring.score(cfg, w, me, lost=lost) if w.history else None
    leaders = (
        [
            {"nation": nid, "score": _r(v["score"], 1), "rank": v["rank"]}
            for nid, v in sorted(result["all_nations"].items(), key=lambda kv: -kv[1]["score"])
        ]
        if result
        else []
    )
    return {
        "quarter": _label(game, w.t) if not game.over else _label(game, w.t - 1),
        "turn": w.t,
        "turns": int(cfg.tune("time.turns")),
        "country": me,
        "difficulty": w.difficulty,
        "over": game.over,
        "lost": lost,
        "election": election,
        "resources": {
            "capital": _r(p.capital, 4),
            "political_capital": _r(p.political_capital, 2),
            "influence": _r(p.influence, 2),
            "slots": dict(p.slots_banked),
            "note": "available to spend this quarter (income included)",
        },
        "economy": {
            "gdp": _r(n.gdp, 3),
            "gdp_vs_2025": _r(n.gdp / n.base["gdp"] - 1),
            "growth_annual": _r(n.growth, 4),
            "approval": _r(n.approval),
            "stability": _r(n.stability),
            "fallen_below": cfg.tune("scoring.fallen_stability"),
            "tax_change": _r(n.tax_change, 4),
            "fx_reserves": _r(n.fx_reserves),
            "debt_hard": _r(n.debt_hard),
            "jobs": {k: _r(v) for k, v in sorted(n.jobs.items())},
            "climate_damage_drag": _r(n.climate_damage, 4),
        },
        "energy": {
            "demand": _r(n.demand),
            "delivered": _r(delivered),
            "shortfall_share": _r(n.shortfall / n.demand) if n.demand else 0.0,
            "curtailment": _r(n.curtailment),
            "price": _r(n.energy_price, 2),
            "price_vs_2025": _r(n.energy_price / n.base["energy_price"] - 1),
            "clean_share": _r(scoring.clean_share(cfg, n)),
            "clean_share_year": _r(scoring.annual_clean_share(cfg, w, me)),
            "carbon_price": _r(n.carbon_price, 1),
            "rebate": _r(n.rebate, 2),
            "fossil_ban": bool(n.fossil_ban),
            "subsidies": {k: _r(v, 2) for k, v in sorted(n.subsidies.items()) if v},
            "supply": supply,
            "capacity": capacity,
            "building": pipeline,
            "costs": costs,
            "integration": integration,
            "policy_effects": {
                "retraining_relief": _r(jobs.retraining_relief(cfg, n)),
                "rebate_price_relief": _r(n.rebate * cfg.tune("economy.rebate_price_relief")),
                "methane_cut_fossil": _r(climate.abatement(cfg, n, "fossil")),
                "methane_cut_other": _r(climate.abatement(cfg, n, "other")),
                "activity_cap": _r(n.activity_cap),
                "pledge_on_track": diplomacy.pledge_on_track(cfg, w, me),
                "permitting": _r(n.permitting),
                "permitting_opposition": economy.permitting_opposition(cfg, me),
                "build_times": {
                    s: construction.build_time(cfg, n, s)
                    for s in ("grid", "onshore_wind", "offshore_wind", "solar")
                },
                "build_times_without": {
                    s: tech.build_quarters(cfg, n, s, reform=False)
                    for s in ("grid", "onshore_wind", "offshore_wind", "solar")
                },
                "cost_saving": {
                    s: _r(tech.permitting_saving(cfg, n, s))
                    for s in ("grid", "onshore_wind", "offshore_wind", "solar")
                },
                "backlash": _r(economy.permitting_backlash(cfg, w, n)),
            },
        },
        "emissions": emissions,
        "world": {
            "warming": _r(w.warming),
            "world_multiplier": _r(scoring.world_multiplier(cfg, w.warming)),
            "warming_5y_ago": _r(w.history[-21]["warming"]) if len(w.history) > 20 else None,
            "champion_at": cfg.tune("scoring.good_world_warming"),
            "global_emissions": _r(w.global_emissions, 0) if w.history else None,
            "credit_price": _r(w.credit_price, 1),
            "club": list(club),
            "coalition_tariff_on_you": _r(w.coalition_tariffs.get(me, 0.0)),
        },
        "relations": relations,
        "research": tree,
        "ccs": {k: _r(v) for k, v in n.ccs.items() if v > 0},
        "deals": {
            "inbox": inbox,
            "sent": sent,
            "active": mine,
            "room_to_host": _r(deals.host_room(cfg, w, me)),
        },  # fmt: skip
        "notices": list(game.notices),
        "leaders": leaders,
        "races": (
            [
                {k: _r(v) if isinstance(v, float) else v for k, v in r.items()}
                for r in scoring.races(cfg, w, me)
            ]
            if w.history
            else []
        ),  # fmt: skip
        "last_quarter": {
            "results": last["nations"][me]["actions"] if last else [],
            "events": events,
        },
        "score": (
            {
                "score": _r(result["score"], 1),
                "score_if_ended_now": _r(result["score_at_exit"], 1),
                "rank": result["rank"],
                "nation_index": _r(result["nation_index"], 1),
                "absolute_index": _r(result["absolute_index"], 1),
                "combined_index": _r(result["combined_index"], 1),
                "difficulty_multiplier": result["difficulty_multiplier"],
                "weights": [
                    cfg.tune("scoring.weight_absolute"),
                    cfg.tune("scoring.weight_relative"),
                ],  # fmt: skip
                "world_multiplier": _r(result["world_multiplier"]),
                "components": {k: _r(v) for k, v in result["components"].items()},
                "bonuses": result["bonuses"],
                "ending": result["ending"],
            }
            if result
            else None
        ),
    }


# --- text --------------------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _kv(d: dict[str, Any], fmt: str = "{:g}") -> str:
    return ", ".join(f"{k} {fmt.format(v)}" for k, v in d.items()) or "none"


def render(obs: dict[str, Any], brief: bool = False) -> str:
    """A compact text screen. `brief` leaves out costs, capacity, relations and the list of
    active deals."""
    o = obs
    e, r, ec, en, em, wd = (
        o["election"],
        o["resources"],
        o["economy"],
        o["energy"],
        o["emissions"],
        o["world"],
    )
    when = "final" if o["over"] else f"turn {o['turn']}/{o['turns']}"
    lines = [f"== {o['country']}  {o['quarter']}  ({when}, {o['difficulty']}) =="]
    if o["over"]:
        final = o["score"]["score"] if o["score"] else 0
        lines.append(f"GAME OVER: {o['lost'] or o['score']['ending']}. Final score {final}.")
    if e["next"] and e["expected_vote"] is None:
        lines.append(
            f"Election {e['next']} (in {e['quarters_away']} q); need {e['needed']} of the vote. "
            "Forecast from the second quarter of the term."
        )
    elif e["next"]:
        lines.append(
            f"Election {e['next']} (in {e['quarters_away']} q): expected vote "
            f"{e['expected_vote']:.3f}, need {e['needed']}; a random swing moves the result by up "
            f"to about {e['swing_range']:.2f} (95% of the time), so keep a margin "
            f"[{_kv(e['parts'], '{:+.3f}')}]"
        )
        gap = e["growth_this_term"] - e["growth_expected"]
        lines.append(
            f"  growth this term {e['growth_this_term'] * 100:.2f}%/yr vs expected "
            f"{e['growth_expected'] * 100:.2f}%/yr ({'ahead' if gap >= 0 else 'behind'} by "
            f"{abs(gap) * 100:.2f} pt); taxes, prices and jobs count as averages over the term"
        )
        lines.append(
            "  levers: growth (lower taxes, lower energy prices, avoid blackouts); jobs "
            "(retraining softens fossil losses; building and factories add jobs); prices (carbon "
            "rebate, lower carbon price); taxes (cuts); local opposition (lower permitting reform; "
            "it halves after a term at the same level)"
        )
        lines.append(
            f"  jobs (m), term average so far {_kv(e['jobs_term_average'], '{:.2f}')} against "
            f"the last term's average {_kv(e['jobs_baseline'], '{:.2f}')} (fossil losses count "
            "double unless retrained)"
        )
    if o["notices"]:
        lines += ["", "THIS QUARTER:"] + [f"  {x}" for x in o["notices"]]
    lq = o["last_quarter"]
    if lq["results"] or lq["events"]:
        lines.append("")
        lines.append("YOUR ACTIONS AND EVENTS:")
        for res in lq["results"]:
            a = res["action"]
            status = "ok" if res["ok"] else f"REJECTED ({res['reason']})"
            lines.append(f"  {a.get('type')}: {status}")
        for ev in lq["events"]:
            lines.append("  event: " + _event(ev))
    lines += [
        "",
        f"RESOURCES (this quarter): capital {r['capital']:.6g} T$ (${r['capital'] * 1000:.2f}B) "
        f"| political capital {r['political_capital']:.2f} | influence {r['influence']:.2f} | "
        f"slots domestic {r['slots'].get('domestic', 0)}, diplomatic "
        f"{r['slots'].get('diplomatic', 0)}",
        "",
        f"ECONOMY: GDP {ec['gdp']:.3f} T$ ({_pct(ec['gdp_vs_2025'])} vs 2025), growth "
        f"{ec['growth_annual'] * 100:.2f}%/yr | approval {ec['approval']:.2f} | stability "
        f"{ec['stability']:.2f} (falls below {ec['fallen_below']}) | tax "
        f"{ec['tax_change'] * 100:+.1f} pt",
        f"  jobs (m): {_kv(ec['jobs'], '{:.2f}')} | FX reserves {ec['fx_reserves']:.3f} | "
        f"hard debt {ec['debt_hard']:.3f} | climate drag {ec['climate_damage_drag'] * 100:.2f}"
        "%/yr",
        "",
        f"ENERGY: demand {en['demand']:.2f} EJ, delivered {en['delivered']:.2f}, shortfall "
        f"{en['shortfall_share'] * 100:.1f}%, curtailed {en['curtailment']:.2f} | price "
        f"{en['price']:.2f} $/GJ ({_pct(en['price_vs_2025'])}) | clean "
        f"{en['clean_share'] * 100:.0f}% (last 4 quarters {en['clean_share_year'] * 100:.0f}%)",
        f"  carbon price {en['carbon_price']:.0f} $/t, rebate {en['rebate']:.2f}, fossil ban "
        f"{'on' if en['fossil_ban'] else 'off'}, subsidies {_kv(en['subsidies'])}",
        f"  supply: {_kv(en['supply'], '{:.2f}')}",
        _integration(en["integration"]),
        _effects(en["policy_effects"]),
    ]
    if not brief:
        lines.append(f"  capacity: {_kv(en['capacity'], '{:.2f}')}")
    lines.append("  building (yours and the market's; total, then the next arrivals):")
    for s, b in en["building"].items():
        nxt = ", ".join(f"{a['amount']:.3g} {a['online']}" for a in b["arrivals"][:4])
        more = f", +{len(b['arrivals']) - 4} more" if len(b["arrivals"]) > 4 else ""
        lines.append(f"    {s} {b['total']:.3g}: {nxt}{more}")
    if not en["building"]:
        lines.append("    none")
    if not brief:
        lines.append(
            "  costs (unit T$ per EJ/yr, removal per Mt/yr | LCOE $/GJ; 'floor' = learning can "
            "cut it no further): "
            + ", ".join(
                f"{s} {c['unit_cost']:.4g}"
                + (f"|{c['lcoe']:.1f}" if c["lcoe"] is not None else "")
                + (" floor" if c["at_floor"] else "")
                for s, c in en["costs"].items()
            )
        )
    lines += [
        "",
        f"EMISSIONS (net of removals): {em['now']:.0f} Mt/yr ({_pct(em['vs_2025'])} vs 2025) | "
        f"target path now {em['target_path_now']:.0f} | 1.5C pathway now "
        f"{em['pathway_1_5c_now']:.0f} | removals {em['removals']:.0f} | credits held "
        f"{em['credit_balance']:.0f} Mt | pledge "
        + (
            f"{em['pledge']['target']:.0f} Mt by {em['pledge']['year']}" if em["pledge"] else "none"
        ),
        f"WORLD: warming {wd['warming']:.3f} C"
        + (f" (5 years ago {wd['warming_5y_ago']:.3f})" if wd["warming_5y_ago"] is not None else "")
        + f", multiplier {wd['world_multiplier']:.2f}; good world (Champion) at or below "
        f"{wd['champion_at']:g} C and falling | "
        "global CO2 "
        + (f"{wd['global_emissions'] / 1000:.1f}" if wd["global_emissions"] is not None else "-")
        + f" Gt/yr | credit price {wd['credit_price']:.0f} $/t | club: "
        f"{', '.join(wd['club']) or 'none'} | coalition tariff on you "
        f"{wd['coalition_tariff_on_you']:.2f}",
    ]
    if not brief:
        lines += [
            "",
            "RELATIONS (their trust in you; tariffs yours/theirs; * = club):",
            "  "
            + "  ".join(
                f"{k}{'*' if v['club'] else ''} {v['their_trust_in_you']:.2f}"
                + (
                    f" t{v['your_tariff']:.2f}/{v['their_tariff']:.2f}"
                    if v["your_tariff"] or v["their_tariff"]
                    else ""
                )
                for k, v in o["relations"].items()
            ),
        ]
    lines += _research(o.get("research", []), o.get("ccs", {}), brief)
    inbox, active = o["deals"]["inbox"], o["deals"]["active"]
    sent = o["deals"].get("sent", [])
    lines.append("")
    lines.append(
        f"DEALS: inbox {len(inbox)}, awaiting answers {len(sent)}, active {len(active)}; you can "
        f"host {o['deals'].get('room_to_host', 0):.3g} EJ/yr more of deal capacity"
    )
    for d in inbox:
        lines.append(
            f"  OFFER {d['id']} {d['type']} {d['financier']}->{d['host']} "
            f"{_terms(d['terms'])} (expires {d['expires']})"
            + ("" if d["can_answer"] else " (answer next quarter)")
        )
    for d in sent:
        lines.append(
            f"  SENT {d['id']} {d['type']} {d['financier']}->{d['host']} "
            f"{_terms(d['terms'])} (awaiting {_other(d, o['country'])}, expires {d['expires']})"
        )
    if not brief:
        for d in active:
            t = d["terms"]
            ends = f" until {t['end_label']}" if "end_label" in t else ""
            lines.append(
                f"  ACTIVE {d['id']} {d['type']} {d['financier']}->{d['host']} "
                f"{t.get('source')} {t.get('capacity', t.get('amount', 0)):.3g} EJ{ends}"
            )
    s = o["score"]
    lines.append("")
    if s is None:
        lines.append("SCORE: shown from the end of the first quarter.")
    else:
        head = "SCORE at exit" if o["over"] and o["lost"] else "SCORE now"
        lines.append(
            f"{head} {s['score_if_ended_now']:.1f} (rank {s['rank']}/16, ranked on this score) = "
            f"combined {s['combined_index']:.1f} x world {s['world_multiplier']:.2f} + bonuses; "
            f"combined = {s['weights'][0]:g} x absolute {s['absolute_index']:.1f} + "
            f"{s['weights'][1]:g} x nation index {s['nation_index']:.1f} x country "
            f"{s['difficulty_multiplier']:g}"
        )
        lines.append(
            f"  nation index parts: {_kv(s['components'], '{:.2f}')}"
            + (f" | bonuses {_kv(s['bonuses'])}" if s["bonuses"] else "")
            + (" | clean = your share of world clean-tech equipment sales over the last year "
               "against your 2025 share of factory capacity")
        )  # fmt: skip
        top = o["leaders"][:5]
        mine = next((x for x in o["leaders"] if x["nation"] == o["country"]), None)
        board = ", ".join(f"{x['nation']} {x['score']:.1f}" for x in top)
        if mine and mine not in top:
            board += f" ... you {mine['score']:.1f}"
        lines.append(f"  leaders (score now): {board}")
        lines.append("  bonus races: " + "; ".join(_race(r, o["country"]) for r in o["races"]))
    return "\n".join(lines)


def _research(tree: list[dict[str, Any]], ccs: dict[str, float], brief: bool) -> list[str]:
    if not tree:
        return []
    out = [
        "",
        "RESEARCH (fund_research; cost T$ now / minimum quarters; a technology someone already has "
        "costs less):",
    ]
    have = [r["tech"] + (" (licensed)" if r.get("licensed") else "") for r in tree if r["have"]]
    out.append("  you have: " + (", ".join(have) if have else "nothing yet"))
    mine = [r for r in tree if r["have"] and not r.get("licensed")]
    if mine:
        out.append(
            "  your licences (set_license_price): "
            + "; ".join(
                f"{r['tech']} "
                + ("free (patent expired)" if r.get("patent_expired")
                   else f"{r['my_price']:.3g} T$" if r.get("my_price") is not None
                   else "not for sale")
                + (f", excluding {', '.join(r['excluded'])}" if r.get("excluded") else "")
                for r in mine
            )
        )  # fmt: skip
    sale = [r for r in tree if not r["have"] and r.get("offers")]
    if sale:
        out.append(
            "  for sale to you (buy_license; cheapest first): "
            + "; ".join(
                f"{r['tech']} "
                + ("free from any owner (patent expired)" if r.get("patent_expired")
                   else ", ".join(f"{s} {p:.3g}" for s, p in r["offers"]))
                + ("" if not r["blocked"] or "already" in r["blocked"] else f" ({r['blocked']})")
                for r in sale
            )
        )  # fmt: skip
    for r in tree:
        if not r["have"] and r["progress"] > 0:
            out.append(
                f"  in progress: {r['tech']} {r['progress']:.0%} (cost {r['cost_now']:.3g}, spend "
                f"up to {r['useful_now']:.3g} this quarter; gives {', '.join(r['gives'])})"
            )
    ready = [r for r in tree if not r["have"] and r["progress"] <= 0 and not r["blocked"]]
    if ready:
        out.append(
            "  available: "
            + "; ".join(
                f"{r['tech']} {r['cost_now']:.3g}/{r['min_quarters']}q -> {', '.join(r['gives'])}"
                for r in ready
            )
        )
    locked = [r for r in tree if not r["have"] and r["blocked"] and r["progress"] <= 0]
    if locked and not brief:
        out.append("  locked: " + "; ".join(f"{r['tech']} ({r['blocked']})" for r in locked))
    firsts = [r for r in tree if r["first"]]
    if firsts:
        out.append(
            "  breakthroughs: "
            + ", ".join(
                f"{r['tech']} {r['first'][0]} {r['first'][1]} ({len(r['owners'])} have it)"
                for r in firsts
            )
        )
    if ccs:
        out.append("  carbon capture fitted: " + _kv(ccs, "{:.2f}") + " EJ/yr")
    return out


def _other(d: dict[str, Any], me: str) -> str:
    return d["host"] if d["financier"] == me else d["financier"]


def _race(r: dict[str, Any], me: str) -> str:
    name = r["race"].replace("_", " ")
    if r["race"] == "first_net_zero":
        if r["claimed"]:
            who = "you" if r["leader"] == me else r["leader"]
            return f"{name} claimed by {who} in {r['claimed']}"
        return f"{name} open (you at {r['you']:.0%} of 2025)"
    if r["leader"] is None:
        return f"{name}: nobody yet"
    if r["leader"] == me:
        return f"{name}: you lead ({r['you']:.3g})"
    return f"{name}: {r['leader']} {r['lead']:.3g}, you {r['you']:.3g}"


def _effects(e: dict[str, Any]) -> str:
    pledge = {None: "none", True: "on track", False: "off track"}[e["pledge_on_track"]]
    times = ", ".join(
        f"{s} {q}" + (f" (was {e['build_times_without'][s]}, {e['cost_saving'][s]:.1%} cheaper)"
                      if q < e["build_times_without"][s] else "")
        for s, q in e["build_times"].items()
    )  # fmt: skip
    return (
        f"  permitting reform {e['permitting']:.2f} (build quarters now: {times}); backlash "
        f"x{e['backlash']:g} (your country x{e['permitting_opposition']:g}, halved once a "
        "level has held a full term)\n"
        f"  policy effects: retraining removes {e['retraining_relief']:.0%} of the fossil-job "
        f"penalty at elections | rebate removes {e['rebate_price_relief']:.0%} of the growth drag "
        f"from energy prices | methane cut {e['methane_cut_fossil']:.0%} (fossil), "
        f"{e['methane_cut_other']:.0%} (other) | activity cap {e['activity_cap']:.0%} of output "
        f"| pledge {pledge}"
    )


def _integration(g: dict[str, Any]) -> str:
    """Why wind and solar are curtailed, in one line."""
    grid = " + ".join(f"{k} {v:.2f}" for k, v in g["enablers"].items())
    return (
        f"  wind+solar: {g['wind_solar_available']:.2f} EJ available, usable up to "
        f"{g['wind_solar_usable']:.2f} = base {g['base_absorb']:.2f} + {grid}, capped by the "
        f"electrifiable share {g['electrifiable_cap']:.2f}; all clean sources capped at "
        f"{g['clean_cap']:.2f} (electrification raises both caps, now "
        f"+{g['electrification_bonus'] * 100:.0f} pts)"
    )


def _terms(t: dict[str, Any]) -> str:
    keys = ("source", "amount", "duration", "rate", "price", "share", "currency", "collateral")
    return " ".join(f"{k}={t[k]}" for k in keys if k in t)


def _event(ev: dict[str, Any]) -> str:
    kind = ev.get("type")
    if kind == "disaster":
        return (
            f"climate disaster: GDP -{ev['gdp_loss'] * 100:.1f}%, "
            f"{ev.get('source') or 'no'} capacity damaged"
        )
    if kind == "disruption":
        return f"factory disruption: {ev['tech']} line for {ev['quarters']} quarters"
    if kind == "elsewhere":
        return f"{ev['count']} disasters or disruptions in other nations"
    if kind == "election":
        return f"election {ev['event']} with {ev['vote']:.3f} of the vote"
    return str(ev)


def render_actions(cfg) -> str:
    """The action catalogue as text."""
    lines = []
    for name, a in catalogue(cfg).items():
        lines.append(f"{name} [{a['slot']}] - {a['summary']}")
        for k, v in a["params"].items():
            lines.append(f"    {k}: {v}")
        lines.append(f"    cost: {a['cost']}")
        lines.append(f"    e.g. {_json(a['example'])}")
    return "\n".join(lines)


def _json(x: Any) -> str:
    return json.dumps(x)
