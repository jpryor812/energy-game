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

### World

| Metric | 2025 | 2030 | 2040 | 2049 |
|---|---|---|---|---|
| Global CO2 (Gt/yr) | 43.6 | 42.7 | 41.8 | 42.1 |
| Warming, end of year (degC) | 1.39 | 1.53 | 1.80 | 2.05 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.79 | 1.7 | 363 | 321 | 256 | 219 | 84% | 48% | 0.0% |
| BRA | 2.31 | 3.68 | 2.0 | 435 | 433 | 430 | 481 | 48% | 29% | 0.2% |
| CAN | 2.34 | 3.32 | 1.5 | 502 | 447 | 362 | 307 | 66% | 49% | 0.0% |
| CHN | 20.12 | 44.23 | 3.3 | 11,531 | 11,289 | 10,832 | 10,336 | 79% | 54% | 0.0% |
| EUU | 21.49 | 29.77 | 1.4 | 2,288 | 1,883 | 1,249 | 896 | 66% | 35% | 0.0% |
| GBR | 4.05 | 5.53 | 1.3 | 300 | 247 | 169 | 122 | 72% | 43% | 0.0% |
| IDN | 1.49 | 3.92 | 4.1 | 788 | 909 | 1,247 | 1,685 | 88% | 57% | 0.0% |
| IND | 4.08 | 14.77 | 5.5 | 3,036 | 3,388 | 4,269 | 5,102 | 88% | 60% | 0.0% |
| JPN | 4.47 | 5.24 | 0.7 | 926 | 811 | 616 | 474 | 82% | 54% | 0.0% |
| MEX | 1.85 | 2.67 | 1.5 | 428 | 393 | 343 | 311 | 89% | 58% | 0.0% |
| NGA | 0.30 | 0.63 | 3.2 | 113 | 115 | 130 | 155 | 94% | 55% | 0.0% |
| RUS | 2.59 | 3.09 | 0.7 | 1,674 | 1,620 | 1,519 | 1,434 | 87% | 66% | 0.0% |
| SAU | 1.30 | 2.44 | 2.6 | 655 | 645 | 625 | 609 | 98% | 70% | 0.0% |
| USA | 31.27 | 48.94 | 1.9 | 4,629 | 4,019 | 3,108 | 2,548 | 79% | 49% | 0.0% |
| VNM | 0.52 | 1.81 | 5.4 | 330 | 386 | 589 | 921 | 76% | 43% | 0.0% |
| ZAF | 0.43 | 0.59 | 1.3 | 433 | 393 | 316 | 262 | 94% | 59% | 0.0% |

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

## Placeholders that matter most for balance

Climate damage coefficient, the growth drag weights (shortfall, price, trade, debt, stranded
assets), the capital share of GDP, the long-run growth rule, carbon prices, climate
vulnerability, tech costs and learning rates, the market cost weight, the electrifiable share,
and all scoring constants. All are tagged `status: placeholder` in `data/`.
