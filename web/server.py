"""The local game server (W1): a JSON API over sim.session plus the static front end.

    python -m web            # then open http://127.0.0.1:8765

It adds no rules. Every number the page shows comes from sim.view.observe (the same data as the
text screen) or from read-only summaries of the world built here; every move goes through
Game.check / Game.turn. Saves live in games/web/<name>/ in the usual session format, so a game
started in the browser can be continued with `python -m sim.play` and the other way round.

Binds to 127.0.0.1 only. Standard library only (no new dependencies).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sim import canonical, config, construction, diplomacy, regions, scoring, trade, view
from sim.catalogue import catalogue
from sim.session import Game, SaveError
from web.profiles import profiles

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
SAVES = ROOT / "games" / "web"
NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class ApiError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


class Server:
    """One game at a time, saved after every move."""

    def __init__(self, cfg: config.Config | None = None, saves: Path = SAVES):
        self.cfg = cfg or config.load()
        self.saves = saves
        self.game: Game | None = None
        self.name: str | None = None
        self.lock = threading.Lock()
        self._profiles: dict[str, Any] | None = None

    # --- read-only views --------------------------------------------------------------------

    def meta(self) -> dict[str, Any]:
        cfg = self.cfg
        return {
            "playable": cfg.playable_ids,
            "nations": {
                nid: {
                    "name": cfg.nat_spec(nid)["name"],
                    "playable": cfg.nat_spec(nid)["playable"],
                    "difficulty": cfg.nat_spec(nid)["difficulty"],
                    "personality": cfg.nat_spec(nid)["personality"],
                }
                for nid in cfg.nation_ids
            },
            "regions": {rid: cfg.regions["regions"][rid]["name"] for rid in cfg.region_ids},
            "difficulties": list(cfg.tuning["difficulty"]["levels"]),
            # W2: the tech tree's shape (prerequisites and earliest years) for the tree view
            "techs": {
                tid: {
                    "name": cfg.rtech(tid)["name"],
                    "requires": list(cfg.rtech(tid).get("requires", [])),
                    "earliest_year": (cfg.rtech(tid).get("earliest_year") or {}).get("value"),
                    "min_quarters": cfg.rtech(tid)["min_quarters"]["value"],
                }
                for tid in cfg.tech_ids
            },
            # the new-game screen: strengths, weaknesses and figures, easiest nation first
            "profiles": self.profiles(),
            "profile_order": list(self.profiles()),  # JSON keys are sorted, so the order goes here
            "catalogue": catalogue(cfg),
            "saves": self.list_saves(),
            "current": self.name,
        }

    def profiles(self) -> dict[str, Any]:
        if self._profiles is None:
            self._profiles = profiles(self.cfg)
        return self._profiles

    def list_saves(self) -> list[dict[str, Any]]:
        out = []
        if self.saves.exists():
            for d in sorted(self.saves.iterdir()):
                try:
                    meta = json.loads((d / "game.json").read_text())
                except (OSError, ValueError):
                    continue
                out.append(
                    {
                        "name": d.name,
                        "country": meta.get("country"),
                        "seed": meta.get("seed"),
                        "difficulty": meta.get("difficulty"),
                        "quarters_played": len(meta.get("moves", [])),
                    }
                )
        return out

    def world_view(self) -> dict[str, Any]:
        """Per-nation and per-region figures for the map modes (read-only)."""
        game = self._game()
        cfg, w, me = game.cfg, game.world, game.country
        club = set(trade.club_members(w))
        result = scoring.score(cfg, w, me, lost=game.lost) if w.history else None
        scores = result["all_nations"] if result else {}
        nations = {}
        for nid, n in sorted(w.nations.items()):
            base = n.base.get("emissions", 0.0)
            nations[nid] = {
                "name": cfg.nat_spec(nid)["name"],
                "emissions": round(n.emissions, 1),
                "emissions_change": round(n.emissions / base - 1, 4) if base else 0.0,
                "clean_share": round(scoring.clean_share(cfg, n), 4),
                "gdp": round(n.gdp, 3),
                "growth": round(n.growth, 4),
                "carbon_price": round(n.carbon_price, 1),
                "club": nid in club,
                "trust_in_you": round(diplomacy.trust(w, nid, me), 3) if nid != me else None,
                "your_trust": round(diplomacy.trust(w, me, nid), 3) if nid != me else None,
                "your_tariff": round(w.nations[me].tariffs.get(nid, 0.0), 3),
                "their_tariff": round(n.tariffs.get(me, 0.0), 3),
                "score": round(scores[nid]["score"], 1) if nid in scores else None,
                "rank": scores[nid]["rank"] if nid in scores else None,
                "personality": cfg.nat_spec(nid)["personality"],
                "techs": len(n.techs) + len(n.licensed),
                "demand": round(n.demand, 3),  # W3: deal sizes as a share of the host's energy
            }
        regs = {}
        for rid, r in sorted(w.regions.items()):
            demand = r.clean + r.fossil
            regs[rid] = {
                "name": cfg.regions["regions"][rid]["name"],
                "emissions": round(r.emissions, 1),
                "emissions_change": round(r.emissions / cfg.reg(rid, "co2") - 1, 4),
                "clean_share": round(r.clean / demand, 4) if demand else 0.0,
                "gdp": round(r.gdp, 3),
                "growth": round(r.growth, 4),
                "trust_in_you": round(r.trust.get(me, 0.5), 3),
                "financed_by_you": round(r.financed.get(me, 0.0), 4),
                "room_ej": round(regions.room(cfg, w, rid), 4),
                "open_events": [
                    e["id"] for e in w.minor_events if e["region"] == rid and e["status"] == "open"
                ],
            }
        history = [
            {
                "label": h["label"],
                "warming": round(h["warming"], 4),
                "global_emissions": round(h["global_emissions"], 0),
                "gdp": round(h["nations"][me]["gdp"], 4),
                "emissions": round(h["nations"][me]["emissions"], 1),
                "approval": round(h["nations"][me]["approval"], 3),
                "capital": round(h["nations"][me]["capital"], 4),
            }
            for h in w.history
        ]
        # W3: the orders drawer shows build times and whether a source is clean
        sources = {
            s: {
                "quarters": construction.build_time(cfg, w.nations[me], s),
                "category": cfg.category(s),
            }
            for s in cfg.source_ids
        }
        return {
            "me": me,
            "nations": nations,
            "regions": regs,
            "history": history,
            "sources": sources,
        }

    def state(self) -> dict[str, Any]:
        game = self._game()
        return {
            "name": self.name,
            "screen": view.observe(game),
            "world": self.world_view(),
            "text": view.render(view.observe(game)),
        }

    # --- moves ------------------------------------------------------------------------------

    def new(self, body: dict[str, Any]) -> dict[str, Any]:
        country = body.get("country")
        if country not in self.cfg.playable_ids:
            raise ApiError(f"choose a playable country: {self.cfg.playable_ids}")
        seed = body.get("seed", 1)
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**31:
            raise ApiError("seed must be a whole number")
        difficulty = body.get("difficulty") or None
        if difficulty and difficulty not in self.cfg.tuning["difficulty"]["levels"]:
            raise ApiError("unknown difficulty")
        name = body.get("name") or f"{country.lower()}_{seed}"
        if not NAME.match(name):
            raise ApiError("save names use letters, digits, - and _ (up to 40)")
        self.game = Game.new(self.cfg, country, seed, difficulty)
        self.name = name
        self._save()
        return self.state()

    def load(self, body: dict[str, Any]) -> dict[str, Any]:
        name = body.get("name", "")
        if not NAME.match(name):
            raise ApiError("bad save name")
        try:
            self.game = Game.load(self.cfg, self.saves / name)
        except SaveError as exc:
            raise ApiError(str(exc)) from exc
        self.name = name
        return self.state()

    def check(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"results": self._game().check(_actions(body))}

    def turn(self, body: dict[str, Any]) -> dict[str, Any]:
        game = self._game()
        if game.over:
            raise ApiError("the game is over")
        report = game.turn(_actions(body))
        self._save()
        return {"report": report} | self.state()

    def wait(self, body: dict[str, Any]) -> dict[str, Any]:
        game = self._game()
        n = body.get("quarters", 1)
        if not isinstance(n, int) or not 1 <= n <= 20:
            raise ApiError("quarters must be 1 to 20")
        reports = game.wait(n)
        self._save()
        return {"reports": reports} | self.state()

    def _game(self) -> Game:
        if self.game is None:
            raise ApiError("no game loaded", HTTPStatus.CONFLICT)
        return self.game

    def _save(self) -> None:
        self.game.save(self.saves / self.name)

    ROUTES = {
        ("GET", "/api/meta"): "meta",
        ("GET", "/api/state"): "state",
        ("POST", "/api/new"): "new",
        ("POST", "/api/load"): "load",
        ("POST", "/api/check"): "check",
        ("POST", "/api/turn"): "turn",
        ("POST", "/api/wait"): "wait",
    }

    def handle(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        name = self.ROUTES.get((method, path))
        if name is None:
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        with self.lock:
            fn = getattr(self, name)
            return fn() if method == "GET" else fn(body)


def _actions(body: dict[str, Any]) -> list[dict[str, Any]]:
    acts = body.get("actions", [])
    if not isinstance(acts, list) or not all(isinstance(a, dict) for a in acts):
        raise ApiError("actions must be a list of objects")
    return acts


def make_handler(server: Server) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quiet
            pass

        def _send(self, status: int, data: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _api(self, method: str) -> None:
            try:
                body: dict[str, Any] = {}
                if method == "POST":
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > 1_000_000:
                        raise ApiError("request too large")
                    raw = self.rfile.read(length) if length else b"{}"
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise ApiError("body must be a JSON object")
                out = server.handle(method, self.path.split("?")[0], body)
                status = HTTPStatus.OK
            except ApiError as exc:
                out, status = {"error": str(exc)}, exc.status
            except (ValueError, RuntimeError) as exc:
                out, status = {"error": str(exc)}, HTTPStatus.BAD_REQUEST
            self._send(status, canonical.dumps(out).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path.startswith("/api/"):
                return self._api("GET")
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (STATIC / rel).resolve()
            if STATIC not in target.parents or not target.is_file():
                return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(HTTPStatus.OK, target.read_bytes(), ctype)

        def do_POST(self) -> None:  # noqa: N802
            self._api("POST")

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m web")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = Server()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(server))
    print(f"Energy game: open http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    with contextlib.suppress(KeyboardInterrupt):
        httpd.serve_forever()
    return 0
