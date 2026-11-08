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
- **What BAU means.** Nobody makes decisions. Each nation keeps building new capacity in the
  same mix as its 2019-2024 change in energy use (a frozen-trend baseline), retires old capacity
  at 1/lifespan or its observed 2019-2024 decline rate, and grows at IMF projected rates that
  converge toward a long-run rate. It is a "nobody acts" reference, not a forecast.

## Results (seed 1)

### World

| Metric | 2025 | 2030 | 2040 | 2049 |
|---|---|---|---|---|
| Global CO2 (Gt/yr) | 43.8 | 44.2 | 46.1 | 48.3 |
| Warming, end of year (degC) | 1.39 | 1.53 | 1.83 | 2.10 |

### Nations

| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) | CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS | 1.86 | 2.82 | 1.7 | 363 | 316 | 246 | 197 | 84% | 44% | 0.0% |
| BRA | 2.31 | 3.68 | 2.0 | 435 | 431 | 418 | 414 | 48% | 28% | 0.0% |
| CAN | 2.34 | 3.34 | 1.5 | 504 | 470 | 422 | 385 | 66% | 62% | 0.0% |
| CHN | 20.12 | 44.12 | 3.3 | 11,580 | 11,905 | 12,409 | 12,464 | 79% | 66% | 0.0% |
| EUU | 21.49 | 29.71 | 1.4 | 2,286 | 1,859 | 1,203 | 828 | 66% | 33% | 0.0% |
| GBR | 4.05 | 5.52 | 1.3 | 299 | 241 | 161 | 113 | 72% | 41% | 0.0% |
| IDN | 1.49 | 3.93 | 4.1 | 799 | 1,058 | 1,738 | 2,508 | 89% | 84% | 0.0% |
| IND | 4.08 | 14.70 | 5.5 | 3,072 | 3,894 | 5,747 | 7,307 | 89% | 85% | 0.0% |
| JPN | 4.47 | 5.22 | 0.6 | 925 | 802 | 593 | 445 | 82% | 51% | 0.0% |
| MEX | 1.85 | 2.66 | 1.5 | 429 | 406 | 381 | 365 | 90% | 72% | 0.0% |
| NGA | 0.30 | 0.64 | 3.2 | 113 | 126 | 159 | 193 | 95% | 74% | 0.0% |
| RUS | 2.59 | 3.15 | 0.8 | 1,683 | 1,728 | 1,805 | 1,852 | 88% | 87% | 0.0% |
| SAU | 1.30 | 2.47 | 2.7 | 660 | 701 | 765 | 790 | 99% | 95% | 0.0% |
| USA | 31.27 | 48.86 | 1.9 | 4,633 | 4,055 | 3,247 | 2,707 | 79% | 55% | 0.0% |
| VNM | 0.52 | 1.80 | 5.4 | 333 | 435 | 748 | 1,161 | 77% | 55% | 0.0% |
| ZAF | 0.43 | 0.59 | 1.3 | 433 | 392 | 315 | 257 | 94% | 61% | 0.0% |

## Against references

| Check | Reference | Model | Verdict |
|---|---|---|---|
| Global CO2 2025, incl. land use | ~43 Gt (GCB: fossil 38.6 + land use ~4.6, 2024) | 43.8 Gt | Match. Land use uses the 2015-2024 mean (5.0 Gt), slightly above 2024. |
| Nation fossil CO2 at t=0 | Each nation's 2024 GCB value | Exact (by construction) | Match. 2025 annual values differ slightly due to growth and seasonality. |
| Warming rate 2025-2035 | 0.27 [0.2-0.4] degC/decade (Forster et al. 2025) | 0.29 degC/decade | Match. The non-CO2 multiplier was set for this. |
| Energy CO2 2049 | ~38 Gt, roughly flat (IEA WEO 2025 Current Policies) | ~42 Gt, rising | About 10% high. Expected for a frozen-trend baseline, see below. |
| Warming 2049 | Passes 2 degC around 2050 (IEA WEO 2025 Current Policies) | 2.10 degC | Consistent. |
| Real GDP growth 2025-2030 | IMF WEO projections | Within 0.5 pp for every nation | Match. |
| Energy shortfall | None expected without shocks | Below 1% for every nation, every quarter | Match. |

## Known deviations

1. **Coal-heavy growers keep growing on coal.** China, India, Indonesia and Vietnam keep their
   2019-2024 build mix, which was coal-heavy, so India's CO2 rises about 2.4x by 2049 and China's
   stays near 12 Gt. The IEA's scenarios have China declining and India rising more slowly,
   because they model falling clean-energy costs shifting new builds. The BAU builder ignores
   cost; AI nations in M3, and the player, will respond to costs and policy instead.
2. **EU, US, UK, Japan decline faster than coal-heavy growers.** Their recent build mix is
   mostly wind, solar and gas, and coal retires at the observed 2019-2024 rate.
3. **Russia and Saudi Arabia barely change their mix.** Their recent additions were almost all
   fossil. Export revenue falls (Russia -16%, Saudi Arabia -29% by 2049) because world use of
   their fuels falls.
4. **Energy prices fall as wind and solar grow**, because prices count only variable costs.
   That understates transition costs; capital costs enter the game when actions arrive in M2.
5. **GDP 2025 annual figures are ~1% above IMF 2025**, because the IMF 2025 value is used as the
   2025Q1 level and growth continues through the year.

## Placeholders that matter most for M2 balance

Climate damage coefficient, the growth drag weights (shortfall, price, trade, debt), the
capital share of GDP, the long-run growth rule, carbon prices, climate vulnerability, and the
tech costs and learning rates. All are tagged `status: placeholder` in `data/`.
