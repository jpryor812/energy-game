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
10. **Only the `noop` bot exists in M0.** (Superseded in M2: four playing bots exist, and
    invalid actions are rejected and logged.)
11. **`new_world` lives in `sim/scenario.py`** (moved from `sim/state.py` in M1 so `state.py`
    stays plain data). Not listed in the build doc's layout.
12. **Action slots are not banked yet.** (Superseded in M2: slots bank every quarter.)

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
18. **BAU builder (M1 decision 2; replaced by the market builder in M2, item 29).** Orders are placed to meet projected demand at the slowest
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

## M2: actions, bots, scoring, endings

29. **Market builder (M2 decision 1).** The M1 BAU builder becomes a private market that runs
    for every nation, the player's included. New capacity = (1 - w) x the 2019-2024 trend mix +
    w x a logit over levelized cost (w = `market.cost_weight` = 0.5, temperature $3/GJ).
    Nuclear and hydro are policy-driven and appear only through the trend mix; the market picks
    coal on cost only where the nation already burns it. Public builds from actions sit in the
    same pipeline, so the market builds less when the player builds more. The market pays
    nothing itself; subsidies are paid from capital when the market orders, and borrowed
    locally if capital runs out.
30. **Levelized cost.** Capital cost annualized at a 7% real discount rate over the lifespan,
    per GJ of normal output, plus variable and carbon cost; wind and solar add a system cost of
    the grid charge x (share / base absorb share)^2.
31. **Electrifiable share.** Wind and solar can serve at most a share of primary demand that
    rises from 40% (2025) to 70% (2050), placeholders standing in for electrification. Without
    it, solar replaced all oil, including transport. Grid is not built beyond it.
32. **Energy price includes capital costs.** The reported price is the average of capital
    charge (at today's unit costs) + fuel + carbon over the sources dispatched, plus grid and
    storage charges. Variable cost alone fell to zero as solar grew. Merit order still uses
    variable cost only.
33. **Slots (M2 decision 2).** 2 domestic + 1 diplomatic per quarter, banked with no cap. Every
    action uses one slot of its type. `buy_influence` is domestic, as listed in the build doc.
34. **Rejected, not raised.** A malformed or unaffordable action is rejected with a reason in
    the history and costs nothing. Actions for an unknown nation are a programming error and
    raise.
35. **Political capital.** Starts at 10; earned at 4/yr plus 20 x (approval - 0.55)/yr, never
    below zero. Spent on carbon-price increases (0.1 per $/t), early retirements (2 per EJ/yr,
    x1.5 for coal) and activity caps.
36. **Carbon revenue.** Only the price above its 2025 level adds to discretionary capital (2025
    revenue is already in the ordinary budget), minus the rebated share. A rebate also removes
    up to 80% of the energy-price growth drag.
37. **Early retirement.** Writes off half of today's replacement cost (no plant-age data); half
    of that is a one-off GDP loss in the next step (the R term). Fossil retirements also cut
    approval.
38. **Research.** Cumulative research spend on a technology cuts the nation's own unit cost for
    it (up to 30%, half at $50bn), and research / GDP adds up to 0.5 pp/yr productivity (the P
    term). Global learning curves are unaffected. The investment term I stays zero: baseline
    growth already includes normal investment.
39. **Efficiency, adaptation, activity cap.** Efficiency spending cuts energy intensity with
    diminishing returns relative to GDP. Adaptation is a stock that removes up to 50% of
    climate damage. The activity cap removes a share of demand and half as large a share of GDP,
    and costs approval while in force.
40. **Pledges** are recorded (target as a share of 2025 emissions, and a year) but have no
    effect until trust and stocktakes arrive in M4.
41. **Scoring.** Nation Index components are measured against each nation's own start: income
    per person vs. its baseline-growth path; security from shortfall and import dependence;
    welfare from average approval and the energy price change; clean competitiveness from its
    share of clean capacity built vs. its share of 2025 GDP. Each maps to 0..1 through a
    logistic or a linear ramp; sub-scores are averaged equally. Weights are equal. Running
    scores are not stored per turn; the inputs are in the history and the score is computed at
    the end.
42. **World multiplier.** 1.0 up to 1.6 degC, falling quadratically to 0.1 at 2.6 degC.
43. **Endings.** "Top rank" means rank 4 or better of 16 on N; a "good world" is final warming at
    or below 2.0 degC. Fallen Government: the run stops as soon as the player's stability is
    below 0.1.
44. **Bonuses.** First net zero (at or below 5% of 2025 emissions, ties broken by nation id) and
    largest percentage cut, 5 points each. Breakthrough technology and most impactful deal
    wait for M4-M5.
45. **Bots** plan with this quarter's slots and spend shares of current capital; the shares
    and steps are bot behaviour and live in `sim/bots.py`, not in `data/`. `deal_maker` is
    `balanced` plus a pledge and influence buying until deals exist.
46. **Non-player nations take no actions in M2**; only the market runs for them. M3 adds AI.

## M3: AI nations

47. **Assumed target paths, not real pledges** (decided with the user, 2026-11-07). Each nation
    follows a path in `data/targets.yaml` (levels as a share of its 2025 energy CO2 at waypoint
    years, linear between, flat after) chosen from its general climate-policy stance over
    roughly 2005-2025, grouped as consistently ambitious, ambitious targets with slower
    delivery, volatile, peak-then-decline, growth first, moderate, and low ambition. They are
    placeholders, not sourced data.
48. **Personalities** are game archetypes based on energy-policy stance, not commentary:
    green leader (EU, UK), opportunist (China, India, Indonesia, Vietnam, USA), cautious
    follower (Japan, Canada, Australia, Brazil, South Africa), fossil defender (Saudi Arabia,
    Russia, Nigeria, Mexico).
49. **Utility AI.** Each quarter an AI nation scores a fixed menu of concrete candidates with
    closed-form estimates (no lookahead simulation, which would be ~100x slower): growth in
    pp/yr, security in pp of demand, emissions in % of 2025 emissions/yr, and costs in years
    of capital and political-capital income. Utility = personality-weighted effects minus
    costs. It takes the best affordable candidates, one per action type, up to its slots;
    ties break by action type then target. AI nations decide from the same start-of-quarter
    state, so moves are simultaneous. They never use the RNG (a test enforces this).
50. **Estimates.** A public build replaces what the market would have built over the next year;
    any surplus pushes out the most expensive fossil source running. Clean output beyond the
    ceilings, or wind and solar the grid cannot absorb, counts for nothing. A retirement is
    penalised heavily once spare capacity would fall below 5% of demand, and charged the
    expected shortfall growth loss if it goes negative. A carbon-price step is assumed to cut
    0.1% of emissions per $/t in the long run.
51. **Emissions weight** = personality weight x (1 + adherence x gap / 0.1), where gap is
    actual emissions minus the target path (shares of 2025 emissions), never below zero: a
    nation well ahead of its path stops pushing. Followers add the gap between their peers'
    average cut and their own. Trust and deal weights are defined but unused until M4.
52. **Pledges.** At t=0 each AI nation makes a pledge equal to its first waypoint.
53. **Clean ceiling.** All non-fossil sources together can serve at most a share of demand
    rising from 55% (2025) to 95% (2050), standing in for end-use conversion limits; without it
    bioenergy replaced all oil. The market and the AI respect it, and 5% of demand stays fossil
    at the end without new technology (carbon capture is not modelled).
54. **Market counts only absorbable wind and solar** when planning, so public wind built ahead
    of grid no longer leaves a shortfall.
55. **Efficiency is a cumulative stock.** All efficiency spending together can cut energy
    intensity by at most 30% beyond the trend (63% of that at 5% of GDP); M2 reset the
    diminishing returns on every investment.
56. **AI-only and bot runs.** `--bot ai` hands the player's nation to the AI too. In every run,
    nations without player or bot actions are AI-controlled; the business-as-usual reference
    (`report.bau_world`) switches AI off.
57. **Seeds.** Nothing uses the RNG yet, so seeds give identical runs; the default batch uses
    one seed until events arrive.

## M4: trade and diplomacy

Decisions made with the user on 2026-11-08 are recorded in docs/DESIGN.md ("Decided
2026-11-08"); the modelling choices below implement them.

58. **Clean slate.** Every pair of nations starts at trust 0.5 with no tariffs; nothing from real
    2025 trade restrictions carries over. Trust is directional (how much A trusts B) and drifts
    back to neutral at 5%/yr.
59. **Goods trade** is a gravity model: each nation exports its non-fossil export share of GDP
    (World Bank exports/GDP minus its fossil export revenue; EU uses ~22% extra-EU), split across
    the other nations and the rest of the world by GDP. No bilateral data, so no real trade
    pattern is imposed. The growth effect counts only changes against the no-tariff level, as
    with the other drags.
60. **Tariffs** cut the target's exports to the imposer by 1.5x the tariff, cost the imposer the
    tariff paid on its imports (a growth drag) and earn it the same as revenue (added to
    capital), and cost trust. There is no trade diversion to third countries.
61. **Clean-tech equipment** (solar, wind, batteries) is bought from manufacturers by approximate
    real 2024 world shares, the rest of the world making the remainder; a buyer shifts away from
    suppliers it tariffs ((1 + tariff)^-3) and pays its tariff on what it still buys, raising
    its build cost. Manufacturing shares are fixed until M4b adds supply-chain levers. The
    supplier's growth effect counts only sales above or below its base share.
62. **Exported-tech credit.** A supplier earns credit for the emissions its equipment displaces
    abroad (output x the buyer's average fossil emission factor), scored at 0.6.
63. **Carbon club.** One bloc, founded by the EU in 2025 (its effective price, $32/t, clears the
    $25/t bar); members cannot tariff each other, get a 2-point interest discount on deals with
    each other, and are exempt from coalition tariffs. A member whose carbon price falls below
    the bar is dropped at the next stocktake.
64. **Deals.** Only clean capacity can be financed. The financier pays its own unit cost; the
    host gets the capacity. Equipment-on-credit hosts carry the cost as hard or local debt,
    repaid in equal principal plus interest once the plant is running. Energy-as-a-service hosts
    pay per GJ of the plant's normal output. Hard-currency payments that capital and FX reserves
    cannot cover are a default: collateral is seized, the remaining debt is written off, half of
    it is lost from GDP (like a stranded asset), and trust falls. Local-currency payments never
    default (the host borrows locally) but lose value to the financier as the host's FX reserves
    fall below 2025. Proposals expire after 4 quarters; a counter-offer reopens the deal with
    new terms for the other side to answer.
65. **Emissions credit for deals.** The host's real emissions already show the cut (its 1:1
    credit). The financier scores 0.75 x output x the host's average fossil emission factor at
    signing, every quarter the plant runs. Credit never enters the atmosphere (tested).
66. **Credit market.** Credits come from emissions below a nation's own target path each quarter
    and from any surplus under its fair-share allowance at a stocktake (rare once the 1.5 degC
    budget is spent). They are bought to cover stocktake overshoot (surrendered automatically)
    and score at 0.25. One uniform-price call auction per quarter; one-sided markets drift 5%. A
    nation may only buy or only sell in a quarter.
67. **Stocktake.** The remaining 1.5 degC budget comes from the model's own warming rule (about
    215 Gt from 2025, more than the published ~130 Gt because the model's single warming
    coefficient differs from full climate models), split by share of current global emissions
    and spread evenly to 2050. Overshoot is measured as a share of the nation's 2025 emissions
    over the period; above 5% it costs trust with everyone and, for non-members, brings a
    coalition tariff of 0.1 x the overshoot share (capped at 15%) from club members until the
    next stocktake. Pledges are checked against a straight line from 2025 to the pledged level.
68. **Nation Index, fifth component: climate.** Credit-weighted MtCO2 cut over the game per year
    as a share of 2025 emissions, through a logistic (0.5 = no change). The five components
    weigh 0.2 each.
69. **World Multiplier and endings use 1.5 degC.** M is 1.0 at 1.5 degC and 0.1 at 2.5 degC; a
    "good world" ending needs final warming at or below 1.5 degC. Until M4b adds cooling
    technology, no run reaches it.
70. **Best-deal bonus** (5 points) goes to both parties of the deal with the most credited cut.
71. **AI diplomacy.** Each quarter an AI nation also considers: answering proposals (accept if
    the capacity's estimated value, net of payments, clears a bar that rises with hard-currency
    payments over FX reserves and falls with trust; counter at 70% of the rate if close);
    matching tariffs placed on it (fossil defenders and opportunists) or lifting its own when
    the other side lifts; joining the club when eligible; offering one deal a year to its most
    trusted high-emitting partner, sized so the host's payments on all deals stay within half
    its yearly capital income; and buying or selling credits against a personality value
    ($15-80/t). AI hosts keep six months of deal payments in hand before spending.
72. **`deal_maker` bot** now offers a yearly solar credit deal, accepts affordable offers, opens
    talks, joins the club when eligible, and pledges.
73. **Simultaneous moves can clash.** If another nation accepts your deal in the same quarter,
    the financier's capital may be gone before its own actions resolve; those actions are
    rejected and logged.

## Open questions

- **Difficulty ordering (for M5).** Early bot runs score the US below India and Vietnam on the
  same bot, the reverse of the design intent, because each Nation Index component is relative
  to the nation's own start. Tune in the balance pass.
- **AI overshoot (for M5).** Cheap clean energy leads several low-ambition nations to cut far
  past their target paths, and the US and China drop sharply in the late 2040s
  (docs/CALIBRATION.md, "AI world").
- **All-or-nothing fair share (for M5).** The 1.5 degC budget is spent by about 2030, after
  which every nation overshoots a zero allowance; consider judging against target paths or
  peers instead.
- **Resolved in M2:** BAU builder vs. player builds (market runs for everyone), frozen-trend
  BAU (market follows cost), and slots (2 + 1).
