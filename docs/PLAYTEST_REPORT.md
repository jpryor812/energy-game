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

### For the mechanics pass (M8 outcome in brackets; docs/ASSUMPTIONS.md items 118-132)

**Exploits.**
- **Tax timing.** The vote compares only the current tax rate with the rate at the start of the
  term. Raising tax after an election and cutting it before the next is free money. [Fixed: the vote averages the tax rise over the term.]
- **Inbound equity deals cost the host nothing.** Counter-offers at 3% were always accepted.
  [Fixed: AI financiers refuse counters below 70% of their ask; inbound equity stays good for
  the host by design.]
- **Tiny factories swing the clean component.** 0.015 T$ moved it from 0.49 to 0.79 for India,
  because the share ratio starts from almost nothing. [Partly: share floor 0.01 -> 0.03; a
  higher factory cost broke China's manufacturing jobs and was reverted.]
- **Storage was the best buy most of the game.** It is cheap, fast, and pushes coal off
  whenever wind is curtailed. [Storage cost 0.05 -> 0.15, with a learning floor.]

**Weak or dead options.**
- **Talks are too expensive.** One costs about a quarter's capital through influence. [Influence
  10x cheaper.]
- **Diplomatic slots were worthless.** The tester banked 69 of them. [Banking capped at 4.]
- **No visible effect:** set_activity_cap (100 political capital per unit), rebate, make_pledge,
  methane abatement and retraining. [Effects shown on screen;
  activity cap at half the political capital.]
- **AI deal offers stopped after 2033.** Diplomacy was dead in the second half.
  [Offers to India stopped because hosts were ranked by emissions intensity; growth now counts.]

**Possible bugs to check.**
- **largest_clean_gain flickers with the season.** It switched on and off quarter to quarter
  because it reads the current quarter's supply. [Fixed: four-quarter averages.]
- **Carbon removal unit cost never fell** during play, despite learning. [Already at its learning floor;
  now marked on screen.]
- **Coal under construction kept arriving after the fossil ban,** until 2033. [Fixed: a ban cancels
  fossil projects not yet started.]
- **No net-zero bonus at -130 Mt.** Possibly another nation reached net zero first; to be
  checked. [Not a bug: Canada got there first, in 2043Q2; races now on screen.]
- **Wind ordered in 2038-41 seemed to arrive slowly.** Needs checking against build times. [Wind takes 8 quarters;
  build times are now in the action list.]

**Design.**
- **Champion looked unreachable.** Warming passed 1.5 degC by 2030 even as global CO2 fell from
  45 to 8 Gt; staying under it would need most of the world's cuts in the first 5-8 years. [Champion now 1.6 degC and falling.]
- **The late game was dull.** From 2037 to 2049 it was the same move each quarter (all capital
  into storage, removal or solar), with political capital near zero. [To
  recheck in the playtest round.]
- **Disasters dominated income.** About ten hits of 1-2.4% of GDP each kept the income
  component at 0.20. [To recheck in the playtest round.]
