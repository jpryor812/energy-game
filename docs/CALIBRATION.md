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
| Global CO2 (Gt/yr) | 43.6 | 42.7 | 41.6 | 41.5 |
| Warming, end of year (degC) | 1.39 | 1.53 | 1.80 | 2.05 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.76 | 1.7 | 363 | 321 | 255 | 217 | 84% | 48% | 0.0% |
| BRA | 2.31 | 3.64 | 1.9 | 435 | 433 | 427 | 472 | 48% | 29% | 0.0% |
| CAN | 2.34 | 3.27 | 1.4 | 502 | 446 | 359 | 302 | 66% | 49% | 0.0% |
| CHN | 20.12 | 43.45 | 3.3 | 11,531 | 11,286 | 10,714 | 10,120 | 79% | 53% | 0.0% |
| EUU | 21.49 | 28.63 | 1.2 | 2,288 | 1,882 | 1,222 | 855 | 66% | 35% | 0.0% |
| GBR | 4.05 | 5.46 | 1.3 | 300 | 247 | 168 | 121 | 72% | 44% | 0.0% |
| IDN | 1.49 | 3.83 | 4.0 | 788 | 909 | 1,234 | 1,642 | 88% | 57% | 0.0% |
| IND | 4.08 | 14.41 | 5.4 | 3,036 | 3,387 | 4,219 | 4,966 | 88% | 59% | 0.0% |
| JPN | 4.47 | 5.18 | 0.6 | 926 | 811 | 612 | 469 | 82% | 54% | 0.0% |
| MEX | 1.85 | 2.61 | 1.4 | 428 | 393 | 338 | 302 | 89% | 57% | 0.0% |
| NGA | 0.30 | 0.63 | 3.2 | 113 | 115 | 130 | 155 | 94% | 55% | 0.0% |
| RUS | 2.59 | 3.06 | 0.7 | 1,674 | 1,620 | 1,511 | 1,415 | 87% | 66% | 0.0% |
| SAU | 1.30 | 2.40 | 2.6 | 655 | 645 | 621 | 601 | 98% | 70% | 0.0% |
| USA | 31.27 | 48.62 | 1.9 | 4,629 | 4,019 | 3,099 | 2,533 | 79% | 49% | 0.0% |
| VNM | 0.52 | 1.62 | 4.9 | 330 | 385 | 553 | 809 | 76% | 41% | 0.0% |
| ZAF | 0.43 | 0.58 | 1.2 | 433 | 392 | 313 | 259 | 94% | 59% | 0.0% |

## Against references

| Check | Reference | Model | Verdict |
|---|---|---|---|
| Global CO2 2025, incl. land use | ~43 Gt (GCB: fossil 38.6 + land use ~4.6, 2024) | 43.6 Gt | Match. Land use uses the 2015-2024 mean (5.0 Gt), slightly above 2024. |
| Nation fossil CO2 at t=0 | Each nation's 2024 GCB value | Exact (by construction) | Match. 2025 annual values differ slightly due to growth and seasonality. |
| Warming rate 2025-2035 | 0.27 [0.2-0.4] degC/decade (Forster et al. 2025) | 0.28 degC/decade | Match. The non-CO2 multiplier was set for this. |
| Energy CO2 2049 | ~38 Gt, roughly flat (IEA WEO 2025 Current Policies) | ~36 Gt, slowly falling | About 6% low. |
| Warming 2049 | Passes 2 degC around 2050 (IEA WEO 2025 Current Policies) | 2.05 degC | Consistent. |
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
| Global CO2 (Gt/yr) | 43.2 | 37.1 | 32.0 | 20.7 |
| Warming, end of year (degC) | 1.39 | 1.52 | 1.74 | 1.90 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.70 | 1.6 | 353 | 210 | 198 | 22 | 83% | 6% | 0.0% |
| BRA | 2.31 | 3.55 | 1.8 | 427 | 318 | 230 | 55 | 47% | 6% | 0.0% |
| CAN | 2.34 | 3.10 | 1.2 | 491 | 281 | 133 | 68 | 65% | 15% | 0.0% |
| CHN | 20.12 | 43.67 | 3.3 | 11,391 | 9,727 | 6,759 | 908 | 79% | 6% | 0.0% |
| EUU | 21.44 | 28.93 | 1.3 | 2,260 | 1,293 | 481 | 93 | 66% | 6% | 0.0% |
| GBR | 4.04 | 5.23 | 1.1 | 298 | 112 | 46 | 12 | 72% | 6% | 0.0% |
| IDN | 1.49 | 3.82 | 4.0 | 768 | 676 | 592 | 351 | 88% | 17% | 0.0% |
| IND | 4.08 | 14.40 | 5.4 | 2,999 | 2,737 | 2,535 | 1,061 | 88% | 15% | 0.0% |
| JPN | 4.46 | 5.05 | 0.5 | 917 | 510 | 393 | 42 | 82% | 6% | 0.0% |
| MEX | 1.85 | 2.65 | 1.5 | 422 | 284 | 157 | 117 | 89% | 33% | 0.0% |
| NGA | 0.30 | 0.58 | 2.9 | 107 | 63 | 84 | 71 | 94% | 37% | 0.0% |
| RUS | 2.59 | 2.66 | 0.1 | 1,604 | 1,311 | 834 | 853 | 87% | 53% | 0.0% |
| SAU | 1.30 | 2.15 | 2.1 | 625 | 393 | 305 | 249 | 98% | 48% | 0.0% |
| USA | 31.27 | 48.77 | 1.9 | 4,553 | 3,228 | 3,017 | 295 | 79% | 6% | 0.0% |
| VNM | 0.51 | 1.68 | 5.1 | 321 | 317 | 357 | 151 | 75% | 12% | 0.0% |
| ZAF | 0.43 | 0.52 | 0.8 | 425 | 303 | 122 | 91 | 94% | 26% | 0.0% |

Energy CO2 in 2049 is about 14.5 Gt: between the no-action baseline (~36 Gt) and the IEA's
announced-pledges level for 2050 (roughly 12 Gt, from memory of WEO scenarios, not re-checked).
Warming reaches 1.90 degC, against 2.05 degC with no action.

| Nation | Personality | Target path 2049 | Actual 2049 |
|---|---|---|---|
| AUS | cautious_follower | 0.21 | 0.05 |
| BRA | cautious_follower | 0.31 | 0.11 |
| CAN | cautious_follower | 0.21 | 0.13 |
| CHN | opportunist | 0.43 | 0.07 |
| EUU | green_leader | 0.05 | 0.04 |
| GBR | green_leader | 0.06 | 0.03 |
| IDN | opportunist | 0.56 | 0.48 |
| IND | opportunist | 1.00 | 0.30 |
| JPN | cautious_follower | 0.11 | 0.04 |
| MEX | fossil_defender | 0.60 | 0.24 |
| NGA | fossil_defender | 0.73 | 0.60 |
| RUS | fossil_defender | 0.73 | 0.50 |
| SAU | fossil_defender | 0.66 | 0.38 |
| USA | opportunist | 0.60 | 0.06 |
| VNM | opportunist | 0.32 | 0.42 |
| ZAF | cautious_follower | 0.31 | 0.21 |

Diplomacy in this run:

- **Deals:** 87 signed (48 completed, 39 still paying), none defaulted; 153 offers expired
  unanswered.
- **Carbon club:** grew from the EU to 8 members (Australia, Brazil, Canada, EU, UK, Japan,
  Vietnam, South Africa).
- **Stocktakes** judge each nation against the same 1.5 degC pathway on its own 2025 emissions.
  The EU and UK stay on it; Canada, Japan and Australia come close; China, India, Indonesia,
  Vietnam, Russia and Nigeria overshoot by 25-80% of their 2025 emissions per period and face
  coalition tariffs of 1-8%.
- **Credit market:** credits are scarce (2.1 Gt issued, 0.4 Gt traded), so the price climbs
  from $20 to about $70/t over the game.
- **No AI starts a trade war:** AI nations only match tariffs placed on them, so with a clean
  slate none appear.

What to look at in M5:

- **Several nations overshoot their target path** (Saudi Arabia, Mexico, the US, China), because
  cheap wind and solar pay for themselves through lower energy prices.
- **A late-2040s drop for the US and China** as clean energy gets cheap and the clean ceiling
  rises; many nations finish near the 5% fossil floor.
- **India stays high** (its path allows growth) and pays coalition tariffs.

## Placeholders that matter most for balance

Climate damage coefficient, the growth drag weights (shortfall, price, trade, debt, stranded
assets), the capital share of GDP, the long-run growth rule, carbon prices, climate
vulnerability, tech costs and learning rates, the market cost weight, the electrifiable share and
clean ceiling, the AI personality weights, the target paths, and all scoring constants. All are tagged `status: placeholder` in `data/`.
