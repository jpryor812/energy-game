# Playtest report

Agent playtests run through `python -m sim.play` with the guide in `docs/PLAYTEST.md`. Each agent
plays from the commands and the guide only, without reading the code or data.

## Pilot (M7): India, seed 11, normal

One Claude Code subagent played a full game (117 commands, about 13 minutes).

**Result.** Score 64.8, Shared Failure, rank 8 of 16. Final warming 1.63 degC (multiplier
0.88). Won all six elections; the closest was 0.504 in 2040. Emissions went from 3,005 Mt to
-130 Mt net, and GDP rose 246%.

**How it played.**
1. A fossil ban, wind and solar subsidies, a carbon price with full rebate, and joining the
   carbon club.
2. Accepted inbound equity deals and countered loan offers down to 3-5%.
3. Built storage once wind was curtailed.
4. Retired idle coal and finished with carbon removal.

### Fixed in M7 (interface)

| Problem the tester hit | Fix |
|---|---|
| Orders failed by rounding ("needs 0.01088, has 0.01077") | `"amount": "max"`; capital shown to 6 significant digits |
| Could not tell when its own orders would arrive | Construction listed by arrival quarter |
| No word on counter-offers, accepted deals, or deal payments | THIS QUARTER notices: offers, answers, signings with cost, failures, endings |
| Pledge results, credit sales and bonus changes unreported | Notices for stocktakes (pledge on track or broken), credits, and bonuses gained or lost |
| `check` showed a proposed deal as free | `check` shows the capital a deal will take if accepted |
| Deal end dates only in JSON | Active deals show their end quarter |
| No comparison with other nations | Leaderboard line under the score |
| The vote did not say what growth it expects | Growth this term against expected growth |
| Why wind and solar were curtailed was a mystery | Integration line: base absorption + grid + storage, capped by the electrifiable share; clean cap; electrification bonus |
| Long screen every turn | `--brief` on `show`, `turn` and `wait` |
| Emissions gross or net? | Labelled "net of removals" |

### For the mechanics pass (not changed yet)

**Exploits.**
- **Tax timing.** The vote compares only the current tax rate with the rate at the start of the
  term. Raising tax after an election and cutting it before the next is free money.
- **Inbound equity deals cost the host nothing.** Counter-offers at 3% were always accepted.
- **Tiny factories swing the clean component.** 0.015 T$ moved it from 0.49 to 0.79 for India,
  because the share ratio starts from almost nothing.
- **Storage was the best buy most of the game.** It is cheap, fast, and pushes coal off
  whenever wind is curtailed.

**Weak or dead options.**
- **Talks are too expensive.** One costs about a quarter's capital through influence.
- **Diplomatic slots were worthless.** The tester banked 69 of them.
- **No visible effect:** set_activity_cap (100 political capital per unit), rebate, make_pledge,
  methane abatement and retraining.
- **AI deal offers stopped after 2033.** Diplomacy was dead in the second half.

**Possible bugs to check.**
- **largest_clean_gain flickers with the season.** It switched on and off quarter to quarter
  because it reads the current quarter's supply.
- **Carbon removal unit cost never fell** during play, despite learning.
- **Coal under construction kept arriving after the fossil ban,** until 2033.
- **No net-zero bonus at -130 Mt.** Possibly another nation reached net zero first; to be
  checked.
- **Wind ordered in 2038-41 seemed to arrive slowly.** Needs checking against build times.

**Design.**
- **Champion looked unreachable.** Warming passed 1.5 degC by 2030 even as global CO2 fell from
  45 to 8 Gt; staying under it would need most of the world's cuts in the first 5-8 years.
- **The late game was dull.** From 2037 to 2049 it was the same move each quarter (all capital
  into storage, removal or solar), with political capital near zero.
- **Disasters dominated income.** About ten hits of 1-2.4% of GDP each kept the income
  component at 0.20.
