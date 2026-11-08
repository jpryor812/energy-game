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

No nation takes actions and AI is off; the market, trade and stocktakes still run.

### World

| Metric | 2025 | 2030 | 2040 | 2049 |
|---|---|---|---|---|
| Global CO2 (Gt/yr) | 43.6 | 42.7 | 41.3 | 41.3 |
| Warming, end of year (degC) | 1.39 | 1.53 | 1.80 | 2.04 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.73 | 1.6 | 363 | 321 | 254 | 216 | 84% | 48% | 0.0% |
| BRA | 2.31 | 3.61 | 1.9 | 435 | 433 | 421 | 468 | 48% | 29% | 0.0% |
| CAN | 2.34 | 3.22 | 1.3 | 502 | 446 | 355 | 298 | 66% | 49% | 0.0% |
| CHN | 20.12 | 42.93 | 3.2 | 11,531 | 11,280 | 10,590 | 10,013 | 79% | 53% | 0.0% |
| EUU | 21.49 | 27.99 | 1.1 | 2,288 | 1,879 | 1,197 | 846 | 66% | 35% | 0.0% |
| GBR | 4.05 | 5.38 | 1.2 | 300 | 246 | 167 | 120 | 72% | 44% | 0.0% |
| IDN | 1.49 | 3.80 | 4.0 | 788 | 908 | 1,224 | 1,630 | 88% | 57% | 0.0% |
| IND | 4.08 | 14.26 | 5.4 | 3,036 | 3,386 | 4,177 | 4,919 | 88% | 59% | 0.0% |
| JPN | 4.47 | 5.12 | 0.6 | 926 | 811 | 606 | 466 | 82% | 54% | 0.0% |
| MEX | 1.85 | 2.57 | 1.4 | 428 | 393 | 333 | 298 | 89% | 57% | 0.0% |
| NGA | 0.30 | 0.63 | 3.1 | 113 | 115 | 130 | 154 | 94% | 55% | 0.0% |
| RUS | 2.59 | 3.04 | 0.7 | 1,674 | 1,620 | 1,502 | 1,406 | 87% | 66% | 0.0% |
| SAU | 1.30 | 2.38 | 2.6 | 655 | 645 | 617 | 597 | 98% | 70% | 0.0% |
| USA | 31.27 | 48.36 | 1.8 | 4,629 | 4,018 | 3,088 | 2,525 | 79% | 49% | 0.0% |
| VNM | 0.52 | 1.57 | 4.7 | 330 | 384 | 532 | 784 | 76% | 41% | 0.0% |
| ZAF | 0.43 | 0.57 | 1.2 | 433 | 392 | 311 | 257 | 94% | 60% | 0.0% |

## Against references

| Check | Reference | Model | Verdict |
|---|---|---|---|
| Global CO2 2025, incl. land use | ~43 Gt (GCB: fossil 38.6 + land use ~4.6, 2024) | 43.6 Gt | Match. Land use uses the 2015-2024 mean (5.0 Gt), slightly above 2024. |
| Nation fossil CO2 at t=0 | Each nation's 2024 GCB value | Exact (by construction) | Match. 2025 annual values differ slightly due to growth and seasonality. |
| Warming rate 2025-2035 | 0.27 [0.2-0.4] degC/decade (Forster et al. 2025) | 0.28 degC/decade | Match. The non-CO2 multiplier was set for this. |
| Energy CO2 2049 | ~38 Gt, roughly flat (IEA WEO 2025 Current Policies) | ~36 Gt, slowly falling | About 6% low. |
| Warming 2049 | Passes 2 degC around 2050 (IEA WEO 2025 Current Policies) | 2.04 degC | Consistent. |
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

## AI world (M3, with M4 diplomacy)

All 16 nations played by the AI (`python -m sim.report ai`). Each follows an assumed target path
(data/targets.yaml, a design assumption from its policy stance, not a real pledge) as strongly as
its personality says, and since M4 also trades, tariffs, finances deals, joins the carbon club and
trades carbon credits.

### World

| Metric | 2025 | 2030 | 2040 | 2049 |
|---|---|---|---|---|
| Global CO2 (Gt/yr) | 43.2 | 37.1 | 32.8 | 22.4 |
| Warming, end of year (degC) | 1.39 | 1.52 | 1.74 | 1.90 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.72 | 1.6 | 353 | 210 | 96 | 106 | 83% | 26% | 0.0% |
| BRA | 2.31 | 3.53 | 1.8 | 427 | 318 | 228 | 56 | 47% | 6% | 0.0% |
| CAN | 2.34 | 3.07 | 1.1 | 491 | 281 | 129 | 53 | 65% | 12% | 0.0% |
| CHN | 20.12 | 42.62 | 3.2 | 11,391 | 9,712 | 6,950 | 900 | 79% | 6% | 0.0% |
| EUU | 21.44 | 28.74 | 1.2 | 2,260 | 1,301 | 478 | 93 | 66% | 6% | 0.0% |
| GBR | 4.04 | 5.20 | 1.1 | 298 | 113 | 45 | 11 | 72% | 6% | 0.0% |
| IDN | 1.49 | 3.77 | 3.9 | 768 | 673 | 569 | 335 | 88% | 17% | 0.0% |
| IND | 4.08 | 14.24 | 5.3 | 2,999 | 2,728 | 2,610 | 2,600 | 88% | 39% | 0.0% |
| JPN | 4.46 | 5.02 | 0.5 | 917 | 510 | 387 | 42 | 82% | 6% | 0.0% |
| MEX | 1.85 | 2.55 | 1.3 | 422 | 282 | 146 | 115 | 89% | 33% | 0.0% |
| NGA | 0.30 | 0.58 | 2.8 | 107 | 63 | 82 | 75 | 94% | 40% | 0.0% |
| RUS | 2.59 | 2.62 | 0.1 | 1,604 | 1,308 | 1,011 | 883 | 87% | 56% | 0.0% |
| SAU | 1.30 | 2.12 | 2.1 | 625 | 391 | 309 | 208 | 98% | 40% | 0.0% |
| USA | 31.27 | 48.29 | 1.8 | 4,553 | 3,226 | 3,518 | 358 | 79% | 6% | 0.0% |
| VNM | 0.51 | 1.59 | 4.8 | 321 | 314 | 324 | 150 | 75% | 11% | 0.0% |
| ZAF | 0.43 | 0.51 | 0.8 | 425 | 303 | 117 | 119 | 94% | 32% | 0.0% |

Energy CO2 in 2049 is about 16 Gt: between the no-action baseline (~36 Gt) and the IEA's
announced-pledges level for 2050 (roughly 12 Gt, from memory of WEO scenarios, not re-checked).
Warming reaches 1.90 degC, against 2.04 degC with no action.

| Nation | Personality | Target path 2049 | Actual 2049 |
|---|---|---|---|
| AUS | cautious_follower | 0.21 | 0.28 |
| BRA | cautious_follower | 0.31 | 0.11 |
| CAN | cautious_follower | 0.21 | 0.10 |
| CHN | opportunist | 0.43 | 0.07 |
| EUU | green_leader | 0.05 | 0.04 |
| GBR | green_leader | 0.06 | 0.03 |
| IDN | opportunist | 0.56 | 0.13 |
| IND | opportunist | 1.00 | 0.86 |
| JPN | cautious_follower | 0.11 | 0.04 |
| MEX | fossil_defender | 0.60 | 0.27 |
| NGA | fossil_defender | 0.73 | 0.65 |
| RUS | fossil_defender | 0.73 | 0.52 |
| SAU | fossil_defender | 0.66 | 0.31 |
| USA | opportunist | 0.60 | 0.07 |
| VNM | opportunist | 0.32 | 0.45 |
| ZAF | cautious_follower | 0.31 | 0.27 |

Diplomacy in this run:

- **Deals:** 77 signed (50 completed, 27 still paying), none defaulted; 129 offers expired
  unanswered and 1 was countered.
- **Carbon club:** grew from the EU to 10 members (Australia, Brazil, Canada, EU, UK, Indonesia,
  Japan, US, Vietnam, South Africa).
- **Coalition tariffs** at the end: India 3.9%, Nigeria 6.9%, Russia 5.1%, Mexico 2.7%, Saudi
  Arabia 2.7%: the non-members that overshoot.
- **Credit market:** 149 Gt of credits issued (mostly for beating target paths), 22 Gt traded,
  price between ~$20 and ~$50/t, ending at $22.5/t.
- **No AI starts a trade war:** AI nations only match tariffs placed on them, so with a clean
  slate none appear.

What to look at in M5:

- **The 1.5 degC budget is gone by about 2030** in every run, so from then on every nation
  overshoots its (zero) allowance at each stocktake, and consequences scale with emissions
  relative to 2025. This works as pressure but makes "fair share" an all-or-nothing test.
- **Several nations overshoot their path** (Saudi Arabia, Mexico, the US, China), because cheap
  wind and solar pay for themselves through lower energy prices.
- **A late-2040s drop for the US and China** as clean energy gets cheap and the clean ceiling
  rises; many nations finish near the 5% fossil floor.
- **India stays high** (its path allows growth) and pays coalition tariffs.

## Placeholders that matter most for balance

Climate damage coefficient, the growth drag weights (shortfall, price, trade, debt, stranded
assets), the capital share of GDP, the long-run growth rule, carbon prices, climate
vulnerability, tech costs and learning rates, the market cost weight, the electrifiable share and
clean ceiling, the AI personality weights, the target paths, and all scoring constants. All are tagged `status: placeholder` in `data/`.
