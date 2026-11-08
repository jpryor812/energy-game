"""A game session: one player nation against the AI, one quarter per turn, saved after each move.

This is the layer the text interface (sim.play) and, later, the web UI sit on. It adds nothing to
the rules: a turn is exactly `turn.step` with the player's actions, so a session driven by a bot
reproduces `runner.play` with that bot (tested).

A save is a directory holding:

- `game.json`: country, seed, difficulty, the data's config hash, and the move log (the actions
  submitted each quarter). Replaying the log from the seed rebuilds the world exactly.
- `world.json`: the current world, so loading does not need a replay.

Loading refuses a save made with different data files, because its moves would no longer
replay to the same world.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sim import actions, canonical, economy, elections, runner, scoring, turn
from sim.config import Config
from sim.scenario import new_world
from sim.state import World

GAME_FILE = "game.json"
WORLD_FILE = "world.json"


class SaveError(Exception):
    """A save that cannot be loaded (missing, or made with different data)."""


@dataclass
class Game:
    cfg: Config
    world: World
    country: str
    moves: list[dict[str, Any]] = field(default_factory=list)

    # --- lifecycle --------------------------------------------------------------------------

    @classmethod
    def new(cls, cfg: Config, country: str, seed: int, difficulty: str | None = None) -> Game:
        if country not in cfg.playable_ids:
            raise ValueError(f"'{country}' is not playable; choose from {cfg.playable_ids}")
        world = new_world(cfg, seed, difficulty)
        world.player = country
        elections.start_term(world)
        return cls(cfg=cfg, world=world, country=country)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        meta = {
            "country": self.country,
            "seed": self.world.seed,
            "difficulty": self.world.difficulty,
            "config_hash": self.cfg.hash,
            "moves": self.moves,
        }
        (path / GAME_FILE).write_text(canonical.dumps(meta))
        (path / WORLD_FILE).write_text(self.world.to_json(indent=None))

    @classmethod
    def load(cls, cfg: Config, path: Path) -> Game:
        try:
            meta = json.loads((path / GAME_FILE).read_text())
            world = World.from_json((path / WORLD_FILE).read_text())
        except FileNotFoundError as exc:
            raise SaveError(f"no saved game at {path}") from exc
        if meta["config_hash"] != cfg.hash:
            raise SaveError(
                f"{path} was saved with different data files (config {meta['config_hash'][:12]}, "
                f"now {cfg.hash[:12]}); its moves would not replay the same way"
            )
        return cls(cfg=cfg, world=world, country=meta["country"], moves=meta["moves"])

    def replay(self) -> World:
        """Rebuild the world from the seed and the move log."""
        game = Game.new(self.cfg, self.country, self.world.seed, self.world.difficulty)
        for move in self.moves:
            game.world = turn.step(game.world, self.cfg, actions={self.country: move["actions"]})
        return game.world

    # --- state ------------------------------------------------------------------------------

    @property
    def over(self) -> bool:
        return self.world.t >= self.cfg.tune("time.turns") or self.lost is not None

    @property
    def lost(self) -> str | None:
        return scoring.loss(self.cfg, self.world, self.country)

    def preview(self) -> World:
        """The world as the player can act on it this quarter: after this quarter's income and
        slots arrive (they come before actions resolve)."""
        w = copy.deepcopy(self.world)
        economy.apply_income(w, self.cfg, 1)
        return w

    def check(self, acts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """What would happen to these actions this quarter, without playing it."""
        w = self.preview()
        return actions.resolve(self.cfg, w, self.country, copy.deepcopy(acts))

    def summary(self) -> dict[str, Any]:
        return runner.summarize(self.cfg, self.world, self.country, "player", 1)

    # --- moves ------------------------------------------------------------------------------

    def turn(self, acts: list[dict[str, Any]]) -> dict[str, Any]:
        """Play one quarter with the player's actions; return what happened."""
        if self.over:
            raise RuntimeError("the game is over")
        acts = copy.deepcopy(acts)
        self.world = turn.step(self.world, self.cfg, actions={self.country: acts})
        self.moves.append({"t": self.world.t - 1, "actions": acts})
        record = self.world.history[-1]
        return {
            "quarter": record["label"],
            "results": record["nations"][self.country]["actions"],
            "events": record.get("events", []),
            "election": record.get("election"),
            "over": self.over,
            "lost": self.lost,
        }

    def wait(self, quarters: int) -> list[dict[str, Any]]:
        """Play up to `quarters` quarters with no actions, stopping early if the game ends."""
        out = []
        for _ in range(quarters):
            if self.over:
                break
            out.append(self.turn([]))
        return out
