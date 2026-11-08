# CLAUDE.md

Project guide for Claude Code. Read this first, then `docs/DESIGN.md`, then `docs/BUILD_SIM_V0.md`.

## What this project is

A turn-based strategy game about national energy economies, 2025 to 2050, one turn per quarter (100 turns). The player leads one country. Score is the nation's prosperity multiplied by how the world did on climate, so winning for yourself needs the world close to net zero. No war: conflict is tariffs, export controls, sanctions, and competition. The core action is the deal (trade, loan, equity swap).

We are building the **headless simulation first** (Python, no UI). The full game is web-based later. The simulation's job is to prove the core tension and let us tune the numbers.

## Principles

- **Deterministic.** Same seed and same inputs produce byte-identical output. All randomness goes through seeded streams in `sim/rng.py`. AI nations use no randomness at all.
- **No LLM calls and no runtime network access.** Ever, in the simulation.
- **No magic numbers.** Every tunable constant lives in `data/*.yaml` and is tagged `status: placeholder` or `status: calibrated`, with a note on where it came from.
- **Do not invent real-world data silently.** Country starting values are approximate 2025 figures. Record each value's source (IEA, Ember, World Bank, or similar) in `data/SOURCES.md`, or mark it `unsourced approximate`. If you cannot verify a number, say so.
- **Simple first.** National-level model, one GDP number, abstract energy units. Add detail only when a test or a balance run shows it is needed.
- **Pure, serializable state.** The engine is functions over plain dataclasses that serialize to JSON, so runs can be replayed, saved, and resumed.
- **Neutral tone.** Geopolitics appears only as mechanics (tariffs, financing limits, sanctions exposure), never as commentary. Leaders are abstract; no real people.

## Stack and commands

- Python 3.11+, `pyyaml`, `numpy` (optional), `pytest`, `ruff`.
- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Test: `pytest -q`
- Lint: `ruff check . && ruff format --check .`
- Single run: `python -m sim.runner run --country IND --bot balanced --seed 1 --out runs/ind_balanced_1`
- Batch: `python -m sim.runner batch --config scripts/batch_default.yaml`

(Create these commands as part of milestone M0 if they do not exist yet.)

## Working agreements

- Plan before coding. Propose a short plan and wait for approval before starting each milestone.
- Work one milestone at a time. Each ends with passing tests, a short summary of what was built and what was assumed, and a git commit.
- Keep `docs/ASSUMPTIONS.md` current: every modelling choice that was not in the design doc goes there, with the reason.
- When the design doc and the code disagree, stop and ask, or update the doc with a note, and never drift silently.
- Prefer small modules with clear inputs and outputs, and tests for each.

## Repository layout

```
CLAUDE.md
docs/        DESIGN.md, BUILD_SIM_V0.md, ASSUMPTIONS.md, CALIBRATION.md, BALANCE_REPORT.md
data/        countries.yaml, techs.yaml, tuning.yaml, SOURCES.md
sim/         config, state, rng, economy, energy, climate, tech, diplomacy,
             deals, actions, ai, bots, scoring, turn, events (hook), runner, report
tests/
scripts/     batch configs
runs/        outputs (gitignored)
```
