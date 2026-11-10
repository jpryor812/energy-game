"""The OpenRouter playtest runner's tools (scripts/playtest_agent.py). No network calls."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "playtest_agent", ROOT / "scripts" / "playtest_agent.py"
)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


@pytest.fixture
def save(tmp_path, monkeypatch):
    path = tmp_path / "r_test"
    cmd = [sys.executable, "-m", "sim.play", "new", "--country", "VNM", "--seed", "1",
           "--save", str(path)]  # fmt: skip
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
    return path


def test_play_runs_only_game_subcommands_on_its_own_save(save):
    tools = agent.Tools(save, hunter=False)
    assert "VNM" in tools.play("show --brief")
    assert "turn 1/" in tools.play("turn []")
    assert tools.play("rm -rf /").startswith("error")
    assert tools.play("new --country USA --save x").startswith("error")
    assert "VNM" in tools.play(f"python -m sim.play show {save} --brief")


def test_read_file_is_limited(save):
    player, hunter = agent.Tools(save, hunter=False), agent.Tools(save, hunter=True)
    assert "Playtest guide" in player.read_file("docs/PLAYTEST.md")
    assert player.read_file("sim/scoring.py").startswith("error")
    first = hunter.read_file("sim/scoring.py")
    assert "continues: read again with offset" in first
    offset = int(first.rsplit("offset ", 1)[1].rstrip("]"))
    assert "def score" in first + hunter.read_file("sim/scoring.py", offset)
    for path in (".env", "../etc/passwd", "README.md"):
        assert hunter.read_file(path).startswith("error")


def test_notes_append(save):
    tools = agent.Tools(save, hunter=False)
    tools.notes("2025: carbon price 25")
    tools.notes("2026: joined the club")
    assert (save / "notes.md").read_text().splitlines() == [
        "2025: carbon price 25",
        "2026: joined the club",
    ]


def test_env_file_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comment\nOPENROUTER_API_KEY="abc"\n\nOPENROUTER_MODEL=some/model\n')
    assert agent.load_env(env) == {"OPENROUTER_API_KEY": "abc", "OPENROUTER_MODEL": "some/model"}
    assert agent.load_env(tmp_path / "missing") == {}


def test_older_tool_results_are_shortened():
    msgs = [{"role": "user", "content": "go"}]
    msgs += [{"role": "tool", "tool_call_id": str(i), "content": "x" * 5000} for i in range(10)]
    out = agent.shorten(msgs)
    lengths = [len(m["content"]) for m in out if m["role"] == "tool"]
    assert all(n < 1000 for n in lengths[:4]) and all(n == 5000 for n in lengths[4:])
