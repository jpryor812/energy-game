# energy-game

A turn-based strategy game about national energy economies, 2025 to 2050, one turn per quarter
(100 turns). You lead one country; your score is your nation's prosperity multiplied by how the
world did on climate. No war: conflict runs through tariffs, export controls, sanctions, and deals.

This repository currently holds the **headless simulation** (Python, no UI), used to prove the
core tension and tune the numbers. See:

- `docs/DESIGN.md`: game design, the source of truth
- `docs/BUILD_SIM_V0.md`: what the simulation builds now, milestone by milestone
- `docs/ASSUMPTIONS.md`: modelling choices not in the design doc
- `data/SOURCES.md`: where every real-world starting value comes from

## Setup

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

## Commands

```bash
pytest -q                                   # tests
ruff check . && ruff format --check .       # lint
python -m sim.runner run --country IND --bot noop --seed 1 --out runs/ind_noop_1
python -m sim.runner batch --config scripts/batch_default.yaml
```

A run writes `history.jsonl` (one line per turn), `summary.json`, and the final `state.json`.
Same seed and inputs always produce byte-identical output.

## Status

M0 (scaffold) is done: config loader, seeded RNG, serializable state, a no-op 100-turn pipeline,
and the CLI. The world model (M1), actions and bots (M2), and later milestones are not built yet.
Only the `noop` bot exists for now.
