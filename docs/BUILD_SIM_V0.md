# Build Instructions: Simulation v0

Read `CLAUDE.md` and `docs/DESIGN.md` first. This file says what to build now, in what order, and how to know it works.

## Goal

Build a **headless, deterministic Python simulation** of the game: 100 quarterly turns (2025Q1 to 2049Q4), 16 nations, scoring, and bots that play it. No UI. The sim must prove one thing: **winning for your country and getting the world to net zero are both achievable, and they pull against each other.** Every number is a placeholder to tune, so the harness matters as much as the model.

## Working rules

1. Plan first. Before each milestone, post a short plan and wait for approval.
2. One milestone at a time. Each ends with passing tests, a short summary (built, assumed, open questions), and a git commit.
3. All tunables live in `data/*.yaml`, each tagged `status: placeholder` or `status: calibrated`.
4. Do not invent real-world data silently. Starting values are approximate 2025 figures. Cite the source in `data/SOURCES.md` (IEA, Ember, World Bank, etc.) or mark the value `unsourced approximate`. Say so when you cannot verify something.
5. Log every modelling choice not in the design doc in `docs/ASSUMPTIONS.md`.
6. No LLM calls and no runtime network access. All randomness uses seeded streams from `sim/rng.py`; AI nations use none.
7. State is plain dataclasses that serialize to JSON, so any run can be saved, resumed, and replayed.

## Stack

Python 3.11+, `pyyaml`, `pytest`, `ruff`, optional `numpy`. Package with `pyproject.toml` and an `[dev]` extra.

## Layout

```
sim/
  config.py     load and validate YAML
  state.py      World, Nation, Deal, Pledge dataclasses; JSON (de)serialization
  rng.py        named seeded streams (events, shocks), derived from the master seed
  economy.py    GDP growth, capital, debt
  energy.py     capacity, dispatch, demand, curtailment
  climate.py    cumulative emissions -> warming -> damage
  tech.py       learning curves, research, adoption
  diplomacy.py  trust, blocs, tariffs, pledges
  deals.py      deal types, resolution, emissions credit (M4+)
  actions.py    action definitions, validation, slot accounting
  ai.py         deterministic utility AI for non-player nations
  bots.py       scripted player policies for testing
  scoring.py    Nation Index, World Multiplier, bonuses, endings
  turn.py       the quarterly pipeline
  events.py     hook only in v0 (no-op)
  runner.py     CLI: run, batch
  report.py     metrics and BALANCE_REPORT.md generation
data/           countries.yaml, techs.yaml, events.yaml (empty), tuning.yaml, SOURCES.md
tests/
scripts/        run_batch.py, batch_default.yaml
```

## Scope

**In v0:** national-level model, one GDP number, abstract energy units, 100 turns, 16 nations (6 playable: US, India, EU, China, Vietnam, Russia), capital / political capital / influence / tech points / emissions / FX reserves, the action set below, four deal types, tariffs, one bloc, stocktake every 20 turns, scoring and endings, bots, balance harness.

**Out of v0:** regions, UI, events and advisers (hook only), elections, mineral supply chains, mock UN, any LLM.

## Time model

- 100 turns. Turn `t` runs 0..99; `t=0` is 2025Q1.
- Seasonal factors on demand (summer and winter peaks) as a small multiplier per quarter.
- Stocktake when `t % 20 == 19` (end of 2029, 2034, 2039, 2044, 2049).
- Annual mode later = same rules, four quarters per turn. Do not build it yet, but keep the pipeline callable with a `dt` parameter.

## Data model

**World:** `t`, `seed`, `nations`, `global_cumulative_emissions`, `warming`, `tech_state` (cumulative deployment per tech), `blocs`, `deals`, `trust` matrix, `history`.

**Nation:** `id`, `playable`, `personality`, `gdp`, `population`, `capital`, `political_capital`, `influence`, `tech_points`, `fx_reserves`, `debt_hard`, `debt_local`, `approval`, `stability`, `energy_intensity` (energy per unit GDP), `demand`, `capacity` (per source), `pipeline` (under construction), `carbon_price`, `subsidies`, `tariffs`, `emissions`, `cumulative_emissions`, `fair_share_budget`, `slots_banked`, `pledge`.

**Sources:** coal, oil, gas, nuclear, hydro, wind, solar, plus `storage` and `grid` as enablers. Each has build cost, build time (quarters), lifespan, capacity factor, emissions per unit, and a learning-curve exponent `b`. Variable renewables (wind, solar) are curtailed beyond a share the grid and storage can absorb.

## The quarterly pipeline (`turn.py`)

Run these in order for every nation each turn:

1. **Income and slots.** Capital += tax share of GDP + deal income + fossil export revenue - debt service. Add slots (placeholder: 2 domestic + 1 diplomatic per quarter, banked, no cap).
2. **Actions.** Player (or bot) submits actions, then AI nations submit theirs. Validate against capital, political capital, influence, and slots.
3. **Resolve actions.** Apply instant effects; queue construction and research.
4. **Construction.** Advance the pipeline; completed capacity comes online; retirements happen.
5. **Energy dispatch.** Merit order including carbon price. Meet demand; compute shortfall, imports, curtailment, emissions.
6. **Economy.** Update GDP with the growth formula (below), approval, stability.
7. **Climate.** Add emissions to the global total, update warming, compute damage per country (scaled by vulnerability).
8. **Technology.** Update cumulative deployment and unit costs via learning curves; research spending yields tech points.
9. **Diplomacy and deals.** Resolve proposals, update trust, apply deal flows, tariffs, and bloc effects.
10. **Stocktake** if `t % 20 == 19`: compare emissions with fair share, apply consequences, update fair shares.
11. **Scoring snapshot.** Record Nation Index inputs and running score.
12. **Events hook.** No-op in v0, but called so v1 can plug in.

## Core formulas (placeholders; constants in `tuning.yaml`)

- **GDP growth:** `g = g0 + I + P + T - S - E - R - D - C`
  - `g0` baseline per country; `I` investment; `P` productivity (from tech points and falling costs); `T` trade; `S` energy shortfall; `E` energy price shock; `R` restrictions and stranded-asset write-offs; `D` debt and currency drag; `C` climate damage.
- **Emissions (Kaya):** `E = population * (GDP/pop) * (energy/GDP) * (emissions/energy)`. Compute from dispatch; keep the identity as a test.
- **Learning curve:** `C(n) = C0 * n^(-b)`, with `n` the global cumulative deployment of that technology.
- **Warming:** proportional to cumulative global emissions (a single coefficient).
- **Activity cap (degrowth):** reduces energy-intensive output and emissions, and lowers GDP, capital, and approval. It must be viable but rarely the best option.
- **Fair share:** each nation's share of the remaining carbon budget based on emissions, recomputed at each stocktake.
- **Score:** `Score = N * M(T) + bonuses`
  - `N` = weighted blend of income growth per person, energy security, stability and welfare, clean competitiveness, each scaled to the nation's own starting point.
  - `M(T)` = near 1.0 for a good outcome, falling steeply as warming rises.
  - Bonuses (flat): first net zero, largest reduction, breakthrough tech adopted by the most nations, most impactful deal for emissions.

## Actions (`actions.py`)

Domestic: `build_capacity(source, amount)`, `retire_capacity(source, amount)`, `set_carbon_price(level)`, `set_subsidy(source, level)`, `invest_research(tech, amount)`, `invest_efficiency(amount)`, `buy_influence(amount)`, `build_grid_storage(amount)`, `set_activity_cap(level)`, `adaptation_spend(amount)`, `rebate(level)`.

Diplomatic: `propose_deal(target, type, terms)`, `respond_deal(id, accept|counter|refuse)`, `set_tariff(target, level)`, `lift_tariff(target)`, `make_pledge(target_emissions, year)`, `open_talks(target)`, `join_bloc(id)`, `leave_bloc(id)`.

Each action declares its cost (resource and amount), slot type, and effect delay. Political-capital costs apply to unpopular moves (carbon price, coal closures).

## Deals

- **M4:** `equipment_on_credit`, `energy_as_a_service`.
- **M5:** `equity_for_energy`, `climate_loan`.
- Every deal has price, currency (hard or local), duration, collateral, exit clause. Currency mismatch is the main failure mode: hard-currency repayments against local-currency revenue drain FX reserves and can trigger default.
- **Emissions credit:** host 1 : 1, financier 0.75 : 1, technology inventor 0.6 : 1 (placeholders). Credit counts for score and bonuses only; the atmosphere uses real emissions. Add a test that credit never changes global warming.
- Defaults reduce trust and cost the defaulter via the debt/currency drag term.

## AI nations (`ai.py`)

Deterministic utility scoring: each nation scores its available actions by its personality weights and its state, picks the best affordable set for its slots, and breaks ties by a fixed order (action id, then target id). No randomness.

Personalities: `green_leader`, `fossil_defender`, `opportunist`, `cautious_follower`. Each has weights for growth, security, emissions, trust, and deals. Assign by nation in `countries.yaml`. Nations follow their real stated climate pledges directionally (recorded as targets in the data file with sources), not exactly.

Deal acceptance: accept if the nation's utility gain exceeds a threshold that rises with currency risk and falls with trust.

## Bots (`bots.py`)

Scripted player policies for balance testing: `all_fossil`, `all_clean`, `balanced`, `deal_maker`. Each is a function from state to a list of actions, deterministic given the seed.

## CLI

```
python -m sim.runner run --country IND --bot balanced --seed 1 --out runs/ind_balanced_1
python -m sim.runner batch --config scripts/batch_default.yaml
```

Each run writes `history.jsonl` (one line per turn), `summary.json` (final score, ending, bonuses), and a final `state.json`. Batch writes an aggregate CSV and regenerates `docs/BALANCE_REPORT.md`.

## Milestones

| # | Deliverable | Done when |
| --- | --- | --- |
| M0 | Scaffold: repo, packaging, lint, test setup, config loader, RNG, state (de)serialization, CLI skeleton | `pytest` and `ruff` pass; a no-op run writes outputs |
| M1 | World model with no player actions (business as usual) for the 6 playable nations first, then all 16 | BAU runs 100 turns; GDP, energy, emissions, and warming look plausible and are documented against sources |
| M2 | Actions, slots, bots, scoring, endings | Four bots play any playable nation; scores and endings are produced |
| M3 | AI nations for all 16 with personalities | Full 16-nation world runs with AI-only and with a bot player; deterministic |
| M4 | Trust, tariffs, one bloc, two deal types, emissions credit, stocktake | Deals change outcomes; credit test passes; stocktake consequences fire |
| M5 | Four deal types, batch harness, auto-generated `docs/BALANCE_REPORT.md` | Acceptance criteria below measured and reported |

## Balance acceptance criteria

Report on each (pass, fail, or tune) in `BALANCE_REPORT.md`:

1. **Determinism:** same seed, same output hash, across runs and machines.
2. **No dominant bot:** no bot wins on every playable nation.
3. **Viable strategies:** for each playable nation, at least two bot strategies finish within a set tolerance of the best score.
4. **Difficulty ordering:** the US and UK (the easier nations) score higher than India, Vietnam, and Russia on average with the same bot.
5. **Free-rider tension:** a nation that cuts less than its fair share gains on N in the short term but loses to M(T) when many nations do the same; show this in a scenario run.
6. **Sanity:** no NaN, no negative GDP, no negative capacity, no impossible emissions.
7. **Game length:** runs finish 100 turns; a bot that ignores energy security triggers `Fallen Government` in a meaningful share of runs.

## Tests

- **Unit tests** for each formula and each action.
- **Property tests**: energy balance (supply meets demand plus losses plus shortfall), the Kaya identity, capital is conserved except through income and spending, and credit never changes warming.
- **Golden-run test**: a fixed seed and config produce a stored hash; update it only on purpose.
- **Determinism test**: run twice, compare byte-for-byte.

## Kickoff prompt (paste into Claude Code)

> Read `CLAUDE.md`, `docs/DESIGN.md`, and `docs/BUILD_SIM_V0.md`. We are building the headless simulation first. Start with M0. Before writing code, give me a short plan for M0 (files, dependencies, tests) and list any assumptions or questions. Wait for my approval, then build M0, run tests and lint, commit, and summarize. Do not start M1 until I say so. Do not invent real-world data without a source or an explicit "unsourced approximate" tag.
