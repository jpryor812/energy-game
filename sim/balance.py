"""Balance harness: run the grid, measure the build doc's acceptance criteria, and write
docs/BALANCE_REPORT.md.

    python -m sim.balance --workers 8            # full report (6 seeds)
    python -m sim.balance --workers 8 --seeds 1  # quicker

Criteria (docs/BUILD_SIM_V0.md, with the 2026-11-08 change to criterion 4):

1. Determinism: the same seed gives the same state hash, run twice.
2. No dominant bot: no scripted bot has the best expected score for every playable nation.
   Since M7 a lost game (Voted Out or Fallen Government) scores `loss_score`, so expected
   scores include the risk of losing; the report also shows completion rates.
3. Viable strategies: for each playable nation at least two scripted bots finish within
   `TOLERANCE` of the best expected score.
4. Difficulty ordering: with the same bot, the easy and medium nations' mean absolute index is
   higher than the hard nations', for at least three of the four scripted bots (all_fossil can
   invert it: when nobody cuts, per-person emissions dominate and big emitters look worst).
5. Free-rider tension: a nation that free-rides (all_fossil) gains on the economic components
   of its relative index (income and welfare) by 2030 against a cooperative strategy
   (balanced), but its final score falls when many nations free-ride (every nation plays
   all_fossil). The economic components are used because the index now also scores climate
   contribution (decided 2026-11-08), which free-riding loses by construction. Both final-score
   worlds run the full game without elections.
6. Sanity: no impossible values in any run.
7. Game length and punishment for neglect: every run reaches the final turn unless the player
   loses; reckless play is removed from office more than any other strategy; steady play
   (`STEADY`) completes at least `STEADY_COMPLETION` of its games.

The thresholds below are report settings, not world tuning.
"""

from __future__ import annotations

import argparse
import itertools
import statistics
import sys
from pathlib import Path
from typing import Any

from sim import config, runner, scoring
from sim.config import Config

SCRIPTED = ["all_clean", "all_fossil", "balanced", "deal_maker"]
BOTS = ["ai", *SCRIPTED, "reckless"]
TOLERANCE = 0.05
FALLEN_SHARE = 0.3
STEADY = ["balanced", "deal_maker"]
STEADY_COMPLETION = 0.7
REPORT = Path(__file__).resolve().parent.parent / "docs" / "BALANCE_REPORT.md"


def free_rider_world(cfg: Config, seed: int, country: str, everyone: bool) -> dict[str, Any]:
    """`country` plays all_fossil for the full game, with no elections (so both worlds run to
    the end and compare like with like). If `everyone`, every nation plays all_fossil: a world
    of free-riders; otherwise the others are AI. Returns the country's summary."""
    from sim import bots, turn
    from sim.scenario import new_world

    world = new_world(cfg, seed)
    while world.t < cfg.tune("time.turns"):
        who = world.nations if everyone else [country]
        acts = {nid: bots.all_fossil(cfg, world, nid) for nid in who}
        world = turn.step(world, cfg, actions=acts, ai=not everyone)
    return runner.summarize(cfg, world, country, "all_fossil", 1)


def _free_job(args: tuple) -> dict[str, Any]:
    return free_rider_world(*args)


def completed(main: list[dict[str, Any]], bot: str, country: str | None = None) -> float:
    """Share of a bot's runs that reached the end without losing."""
    rs = [r for r in main if r["bot"] == bot and country in (None, r["country"])]
    return sum(r["ending"] not in scoring.LOSSES for r in rs) / max(1, len(rs))


def mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else float("nan")


def verdict(ok: bool, tune: bool = False) -> str:
    return "PASS" if ok else ("TUNE" if tune else "FAIL")


def run(cfg: Config, seeds: list[int], workers: int) -> dict[str, Any]:
    playable = cfg.playable_ids
    main_jobs = [
        (seed, c, b, None, "normal") for c, b, seed in itertools.product(playable, BOTS, seeds)
    ]
    main = runner.run_grid(cfg, main_jobs, workers)
    diff_jobs = [
        (seeds[0], c, "balanced", None, d)
        for d, c in itertools.product(config.DIFFICULTIES, playable)
    ]
    by_difficulty = runner.run_grid(cfg, diff_jobs, workers)
    free_args = [(cfg, seeds[0], c, e) for e in (False, True) for c in playable]
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as pool:
            many_free = list(pool.map(_free_job, free_args))
    else:
        many_free = [_free_job(a) for a in free_args]
    short = {}
    for c, bot in itertools.product(playable, ("balanced", "all_fossil")):
        w = runner.play(cfg, seeds[0], c, bot, until=20)
        comps = scoring.score(cfg, w, c)["components"]
        short[(c, bot)] = 100 * (comps["income"] + comps["welfare"]) / 2
    w1 = runner.play(cfg, seeds[0], "IND", "balanced")
    w2 = runner.play(cfg, seeds[0], "IND", "balanced")
    return {
        "main": main,
        "by_difficulty": by_difficulty,
        "many_free": many_free,
        "short": short,
        "determinism": (w1.hash(), w2.hash()),
        "seeds": seeds,
    }


def report(cfg: Config, data: dict[str, Any]) -> str:
    main, playable = data["main"], cfg.playable_ids
    by = {}
    for r in main:
        by.setdefault((r["country"], r["bot"]), []).append(r)
    score = {k: mean([r["score"] for r in v]) for k, v in by.items()}
    absolute = {k: mean([r["absolute_index"] for r in v]) for k, v in by.items()}
    lines = [
        "# Balance report",
        "",
        "Generated by `python -m sim.balance`. Do not edit by hand.",
        "",
        f"Seeds: {data['seeds']}. World difficulty: normal unless stated. "
        f"{len(main)} main runs over {len(playable)} playable nations and {len(BOTS)} bots.",
        "",
        "## Summary",
        "",
        "| # | Criterion | Verdict |",
        "|---|---|---|",
    ]
    results: list[tuple[str, str, list[str]]] = []

    # 1. Determinism
    a, b = data["determinism"]
    results.append(
        (
            "Determinism",
            verdict(a == b),
            [
                f"India, balanced, seed {data['seeds'][0]}, run twice: `{a[:16]}` / `{b[:16]}`.",
                "Byte-identical across machines is not tested here: the simulation uses only "
                "plain Python floats and SHA-256-seeded streams, so it should hold.",
            ],
        )
    )

    # 2 and 3. Dominant bot, viable strategies
    table = [
        "| Nation | " + " | ".join(BOTS) + " | Best scripted |",
        "|---" * (len(BOTS) + 2) + "|",
    ]
    best_bots, viable_ok = {}, True
    viable_rows = []
    for c in playable:
        scripted = {b: score[(c, b)] for b in SCRIPTED}
        best = max(scripted, key=lambda b: (scripted[b], b))
        best_bots[c] = best
        close = [b for b in SCRIPTED if scripted[b] >= (1 - TOLERANCE) * scripted[best]]
        viable_ok &= len(close) >= 2
        viable_rows.append(f"- {c}: within {TOLERANCE:.0%} of best: {', '.join(close)}")
        table.append(
            f"| {c} | " + " | ".join(f"{score[(c, b)]:.1f}" for b in BOTS) + f" | {best} |"
        )
    dominant = len(set(best_bots.values())) == 1
    survive = [
        "| Nation | " + " | ".join(BOTS) + " |",
        "|---" * (len(BOTS) + 1) + "|",
    ]
    for c in playable:
        cells = []
        for b in BOTS:
            done = [r["score"] for r in by[(c, b)] if r["ending"] not in scoring.LOSSES]
            share = len(done) / len(by[(c, b)])
            cells.append(f"{share:.0%} / {mean(done):.1f}" if done else f"{share:.0%} / -")
        survive.append(f"| {c} | " + " | ".join(cells) + " |")
    results.append(
        (
            "No dominant bot",
            verdict(not dominant),
            [
                "Expected score by nation and bot (mean over seeds; a lost game scores "
                f"{cfg.tune('scoring.loss_score'):g}):",
                "",
                *table,
                "",
                "Games completed / mean score of completed games:",
                "",
                *survive,
                "",
            ],
        )
    )
    results.append(("Viable strategies", verdict(viable_ok, tune=True), viable_rows))

    # 4. Difficulty ordering on the absolute index
    hard_ids = [c for c in playable if cfg.nat_spec(c)["difficulty"] == "hard"]
    easy_ids = [c for c in playable if c not in hard_ids]
    rows = [
        f"| Bot | Easier ({', '.join(easy_ids)}) | Hard ({', '.join(hard_ids)}) | Order |",
        "|---|---|---|---|",
    ]
    in_order = 0
    for b in SCRIPTED:
        easy = mean([absolute[(c, b)] for c in easy_ids])
        hard = mean([absolute[(c, b)] for c in hard_ids])
        in_order += easy > hard
        rows.append(f"| {b} | {easy:.1f} | {hard:.1f} | {'ok' if easy > hard else 'inverted'} |")
    rows.append("")
    rows.append(
        "Final scores, which multiply the relative index by country difficulty, by design "
        "reward harder nations' improvements; see the table under criterion 2."
    )
    order_ok = bool(easy_ids and hard_ids) and in_order >= len(SCRIPTED) - 1
    results.append(("Difficulty ordering (absolute index)", verdict(order_ok, tune=True), rows))

    # 5. Free-rider tension
    rows = ["| Nation | Economic index 2030: balanced | all_fossil | Final score, all_fossil: "
            "cooperative world | free-rider world | Warming: coop / free-rider |",
            "|---|---|---|---|---|---|"]  # fmt: skip
    n_free = len(data["many_free"]) // 2
    coops = {r["country"]: r for r in data["many_free"][:n_free]}
    free = {r["country"]: r for r in data["many_free"][n_free:]}
    gain = loss = 0
    for c in playable:
        coop = coops[c]
        fr = free[c]
        s_bal, s_fos = data["short"][(c, "balanced")], data["short"][(c, "all_fossil")]
        gain += s_fos > s_bal
        loss += fr["score"] < coop["score"]
        rows.append(
            f"| {c} | {s_bal:.1f} | {s_fos:.1f} | {coop['score']:.1f} | {fr['score']:.1f} | "
            f"{coop['warming']:.2f} / {fr['warming']:.2f} |"
        )
    rows.append("")
    rows.append(
        f"Free-riding gains by 2030 for {gain}/{len(playable)} nations; the free-rider's "
        f"final score falls when everyone free-rides for {loss}/{len(playable)}. Both final-score "
        "worlds run the full game without elections."
    )
    results.append(
        (
            "Free-rider tension",
            verdict(gain >= len(playable) / 2 and loss == len(playable), tune=True),
            rows,
        )
    )

    # 6. Sanity
    issues = [(r["country"], r["bot"], r["seed"], i) for r in main for i in r["sanity_issues"]]
    rows = [f"- {c} {b} seed {s}: {i}" for c, b, s, i in issues[:20]] or ["No issues in any run."]
    results.append(("Sanity", verdict(not issues), rows))

    # 7. Game length and punishment for neglect
    short_runs = [r for r in main if r["turns_played"] < 100 and r["ending"] not in scoring.LOSSES]
    reckless = [r for r in main if r["bot"] == "reckless"]
    fallen = [r for r in reckless if r["ending"] == "Fallen Government"]
    others_fallen = [
        (r["country"], r["bot"], r["seed"])
        for r in main
        if r["bot"] != "reckless" and r["ending"] == "Fallen Government"
    ]
    share = len(fallen) / max(1, len(reckless))

    def loss_rate(bot: str) -> float:
        votes = [e for r in main if r["bot"] == bot for e in r["elections"]]
        contested = [e for e in votes if e["event"] in ("won", "lost")]
        return sum(e["event"] == "lost" for e in contested) / max(1, len(contested))

    reckless_loss = loss_rate("reckless")
    other_loss = {b: loss_rate(b) for b in SCRIPTED}
    completion = {b: completed(main, b) for b in BOTS}
    steady_ok = all(completion[b] >= STEADY_COMPLETION for b in STEADY)
    removed = sum(
        r["ending"] == "Fallen Government" or r["elections_lost"] > 0 for r in reckless
    ) / max(1, len(reckless))
    rows = [
        f"- Runs ending early without a loss: {len(short_runs)}.",
        "- Games completed (not voted out or fallen), by bot: "
        + ", ".join(f"{b} {v:.0%}" for b, v in completion.items())
        + f". Steady play ({', '.join(STEADY)}) should complete at least "
        f"{STEADY_COMPLETION:.0%}.",
        f"- Reckless bot: Fallen Government in {len(fallen)}/{len(reckless)} runs ({share:.0%}); "
        f"loses {reckless_loss:.0%} of the elections it contests; removed from office at least "
        f"once in {removed:.0%} of runs.",
        "- Other bots lose: "
        + ", ".join(f"{b} {v:.0%}" for b, v in other_loss.items())
        + " of the elections they contest.",
        f"- Other bots: Fallen Government in {len(others_fallen)} runs"
        + (f": {others_fallen}" if others_fallen else "."),
        f"- Pass: reckless play is removed from office (falls, or loses an election) at least "
        f"{FALLEN_SHARE:.0%} of the time and more often than any other bot, no other bot falls, "
        "and steady play usually completes. Losing an election ends the game (M7). Neglect is "
        "punished mainly at the ballot box: political capital limits how fast "
        "plants can close and the market backfills, so reckless play rarely causes blackouts. "
        "Blackouts themselves erode stability directly (tests/test_m6.py).",
    ]
    ok = (
        not short_runs
        and steady_ok
        and not others_fallen
        and removed >= FALLEN_SHARE
        and reckless_loss > max(other_loss.values())
    )
    results.append(
        (
            "Game length and punishment for neglect",
            verdict(ok, tune=not short_runs),
            rows,
        )
    )

    for i, (name, v, _) in enumerate(results, 1):
        lines.append(f"| {i} | {name} | {v} |")
    lines.append("")
    for i, (name, v, body) in enumerate(results, 1):
        lines += [f"## {i}. {name}: {v}", "", *body, ""]

    # World difficulty comparison
    lines += [
        "## World difficulty",
        "",
        "Balanced bot, seed " + str(data["seeds"][0]) + ", each playable nation.",
        "",
        "| Difficulty | Expected score | Completed | Mean warming at end | Disasters per run "
        "| Disruptions per run |",
        "|---|---|---|---|---|---|",
    ]
    for d in config.DIFFICULTIES:
        rs = [r for r in data["by_difficulty"] if r["difficulty"] == d]
        cells = [mean([r[k] for r in rs]) for k in ("score", "warming", "disasters", "disruptions")]
        done = sum(r["ending"] not in scoring.LOSSES for r in rs) / max(1, len(rs))
        lines.append(
            f"| {d} | {cells[0]:.1f} | {done:.0%} | {cells[1]:.2f} | {cells[2]:.1f} "
            f"| {cells[3]:.1f} |"
        )
    lines.append("")
    lines += ["## Other signals", ""]
    lines.append(
        "- Elections lost per run, by bot: "
        + ", ".join(
            f"{b} {mean([r['elections_lost'] for r in main if r['bot'] == b]):.1f}" for b in BOTS
        )
    )
    lines.append(
        "- Endings, by bot: "
        + "; ".join(
            f"{b}: "
            + ", ".join(
                f"{e} {n}"
                for e, n in sorted(_count([r["ending"] for r in main if r["bot"] == b]).items())
            )
            for b in BOTS
        )
    )
    lines.append(
        f"- Rejected player actions across all runs: {sum(r['actions_rejected'] for r in main)}."
    )
    return "\n".join(lines) + "\n"


def _count(xs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sim.balance")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seeds", type=int, default=6, help="number of seeds (1..n)")
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    cfg = config.load()
    data = run(cfg, list(range(1, args.seeds + 1)), args.workers)
    text = report(cfg, data)
    args.out.write_text(text, encoding="utf-8")
    print(text.split("## 1.")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
