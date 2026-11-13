# Playtest guide

You lead one country's energy economy from 2025 to 2049, one quarter per turn (100 turns). The
other 15 nations are run by the computer. This guide is all you need to play. Your job is to play
well, and to report honestly on what the game was like.

## Rules in brief

**Winning.** The world wins or loses together. Warming starts at 1.35 degC; if it reaches
2.0 degC (averaged over a year) the game ends in Climate Collapse and every nation scores 0. If the
world reaches the end of 2049 below that line it has won, and the nation with the highest score
is Champion: you want to be first.

**Score.** Country difficulty x (75% Impact + 25% Prosperity).

- *Impact* is the CO2 you cut at home, or helped cut abroad (deals, exported equipment, the
  forest fund and regional finance count at a discount, bought credits least), averaged over the
  game as a share of your own 2025 emissions. 50 means no change. A small nation can beat a
  large one.
- *Prosperity* blends income growth, energy security, welfare (approval and energy prices) and
  clean-tech industry, each against your own 2025 starting point.
- Harder countries get a multiplier on the whole score.
- Honours (unscored): first to net zero, largest cut, the most effective deal, and others.

**Endings.** Champion (the world won and you are first), Shared Victory (the world won), or one of
the losses below.

**Losing.** Three ways, and each ends the game with a score of 0:

- **Climate Collapse.** Warming, averaged over the last four quarters, reaches 2.0 degC. Every
  nation loses. The screen warns you from 1.8 degC.

- **Voted Out.** Elections are held every four years: 2028Q4, 2032Q4, 2036Q4, 2040Q4, 2044Q4 and
  2048Q4. You need 50% of the vote. The vote is purely economic: growth over the term against
  what was expected, energy jobs this term against last term (both averaged over the term;
  fossil job losses count double unless you retrain workers), household energy prices and tax
  rises (both averaged over the term), local opposition to permitting reform, plus a random
  swing of up to about 0.04 either way. The screen shows your expected vote from the second
  quarter of each term.
- **Fallen Government.** If stability falls below 0.1. Blackouts (energy shortfalls) and low
  approval erode stability.

**Staying in office.** Most lost games in testing were lost at the first or second election, by
players who spent everything on clean energy and reacted to the forecast too late. Check the
expected vote every quarter from the start of a term and aim for at least 0.54, because the
swing can take away 0.04. What moves it:

- *Growth* (usually the biggest term): measured against the growth expected for your country.
  Tax cuts, lower energy prices and avoiding blackouts help; heavy carbon prices and closing
  plants hurt.
- *Jobs*: this term's average against last term's. Retraining removes much of the penalty for
  lost fossil jobs; building and factories add jobs.
- *Prices*: the carbon rebate returns carbon revenue to households; a lower carbon price helps
  at once.
- *Taxes*: rises cost votes for every quarter they are in force, so a late cut only partly
  undoes an early rise. A cut is mostly borrowed: a quarter of it comes out of your capital and
  the rest becomes debt whose interest comes out of capital every quarter after, so a long cut
  grows expensive. The RESOURCES line shows where your capital comes from.
- *Local opposition*: permitting reform costs votes in proportion to how much you build; it
  halves once a level has held a full term.

Changes take quarters to show in term averages, so act early in the term, not just before the
vote.

**Each quarter** you get 3 domestic and 2 diplomatic action slots; unused slots are banked, up
to 6 domestic and 4 diplomatic. You
also earn capital (T$, trillions of dollars: 2% of GDP a year for energy policy, plus fossil
export and carbon revenue, less tax cuts, tax credits and interest), political capital (spent on unpopular moves such as
carbon prices, closing plants and tax rises) and can buy influence (spent on talks).

**The market builds for you.** Private investors build new capacity every quarter to meet
demand, choosing by cost: your carbon price, subsidies, tax credits and fossil ban change what
they build. Your own `build_capacity` orders come on top.

**Permitting reform** (`set_permitting`) makes new plants, grid and storage build faster, but
local opposition costs approval and votes, more the more you build; how much depends on your
country (shown on the screen).

**Research.** The RESEARCH section lists the tech tree. `fund_research` makes progress at
funding / cost a quarter, but never faster than the technology's minimum time; finished
technologies make existing sources cheaper or unlock new ones (small modular reactors through to
fusion), for you only. Once any nation has a technology it is cheaper for others to research. You can also buy a
licence (`buy_license`) from a nation that sells it, and sell licences to what you researched
(`set_license_price`, optionally refusing some nations); patents expire after ten years.

**The rest of the world.** Seven regions (REGIONS on the screen) are not playable, but their
emissions count toward warming, and they cut slowly unless helped. `finance_region` lends
cheaply for solar or wind there: it costs you a little (the region repays below market rates),
earns climate credit for the cut, wins the region's trust, and sells equipment from trusted
nations' factories. Each region can absorb only so much a year, shared by all lenders.

**Events.** Every few years a country in one of the regions faces a choice (EVENTS on the
screen): an oil field, a rainforest, a coal plan, a disaster appeal. Any nation can pledge to a
shared fund with `pledge_to_event`; if the fund reaches its target by the deadline the bad
outcome is avoided and contributors gain trust and climate credit, and if not, every pledge is
refunded. Other nations rarely fill a fund on their own.

**Influence.** Bought with capital. Talks spend it (5 each). While you hold it, it is your
standing: more nations offer you deals and they accept terms a little steeper. It is never needed
to propose a deal, and unused influence fades about 5% a quarter.

**Deals.** You can offer other nations clean-energy deals (loans, equipment on credit, energy as
a service, equity) and answer offers in your inbox. Deals cut emissions abroad, earn returns and
build trust; equity can be lost if the host becomes unreliable. A nation can host deal capacity
up to half its energy demand. Rank is on the final score.

## Commands

Run everything from the project folder with the virtual environment active
(`source .venv/bin/activate`). Each command is one quarter or one look; the game saves itself.

```bash
python -m sim.play new --country IND --seed 1 --difficulty normal --save games/<name>
python -m sim.play show games/<name>            # the game screen (add --json for raw data)
python -m sim.play actions                      # every action: parameters, ranges, costs
python -m sim.play check games/<name> '<json>'  # try actions without playing
python -m sim.play turn games/<name> '<json>'   # play this quarter with these actions
python -m sim.play wait games/<name> 4          # play 4 quarters taking no actions
python -m sim.play score games/<name>
python -m sim.play log games/<name> --last 8
```

Actions are a JSON list, for example:

```bash
python -m sim.play turn games/ind1 '[{"type": "set_carbon_price", "level": 20}, {"type": "build_capacity", "source": "solar", "amount": 0.2}]'
```

`turn` with no actions (or `'[]'`) plays the quarter without acting. Rejected actions cost
nothing; the reason is printed. Use `check` when unsure.

- **`"amount": "max"`** spends all you can afford on that action, after the actions before it in
  the same list (for builds, spending, research and plant closures). Actions resolve in list
  order, so a "max" early in the list leaves nothing for the actions after it.
- **`--brief`** on `show`, `turn` or `wait` leaves out costs, capacity, relations and the list of
  active deals.
- **THIS QUARTER** on the screen lists what changed: new offers, answers to your offers and
  counter-offers, deals signed (and what you paid), plants coming online, credits issued or sold,
  stocktake results (including whether your pledge is on track), and bonuses gained or lost.
- **Timing.** Income arrives before your actions, so the screen shows what you can spend. But if
  another nation accepts an offer you made, the deal's cost leaves your capital that same
  quarter, possibly before your own actions resolve.

## How to play the test

- Play only through the commands above and this guide. Do not read the source code or the data
  files, unless your brief says you may.
- Play to the end (2049Q4) or until you lose. You may use `wait` through quiet stretches, but
  look at the screen at least once a year of game time, and before every election.
- Keep notes as you go in `games/<name>/notes.md`: a line or two per game year on what you did
  and why, and anything surprising.

## What to report

Finish with a report (in your notes file and in your final answer), under these headings:

1. **Result.** Country, seed, difficulty, final score, ending, rank, final warming; elections
   won and lost.
2. **Strategy.** What you did, phase by phase, and why.
3. **What decided the result.** The two or three moves or events that mattered most.
4. **Dominant strategies or exploits.** Anything that felt too strong, too cheap or risk-free,
   or any way to score without playing the game as intended.
5. **Weak or pointless options.** Actions you never found a reason to use, or that did nothing
   visible.
6. **Confusing or missing information.** Anything on the screen you could not interpret, or
   information you needed and could not find.
7. **Dull stretches.** Periods with nothing worth deciding.
8. **Bugs.** Anything that looked wrong: impossible numbers, rejected actions you think were
   valid, results that contradict the screen.
9. **Was Champion reachable?** Could you finish first on the score while staying in office? Did
   the 2 degC line ever feel close? What would it have taken?
10. **One change you would make.**
