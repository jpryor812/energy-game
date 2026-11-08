"""Play the game one quarter at a time from the command line. Every command loads the save,
does one thing, and saves again, so each move is a single shell call.

    python -m sim.play new --country IND --seed 1 --difficulty normal --save games/ind1
    python -m sim.play show games/ind1 [--json]
    python -m sim.play actions                      # every action, its parameters and cost
    python -m sim.play check games/ind1 '[{"type": "set_carbon_price", "level": 30}]'
    python -m sim.play turn games/ind1 '[...]'      # play this quarter with these actions
    python -m sim.play wait games/ind1 4            # play 4 quarters taking no actions
    python -m sim.play score games/ind1
    python -m sim.play log games/ind1 [--last 8]

Actions are a JSON list of objects (see `actions`); pass `@file.json` to read them from a file.
A turn spends at most the slots you have (2 domestic and 1 diplomatic arrive each quarter;
unused slots are banked). Losing an election, or stability falling below the threshold, ends the
game.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sim import config, view
from sim.session import Game, SaveError


def _actions(text: str) -> list[dict[str, Any]]:
    if text.startswith("@"):
        text = Path(text[1:]).read_text()
    acts = json.loads(text)
    if isinstance(acts, dict):
        acts = [acts]
    if not isinstance(acts, list) or not all(isinstance(a, dict) for a in acts):
        raise ValueError("actions must be a JSON list of objects")
    return acts


def _results(results: list[dict[str, Any]]) -> list[str]:
    out = []
    for r in results:
        a = r["action"]
        if r["ok"]:
            cost = ", ".join(f"{k} {v:.4g}" for k, v in r.get("cost", {}).items() if v) or "free"
            out.append(f"  ok        {a.get('type')} ({cost})")
        else:
            out.append(f"  REJECTED  {a.get('type')}: {r['reason']}")
    return out


def _quarter(rep: dict[str, Any]) -> list[str]:
    lines = [f"-- {rep['quarter']} played --"]
    lines += _results(rep["results"])
    if rep["election"]:
        e = rep["election"]
        lines.append(f"  ELECTION: {e['event']} with {e['vote']:.3f} of the vote")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sim.play", description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="start a game")
    p.add_argument("--country", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--difficulty", choices=config.DIFFICULTIES, default=None)
    p.add_argument("--save", type=Path, required=True)
    p = sub.add_parser("show", help="the game screen")
    p.add_argument("save", type=Path)
    p.add_argument("--json", action="store_true")
    sub.add_parser("actions", help="every action, its parameters and cost")
    for name, helptext in (("check", "test actions without playing"), ("turn", "play a quarter")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("save", type=Path)
        p.add_argument("actions", nargs="?", default="[]")
    p = sub.add_parser("wait", help="play quarters without acting")
    p.add_argument("save", type=Path)
    p.add_argument("quarters", type=int)
    p = sub.add_parser("score", help="current (or final) score")
    p.add_argument("save", type=Path)
    p = sub.add_parser("log", help="moves and results so far")
    p.add_argument("save", type=Path)
    p.add_argument("--last", type=int, default=8)
    args = parser.parse_args(argv)

    cfg = config.load(args.data_dir) if args.data_dir else config.load()
    try:
        if args.cmd == "new":
            if (args.save / "game.json").exists():
                print(f"a game is already saved at {args.save}", file=sys.stderr)
                return 1
            game = Game.new(cfg, args.country, args.seed, args.difficulty)
            game.save(args.save)
            print(view.render(view.observe(game)))
            return 0
        if args.cmd == "actions":
            print(view.render_actions(cfg))
            return 0

        game = Game.load(cfg, args.save)
        if args.cmd == "show":
            obs = view.observe(game)
            print(json.dumps(obs, indent=1) if args.json else view.render(obs))
        elif args.cmd == "check":
            print("\n".join(_results(game.check(_actions(args.actions)))) or "  (no actions)")
        elif args.cmd == "turn":
            if game.over:
                print("The game is over.\n" + view.render(view.observe(game)))
                return 1
            rep = game.turn(_actions(args.actions))
            game.save(args.save)
            print("\n".join(_quarter(rep)) + "\n\n" + view.render(view.observe(game)))
        elif args.cmd == "wait":
            reps = game.wait(args.quarters)
            game.save(args.save)
            lines = [line for rep in reps for line in _quarter(rep)]
            print("\n".join(lines) + "\n\n" + view.render(view.observe(game)))
        elif args.cmd == "score":
            print(json.dumps(view.observe(game)["score"], indent=1))
        elif args.cmd == "log":
            for h in game.world.history[-args.last :]:
                rec = h["nations"][game.country]
                lines = [f"{h['label']}: GDP {rec['gdp']:.3f}, emissions {rec['emissions']:.0f}, "
                         f"approval {rec['approval']:.2f}"]  # fmt: skip
                lines += _results(rec["actions"])
                print("\n".join(lines))
    except (SaveError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
