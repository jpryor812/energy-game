"""W1: the local web server (web/server.py). No network beyond 127.0.0.1."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from sim.session import Game
from web.server import ApiError, Server, make_handler


@pytest.fixture
def server(cfg, tmp_path):
    return Server(cfg, saves=tmp_path)


def test_new_check_turn_wait_load(cfg, server, tmp_path):
    meta = server.handle("GET", "/api/meta", {})
    assert meta["playable"] == cfg.playable_ids and "build_capacity" in meta["catalogue"]
    state = server.handle("POST", "/api/new", {"country": "AAA", "seed": 2, "name": "g1"})
    assert state["screen"]["country"] == "AAA" and set(state["world"]["regions"])
    act = [{"type": "set_carbon_price", "level": 10}]
    assert server.handle("POST", "/api/check", {"actions": act})["results"][0]["ok"]
    out = server.handle("POST", "/api/turn", {"actions": act})
    assert out["report"]["results"][0]["ok"] and out["screen"]["turn"] == 1
    out = server.handle("POST", "/api/wait", {"quarters": 2})
    assert len(out["reports"]) == 2
    saved = Game.load(cfg, tmp_path / "g1")  # the usual session save: sim.play can continue it
    assert saved.world.t == 3 and saved.moves[0]["actions"] == act
    fresh = Server(cfg, saves=tmp_path)
    assert fresh.handle("POST", "/api/load", {"name": "g1"})["screen"]["turn"] == 3


def test_bad_requests_are_refused(server):
    with pytest.raises(ApiError):
        server.handle("GET", "/api/state", {})  # no game yet
    with pytest.raises(ApiError):
        server.handle("POST", "/api/new", {"country": "ZZZ"})
    with pytest.raises(ApiError):
        server.handle("POST", "/api/new", {"country": "AAA", "name": "../escape"})
    server.handle("POST", "/api/new", {"country": "AAA", "seed": 1})
    with pytest.raises(ApiError):
        server.handle("POST", "/api/turn", {"actions": "not a list"})
    with pytest.raises(ApiError):
        server.handle("POST", "/api/wait", {"quarters": 500})


def test_http_serves_page_and_api_and_blocks_traversal(server):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(server))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        page = urllib.request.urlopen(f"{base}/").read().decode()
        assert "app.js" in page
        meta = json.loads(urllib.request.urlopen(f"{base}/api/meta").read())
        assert meta["current"] is None
        for bad in ("/../sim/config.py", "/%2e%2e/sim/config.py", "/nothing.js"):
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(base + bad)
            assert exc.value.code == 404
        req = urllib.request.Request(f"{base}/api/turn", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 409  # no game loaded
    finally:
        httpd.shutdown()
