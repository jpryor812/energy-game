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
66. **Credit market.** Each quarter a nation earns credits for emissions below the 1.5 degC
    pathway applied to its own 2025 emissions (item 67). Credits are bought to cover stocktake
    overshoot (surrendered automatically) and score at 0.25. One uniform-price call auction per
    quarter; one-sided markets drift 5%. A nation may only buy or only sell in a quarter.
    (Changed 2026-11-08: credits first came from beating each nation's own target path, which
    was too lenient and flooded the market.)
67. **Stocktake against a 1.5 degC pathway** (decided with the user, 2026-11-08). Every nation's
    allowance follows the same proportional pathway from its own 2025 emissions: 55% by 2030, 35%
    by 2035, 20% by 2040, zero in 2050 (placeholders shaped like the IPCC AR6 1.5 degC
    pathways). Overshoot is measured as a share of the nation's 2025 emissions over the period;
    above 5% it costs trust with everyone and, for non-members, brings a coalition tariff of
    0.1 x the overshoot share (capped at 15%) from club members until the next stocktake. Pledges
    are checked against a straight line from 2025 to the pledged level. The first version split
    the remaining 1.5 degC carbon budget (~215 Gt in this model) by emissions share; it was spent
    by about 2030, after which every nation overshot a zero allowance and the test was
    all-or-nothing. The remaining budget is still reported in each stocktake log.
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

## M4b part 1: domestic economy and elections

74. **Taxes.** A discretionary tax change of -1 to +3 points of GDP (decided 2026-11-08) adds
    that share of GDP to capital each year, drags growth by 0.15 pp per point (a cut boosts it),
    costs 0.02 approval per point raised (once) and 3 political capital per point raised.
75. **Tax credits** are paid as foregone revenue each quarter, not from capital up front:
    production credits ($/GJ of a source's output) lower its dispatch cost, its levelized cost
    and the delivered energy price; manufacturing credits (share of factory sales) raise a
    nation's world market share as capacity x (1 + credit)^2.
76. **Factories.** Each nation has solar, wind and battery factory capacity (T$/yr of output),
    starting from 2025 manufacturing shares x an approximate world capacity (0.15, 0.10, 0.10
    T$/yr). Market shares follow capacity; the rest of the world keeps its 2025 capacity.
    Factories cost 0.5 T$ per T$/yr, take 8 quarters, and do not retire (simplification).
    World equipment demand comes from completed builds, so nobody runs short of supply.
77. **Domestic content** forces a nation's own share of its equipment purchases up to the rule;
    if its factories cannot make that much, builds cost up to 0.5 x the shortfall more.
78. **Jobs** (millions): fossil supply = 0.0359/EJ of fossil production (IEA World Energy
    Employment 2025: 18.4 million fossil supply jobs in 2024); clean operations 0.08/EJ of
    non-fossil supply; construction 0.43 per EJ/yr completed per year and manufacturing 36 per
    T$/yr of factory sales, both set so each is ~10 million jobs in the model's 2025 world.
    Build rate and factory sales are smoothed (half the gap each quarter) so job counts do not
    jump with lumpy deliveries; the first year is seeded from projects already under way.
79. **Jobs move approval** each quarter by 3 x the weighted change as a share of the workforce
    (half the population); fossil losses count double, softened by up to 70% by retraining
    (half at a stock of 0.5% of GDP).
80. **Electrification programmes** raise a nation's wind/solar and clean ceilings by up to 20
    points (half at 2% of GDP spent).
81. **Elections** (decided 2026-11-08): the player's nation votes at the end of 2028, 2032, 2036,
    2040, 2044 and 2048. The vote is purely economic: 0.53 incumbency + 0.03 per pp/yr of
    growth above baseline over the term + 2 x weighted job change / workforce - 0.1 x energy
    price rise - 2 x tax raised + a seeded normal swing (sd 0.02). Win at 50%. Losing hands the
    nation to the AI (its default personality) for one term; the player returns at the next
    election date without a vote. Approval is not in the vote. *Superseded in M7 (item 112):
    losing ends the game, and incumbency is 0.56.*
82. **Opposition terms** keep everything the AI does: carbon prices, subsidies, taxes and deals
    carry over when the player returns. *Removed in M7.*
83. **AI and the new levers.** AI nations consider factories (valued by extra export growth) and
    electrification (when within 5 points of their clean ceiling). Taxes, tax credits, domestic
    content and retraining are player levers for now: AI leaders face no elections.
84. **Stage order.** An "elections" stage runs after the stocktake and before the scoring
    snapshot (the build doc's pipeline had no election stage).

## M4b part 2: climate and cooling

85. **Warming in two parts.** Long-lived: TCRE (0.45 degC per 1000 GtCO2) x cumulative CO2 since
    2025, with no multiplier. Short-lived: methane (0.5 degC in 2025) x a methane index that
    relaxes toward current methane emissions with a 12-year lifetime; minus aerosol cooling
    (0.25 degC in 2025, a modest strength by decision) x an aerosol index that follows coal and
    oil burning and a clean-air trend (-3.5%/yr, set so business-as-usual warming stays at
    ~0.27 degC/decade); plus 0.05 degC from other gases, held constant. 2025 still starts at
    1.36 degC. This replaces the M1 non-CO2 multiplier.
86. **Methane.** 35% of human methane is fossil (follows world fossil production), the rest
    follows population. A nation's abatement spending cuts up to 75% of its fossil methane and
    50% of its farming and waste methane (half at 0.2% of GDP).
87. **Carbon removal** is a capacity (MtCO2/yr) with learning (20% per doubling) and a cost floor
    at 40% of its 2025 cost (~$150/t removed with energy). Its energy (8 GJ/t) is added to the
    nation's demand, so a fossil-heavy grid gives back part of the removal. It counts as a real
    cut for score and stocktake. Carbon-price revenue is charged on CO2 emitted before removal.
88. **Forest fund.** Any nation can pay into one global fund that cuts land-use CO2 by up to 150%
    (land becomes a net sink), half at 0.5 T$. Payers earn financed credit (0.75) for the avoided
    land-use CO2, in proportion to what they paid.
89. **The rest of the world responds:** its energy CO2 is scaled by the 16 nations' carbon
    intensity of energy relative to 2025 (clean technology spreads).
90. **"Colder than 2025" is reachable but extreme** (decided 2026-11-08): an all-out world ends
    2049 just below 1.36 degC (tested), but only with carbon removal of ~33 Gt/yr, far beyond
    current physical estimates. The AI world ends at ~1.66 degC.
91. **AI climate levers.** AI nations consider methane abatement (valued as CO2-equivalent: the
    steady-state warming avoided spread over 20 years), carbon removal and the forest fund, and
    judge spare capacity at the seasonal peak before retiring plants.

## M5: last deal types, difficulty, scoring layers, balance

Decisions made with the user on 2026-11-08 are in docs/DESIGN.md ("Decided 2026-11-08 (M5
planning)").

92. **Equity-for-energy:** the investor builds a plant and takes a share of its operating margin
    (host energy price minus the plant's running cost) on normal output, paid in local currency.
    Each quarter the plant may fail or be seized (seeded): 0.4% base, raised by host instability,
    a fall in its FX reserves, its distrust of the investor and recent defaults. A failure shuts
    the plant (capacity lost) and costs trust both ways.
93. **Climate loans** lend cash, assumed spent on the named clean source (the model cannot
    enforce it); repaid like equipment on credit from the next quarter. AI green leaders offer
    them at 2 points below the commercial rate; opportunists offer equity (asking half the
    margin); others offer equipment on credit.
94. **World difficulty** (easy, normal, hard) stretches the stocktake pathway in time so it
    reaches net zero in 2060, 2050 or 2045, and scales climate disasters and factory disruptions
    x0.5, x1, x1.5. Chosen per run (`--difficulty`); normal by default.
95. **Climate disasters** (seeded): chance per quarter 0.03 x (warming above 1.0 degC) x
    vulnerability x difficulty; severity 0.5-1.5; a 1% GDP loss (cut by adaptation), 5% of one
    source's capacity destroyed and 0.03 approval lost for an average one.
96. **Factory disruptions** (seeded): 1% chance per quarter per factory line x difficulty; half
    its output lost for 4-8 quarters; buyers shift supplier and pay 0.3 x the world share
    disrupted (outside their own factories) on equipment meanwhile.
97. **Scoring layers.** Score = (0.5 absolute + 0.5 relative x country difficulty) x World
    Multiplier + absolute bonuses + relative bonuses x difficulty (easy 1.0, easy-to-medium 1.1,
    medium 1.15, hard 1.3). Absolute index weights: income 0.3, clean share 0.15, emissions per
    person 0.15, security 0.2, approval 0.2 (tuned from equal weights so economic outcomes balance
    climate ones). Relative weights: income 0.25, climate 0.15, others 0.2. Bonuses 3 points each.
    Rank for endings uses the combined index.
98. **Clean competitiveness** (relative index) is now the nation's share of world clean-tech
    factory capacity against 2025, as the design doc describes, instead of clean capacity built
    at home, which double-counted the climate component and made all-clean play dominant.
99. **Tuning for balance:** energy-price drag 0.05 -> 0.15; shortfall approval hit 2 -> 6;
    stability follows approval at 60%/yr (was 25%); construction jobs saturate at 3% of the
    workforce (build waves had produced 160 million US construction jobs and toppled AI-run
    governments); the market plans power for carbon removal under construction, and AI keeps
    removal's energy below 25% of demand.
100. **Fossil ban** (`set_fossil_ban`, 10 political capital): the private market stops building
     fossil plants; with the clean ceiling, demand growth can then outrun supply. The reckless
     test bot uses it.
101. **Balance harness** (`python -m sim.balance --workers N`): runs 6 playable nations x 6 bots
     x 3 seeds, a world-difficulty comparison, and a free-rider scenario where every nation plays
     all_fossil, then writes docs/BALANCE_REPORT.md. Thresholds (5% for viable strategies, 30%
     for reckless falls) are report settings. Criterion 4 is checked on the absolute index and
     passes with 3 of 4 scripted bots; criterion 5's short-term gain is measured on N's economic
     components (both changes noted in docs/BUILD_SIM_V0.md).
102. **Parallel runs** are independent and deterministic; results come back in job order, so
     they do not depend on the number of workers (tested).

## M6: mechanics pass

103. **Absolute income** is a straight line in log income per person from 0.05x to 8x the
     16-nation average (`scoring.abs_income_low`, `abs_income_high`). The M5 S-curve was flat
     for poor nations, so a 9% income loss cost India almost nothing while clean share swung 30
     points.
104. **Scoring weights move toward the economy:** relative income 0.25 -> 0.35, relative
     climate 0.15 -> 0.1, absolute income 0.3 -> 0.4, absolute clean share and emissions
     0.15 -> 0.075 each; all bonuses 3 -> 2 points. Without bonuses India's strategies were
     already within 5%; the clean-gain bonus (x1.3) alone made all-clean its best. Climate now
     counts mainly through the shared World Multiplier.
105. **World Multiplier** falls in a straight line from 1.0 at 1.5 degC to 0.1 at 2.5 degC (was
     quadratic). A 1.65 degC world now pays 0.87 instead of 0.98, so the range where games end
     carries real stakes.
106. **Disasters:** chance 0.12 per quarter per degC above 1.0 degC at vulnerability 1 (was
     0.03), costing 1.5% of GDP on average (was 1%), and more severe by 100% per degC of warming
     since 2025 (`shocks.disaster_warming_growth`). Baseline growth already reflects the average
     loss at 2025 warming, so the growth term credits it back
     (`economy.baseline_disaster_loss`); only losses above today's count.
107. **World difficulty** adds `damage` (climate-damage multiplier: 0.5 / 1 / 2) and
     `disruption_length` (0.75 / 1 / 1.5); disaster frequency is now 0.25 / 1 / 2.
     Balanced-bot score: easy 64.7, normal 61.9, hard 60.3 (M5: 73.7 / 73.5 / 73.3).
108. **Blackouts erode stability directly:** 4.0 stability per year per unit of the shortfall
     growth drag (`politics.stability_shortfall_hit`), on top of the pull toward approval. A
     sustained 40% shortfall topples a government within three years (tested).
109. **Criterion 7 reinterpreted.** Reckless play almost never causes blackouts (political
     capital limits closures and the market backfills with clean power), so it is punished at
     the ballot box: it loses 80% of the elections it contests, against 16-24% for other bots.
     The criterion now passes if reckless play is removed from office more than any other
     strategy and no other bot falls (note in docs/BUILD_SIM_V0.md).
110. **Calibration worlds run without shocks** (`report.without_shocks`), so BAU and AI-world
     checks test the deterministic core; one unlucky disaster should not move a calibration
     band. The balance report plays with shocks on.
111. **Bots check affordability** (`bots.affordable`). The reckless bot splits what is left
     after its first moves between the carbon price and plant closures. Rejected bot actions
     fell from about 1,200 to 39 across the balance grid.

## M7: losing an election ends the game; the text interface

112. **Losing an election ends the game** (decided with the user, 2026-11-08), replacing the
     opposition term. A lost game, Voted Out or Fallen Government, scores `loss_score` (0); the
     formula score at that point is kept as `score_at_exit` for diagnostics. Elections are held
     only for the player's nation.
113. **Incumbency 0.53 -> 0.56**, so steady play usually survives six elections: over 6 seeds
     balanced completes 86% of games, deal_maker 89%, all_fossil 89%, all_clean 53%, reckless
     0%. All-out clean play is electorally risky, mostly through fossil job losses and slower
     growth, as intended.
114. **Balance report** now runs 6 seeds by default, reports expected score (lost games count
     as 0) and completion rates, runs the free-rider comparison without elections so both worlds
     reach 2049, and adds to criterion 7 that steady play completes at least 70% of games.
115. **The AI-only calibration world has no player**, so no elections (`report.ai_world`).
116. **The text interface** (`python -m sim.play`, `sim/session.py`, `sim/view.py`,
     `sim/catalogue.py`) adds no rules: a turn is `turn.step` with the player's actions, and a
     session driven by a bot reproduces `runner.play` (tested). The screen shows resources after
     this quarter's income, because income arrives before actions resolve. It hides AI
     personalities, other nations' plans and the seeded draws; the expected vote leaves out the
     swing and is shown from the second year of a term. Saves refuse to load with changed data
     files.

117. **Interface additions after the pilot playtest** (docs/PLAYTEST_REPORT.md):
     `"amount": "max"` (resolved by the session to the most this quarter's resources allow
     after earlier actions; the move log records the number, so replays are unchanged),
     quarterly notices computed by comparing the world before and after a turn, construction
     listed by arrival quarter, a leaderboard, the vote's expected growth, the clean-power
     integration limits, and a brief screen. None changes the rules.

## M8: mechanics pass after the pilot playtest

118. **Clean share and bonus races use four-quarter averages** (`scoring.annual_clean_share`,
     `scoring.annual_emissions`). The largest-clean-gain bonus switched owner from quarter to
     quarter because seasonal demand changes how much fossil fills the gap. The absolute
     clean-share component uses the same average. The 2025 base is still the first quarter's
     mix (Q1 demand is 3% above average, so gains are very slightly flattered).
119. **Bonus races are shown on the screen** (`scoring.races`): the leader of each race, the
     player's standing, and who claimed first-to-net-zero and when. The pilot's missing
     net-zero bonus was not a bug: Canada reached net zero in 2043Q2, India in 2046Q2.
120. **A fossil ban cancels fossil projects not yet under construction** (start = arrival minus
     build time). The market orders all sources for delivery at its horizon (the slowest build
     time, 32 quarters with nuclear), so coal ordered in 2025 was arriving in 2033. Plants
     already being built finish. Unstarted fossil projects the player ordered are cancelled
     too, without refund (a player who bans fossil after ordering it is rare), and new fossil
     orders are refused under a ban.
121. **The vote averages the tax rise over the term** (`elections.term_tax_rise`). It compared
     only the end-of-term rate with the start, so a rise reversed just before the vote was
     free. Each quarter in office records its rate; saves from before M8 start the average at
     their next quarter.
122. **AI financiers refuse low counter-offers.** A counter must keep at least
     `ai.counter_accept_share` (0.7) of the rate, price or share first asked. This equals the
     AI's own counter factor, so AI-to-AI deals are unchanged; the pilot's counters at 3-5%
     on asks of about 9.5% are now refused.
123. **AI financiers rank hosts by need, including growth** (`ai.host_growth_weight`): trust x
     (emissions intensity + baseline growth, each relative to the 16-nation average), and
     nations with no emissions are no longer skipped. Offers to India no longer stop once it is
     clean. Side effect in the AI world: more deals reach India early, and India's 2049 CO2
     falls from about 2.0 to 0.6 Gt (docs/CALIBRATION.md).
124. **Inbound equity stays good for the host by design.** The host gives up a share of the
     plant's operating margin and carries failure risk; that is foreign direct investment, and
     cheap capacity is the point of attracting it. The exploit was the always-accepted counter
     (item 122).
125. **Storage costs about three times more** (0.05 -> 0.15 T$ per EJ/yr absorbed): shifting
     1 EJ/yr with one daily cycle takes about 760 GWh of batteries, roughly 0.15 T$ at
     $200/kWh installed. A cost floor of 0.35 of the 2025 cost stops learning below about
     $70/kWh. Both unsourced approximate.
126. **Carbon removal learning was already at its floor.** With 2 Mt/yr installed worldwide in
     2025, AI deployment reaches the floor (0.4 of the 2025 cost) within a few years, so the
     pilot saw no further fall. Unchanged; the cost table now marks sources at their floor.
127. **Factory exploit only partly addressed.** `scoring.clean_share_floor` 0.01 -> 0.03. A
     factory cost of 1.0 T$ per T$/yr of output (closer to integrated supply chains) was
     tried and reverted: China then built too few factories to hold its manufacturing jobs and
     the AI and deal-maker bots lost China's 2032 vote in 3-4 of 6 seeds. The pilot's case
     (about 9 points of world share for 0.015 T$) still lifts the clean component a lot;
     left for the playtest round.
128. **Banked slots are capped** at 4 domestic and 4 diplomatic (this quarter's included).
129. **Influence is ten times cheaper** (1,000 per T$): talks cost 0.005 T$ instead of 0.05.
130. **The activity cap costs half the political capital** (50 per unit, so 0.1 costs 5).
131. **Policy effects are shown** (screen line): the share of the fossil-job vote penalty
     retraining removes, the share of the price drag the rebate removes, methane cut shares,
     the activity cap and the pledge's status. No rule changed.
132. **Champion needs 1.6 degC and falling** (decided with the user, 2026-11-08):
     `scoring.good_world_warming` 1.5 -> 1.6, and warming must be lower than 5 years earlier
     (`scoring.falling_years`). Every nation on the most aggressive clean bot peaks at
     1.71 degC and passes 1.5 by 2030, so 1.5 was unreachable. The same "good world" test
     applies to Green but Poor. The World Multiplier still reaches 1.0 only at 1.5 degC.
133. **Capital never stays negative** (playtest round 1). A negative quarterly income (tax cuts,
     tax credits and interest on new debt) could push capital below zero, and the resource
     check then crashed every action, free ones included. Free actions now pass when a
     resource is negative, and a shortfall after income is borrowed as local debt, as all
     other spending already was.
134. **The fossil ban skips factories in the pipeline** (playtest round 1): item 120's
     cancellation crashed on factory entries, which are not energy sources.

## M9: mechanics pass after playtest round 1

135. **Climate loans build the plant** in the host (`deals.activate`): the loan pays for
     `amount / host unit cost` of capacity, queued in the host's pipeline like other deals.
     It used to hand over cash the host need not spend while the lender was credited for the
     plant anyway. AI hosts now count the principal as a real cost.
136. **Factories age out** at 1/`industry.factory_lifespan` a year, in all 16 nations and in
     the rest of the world alike, so shares hold steady unless someone builds.
137. **The clean component scores sales, not capacity** (`scoring.sales_share`): the nation's
     clean-tech equipment sales over the last four quarters as a share of all purchases by
     the 16 nations, against its 2025 share of factory capacity. Idle factories (storage
     lines nobody buys from) no longer score. Purchases are now recorded in the history.
138. **The exported-cut credit winds down** over `credits.exported_cut_lifespan` (25 years),
     as the plants the equipment went into retire; it used to grow forever.
139. **The vote averages energy prices over the term**, like taxes (item 121), so a carbon
     price cut just before the vote counts only for its own quarters.
140. **The vote compares term-average jobs with the previous term's average**
     (`elections.term_jobs`), not one quarter with another. One completion, factory or
     disaster rebuild can no longer swing an election; the screen shows both figures.
141. **First to net zero is judged on four-quarter averages.**
142. **Carbon club members below the minimum price leave** (`diplomacy.enforce_club`), checked
     every quarter; they used to stay at 0 $/t for years.
143. **Deal capacity a nation can host is capped** at `deals.host_capacity_cap` (0.5) x its
     energy demand. Accepting beyond it is refused, and AI financiers size offers to fit.
144. **Rank is on the final score**, bonuses included, so it matches the leaderboard (design
     doc note added). It was the combined index before bonuses.
145. **3 domestic and 2 diplomatic slots a quarter** (the design doc's figures; were 2 and 1),
     banking up to 6 and 4.
146. **The market keeps a 3% reserve and fills near-term gaps.** `market.reserve_margin`
     0 -> 0.03 (the winter peak), and besides orders at its horizon (the slowest build time,
     8 years) it orders sources that build within `market.fast_horizon` (8 quarters) for any
     gap expected by then. Without these, Vietnam's AI had 4-5% peak-quarter blackouts in
     the 2040s once its fossil plants retired and an equity plant failed. The AI's own
     spare-capacity check also caps clean output at the clean ceiling.
147. **`"amount": "max"` is resolved by the engine** when the action resolves, from the
     resources the nation has at that moment, and works for closing less than 1 EJ. The move
     log keeps "max", which replays identically.
148. **Interface additions** (no rule changes): your own open offers with expiry dates, offer
     sizes, room left to host deals, the score's construction (combined index x world
     multiplier + bonuses), the jobs baseline in the election forecast, a notice when you
     leave the carbon club, when a credit sell order finds no buyer, and when a new order
     will arrive after the game ends, clearer stocktake wording (the overshoot share is of
     five years of 2025 emissions, after credits), and build times for grid, storage,
     factories and removal in the action list.

## M10: permitting and zoning reform

149. **Permitting reform** (`set_permitting`, level 0-1, decided with the user 2026-11-09).
     Each source's build time includes a permitting share (data/techs.yaml: grid 0.6,
     wind 0.5, hydro and other renewables 0.4, nuclear and solar 0.35, fossil and removal
     0.3, storage 0.25); reform at level L cuts `permitting.max_cut` (0.75) x L of it. At
     full reform grid takes 7 quarters instead of 12, wind 5 instead of 8. It applies to new
     orders from the player, the market and deals in the nation, fossil plants included
     unless a ban is on. Orders already placed keep their dates. Raising it costs
     `permitting.pc_per_level` (10) political capital per level; lowering is free.
150. **Local opposition** enters the vote (an addition to the purely economic vote, decided
     with the user): reform level x the nation's permitting opposition x the share of energy
     demand completed per year, averaged over the term, x `permitting.vote_weight` (0.4). It
     also costs approval (`permitting.approval_hit`, 0.03 a year per unit of level x
     opposition). Full reform from 2025 costs about 0.008-0.02 of the 2028 vote and 0.03-0.11
     of approval, depending on the nation.
151. **Permitting opposition by nation** (countries.yaml, design assumption set with the user,
     unsourced): EU 1.3, USA 1.0, China 0.6, Russia, India and Vietnam 0.4; others 1.0
     (`permitting.default_opposition`; AI nations do not use reform). It stands for how
     strongly local consultation, legal challenge and project opposition push back.
152. **Reform buys speed, not output.** The market builds the same volume either way, so
     reform does not raise GDP by itself; it helps a player who needs capacity, grid or
     deal plants sooner (curtailment, stocktakes, blackouts).

## Open questions

- **AI overshoot.** Cheap clean energy leads several low-ambition nations to cut far past their
  target paths, and the US and China drop sharply in the late 2040s (docs/CALIBRATION.md, "AI
  world").
- **A recession scores as a climate cut.** Lower GDP lowers emissions, which raises the climate
  and emissions components and offsets part of the income loss. The M6 weights shrink the
  effect but do not remove it; measuring cuts against a nation's own business-as-usual path
  would.
- **The score is weakly sensitive to GDP.** The relative income component is an S-curve on the
  log ratio to baseline (scale 0.1) and most bots sit in its lower half, so a further 20% GDP
  loss costs only about 3-5% of score. This also caps how much world difficulty can matter.
- **Viable strategies under election risk (criterion 3, TUNE).** Counting only completed
  games, several strategies stay close in every nation, but the scripted bots ignore elections,
  so expected scores swing with which seeds they lose (all_clean is voted out in every China
  and India run, through coal job losses). Agent playtests are the better test now.
- **Russia is hard to hold.** The balanced bot completes only half its Russian games: falling
  fossil export revenue drags growth below baseline at elections.
- **No bot world reaches a good world.** Every balance run ends at about 1.62-1.76 degC, so
  endings are almost all Shared Failure or Prosperous but Doomed even with Champion at 1.6 degC
  (M8). Agent playtesting should probe whether players can pull the world under it.
- **Fallen Government is rare by design now.** It needs a sustained blackout or an approval
  collapse; neglect is punished mainly through lost elections.
- **Wind and solar stop being built late.** Their LCOE rises to 11-17 $/GJ once curtailed
  (round 1), above coal; not yet investigated.
- **Cheap first doses** of methane abatement, efficiency and electrification, and strong
  research; not changed.
- **The late game and Champion** are untested since M9's extra slots; the next playtest round
  should check them.
- **Resolved in M9:** climate-loan credit for plants never built, factory capacity scoring
  forever, pre-election price cuts, jobs swinging the vote quarter by quarter, unlimited
  inbound deals, club membership at 0 $/t, a rank that left out bonuses, first to net zero on
  one quarter, and the "max" rejections (items 135-148).
- **Disasters may dominate income** for exposed nations (the pilot took about ten hits of
  1-2.4% of GDP); to be judged across the M8 playtest round.
- **Resolved in M8:** tax timing, always-accepted counters, the flickering clean-gain bonus,
  coal arriving after a ban, banked slots, expensive talks, no late deal offers to clean
  nations, storage dominance, and an unreachable Champion (see items 118-132).
- **Resolved in M7:** losing an election helping (it now ends the game).
- **Resolved in M6:** all-clean dominance in India and Vietnam, weak world difficulty, rejected
  bot actions (1,200 -> 39), and criterion 7 (reinterpreted, item 109).
- **Resolved in M5:** construction-job swings (construction jobs now saturate), the difficulty
  order (checked on the absolute index), and dominant all-clean play in most nations.
- **Resolved in M4:** all-or-nothing fair share (now a 1.5 degC pathway on each nation's own
  emissions).
- **Resolved in M2:** BAU builder vs. player builds (market runs for everyone), frozen-trend
  BAU (market follows cost), and slots (2 + 1).
