"""Command-line entry point.

    python -m sim.runner run --country IND --bot noop --seed 1 --out runs/ind_noop_1
    python -m sim.runner batch --config scripts/batch_default.yaml --workers 8

A run writes `history.jsonl`, `summary.json` and `state.json`. A batch writes one run directory per
(country, bot, seed) plus `aggregate.csv`. Balance-report generation arrives in M5.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from pathlib import Path
from typing import Any

import yaml

from sim import bots, canonical, config, elections, scoring, turn
from sim.config import Config
from sim.scenario import new_world
from sim.state import World

MILESTONE = "M7"


def play(
    cfg: Config,
    seed: int,
    country: str,
    bot_name: str,
    *,
    dt: int = 1,
    world: World | None = None,
    until: int | None = None,
    ai: bool = True,
    difficulty: str | None = None,
) -> World:
    """Play from `world` (or a fresh world) until quarter `until` (default: the last turn), or
    until the player loses (government falls or an election is lost). With bot "ai" the AI plays
    the player's nation too; with `ai=False` the other nations take no actions (business as
    usual)."""
    if country not in cfg.playable_ids:
        raise ValueError(f"'{country}' is not playable; choose from {cfg.playable_ids}")
    bot = bots.get(bot_name)
    if world is None:
        world = new_world(cfg, seed, difficulty)
    if world.player is None:
        world.player = country
        elections.start_term(world)
    end = cfg.value("tuning", "time.turns") if until is None else until
    while world.t < end and not scoring.loss(cfg, world, country):
        acts = {} if bot_name == "ai" else {country: bot(cfg, world, country)}
        world = turn.step(world, cfg, actions=acts, dt=dt, ai=ai)
    return world


def summarize(cfg: Config, world: World, country: str, bot_name: str, dt: int) -> dict[str, Any]:
    start_year = cfg.value("tuning", "time.start_year")
    result = scoring.score(cfg, world, country, lost=scoring.loss(cfg, world, country))
    rejected = sum(
        1 for h in world.history for r in h["nations"][country]["actions"] if not r["ok"]
    )
    events = [e for h in world.history for e in h.get("events", [])]
    return {
        "milestone": MILESTONE,
        "seed": world.seed,
        "country": country,
        "bot": bot_name,
        "dt": dt,
        "turns_played": world.t,
        "final_quarter": turn.quarter_label(world.t - 1, start_year) if world.t else None,
        "config_hash": cfg.hash,
        "state_hash": world.hash(),
        "score": result["score"],
        "score_at_exit": result["score_at_exit"],
        "ending": result["ending"],
        "rank": result["rank"],
        "nation_index": result["nation_index"],
        "absolute_index": result["absolute_index"],
        "difficulty_multiplier": result["difficulty_multiplier"],
        "combined_index": result["combined_index"],
        "absolute_components": result["absolute_components"],
        "difficulty": world.difficulty,
        "components": result["components"],
        "world_multiplier": result["world_multiplier"],
        "warming": result["warming"],
        "bonuses": result["bonuses"],
        "all_nations": result["all_nations"],
        "actions_rejected": rejected,
        "elections": world.elections,
        "elections_lost": sum(1 for e in world.elections if e["event"] == "lost"),
        "disasters": sum(1 for e in events if e["type"] == "disaster"),
        "disruptions": sum(1 for e in events if e["type"] == "disruption"),
        "sanity_issues": sanity_issues(world),
    }


def sanity_issues(world: World) -> list[str]:
    """Impossible values in the final state: NaN or infinity anywhere, GDP or population not
    positive, negative capacity, demand or supply. Emissions and money may be negative."""
    issues: list[str] = []

    def walk(x: Any, path: str) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")
        elif isinstance(x, float) and x != x or x in (float("inf"), float("-inf")):
            issues.append(f"{path} is not finite")

    walk({k: v for k, v in world.to_dict().items() if k != "history"}, "world")
    for nid, n in sorted(world.nations.items()):
        if n.gdp <= 0 or n.population <= 0:
            issues.append(f"{nid}: GDP or population not positive")
        for name in ("capacity", "supply"):
            for src, v in getattr(n, name).items():
                if v < -1e-9:
                    issues.append(f"{nid}.{name}.{src} negative")
        if n.demand < 0:
            issues.append(f"{nid}.demand negative")
    return issues[:20]


def write_run(out: Path, world: World, summary: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "history.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for record in world.history:
            fh.write(canonical.dumps(record) + "\n")
    (out / "summary.json").write_text(canonical.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "state.json").write_text(world.to_json() + "\n", encoding="utf-8")


def run_one(
    cfg: Config,
    seed: int,
    country: str,
    bot_name: str,
    out: Path | None,
    dt: int = 1,
    difficulty: str | None = None,
) -> dict[str, Any]:
    """Play one game; write its files to `out` (if given); return its summary."""
    world = play(cfg, seed, country, bot_name, dt=dt, difficulty=difficulty)
    summary = summarize(cfg, world, country, bot_name, dt)
    if out is not None:
        write_run(out, world, summary)
    return summary


def _job(args: tuple) -> dict[str, Any]:
    cfg, seed, country, bot_name, out, difficulty = args
    return run_one(cfg, seed, country, bot_name, out, difficulty=difficulty)


def run_grid(cfg: Config, jobs: list[tuple], workers: int = 1) -> list[dict[str, Any]]:
    """Run (seed, country, bot, out, difficulty) jobs, in parallel if `workers` > 1. Each game
    is independent and deterministic, so results do not depend on the number of workers; they
    come back in job order."""
    args = [(cfg, *job) for job in jobs]
    if workers <= 1:
        return [_job(a) for a in args]
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_job, args))


def run_batch(cfg: Config, batch_path: Path, workers: int = 1) -> Path:
    with batch_path.open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    out_dir = Path(spec["out_dir"])
    difficulties = sorted(spec.get("difficulties", [cfg.tuning["difficulty"]["default"]]))
    jobs = []
    for difficulty, country, bot_name, seed in itertools.product(
        difficulties, sorted(spec["countries"]), sorted(spec["bots"]), sorted(spec["seeds"])
    ):
        name = f"{country.lower()}_{bot_name}_{seed}"
        if len(difficulties) > 1:
            name = f"{difficulty}_{name}"
        jobs.append((seed, country, bot_name, out_dir / name, difficulty))
    rows = [{k: s[k] for k in AGGREGATE_COLUMNS} for s in run_grid(cfg, jobs, workers)]
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "aggregate.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=AGGREGATE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out_dir


AGGREGATE_COLUMNS = [
    "difficulty",
    "country",
    "elections_lost",
    "bot",
    "seed",
    "turns_played",
    "score",
    "nation_index",
    "absolute_index",
    "combined_index",
    "rank",
    "world_multiplier",
    "warming",
    "ending",
    "actions_rejected",
    "state_hash",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sim.runner")
    parser.add_argument("--data-dir", type=Path, default=config.DEFAULT_DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="play one game")
    run_p.add_argument("--country", required=True)
    run_p.add_argument("--bot", default="noop")
    run_p.add_argument("--seed", type=int, required=True)
    run_p.add_argument("--out", type=Path, required=True)
    run_p.add_argument("--difficulty", choices=config.DIFFICULTIES, default=None)

    batch_p = sub.add_parser("batch", help="play a grid of games")
    batch_p.add_argument("--config", type=Path, required=True)
    batch_p.add_argument("--workers", type=int, default=1)

    args = parser.parse_args(argv)
    try:
        cfg = config.load(args.data_dir)
        if args.command == "run":
            summary = run_one(
                cfg, args.seed, args.country, args.bot, args.out, difficulty=args.difficulty
            )
            print(
                f"wrote {args.out}: score {summary['score']:.1f}, rank {summary['rank']}, "
                f"{summary['ending']} (state {summary['state_hash'][:12]})"
            )
        else:
            out_dir = run_batch(cfg, args.config, args.workers)
            print(f"wrote {out_dir / 'aggregate.csv'}")
    except (config.ConfigError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
