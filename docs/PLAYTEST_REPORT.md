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

## Round 1 (M8): six countries and an exploit hunter

Seven Claude Code subagents played after the M8 mechanics pass (normal difficulty). Six played
one playable country each through the commands and docs/PLAYTEST.md only; the exploit hunter
could read the code. Full reports are at the end of `games/r1_*/notes.md` (not in git).

| Country | Seed | Score | Rank | Ending | Elections | Warming 2049 |
|---|---|---|---|---|---|---|
| EUU | 22 | 78.0 | 1 | Prosperous but Doomed | 6 of 6 | 1.661 |
| IND | 23 | 69.1 | 6 | Shared Failure | 6 of 6 | 1.620 |
| VNM | 26 | 61.8 | 11 | Shared Failure | 6 of 6 | 1.650 |
| CHN | 21 | 59.1 | 13 | Shared Failure | 6 of 6 | 1.661 |
| RUS | 24 | 0 (65.3 at exit) | 7 at exit | Voted Out 2048Q4 (0.497) | 5 of 6 | 1.620 |
| USA | 25 | 0 (74.0 at exit) | 4 at exit | Voted Out 2036Q4 (0.494) | 2 of 3 | 1.559 (2036) |
| Hunter (EUU) | 1 | 73.1 | 1 | Prosperous but Doomed | 6 of 6 | 1.650 |

**Caveats.** The agents shared one scratchpad folder at first and a helper script was
overwritten, so one turn of Russia's actions was played into the EU game (about 2026Q2: wind
1.0, wind subsidy 0.3) and one empty turn into the USA game (2026Q4). Vietnam was locked out
of every action from 2039Q4 by a crash (below), so its last decade is not real play.

### Fixed during the round

| Problem | Fix |
|---|---|
| Capital at -0.0002 T$ made every action, even free ones, crash with `KeyError: 'capital'` (VNM, hunter) | Free actions pass when a resource is negative; a negative quarter's income is borrowed as local debt |
| The M8 fossil ban crashed with `KeyError: 'factory_solar'` whenever a factory was being built (hunter, CHN, EUU) | Factories in the pipeline are skipped |

### Exploits (confirmed in code)

1. **Climate loans earn credit for plants never built** (hunter). The lender is credited with
   the cut the cash could buy (`deals.activate`), but the host only receives cash. One loan to
   Japan credited 457 Mt/yr while Japan's solar barely grew; India lending 30% of its capital a
   quarter took its climate component from 0.27 to 0.96 with emissions up 50%.
2. **Factory capacity scores forever** (hunter, USA, RUS, EUU). The clean component counts
   factory *capacity*, `industry.factory_lifespan` is never read, storage factories count with
   no buyers, and `exported_cut_rate` only rises. A first factory lifts the clean component
   from 0.50 to 0.81-0.93. The other side: China starts with 73% of world capacity and slid
   from 0.52 to 0.10 with no lever to stop it.
3. **Pre-election price cuts** (CHN, IND, EUU). The vote's price term compares the current price
   with the start of term (taxes are now averaged, prices are not). Cutting carbon from 75 to
   30 a quarter before the vote moved India's forecast from 0.502 to 0.530; once a fossil ban
   is on, the carbon price only costs votes.
4. **Jobs follow completions, quarter by quarter** (USA, RUS, CHN, IND, EUU). Construction jobs
   track capacity completed (smoothed by half each quarter), so a big deal or an order landing
   in the election quarter swings the vote; one factory or a domestic-content rule moves
   manufacturing jobs by millions. Both lost elections were decided by jobs: Russia's
   construction jobs fell from 2.06m at the start of its last term to 0.05m (jobs term
   +0.029 -> -0.061, lost by 0.003); the US lost by 0.006 after factory disruptions.
5. **Inbound deals are risk-free and unlimited** (IND, VNM, hunter). Offers reached 10-17 EJ
   for economies of 8-15 EJ; failed equity plants cost the host nothing; local-currency debt
   never defaults and has no growth drag.
6. **Carbon club membership at 0 $/t** (CHN, VNM, RUS): members are never checked again after
   joining.
7. **First to net zero on one quarter** (EUU): claimed on a low-season quarter while the year's
   total was still positive (`scoring.first_net_zero` reads single quarters).
8. **Cheap first doses** (several): the first methane, efficiency and electrification spending
   is very strong, later spending nearly worthless.

### Bugs and missing information

- **Rank leaves out bonuses**, so it contradicts the leaderboard (all six). India's displayed
  score was the highest yet its rank was 6. This matters because Champion needs a top-4 rank.
- **The score line is hard to reconcile**: the screen shows the relative "nation index" without
  the country multiplier, not the combined index the score uses (EUU).
- **Stocktake overshoot %** does not match the tonnes shown (CHN, IND, EUU).
- **Credit sales find no buyers** late in the game (AI nations buy only when short), but the
  screen keeps showing the last price and says nothing when an order goes unfilled (CHN, RUS,
  IND). India ended with 2,838 Mt unsold.
- **`"max"`**: refused on `retire_capacity` when less than 1 EJ is left; builds still rejected by
  a sliver when capital changes between preview and resolution. Rounded figures on screen cause
  rejections (RUS, CHN).
- **Deals**: the player's own open offers are not listed; offers and counters expire silently;
  new offers do not show their size; equity capacity leaves when a deal ends, with no warning
  and (under a fossil ban) no replacement, which gave Vietnam 4-6% blackouts.
- **Other**: game-over screen still says "SCORE now 65.3" after a loss; a 2035 pledge never
  resolved; removal ordered in 2048 arrives after the game; the action list lacks build times
  for removal, factories, grid and storage; market-ordered grid in the queue is unexplained;
  disaster GDP effects appear a quarter late; log and screen approval differ; supply and demand
  swing every other quarter (USA oil, India demand); FX reserves drain unexplained (RUS).

### Design

- **Champion was not reached.** World warming ended at 1.62-1.66 degC in every game and was still
  rising in most; global CO2 fell to 5-12 Gt/yr by 2049, but too late. Testers judged it needs
  the world well under 20 Gt by about 2035, which one player cannot drive with one diplomatic
  slot a quarter.
- **The late game is flat.** Score barely moves after about 2036 (CHN, EUU, IND); 2036-47 was the
  same one or two moves a quarter in every report. Rich players pile up capital, poor ones have
  too little to act.
- **Wind and solar stop being built late.** Their LCOE rises to 11-17 $/GJ once curtailed, above
  coal, and the market stops building; construction jobs collapse with it (USA, VNM, IND).
- **Elections feel like noise** rather than a judgement on policy: the jobs baseline is not
  shown, and one vote came in 0.051 below its forecast (CHN).

### M9 outcome

Fixed in M9 (docs/ASSUMPTIONS.md items 135-148): climate loans build real plants; factories age
out and the clean component scores a year of equipment sales; the exported-cut credit winds
down; the vote averages prices and jobs over the term and shows the jobs baseline; hosted deal
capacity is capped at half of energy demand; club members below the minimum price leave; first
to net zero needs a four-quarter average; rank follows the final score; 3 domestic and 2
diplomatic slots a quarter; a 3% market reserve and near-term market orders end peak-quarter
blackouts; `"max"` resolves in the engine; open offers, offer sizes, expiries, the score's
construction, unsold credits, leaving the club and late orders are shown.

Not changed yet: wind and solar priced out once curtailed, cheap first doses, the
log-versus-screen approval gap, supply that swings every other quarter, and FX reserves draining
unexplained. Round 2 (the same seven agents, each with its own helper folder, plus a Vietnam
replay) is planned but not run.

## Round 2 (M13): six countries and an exploit hunter, Claude Haiku 5.5 via OpenRouter

Seven agents played through `scripts/playtest_agent.py` (model `anthropic/claude-haiku-5.5`,
normal difficulty, new seeds 31-37) after M10-M13 (permitting reform, more energy sources, the
tech tree, licensing). Reports are in `games/r2_*/report.md` (not in git). Total cost $1.42,
including two 20-step smoke tests (Haiku $0.031, Ling 3.1 Flash $0.006 per 20 requests).

| Country | Seed | Result | Elections | Score (exit) | Rank | Cost |
|---|---|---|---|---|---|---|
| USA | 35 | Full game, Shared Failure | 6 of 6 won | 56.9 | 11 | $0.38 |
| Hunter (EU) | 37 | Full game, Shared Failure | 6 of 6 won | 61.5 | 8 | $0.30 |
| Vietnam | 36 | Full game, Shared Failure | 6 of 6 won | 52.6 | 15 | $0.25 |
| EU | 32 | Voted out 2040Q4 (0.499) | 3 won, 1 lost | 0 | - | $0.24 |
| China | 31 | Voted out 2032Q4 (0.498) | 1 won, 1 lost | 0 (53) | 16 | $0.11 |
| India | 33 | Voted out 2028Q4 (0.470) | 0 won, 1 lost | 0 (60.3) | 16 | $0.07 |
| Russia | 34 | Voted out 2028Q4 (0.470) | 0 won, 1 lost | 0 (72.3) | 3 | $0.04 |

**Caveats.** Haiku plays less carefully than the Round 1 agents: it pushed hard on climate
early and reacted late to the vote forecast, so four of seven lost an election (none in Round
1's honest play lost before 2036). Five runs were interrupted by dropped connections and
resumed from their saves; a resumed agent keeps its notes but not its earlier reasoning.

### Findings (checked against the saves and code)

1. **Permitting reform costs more than players can see it gives back.** Local opposition cost
   the EU 0.059 of its 2040 vote, which it lost by 0.001, and the USA 0.050 in 2032; the USA
   then switched reform off, judging the benefit invisible. No player found reform worth it.
2. **The random swing can decide a game the forecast says is won.** Russia's forecast was
   exact on every term but the swing, which drew -0.065 (3.3 standard deviations; the RNG is
   unbiased over 9,576 draws). The screen does not say how large the swing can be.
3. **Growth decides first elections.** India lost at 4.6%/yr growth against an expected 6.9%;
   China lost 2032 by 0.002 with growth and fossil-job losses each costing 0.023. Agents asked
   for the growth gap and the levers that close it to be shown from the start of each term.
4. **Licences work and are popular**: the USA, EU and Russia bought SMRs, next-gen solar, HVDC
   and enhanced geothermal for 0.03-0.11 T$, far below research cost. Vietnam took expired
   patents (free licences) for an exploit; the screen should say "patent expired".
5. **New technologies spread through deals**: China supplied Vietnam with advanced fission,
   enhanced geothermal and bioenergy by equity deals; the hosted-deal cap was binding.
6. **Research is out of reach for small economies**: Vietnam could fund 0.002-0.007 T$ a
   quarter, too little to finish anything; licences were its only route.
7. **Cheap levers**: methane abatement (the best late-game warming lever), carbon removal,
   forest funding (fills the climate component, then nothing), and an efficiency "dump" that
   lifts the score for a quarter or two. Retraining decided two of the USA's elections.
8. **Generation tax credits are not free money** (the hunter's claim): over three years they
   cost the EU about 0.27 T$ of capital and cut energy prices 19%, with no effect on GDP or
   approval, because the price drag counts only rises above 2025 prices.
9. **Interface**: the election result is printed inside the next quarter's screen; score
   components are hard to trace; tax cuts stop at -1 point; actions resolve in list order, so
   an efficiency "max" first leaves nothing for builds later in the list.
10. **Champion**: no game reached it. Warming ended 1.63-1.66 degC, still rising in most.

### Runner fixes made during the round

- Retries on dropped or garbled connections (SSL errors stopped five runs).
- A resumed run gets its notes back; an agent that stops talking before the game ends is told
  to keep playing (up to three times).
- The full action list is in each agent's brief (it was cut at 12,000 characters, hiding
  `respond_deal`); tool output is cut at 20,000.
- The exploit hunter can list `sim/` and `data/` (it guessed file names and took "no such
  file" for refusals).
