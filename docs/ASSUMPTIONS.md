# Assumptions

Modelling and engineering choices that are not in `docs/DESIGN.md` or `docs/BUILD_SIM_V0.md`,
with the reason for each. Newest milestone last.

## M0: scaffold

1. **Turn 99 is 2049Q4.** The build doc says 100 turns from 2025Q1 to 2049Q4; the design doc's
   "2025 to 2050" is read as "up to the start of 2050".
2. **`t` counts quarters, and `dt` is quarters per step.** Annual mode will call `step(dt=4)`, and
   `t` still counts quarters. A stocktake fires if any quarter in the step has `t % 20 == 19`, so
   annual mode hits the same five stocktakes.
3. **Stateless RNG streams.** Each draw site gets a generator seeded from
   SHA-256(master seed, stream name, keys such as turn and nation). There is no RNG state to save,
   resumed games replay exactly, and adding a draw in one place never shifts another. Stream names
   are registered in `sim/rng.py` so a typo fails loudly.
4. **No numpy for now.** Plain Python floats keep outputs byte-identical across machines; numpy can
   be added later if a hot loop needs it.
5. **Canonical JSON.** All output uses sorted keys and rejects NaN and infinity. State hashes are
   SHA-256 of the compact encoding.
6. **No bare numbers in data files.** Every number in `data/*.yaml` must sit inside a tunable
   (`value`, `status`, `note`, optional `source` and `unit`); the loader rejects anything else.
   Strings, booleans and nulls are structural and may appear bare. Values fixed by the design doc
   (start year, 100 turns, stocktake every 20) are tagged `calibrated` with a note saying so.
7. **History lives in the world state.** `World.history` holds one compact record per turn and is
   mirrored to `history.jsonl`, so a saved `state.json` is enough to resume and still produce full
   history. Scoring in M2 will read from it.
8. **`step` is pure.** It deep-copies the world and returns a new one. Simple and safe at 16
   nations; revisit only if profiling says so.
9. **Country IDs.** ISO 3166-1 alpha-3 codes; the EU uses the World Bank aggregate code `EUU`.
10. **Only the `noop` bot exists in M0.** The CLI example `--bot balanced` works from M2. Submitting
    any action before M2 raises `NotImplementedError` instead of being silently ignored.
11. **`new_world` lives in `sim/scenario.py`** (moved from `sim/state.py` in M1 so `state.py`
    stays plain data). Not listed in the build doc's layout.
12. **Action slots are not banked yet.** Slot accrual belongs with actions in M2.

## M1: world model, business as usual

### Units

- Energy: EJ/yr of **primary energy**, input-equivalent (substitution method) for non-fossil
  sources, so 1 EJ of solar displaces about 1 EJ of fossil fuel. Covers all sectors, including
  oil for transport (M1 decision 1).
- Capacity: maximum output in EJ/yr. For wind, solar and hydro it equals expected output.
- GDP and money: T$ per year, 2025 USD at market exchange rates, held constant thereafter.
- Emissions: MtCO2/yr for rates, MtCO2 for cumulative totals. Population: millions.

### Modelling choices

13. **Other renewables added as a source.** Bioenergy, geothermal and other renewables (the
    residual of primary energy after the listed sources) need a home, or demand could never be
    met. Category `clean_dispatchable`, zero direct CO2 as in energy inventories.
14. **Dispatch reproduces 2024 at t=0.** Each non-variable source has a normal output
    (capacity / headroom). Excess is cut from the most expensive source, shortfall filled from
    the cheapest headroom. A pure merit order across all primary energy would instantly switch
    oil for coal, which is not substitutable in transport.
15. **Wind and solar curtailment.** The grid absorbs wind and solar up to a base share of demand
    (placeholder 25%) plus grid and storage capacity. Starting grid is set so 2024 output is not
    curtailed.
16. **Per-nation emission factors.** Fossil fuels use each nation's 2024 CO2 / use, so t=0
    emissions match the Global Carbon Budget exactly; Nigeria uses world factors.
17. **Retirement.** Constant rate 1/lifespan (no plant-age data), or the observed 2019-2024
    decline in use where faster (e.g. EU and US coal).
18. **BAU builder (M1 decision 2).** Orders are placed to meet projected demand at the slowest
    build time in the nation's mix, split by the nation's 2019-2024 change in use, and all
    delivered on that date. The pipeline is seeded at t=0 with what would already be under way.
    It builds grid to absorb new wind and solar. BAU builds cost no capital. Two simpler
    versions were tried and rejected during M1: a fixed 2-year horizon left coal-heavy growers
    short of energy (coal takes 4 years), and a separate horizon per source distorted the mix.
19. **Growth drags are relative to 2025.** Baseline growth already reflects 2025 conditions, so
    shortfall, price, debt and climate damage drag only on changes since 2025. Trade (T) is the
    change in fossil export value since 2025 as a share of GDP. Investment, productivity and
    restrictions (I, P, R) are zero until actions exist.
20. **Baseline growth.** IMF mean 2025-2030 real growth, interpolated linearly to a long-run
    rate at the final turn (placeholder rule in SOURCES.md).
21. **Capital (M1 decision 4).** A discretionary share of GDP (placeholder 2%) plus the
    government take on fossil exports, minus interest on debt taken on *during the game*.
    Pre-existing public debt is serviced by the ordinary budget, not discretionary capital.
    With no actions, capital simply accumulates in M1.
22. **Fossil trade.** A 2024 net exporter keeps its export volume scaled by world (16-nation)
    use of that fuel relative to 2025. A net importer keeps its 2024 self-sufficiency share. One
    world price per fuel.
23. **FX reserves.** Only for non-issuers. They move by a pass-through share (placeholder 25%) of
    the change in fossil trade balance; the exchange rate absorbs the rest. An importer's 2025
    deficit is assumed to grow with GDP (other exports finance it); an exporter's surplus is
    compared with its 2025 level.
24. **Climate.** Warming = 2025 warming + TCRE x (1 + non-CO2 multiplier) x cumulative CO2
    since 2025. Rest-of-world energy CO2 grows 1%/yr, land-use CO2 falls 1%/yr, other fossil CO2
    is constant (all placeholders). Damage is a growth drag proportional to vulnerability and
    the square of warming since 2025.
25. **Learning curves.** Global deployment grows by what the 16 nations build divided by their
    share of world use, so the rest of the world builds in proportion.
26. **Approval and stability.** Approval drifts to a baseline and is hit by the shortfall,
    price and damage drags; stability follows approval. All placeholders, same for every nation.
27. **Data vintage.** Energy and CO2 data are for 2024 (the latest in the sources), GDP and
    population for 2025. The 2024 mix stands in for 2025Q1.
28. **Six then sixteen.** The build doc says to do the 6 playable nations first, then all 16.
    The same extraction script covers all 16 at once, so they were added together.

## Open questions

- **BAU builder vs. player builds (for M2).** When the player acts, should the BAU builder
  still run for the player's nation (a private market that responds to prices and subsidies),
  or should all building come from player actions?
- **Frozen-trend BAU.** BAU emissions sit ~10% above the IEA Current Policies Scenario by 2049
  because the builder ignores falling clean-energy costs (docs/CALIBRATION.md). Making it
  cost-responsive would close the gap; AI nations in M3 may make this moot.
- **Slots per quarter.** The design doc suggests 3 domestic + 2 diplomatic; the build doc says
  2 domestic + 1 diplomatic (placeholder). M2 will use the build doc's numbers unless told
  otherwise.
