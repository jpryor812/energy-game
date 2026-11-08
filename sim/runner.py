"""Command-line entry point.

    python -m sim.runner run --country IND --bot noop --seed 1 --out runs/ind_noop_1
    python -m sim.runner batch --config scripts/batch_default.yaml

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

from sim import bots, canonical, config, scoring, turn
from sim.config import Config
from sim.scenario import new_world
from sim.state import World

MILESTONE = "M3"


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
) -> World:
    """Play from `world` (or a fresh world) until quarter `until` (default: the last turn), or
    until the player's government falls. With bot "ai" the AI plays the player's nation too;
    with `ai=False` the other nations take no actions (business as usual)."""
    if country not in cfg.playable_ids:
        raise ValueError(f"'{country}' is not playable; choose from {cfg.playable_ids}")
    bot = bots.get(bot_name)
    if world is None:
        world = new_world(cfg, seed)
    end = cfg.value("tuning", "time.turns") if until is None else until
    while world.t < end and not scoring.is_fallen(cfg, world, country):
        acts = {} if bot_name == "ai" else {country: bot(cfg, world, country)}
        world = turn.step(world, cfg, actions=acts, dt=dt, ai=ai)
    return world


def summarize(cfg: Config, world: World, country: str, bot_name: str, dt: int) -> dict[str, Any]:
    start_year = cfg.value("tuning", "time.start_year")
    result = scoring.score(cfg, world, country, fallen=scoring.is_fallen(cfg, world, country))
    rejected = sum(
        1 for h in world.history for r in h["nations"][country]["actions"] if not r["ok"]
    )
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
        "ending": result["ending"],
        "rank": result["rank"],
        "nation_index": result["nation_index"],
        "components": result["components"],
        "world_multiplier": result["world_multiplier"],
        "warming": result["warming"],
        "bonuses": result["bonuses"],
        "all_nations": result["all_nations"],
        "actions_rejected": rejected,
    }


def write_run(out: Path, world: World, summary: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "history.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for record in world.history:
            fh.write(canonical.dumps(record) + "\n")
    (out / "summary.json").write_text(canonical.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "state.json").write_text(world.to_json() + "\n", encoding="utf-8")


def run_one(
    cfg: Config, seed: int, country: str, bot_name: str, out: Path, dt: int = 1
) -> dict[str, Any]:
    world = play(cfg, seed, country, bot_name, dt=dt)
    summary = summarize(cfg, world, country, bot_name, dt)
    write_run(out, world, summary)
    return summary


def run_batch(cfg: Config, batch_path: Path) -> Path:
    with batch_path.open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    out_dir = Path(spec["out_dir"])
    rows = []
    for country, bot_name, seed in itertools.product(
        sorted(spec["countries"]), sorted(spec["bots"]), sorted(spec["seeds"])
    ):
        run_dir = out_dir / f"{country.lower()}_{bot_name}_{seed}"
        summary = run_one(cfg, seed, country, bot_name, run_dir)
        rows.append({k: summary[k] for k in AGGREGATE_COLUMNS})
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "aggregate.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=AGGREGATE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out_dir


AGGREGATE_COLUMNS = [
    "country",
    "bot",
    "seed",
    "turns_played",
    "score",
    "nation_index",
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

    batch_p = sub.add_parser("batch", help="play a grid of games")
    batch_p.add_argument("--config", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        cfg = config.load(args.data_dir)
        if args.command == "run":
            summary = run_one(cfg, args.seed, args.country, args.bot, args.out)
            print(
                f"wrote {args.out}: score {summary['score']:.1f}, rank {summary['rank']}, "
                f"{summary['ending']} (state {summary['state_hash'][:12]})"
            )
        else:
            out_dir = run_batch(cfg, args.config)
            print(f"wrote {out_dir / 'aggregate.csv'}")
    except (config.ConfigError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
