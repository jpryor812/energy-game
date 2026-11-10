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

from sim import (
    actions,
    canonical,
    deals,
    economy,
    elections,
    runner,
    scoring,
    tech,
    trade,
    turn,
)
from sim.config import Config
from sim.scenario import new_world
from sim.state import World

GAME_FILE = "game.json"
WORLD_FILE = "world.json"


class SaveError(Exception):
    """A save that cannot be loaded (missing, or made with different data)."""


LINEAR = actions.LINEAR  # M9: "max" is resolved by the engine (sim.actions)


@dataclass
class Game:
    cfg: Config
    world: World
    country: str
    moves: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)  # what changed in the last quarter

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
            "notices": self.notices,
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
        return cls(
            cfg=cfg,
            world=world,
            country=meta["country"],
            moves=meta["moves"],
            notices=meta.get("notices", []),
        )

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

    def expand(self, acts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Kept for callers: `"amount": "max"` is now resolved by the engine when the action
        resolves (M9), from the resources the nation has at that moment."""
        return copy.deepcopy(acts)

    def check(self, acts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """What would happen to these actions this quarter, without playing it."""
        w = self.preview()
        acts = self.expand(acts)
        results = actions.resolve(self.cfg, w, self.country, acts)
        for r in results:
            a = r["action"]
            if r["ok"] and a["type"] == "propose_deal":
                n = w.nations[self.country]
                cost = a["amount"]
                if a["deal_type"] != "climate_loan":
                    cost = tech.nation_unit_cost(self.cfg, w, n, a["source"]) * a["amount"]
                r["note"] = f"free now; {cost:.4g} T$ of your capital if accepted"
        return results

    def summary(self) -> dict[str, Any]:
        return runner.summarize(self.cfg, self.world, self.country, "player", 1)

    # --- moves ------------------------------------------------------------------------------

    def turn(self, acts: list[dict[str, Any]]) -> dict[str, Any]:
        """Play one quarter with the player's actions; return what happened."""
        if self.over:
            raise RuntimeError("the game is over")
        acts = self.expand(acts)
        before = self.world
        self.world = turn.step(self.world, self.cfg, actions={self.country: acts})
        self.moves.append({"t": self.world.t - 1, "actions": acts})
        self.notices = notices(self.cfg, before, self.world, self.country)
        record = self.world.history[-1]
        return {
            "quarter": record["label"],
            "results": record["nations"][self.country]["actions"],
            "events": record.get("events", []),
            "election": record.get("election"),
            "notices": self.notices,
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


# --- what changed in a quarter -------------------------------------------------------------------

DEAL_ENDINGS = {
    "refused": "refused",
    "countered": "answered with a counter-offer",
    "expired": "expired unanswered",
    "lapsed": "lapsed (the financier could not pay)",
    "failed": "FAILED: the plant closed",
    "defaulted": "DEFAULTED",
    "exited": "was exited",
    "completed": "completed",
}


def notices(cfg: Config, before: World, after: World, me: str) -> list[str]:
    """Plain-language changes the player would want to hear about after a quarter."""
    out: list[str] = []
    label = turn.quarter_label(before.t, cfg.tune("time.start_year"))

    # Deals: new offers, answers, payments, failures and endings.
    for did in sorted(after.deals):
        d = after.deals[did]
        if me not in (d.host, d.financier):
            continue
        old = before.deals.get(did)
        other = d.host if d.financier == me else d.financier
        what = f"{did} {d.type} ({d.financier}->{d.host}, {d.terms.get('source')})"
        size = (
            f"{d.terms['amount']:.3g} T$" if d.type == "climate_loan"
            else f"{d.terms['amount']:.3g} EJ/yr"
        )  # fmt: skip
        if old is None and d.status == deals.OPEN and deals.responder(d) == me:
            out.append(
                f"New offer {what}, {size}, from {other}: answer from next quarter "
                f"(expires after {int(cfg.tune('deals.proposal_expiry'))} quarters)."
            )
        elif old is None and d.status == deals.OPEN:
            out.append(f"Your offer {what} was sent to {other}.")
        elif old is not None and old.status != d.status:
            if d.status == deals.ACTIVE:
                cost = d.terms.get("cost", 0.0)
                start = cfg.tune("time.start_year")
                online = turn.quarter_label(int(d.terms["online_turn"]), start)
                paid = f"; you paid {cost:.4g} T$" if d.financier == me else ""
                out.append(f"Deal {what} signed{paid}; online {online}.")
            else:
                out.append(f"Deal {what} {DEAL_ENDINGS.get(d.status, d.status)}.")

    nb, na = before.nations[me], after.nations[me]

    # Plants coming online.
    online: dict[str, float] = {}
    for c in nb.pipeline:
        if c.complete_turn <= before.t:
            online[c.source] = online.get(c.source, 0.0) + c.amount
    if online:
        out.append(
            "Online this quarter: "
            + ", ".join(f"{s} {v:.3g}" for s, v in sorted(online.items()))
            + " (yours and the market's)."
        )

    # Credits and the stocktake.
    rec = after.history[-1]
    st = (rec.get("stocktake") or {}).get("nations", {}).get(me) if rec.get("stocktake") else None
    surrendered = st.get("credits_surrendered", 0.0) if st else 0.0
    change = na.credit_balance - nb.credit_balance + surrendered
    if abs(change) > 1e-6:
        out.append(
            f"Credits held {nb.credit_balance:.0f} -> {na.credit_balance:.0f} Mt "
            f"(issued or traded {change:+.0f}; market price {after.credit_price:.0f} $/t)."
        )
    if st:
        pledge = st.get("pledge_on_track")
        out.append(
            f"STOCKTAKE {label}: your emissions over the period {st['emissions']:.0f} Mt against "
            f"your allowance of {st['allowance']:.0f}; {surrendered:.0f} Mt of credits "
            f"surrendered; overshoot left after credits {st['overshoot_share'] * 100:.0f}% of "
            f"five years of your 2025 emissions; coalition tariff on you "
            f"{st.get('coalition_tariff', 0.0):.2f}"
            + (f"; pledge {'on track' if pledge else 'BROKEN'}" if pledge is not None else "")
            + "."
        )

    # Research completed this quarter (M12).
    for nid, tid in rec.get("research", []):
        first = after.tech_firsts.get(tid, [None])[0] == nid
        gives = cfg.rtech(tid).get("unlocks", []) + cfg.rtech(tid).get("enables", [])
        what = f" (unlocks {', '.join(gives)})" if gives else ""
        if nid == me:
            out.append(f"Research complete: {tid}{what}.")
        elif first:
            out.append(f"{nid} is the first to complete {tid}{what}; it now costs others less.")

    # Licences bought and sold this quarter (M13).
    for buyer, seller, tid, price, t in after.licenses:
        if t != before.t:
            continue
        if seller == me:
            out.append(f"Licence sold: {buyer} bought {tid} from you for {price:.4g} T$.")
        elif buyer == me:
            out.append(f"Licence bought: {tid} from {seller} for {price:.4g} T$.")

    # Orders that will not arrive before the game ends (M9).
    end = int(cfg.tune("time.turns"))
    known = {(c.source, c.complete_turn, c.amount) for c in nb.pipeline}
    late = sorted({
        c.source for c in na.pipeline
        if c.complete_turn >= end and (c.source, c.complete_turn, c.amount) not in known
    })  # fmt: skip
    if late:
        out.append(
            "New orders that will not come online before the game ends: " + ", ".join(late) + "."
        )

    # Credit orders that found no buyer (M9), and the carbon club.
    mine = rec["nations"][me]["actions"]
    sold = any(r["ok"] and r["action"].get("type") == "sell_credits" for r in mine)
    if sold and not (rec.get("credit_market") or {}).get("traded"):
        out.append(
            "Your credit sell order found no buyer this quarter (nations buy only when they "
            "need credits for a stocktake); the shown price is the last one, not a bid."
        )
    if me in trade.club_members(before) and me not in trade.club_members(after):
        out.append(
            "You left the carbon club: your carbon price is below "
            f"{cfg.tune('diplomacy.club_min_carbon_price'):g} $/t."
        )

    # How the score moved this quarter, by component (M14).
    if before.history:
        old_s = scoring.score(cfg, before, me)
        new_s = scoring.score(cfg, after, me)
        moved = {
            k: new_s["components"][k] - old_s["components"][k]
            for k in new_s["components"]
            if abs(new_s["components"][k] - old_s["components"][k]) >= 0.005
        }
        parts = ", ".join(f"{k} {v:+.2f}" for k, v in moved.items())
        out.append(
            f"Score {old_s['score_at_exit']:.1f} -> {new_s['score_at_exit']:.1f}"
            + (f" (nation index parts: {parts})" if parts else "")
            + (f"; world multiplier {new_s['world_multiplier']:.2f}"
               if abs(new_s["world_multiplier"] - old_s["world_multiplier"]) >= 0.005 else "")
            + "."
        )  # fmt: skip

    # Bonuses gained or lost.
    if before.history:
        old_b = scoring.bonuses(cfg, before)[me]
        new_b = scoring.bonuses(cfg, after)[me]
        for k in sorted(set(old_b) | set(new_b)):
            if k in new_b and k not in old_b:
                out.append(f"Bonus gained: {k} (+{new_b[k]:g}).")
            elif k in old_b and k not in new_b:
                out.append(f"Bonus lost: {k}.")
    return out
