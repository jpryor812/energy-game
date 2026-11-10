"""Run one playtest agent through OpenRouter (M10).

The model plays a full game through `python -m sim.play`, keeps notes, and ends with the report
from docs/PLAYTEST.md. This script lives outside sim/: the simulation itself never uses the
network. Settings come from `.env` in the project folder (git ignores it; see .env.example):

    OPENROUTER_API_KEY=...
    OPENROUTER_MODEL=...          # any OpenRouter model id that supports tool calling

Usage:

    python scripts/playtest_agent.py --country IND --seed 23 --name r2_ind
    python scripts/playtest_agent.py --country EUU --seed 1 --name r2_hunt --hunter

Each run writes to games/<name>/: the save, notes.md (the agent's notes), report.md (its final
answer) and transcript.jsonl (every request and tool call, for review). Run several at once in
separate terminals; each uses only its own folder.

Tools the model gets, and nothing else:
- play: run one `sim.play` subcommand (new is done for it; show, actions, check, turn, wait,
  score, log) on its own save. No shell is involved.
- notes: append text to its notes file.
- read_file: read docs/PLAYTEST.md; with --hunter also files under sim/ and data/.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://openrouter.ai/api/v1/chat/completions"
SUBCOMMANDS = ("show", "actions", "check", "turn", "wait", "score", "log")
KEEP_FULL = 6  # tool results kept in full; older ones are shortened to save tokens
SHORTENED = 400  # characters kept from an older tool result
MAX_RESULT = 20000  # characters of one tool result sent to the model

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "play",
            "description": "Run one game command on your save. Give the subcommand and its "
            "arguments without the save path, e.g. 'show --brief', 'actions', "
            '\'check [{"type": "set_carbon_price", "level": 30}]\', '
            '\'turn [{"type": "build_capacity", "source": "solar", "amount": 0.2}]\', '
            "'wait 4 --brief', 'score', 'log --last 8'.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notes",
            "description": "Append text to your notes file (a line or two per game year).",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a project file you are allowed to read, by path relative to "
            "the project folder (e.g. docs/PLAYTEST.md). Long files come in parts: pass the "
            "offset the previous part ended at.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "description": "character to start from"},
                },
                "required": ["path"],
            },
        },
    },
]


# --- settings ---------------------------------------------------------------------------------


def load_env(path: Path) -> dict[str, str]:
    """KEY=value lines; blank lines and # comments ignored; optional quotes stripped."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


# --- tools --------------------------------------------------------------------------------------


class Tools:
    def __init__(self, save: Path, hunter: bool) -> None:
        self.save = save
        self.hunter = hunter

    def play(self, command: str) -> str:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"error: could not parse the command ({exc})"
        if parts[:3] == ["python", "-m", "sim.play"]:
            parts = parts[3:]
        if not parts or parts[0] not in SUBCOMMANDS:
            return f"error: the subcommand must be one of {', '.join(SUBCOMMANDS)}"
        sub, rest = parts[0], parts[1:]
        if rest and Path(rest[0]).name == self.save.name:
            rest = rest[1:]  # the model passed its save path itself
        argv = [sys.executable, "-m", "sim.play", sub]
        if sub != "actions":
            argv.append(str(self.save))
        argv += rest
        done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=600)
        text = done.stdout + (f"\n[stderr]\n{done.stderr}" if done.stderr else "")
        return text[:MAX_RESULT] + ("\n[output cut]" if len(text) > MAX_RESULT else "")

    def notes(self, text: str) -> str:
        with (self.save / "notes.md").open("a") as f:
            f.write(text.rstrip() + "\n")
        return "noted"

    def allowed(self, path: Path) -> bool:
        rel = path.relative_to(ROOT).as_posix()
        if rel == "docs/PLAYTEST.md":
            return True
        return self.hunter and (rel.startswith("sim/") or rel.startswith("data/"))

    def read_file(self, path: str, offset: int = 0) -> str:
        target = (ROOT / path).resolve()
        if not target.is_relative_to(ROOT) or not self.allowed(target):
            return "error: you may not read that file"
        if not target.is_file():
            return "error: no such file"
        text = target.read_text()
        end = offset + MAX_RESULT
        more = f"\n[continues: read again with offset {end}]" if len(text) > end else ""
        return text[offset:end] + more

    def call(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "play":
                return self.play(str(args.get("command", "")))
            if name == "notes":
                return self.notes(str(args.get("text", "")))
            if name == "read_file":
                return self.read_file(str(args.get("path", "")), int(args.get("offset") or 0))
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            return f"error: {exc}"
        return f"error: unknown tool {name}"


# --- the model ---------------------------------------------------------------------------------


def brief(country: str, seed: int, difficulty: str, hunter: bool) -> str:
    guide = (ROOT / "docs" / "PLAYTEST.md").read_text()
    role = (
        "You are the exploit hunter: find ways to score far higher than intended or to win "
        "without playing as designed, so the designers can close them. You may read sim/ and "
        "data/ with read_file. Test ideas through the game, play one full game with your best "
        "strategy, and finish with: each exploit (steps, evidence, code location), ideas that "
        "did not work, your full-game result, and suggested fixes."
        if hunter
        else "You are a playtester. Play only through the play tool and the guide below; do not "
        "ask to read code or data. Play to win: the highest score you can without losing. Look "
        "at the screen at least once a game year and before every election. Finish with the "
        "report under the 10 headings in the guide, concrete with numbers and quarters, under "
        "about 900 words."
    )
    return (
        f"{role}\n\nYour game: {country}, seed {seed}, {difficulty} difficulty. It has already "
        "been started; use the play tool (for example 'show') to see it. Keep notes with the "
        "notes tool as you go. When the game is over (2049Q4 or a loss), reply with your final "
        "report as plain text and no tool call.\n\n--- docs/PLAYTEST.md ---\n"
        + guide
        + "\n\n--- every action (the same as the 'actions' command) ---\n"
        + action_list()
    )


def action_list() -> str:
    """The full action catalogue, given up front so the model never has to guess names."""
    argv = [sys.executable, "-m", "sim.play", "actions"]
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=True).stdout


def shorten(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last KEEP_FULL tool results whole and shorten older ones."""
    tool_idx = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    old = set(tool_idx[:-KEEP_FULL])
    out = []
    for i, m in enumerate(messages):
        if i in old and len(m["content"]) > SHORTENED:
            m = m | {"content": m["content"][:SHORTENED] + "\n[older output shortened]"}
        out.append(m)
    return out


def request(key: str, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    body = json.dumps({"model": model, "messages": shorten(messages), "tools": TOOLS}).encode()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "energy-game playtest",
    }
    for attempt in range(6):
        req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            if exc.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(min(60, 5 * 2**attempt))
                continue
            raise RuntimeError(f"OpenRouter error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt < 5:
                time.sleep(min(60, 5 * 2**attempt))
                continue
            raise RuntimeError(f"network error: {exc}") from exc
    raise RuntimeError("OpenRouter kept failing")


def run(args: argparse.Namespace) -> int:
    env = load_env(ROOT / ".env")
    key, model = env.get("OPENROUTER_API_KEY"), args.model or env.get("OPENROUTER_MODEL")
    if not key or not model:
        print(
            "set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env (see .env.example)",
            file=sys.stderr,
        )
        return 1
    save = ROOT / "games" / args.name
    if not (save / "game.json").exists():
        new = [sys.executable, "-m", "sim.play", "new", "--country", args.country, "--seed",
               str(args.seed), "--difficulty", args.difficulty, "--save", str(save)]  # fmt: skip
        done = subprocess.run(new, cwd=ROOT, capture_output=True, text=True)
        if done.returncode:
            print(done.stderr, file=sys.stderr)
            return 1
    tools = Tools(save, args.hunter)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": brief(args.country, args.seed, args.difficulty, args.hunter)}
    ]
    log = (save / "transcript.jsonl").open("a")
    for step in range(args.max_steps):
        reply = request(key, model, messages)
        msg = reply["choices"][0]["message"]
        log.write(json.dumps({"step": step, "message": msg, "usage": reply.get("usage")}) + "\n")
        log.flush()
        calls = msg.get("tool_calls") or []
        messages.append(
            {"role": "assistant", "content": msg.get("content") or ""}
            | ({"tool_calls": calls} if calls else {})
        )
        if not calls:
            (save / "report.md").write_text(msg.get("content") or "")
            print(f"{args.name}: finished after {step + 1} requests; report in {save}/report.md")
            return 0
        for call in calls:
            fn = call["function"]
            try:
                params = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                params = {}
            result = tools.call(fn["name"], params)
            log.write(json.dumps({"step": step, "tool": fn["name"], "args": params}) + "\n")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    print(f"{args.name}: stopped at --max-steps {args.max_steps}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--country", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--difficulty", default="normal")
    parser.add_argument("--name", required=True, help="folder under games/ for this run")
    parser.add_argument("--hunter", action="store_true", help="may read sim/ and data/")
    parser.add_argument("--model", default=None, help="overrides OPENROUTER_MODEL")
    parser.add_argument("--max-steps", type=int, default=400, help="model requests at most")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
