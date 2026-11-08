import csv
import json
import os
from pathlib import Path

import pytest

from sim import config, runner
from sim.state import World

GOLDEN = Path(__file__).parent / "golden_hashes.json"


@pytest.fixture(scope="module")
def cfg():
    return config.load()


def run_files(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())}


def test_noop_run_writes_outputs(tmp_path):
    out = tmp_path / "run"
    assert (
        runner.main(["run", "--country", "IND", "--bot", "noop", "--seed", "1", "--out", str(out)])
        == 0
    )
    assert sorted(p.name for p in out.iterdir()) == ["history.jsonl", "state.json", "summary.json"]
    lines = (out / "history.jsonl").read_text().splitlines()
    assert len(lines) == 100
    assert json.loads(lines[-1])["label"] == "2049Q4"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["turns_played"] == 100 and summary["final_quarter"] == "2049Q4"
    state = World.from_json((out / "state.json").read_text())
    assert state.hash() == summary["state_hash"]


def test_determinism_byte_for_byte(tmp_path, cfg):
    a, b = tmp_path / "a", tmp_path / "b"
    runner.run_one(cfg, 3, "VNM", "noop", a)
    runner.run_one(cfg, 3, "VNM", "noop", b)
    assert run_files(a) == run_files(b)


def test_resume_matches_full_run(cfg):
    full = runner.play(cfg, 5, "USA", "noop")
    half = runner.play(cfg, 5, "USA", "noop", until=50)
    saved = World.from_json(half.to_json())
    resumed = runner.play(cfg, 5, "USA", "noop", world=saved)
    assert resumed.hash() == full.hash()


def test_rejects_unplayable_country_and_unknown_bot(tmp_path):
    args = ["run", "--seed", "1", "--out", str(tmp_path / "x")]
    assert runner.main([*args, "--country", "GBR"]) == 2
    assert runner.main([*args, "--country", "IND", "--bot", "nope"]) == 2


def test_batch(tmp_path, cfg):
    spec = tmp_path / "batch.yaml"
    spec.write_text(
        f"out_dir: {tmp_path / 'out'}\ncountries: [IND, USA]\nbots: [noop]\nseeds: [2, 1]\n"
    )
    out = runner.run_batch(cfg, spec)
    rows = list(csv.DictReader((out / "aggregate.csv").open()))
    assert [(r["country"], r["seed"]) for r in rows] == [
        ("IND", "1"), ("IND", "2"), ("USA", "1"), ("USA", "2"),
    ]  # fmt: skip
    assert (out / "ind_noop_1" / "state.json").exists()


def test_golden_run(cfg):
    """Final state hash of a fixed run. Regenerate deliberately with UPDATE_GOLDEN=1 pytest."""
    world = runner.play(cfg, 1, "IND", "noop")
    actual = {"ind_noop_seed1": world.hash(), "config": cfg.hash}
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN.read_text())
    assert actual == expected
