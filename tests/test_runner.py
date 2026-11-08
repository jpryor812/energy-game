import csv
import json
import os
from pathlib import Path

from sim import config, runner, scoring
from sim.state import World

GOLDEN = Path(__file__).parent / "golden_hashes.json"


def run_files(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())}


def test_noop_run_writes_outputs(tmp_path, fixture_dir):
    out = tmp_path / "run"
    args = ["--data-dir", str(fixture_dir), "run", "--country", "AAA", "--seed", "1"]
    assert runner.main([*args, "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["history.jsonl", "state.json", "summary.json"]
    lines = (out / "history.jsonl").read_text().splitlines()
    summary = json.loads((out / "summary.json").read_text())
    assert len(lines) == summary["turns_played"]
    assert json.loads(lines[-1])["label"] == summary["final_quarter"]
    # Doing nothing on the fixture loses an election; a lost game stops early.
    assert summary["turns_played"] == 100 or summary["ending"] in scoring.LOSSES
    state = World.from_json((out / "state.json").read_text())
    assert state.hash() == summary["state_hash"]


def test_determinism_byte_for_byte(tmp_path, cfg):
    a, b = tmp_path / "a", tmp_path / "b"
    runner.run_one(cfg, 3, "AAA", "noop", a)
    runner.run_one(cfg, 3, "AAA", "noop", b)
    assert run_files(a) == run_files(b)


def test_rejects_unplayable_country_and_unknown_bot(tmp_path, fixture_dir):
    args = ["--data-dir", str(fixture_dir), "run", "--seed", "1", "--out", str(tmp_path / "x")]
    assert runner.main([*args, "--country", "BBB"]) == 2
    assert runner.main([*args, "--country", "AAA", "--bot", "nope"]) == 2


def test_batch(tmp_path, cfg):
    spec = tmp_path / "batch.yaml"
    spec.write_text(f"out_dir: {tmp_path / 'out'}\ncountries: [AAA]\nbots: [noop]\nseeds: [2, 1]\n")
    out = runner.run_batch(cfg, spec)
    rows = list(csv.DictReader((out / "aggregate.csv").open()))
    assert [(r["country"], r["seed"]) for r in rows] == [("AAA", "1"), ("AAA", "2")]
    assert (out / "aaa_noop_1" / "state.json").exists()


def test_golden_run():
    """Final state hash of a fixed run on the real data. Regenerate deliberately with
    UPDATE_GOLDEN=1 pytest."""
    cfg = config.load()
    world = runner.play(cfg, 1, "IND", "noop")
    actual = {"ind_noop_seed1": world.hash(), "config": cfg.hash}
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN.read_text())
    assert actual == expected
