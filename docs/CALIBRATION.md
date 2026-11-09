# Calibration

How the business-as-usual (BAU) world compares with real data and published projections.
Regenerate the tables with `python -m sim.report bau`. The loose checks below are enforced by
`tests/test_calibration.py`.

## Method

- **Starting point.** Every nation starts from its 2024 energy mix (Energy Institute via OWID;
  Nigeria derived, see SOURCES.md) and 2025 GDP and population (IMF WEO). Capacity is sized so
  that dispatch at t=0 reproduces the 2024 mix exactly, and each nation's own 2024 emission
  factors reproduce its 2024 fossil-fuel CO2 exactly.
- **World total.** The rest of the world, land use, and cement/flaring/other CO2 are exogenous
  paths set so that the 2025 global total matches the Global Carbon Budget.
- **What BAU means.** No nation takes any action; only the market builder runs (M2). It builds
  to meet demand, splitting new capacity half by the nation's 2019-2024 build trend and half by
  levelized cost (carbon price, learning curves, a rising system cost for wind and solar). Old
  capacity retires at 1/lifespan or the observed 2019-2024 decline rate. GDP grows at IMF
  projected rates converging toward a long-run rate. It is a "nobody acts" reference.
- **Calibration knob.** `market.cost_weight` (0.5) sets how much the market follows cost
  rather than the recent trend. At 0 (M1's frozen trend) BAU energy CO2 reaches ~42 Gt by 2049,
  about 10% above the IEA Current Policies Scenario; at 0.5 it is ~36 Gt, about 6% below.

## Results (seed 1)

No nation takes actions and AI is off; the market, trade and stocktakes still run. Since M6 both
calibration worlds (BAU and AI) run without seeded shocks, so they check the deterministic core;
the balance report plays with disasters and disruptions on.

### World

| Metric | 2025 | 2030 | 2040 | 2049 |
|---|---|---|---|---|
| Global CO2 (Gt/yr) | 43.6 | 41.8 | 39.4 | 38.7 |
| Warming, end of year (degC) | 1.39 | 1.53 | 1.77 | 1.96 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.77 | 1.7 | 363 | 321 | 256 | 218 | 84% | 48% | 0.0% |
| BRA | 2.31 | 3.65 | 1.9 | 435 | 432 | 427 | 476 | 48% | 29% | 0.0% |
| CAN | 2.34 | 3.27 | 1.4 | 502 | 446 | 359 | 303 | 66% | 49% | 0.0% |
| CHN | 20.12 | 43.60 | 3.3 | 11,531 | 11,286 | 10,720 | 10,169 | 79% | 54% | 0.0% |
| EUU | 21.49 | 28.70 | 1.2 | 2,288 | 1,882 | 1,223 | 858 | 66% | 35% | 0.0% |
| GBR | 4.05 | 5.48 | 1.3 | 300 | 247 | 168 | 121 | 72% | 44% | 0.0% |
| IDN | 1.49 | 3.85 | 4.0 | 788 | 909 | 1,235 | 1,652 | 88% | 57% | 0.0% |
| IND | 4.08 | 14.49 | 5.4 | 3,036 | 3,387 | 4,222 | 4,997 | 88% | 59% | 0.0% |
| JPN | 4.47 | 5.19 | 0.6 | 926 | 811 | 612 | 471 | 82% | 54% | 0.0% |
| MEX | 1.85 | 2.62 | 1.5 | 428 | 393 | 338 | 304 | 89% | 57% | 0.0% |
| NGA | 0.30 | 0.63 | 3.2 | 113 | 115 | 130 | 156 | 94% | 55% | 0.0% |
| RUS | 2.59 | 3.06 | 0.7 | 1,674 | 1,620 | 1,512 | 1,421 | 87% | 66% | 0.0% |
| SAU | 1.30 | 2.41 | 2.6 | 655 | 645 | 622 | 604 | 98% | 70% | 0.0% |
| USA | 31.27 | 48.75 | 1.9 | 4,629 | 4,019 | 3,101 | 2,542 | 79% | 49% | 0.0% |
| VNM | 0.52 | 1.63 | 4.9 | 330 | 385 | 554 | 814 | 76% | 41% | 0.0% |
| ZAF | 0.43 | 0.58 | 1.2 | 433 | 392 | 314 | 260 | 94% | 59% | 0.0% |

## Against references

| Check | Reference | Model | Verdict |
|---|---|---|---|
| Global CO2 2025, incl. land use | ~43 Gt (GCB: fossil 38.6 + land use ~4.6, 2024) | 43.6 Gt | Match. Land use uses the 2015-2024 mean (5.0 Gt), slightly above 2024. |
| Nation fossil CO2 at t=0 | Each nation's 2024 GCB value | Exact (by construction) | Match. 2025 annual values differ slightly due to growth and seasonality. |
| Warming rate 2025-2035 | 0.27 [0.2-0.4] degC/decade (Forster et al. 2025) | 0.27 degC/decade | Match. The clean-air aerosol trend was set for this. |
| Energy CO2 2049 | ~38 Gt, roughly flat (IEA WEO 2025 Current Policies) | ~33 Gt, slowly falling | About 13% low: since M4b the rest of the world decarbonises with the 16 nations. |
| Warming 2049 | Passes 2 degC around 2050 (IEA WEO 2025 Current Policies) | 1.96 degC | Consistent. |
| Real GDP growth 2025-2030 | IMF WEO projections | Within 0.5 pp for every nation | Match. |
| Energy shortfall | None expected without shocks | Below 1% for every nation, every quarter | Match. |

## Known deviations

1. **Fast-growing coal users still grow emissions.** India rises about 1.7x by 2049, Indonesia
   2.1x and Vietnam 2.8x, because demand grows fast and half the market still follows the
   2019-2024 coal-heavy trend. China declines about 10% by 2049. The IEA has China falling
   faster.
2. **EU, US, UK and Japan decline steadily** (roughly -45% to -60% by 2049), led by the market
   choosing wind, solar and gas and by coal retiring at the observed 2019-2024 rate.
3. **Fossil exporters lose revenue.** Russia's export revenue falls about 33% and Saudi
   Arabia's about 42% by 2049 as world use of their fuels falls; their own mix changes slowly.
4. **Wind and solar saturate.** They can serve at most the electrifiable share of demand
   (40% in 2025 rising to 70% by 2050, placeholder) and their system cost rises with the square
   of their share, so the market turns to other sources as they grow.
5. **GDP 2025 annual figures are ~1% above IMF 2025**, because the IMF 2025 value is used as the
   2025Q1 level and growth continues through the year.

## AI world (M3, with M4 diplomacy and M4b levers)

All 16 nations played by the AI (`python -m sim.report ai`). Each follows an assumed target path
(data/targets.yaml, a design assumption from its policy stance, not a real pledge) as strongly as
its personality says, trades, finances deals, joins the carbon club, trades credits, and since
M4b also builds factories, abates methane, funds forests and builds carbon removal.

### World

| Metric | 2025 | 2030 | 2040 | 2049 |
|---|---|---|---|---|
| Global CO2 (Gt/yr) | 42.0 | 33.1 | 22.5 | 6.4 |
| Warming, end of year (degC) | 1.40 | 1.50 | 1.59 | 1.65 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.81 | 1.7 | 346 | 217 | 82 | 21 | 81% | 25% | 0.0% |
| BRA | 2.31 | 3.69 | 2.0 | 417 | 327 | 216 | -66 | 46% | 12% | 0.0% |
| CAN | 2.34 | 3.21 | 1.3 | 480 | 304 | 206 | 37 | 64% | 22% | 0.0% |
| CHN | 20.12 | 43.42 | 3.3 | 11,296 | 9,850 | 7,143 | 706 | 77% | 6% | 0.0% |
| EUU | 21.40 | 29.42 | 1.3 | 2,184 | 1,345 | 419 | -692 | 64% | 1% | 0.0% |
| GBR | 4.03 | 5.31 | 1.2 | 290 | 116 | 61 | -80 | 70% | 6% | 0.0% |
| IDN | 1.49 | 3.90 | 4.1 | 760 | 685 | 699 | 620 | 87% | 39% | 0.0% |
| IND | 4.08 | 14.78 | 5.5 | 2,976 | 2,771 | 2,682 | 401 | 87% | 6% | 0.0% |
| JPN | 4.47 | 5.33 | 0.7 | 895 | 571 | 182 | 61 | 80% | 7% | 0.0% |
| MEX | 1.85 | 2.72 | 1.6 | 417 | 290 | 76 | 23 | 88% | 6% | 0.0% |
| NGA | 0.30 | 0.62 | 3.1 | 109 | 87 | 64 | 14 | 93% | 6% | 0.0% |
| RUS | 2.59 | 2.90 | 0.5 | 1,630 | 1,212 | 1,150 | 878 | 86% | 45% | 0.0% |
| SAU | 1.30 | 2.28 | 2.4 | 638 | 463 | 317 | 261 | 97% | 43% | 0.0% |
| USA | 31.27 | 49.55 | 1.9 | 4,480 | 3,251 | 1,314 | 132 | 77% | 6% | 0.0% |
| VNM | 0.51 | 1.67 | 5.0 | 316 | 321 | 273 | 243 | 74% | 16% | 0.0% |
| ZAF | 0.43 | 0.54 | 0.9 | 422 | 319 | 250 | 106 | 92% | 30% | 0.0% |

Warming reaches 1.65 degC in 2049 (seed 1, no shocks, M9), against 1.96 degC with no
action. By 2049 methane is down to
about half its 2025 level, aerosols (and their cooling) are nearly gone, the forest fund has
turned land use slightly negative, and AI nations run about 3.5 Gt/yr of carbon removal.

| Nation | Personality | Target path 2049 | Actual 2049 |
|---|---|---|---|
| AUS | cautious_follower | 0.21 | -0.30 |
| BRA | cautious_follower | 0.31 | 0.26 |
| CAN | cautious_follower | 0.21 | 0.13 |
| CHN | opportunist | 0.43 | -0.00 |
| EUU | green_leader | 0.05 | 0.04 |
| GBR | green_leader | 0.06 | -0.18 |
| IDN | opportunist | 0.56 | 0.48 |
| IND | opportunist | 1.00 | 0.53 |
| JPN | cautious_follower | 0.11 | 0.19 |
| MEX | fossil_defender | 0.60 | 0.33 |
| NGA | fossil_defender | 0.73 | 0.76 |
| RUS | fossil_defender | 0.73 | 0.48 |
| SAU | fossil_defender | 0.66 | 0.43 |
| USA | opportunist | 0.60 | -0.30 |
| VNM | opportunist | 0.32 | 0.61 |
| ZAF | cautious_follower | 0.31 | 0.25 |

Target paths and diplomacy below are from the M5 run (with shocks); the M6 changes moved
warming by 0.01 degC.

Diplomacy in that run:

- **Deals (M5):** 136 signed: 87 equipment on credit, 26 climate loans, 33 equity deals (10 of
  which failed when hosts became unreliable); none defaulted.
- **Carbon club:** 7 members (Brazil, Canada, EU, UK, Indonesia, Vietnam, South Africa).
- **Coalition tariffs** at the end: India 6.7%, Nigeria 6.4%, Russia 4.3%, Saudi Arabia 4.3%,
  Mexico 3.6%, China 2.7%, US 1.9%, Japan 0.8%.
- **Credit market:** 6.2 Gt issued, 1.5 Gt traded, ending at $40/t.

## All-out world (M4b)

To check that "colder than 2025" is reachable, `tests/test_climate.py` scripts every nation to go
all-out from 2025: maximum tax, the cheapest clean source every quarter, methane abatement,
electrification, a carbon price rising to $300/t, forest funding, and carbon removal from 2032.
Warming peaks at about 1.56 degC in the mid-2030s and ends 2049 at about 1.34 degC, just below
2025's 1.36 degC. It takes near-zero emissions by the late 2030s, methane cut by half, a
land-use sink, and about 33 Gt/yr of carbon removal by 2049. **That removal scale is far beyond
current physical estimates** (around 10 Gt/yr is an optimistic mid-century figure); it is a game
design choice so that excellent global play can cool the planet (decided 2026-11-08).

## Balance (M5, M6)

The acceptance criteria are measured in `docs/BALANCE_REPORT.md` (`python -m sim.balance`).
After the M6 mechanics pass all seven pass on 3 seeds. M6 changes, in short:

- **Scoring.** The absolute income score is a straight line in log income (0.05x to 8x the
  16-nation average) instead of an S-curve that was flat for poor nations. Weights moved toward
  the economy: relative income 0.25 -> 0.35, relative climate 0.15 -> 0.1, absolute income
  0.3 -> 0.4, absolute clean share and emissions 0.15 -> 0.075 each. Bonuses 3 -> 2 points.
  The World Multiplier falls in a straight line (was quadratic), so a 1.65 degC world pays 0.87
  instead of 0.98: climate counts mainly through the shared multiplier.
- **World difficulty.** Disasters are four times as frequent at half the cost each, grow more
  severe with warming, and their frequency multiplier is 0.25 / 1 / 2. Hard also doubles climate
  damage and lengthens factory disruptions. Balanced-bot score: easy 64.7, normal 61.9,
  hard 60.3 (was 73.7 / 73.5 / 73.3). Baseline growth is credited the expected disaster loss at
  2025 warming, so only losses above today's count.
- **Blackouts** erode stability directly (`politics.stability_shortfall_hit`).
- **Criterion 7** now checks that reckless play is removed from office, at the ballot box or by
  collapse, more than any other strategy: it loses 80% of the elections it contests (others
  16-24%). It rarely causes blackouts, because political capital limits closures and the market
  backfills, so Fallen Government stays rare.

M8 (6 seeds) keeps the M7 picture: 6 of 7 criteria pass and viable strategies stays TUNE.
Steady bots complete 92% (balanced) and 89% (deal maker) of games. A higher factory cost was
tried and reverted because China's AI then lost its 2032 vote in most seeds (ASSUMPTIONS item
127). In the AI world, offers ranked by growth as well as emissions send more deals to India,
whose 2049 CO2 falls from about 2.0 to 0.6 Gt; global CO2 in 2049 falls from 12.9 to 9.9 Gt
and warming ends at 1.65 degC.

M9 (6 seeds) again passes 6 of 7, viable strategies TUNE; balanced and deal-maker bots complete
92% of games. In the AI world, climate loans that now build real plants, deals sized to what
hosts can take, and the market's 3% reserve take global CO2 in 2049 from 9.9 to 6.4 Gt; China
ends at 0.7 Gt and India at 0.4 Gt, but warming still ends at 1.65 degC. No nation has a
blackout above 0.1% (Vietnam had 4-5% before the reserve, item 146).

## Placeholders that matter most for balance

Climate damage coefficient, the growth drag weights (shortfall, price, trade, debt, stranded
assets), the capital share of GDP, the long-run growth rule, carbon prices, climate
vulnerability, tech costs and learning rates, the market cost weight, the electrifiable share and
clean ceiling, the AI personality weights, the target paths, and all scoring constants. All are tagged `status: placeholder` in `data/`.
