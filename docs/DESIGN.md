# Energy Diplomacy Game: Design Doc v0.1

Working title. Source of truth for design decisions. Last synced from the design doc on 2026-11-07.

## Vision and pillars

You lead one country's energy economy from 2025 to 2050 in a turn-based strategy game, and your final score is your nation's prosperity multiplied by how the world did on climate. Winning for yourself requires the world to get close to net zero.

There is no war. Conflict runs through tariffs, export controls, sanctions, and competition for capital, minerals, and markets. The core action is the deal: structuring a trade, loan, or equity swap with another nation.

**The four C's (guiding principles for building the game, not a player-facing frame)**

| C | The player's question | What it means in play | How you fail |
| --- | --- | --- | --- |
| Continuation | Can I keep the lights on and the country stable? | Meet energy demand every turn; keep approval and the budget healthy | Blackouts, protests, a fallen government |
| Cultivation | What am I growing for the long run? | Build capacity, grid, research, supply chains, and trust with partners | Underinvest early, then hit a wall in the 2040s |
| Conservation | Am I protecting what can't be replaced? | Stay inside a carbon budget; protect minerals, land, water, and FX reserves | Overshoot the budget; face sanctions and climate damage |
| Competition | Am I winning my place in the world? | Compete for markets, tech leadership, minerals, and investment against other nations | Fall behind rivals; lose deals and leverage |

Each C costs something in another. Cultivation spends capital that continuation needs now, and conservation can cost competitiveness. That tension is where the strategy lives.

**Design principles**

- Your country is your difficulty setting.
- Every decision has a visible cost and a delayed effect.
- Cooperation is selfish: sabotaging the world lowers your own score.
- Deals are the heart of the game, the way the convoy is in Convoy.

## Countries and difficulty

Pick from about 16 nations, and each one plays differently because its starting hand differs, not because of cosmetic bonuses. Each country starts from its approximate 2025 economic and energy state, calibrated against public datasets (for example IEA, Ember, and World Bank data). The difficulty ratings below are design intent, to be checked in the simulation.

**The six dials on every country card**

1. **Wealth:** capital available each turn and access to cheap finance.
2. **Demand growth:** how fast energy demand rises.
3. **Fossil lock-in:** installed coal, oil, and gas, and the jobs that depend on them.
4. **Political constraints:** election cycles, polarization, or elite stability.
5. **Diplomatic leverage:** market size, mineral or tech control, and bloc membership.
6. **Climate vulnerability:** how hard heat, floods, and crop failures hit.

**Proposed roster**

| Country | Archetype | What makes it interesting | Intended difficulty |
| --- | --- | --- | --- |
| United States | Capital-rich, politically volatile | Strong finance and tech, but policy whiplash after elections | Easy |
| United Kingdom | Capital-rich, small, finance hub | Strong deal-making tools, limited domestic scale | Easy |
| Japan | Tech-rich, import-dependent | Few domestic fuels, strong manufacturing and finance | Medium |
| European Union | Rule-setter | Sets carbon prices and border tariffs; must keep its members aligned | Medium |
| China | Manufacturer and scale player | Dominates clean-tech supply chains, coal-heavy grid | Medium |
| Brazil | Hydro and land | Clean grid, but land-use emissions and a volatile currency | Medium |
| Australia | Resource exporter with great sun and wind | Fossil export revenue versus huge renewable potential | Medium |
| Saudi Arabia (Gulf) | Capital-rich fossil exporter | Must diversify before its main revenue erodes | Medium |
| Russia | Fossil exporter exposed to trade restrictions | Large fuel exports, limited access to finance and tech | Hard |
| India | Rising demand, limited capital | Huge demand growth, coal lock-in, massive solar potential, large market | Hard |
| Indonesia | Coal and minerals exporter | Nickel and coal leverage, fast-growing demand | Hard |
| Vietnam | Export manufacturer, dirty grid | Exporters need clean power for buyers; currency risk | Hard |
| South Africa | Coal-dependent grid, mineral-rich | Unreliable grid, high coal dependence, strong mineral leverage | Hard |
| Nigeria | Energy access gap, oil exporter | Low capital and low access, very high growth potential | Hard |
| Canada | Resource-rich, cold | High per-person energy use, hydro, oil sands | Easy to medium |
| Mexico | Trade-linked mid-income | Tied to US supply chains, state-run energy sector | Medium |

**MVP playable six:** United States, India, European Union, China, Vietnam, and Russia. The other ten are AI nations from day one and become playable later.

**The EU decision.** For the first version, treat the EU as one actor with a cohesion meter, because it sets carbon prices and border tariffs as a bloc and that is the behaviour worth modelling. Events can pull its members apart (an energy-price shock, an election). Splitting it into Germany, France, and others is a good fit for the 20-player mock UN later.

**Russia and geopolitics.** The game has no military layer, so geopolitical conflict shows up only as trade restrictions, financing limits, and sanctions exposure. Keep these as mechanics, not commentary, so the game stays a neutral teaching tool.

## Core loop and the turn

One turn is one quarter, so 2025 to 2050 is 100 turns. At a few minutes a turn that is a multi-sitting campaign, so the game needs save and resume, and quiet turns that resolve in seconds. A shorter annual mode is planned for classes. Quarters also let the grid model seasonal peaks such as summer heat and winter heating. These are starting assumptions to test, not measured figures.

1. **Briefing:** a short report shows demand and supply by region, emissions, the budget, news, and any pending offers.
2. **Domestic phase:** build or retire plants and grids, set the carbon price, subsidies and tariffs, and choose research.
3. **Diplomacy phase:** open talks, propose or answer deals, join or leave blocs, and apply tariffs or restrictions.
4. **End turn:** AI nations make their moves at the same time.
5. **Resolution and events:** the economy, grid, and emissions update, then events fire and ask for your response.

Every twentieth turn, once every five years, is a **global stocktake**, where each country's emissions are checked against its fair share and consequences follow. Democracies also face an **election** on a cycle, which tests approval. *(Changed 2026-11-08: the player faces an election every four years in every playable nation; see Decided below.)*

The player has limited action slots each turn (a starting suggestion: three domestic and two diplomatic), so every turn forces a choice about what to leave undone. Unused slots build up for later turns.

## World model

The world model is a small set of linked systems: five player resources (plus FX reserves for developing nations), a regional energy system, global supply chains, and a shared climate. All numbers are placeholders until calibrated.

**Player resources**

| Resource | What it does | How it moves |
| --- | --- | --- |
| Capital | Pays for plants, grids, subsidies, and deals | Quarterly budget from GDP and taxes; deals add or drain it. The master lever: you spend it on building, research, influence, and more |
| Political capital | Pays for unpopular moves such as a carbon price or coal closures | Earned by delivering wins; lost by blackouts, price spikes, and broken promises |
| Influence | Pays for opening talks, forming blocs, and pushing stocktake rules | Bought with capital, and earned through trust and being a reliable partner |
| Tech points | Unlock cheaper or cleaner technologies | Bought with capital as research spending, and earned by deploying technology |
| Emissions | Your share of the global carbon budget | Rises with fossil generation and industry; falls with clean capacity and efficiency |
| FX reserves (developing nations) | Backs hard-currency debt and imports | Built by exports; drained by dollar-denominated loans and equipment imports |

**Energy system.** Each country has 6 to 10 regions. Each region has demand, resources (sun, wind, hydro, coal, gas), and a grid. Every source has a build cost, build time, lifespan, and emissions. As the renewable share grows, regions need storage and transmission or they waste output (curtailment), which makes grid building a real strategic choice.

**Supply chains.** Clean technology needs minerals and manufacturing capacity. A few countries control most of each, so bottlenecks and export controls create leverage, and your own mineral deals can be a way in.

**Learning curve.** The cost of a technology falls as total global deployment grows, so early adopters take on risk that benefits everyone who invests later.

$$C(n) = C_0 \cdot n^{-b}$$

Here C is unit cost, n is cumulative global deployment, and b sets how fast costs fall (a per-technology placeholder to calibrate).

**Climate.** Global warming follows cumulative global emissions. Impacts such as heat, floods, and crop failures grow with warming and hit vulnerable countries first, which raises adaptation spending and can destabilize governments.

## The economy: GDP and its levers

Income comes from GDP. Each quarter your capital is your tax share of GDP, plus deal income and fossil export revenue, minus debt service. Anything that moves GDP moves everything you can afford to do.

**Emissions follow the Kaya identity.**

$$\text{Emissions} = \text{Population} \times \frac{\text{GDP}}{\text{Population}} \times \frac{\text{Energy}}{\text{GDP}} \times \frac{\text{Emissions}}{\text{Energy}}$$

You can cut emissions through any term: shrink GDP per person (degrowth), lower energy used per unit of GDP (efficiency), or lower emissions per unit of energy (clean power). The strategic skill is cutting the last two faster than GDP grows, because cutting the first costs you score directly.

**What raises GDP**

- Investment in plants, grids, and factories, paid for by capital, debt, or deals.
- Reliable, cheap energy: demand met at a low price.
- Trade: manufacturing, clean-tech, and (for exporters) fossil exports.
- Productivity: research and falling technology costs.
- Efficiency: the same output from less energy.
- Cheaper capital: trust, bloc membership, and a stable currency lower borrowing costs.
- Baseline growth from population and catch-up, set by each country's 2025 profile.

**What lowers GDP**

| Drag | How it happens | How you can soften it |
| --- | --- | --- |
| Energy shortfall | Plants retired faster than replacements arrive; grid limits; seasonal peaks | Build storage and grid first, keep reserves, import |
| Higher energy prices | Carbon price, fuel price spikes, costly imports | Recycle carbon revenue as rebates or tax cuts; efficiency |
| Stranded assets | Closing a plant before it pays back writes off capital and jobs | Compensation, retraining, phased closures (these cost capital) |
| Industry flight | Heavy industry relocates under a high carbon price, and emissions move abroad | Border tariffs, clean-power deals for industry |
| Trade restrictions | Tariffs, export controls, and sanctions, given or received | Bloc membership, alternative partners |
| Debt and currency | Hard-currency debt against local revenue; currency shocks | Local-currency deals, reserves |
| Fossil export decline | World demand for oil, gas, and coal falls | Diversification deals and investment |
| Climate damage | Heat, floods, and crop failures grow with global warming | Adaptation spending; global cuts |
| Instability | Protests and strikes after hardship | Welfare spending; a fair transition |

**Degrowth as a lever.** An activity cap on energy-intensive output is available but blunt. It cuts emissions and GDP together, lowers capital and approval, and ranks you lower on the Nation Index, so it should work but rarely be the best option.

**One GDP number.** GDP is a single value per country, and it funds capital. Fuel mix and energy used per unit of GDP are tracked separately, which is enough to show the trade-offs without a sector model.

**Timing.** Transition costs come early and gains come later. Clean investment can slow growth in the first years, then raise it as costs fall and clean industries grow. Quarterly turns also show seasonal shortages.

$$g = g_0 + I + P + T - S - E - R - D - C$$

Quarterly GDP growth g starts from baseline growth g0, adds investment (I), productivity (P), and trade (T), and subtracts energy shortfall (S), energy price shock (E), restrictions and stranded-asset write-offs (R), debt and currency drag (D), and climate damage (C). Each term's weight is a placeholder to calibrate in the simulation.

## Cooperative competition: scoring and endings

Your score is your Nation Index times a World Multiplier, so you can only win big if your country thrives and the world avoids the worst warming.

$$\text{Score} = N \times M(T)$$

N is the Nation Index at the end of the game. M(T) is the World Multiplier, set by final warming T: near 1.0 for a good outcome, falling steeply for a bad one. Both curves are placeholders to tune in the simulation.

**Nation Index (N)** blends four things, each scaled to your starting point so a poor country is not judged against a rich one:

- Income growth per person.
- Energy security: share of demand met, and import dependence.
- Stability and welfare: approval, energy prices, and access to power.
- Clean competitiveness: share of global clean-tech markets and exports you hold.

**Why this is cooperative and competitive at once**

- You are ranked against the AI nations on N, so there is a real race.
- Everyone shares M(T), so a country that free-rides on others' cuts still suffers if the world fails, and sabotage lowers your own score.
- The temptation to free-ride is real, because others' reductions help you. Three things push back: the stocktake (overshooting your fair share brings coalition tariffs), reputation (a broken pledge lowers trust in every future deal), and access (clubs and finance go to reliable partners).

**Achievement bonuses.** Several firsts and bests add bonus points to your score, so there is more than one route to a good result:

- First to reach net zero.
- The largest emissions reduction.
- A breakthrough technology that the world adopts most.
- The most impactful trade deal, measured by the emissions it cuts.

Bonuses are flat points on top of the score, and the size of each is to be tuned in the simulation.

**Technology credit.** If a technology you create (for example a reliable small modular reactor or carbon capture) is adopted by other nations, measured by the share of nations using it, you get a financial boost, a tech boost, and emissions credit at about 0.6 to 1 (a placeholder ratio).

**Endings**

| Ending | Condition |
| --- | --- |
| Champion | Top rank on N and a good world outcome |
| Prosperous but Doomed | Top rank on N, bad world outcome |
| Green but Poor | Good world outcome, low rank on N |
| Shared Failure | Bad outcome for you and the world |
| Fallen Government | Stability reaches zero: you are removed early |

**Fair-share rule:** your fair share of the carbon budget is based on emissions, and it updates as emissions change during the game.

## Diplomacy and deals

Deals are the main way to grow beyond your own borders, and they carry the financial engineering that makes the game different from a pure policy sim. Each deal has terms, and the AI nation accepts or refuses based on its own interests and its trust in you.

**Relationships.** Every pair of countries has a trust score and each side holds some leverage over the other. Trust rises when you honor deals and pledges and falls when you default, overshoot, or break a pact. Blocs (a carbon club, a finance coalition, a mineral pact) are alliances, not mergers: members get cheaper deals and shared tools but give up some freedom.

**Deal terms.** Every deal sets price, currency (hard or local), duration, collateral, and an exit clause. Currency is the key variable: a hard-currency debt against local-currency revenue is how deals fail.

| Deal | You give | You get | Main risk |
| --- | --- | --- | --- |
| Equipment on credit | Clean equipment now | Repayment over years | Partner can't pay; currency swings |
| Energy-as-a-service | Build and run a plant | Per-unit payments for a long period | Partner changes rules; demand falls |
| Equity-for-energy | Plant or capacity | A share in a partner's growth | The business fails or underperforms |
| Goods-for-energy | Plant or equipment | Part of the partner's output | You must resell the goods; price risk |
| Climate loan | Capital | Interest, in hard or local currency | Default; currency mismatch |
| Tech license | Know-how | Fees or market access | Partner becomes a competitor |
| Mineral pact | Capital or tech | Secured supply of key minerals | Export controls; supplier instability |
| Debt-for-climate swap | Debt relief | Partner's clean-energy commitments | Partner doesn't deliver |

A buyer in the supply chain can also pay a green premium when a supplier's power gets cleaner, which is the third-party payer layer and can be added to any deal.

**The conflict layer (no war).** Tariffs, subsidies, export controls on minerals and technology, and sanctions are your pressure tools. They cost you something too (trade lost, trust damaged), and the target can retaliate in kind.

**Emissions credit.** When a deal cuts emissions, the credit is split. The host country gets 1 to 1 and the financier gets about 0.75 to 1 (a placeholder ratio). Credit feeds scoring and bonuses, while the atmosphere counts only real emissions.

**MVP scope.** Start with four deal types (equipment on credit, energy-as-a-service, equity-for-energy, climate loan), plus tariffs and one bloc.

## Competing decisions each turn

Every turn you spend limited capital, political capital, influence, and action slots on choices that pull against each other. No option is free, and the right answer depends on your country.

| Decision | Pulls toward | Pulls against |
| --- | --- | --- |
| Cheap fossil capacity now, or solar plus storage | Lower cost, faster supply, fewer blackouts | Emissions, lock-in, stocktake penalties |
| Spend at home, or invest abroad through deals | Domestic growth and stability | Equity returns, influence, partner emissions cuts |
| Raise the carbon price | Emissions, clean-tech competitiveness | Approval, industry flight, political capital |
| Research, or deploy now | Cheaper technology later | Lower output today |
| Export clean technology, or protect domestic industry | Market share, trust | Domestic jobs, leverage |
| Make a bold pledge, or keep flexibility | Trust, access to finance | Risk of breaking it and losing reputation |
| Ally with a bloc, or hedge | Cheaper deals, shared tools | Freedom of action; rivals' reactions |
| Spend on adaptation, or prevention | Resilience to climate shocks | Less capital for cutting emissions |

The limited action slots matter as much as the money: you cannot do everything, so leaving something undone is part of every turn.

**Country changes the answer.** The US may afford all of the above and be tempted to delay. India may have to choose between growth and cleaner supply every single turn. Vietnam's exporters want clean power to satisfy buyers but have few ways to pay for it. That variety is why the same game plays differently with each country.

## Events and reactive decisions

Events interrupt your plan and force a response, in the style of Crusader Kings. Most should come from the state of the game (a coal region with high unemployment, a grid near its limit) and not from pure chance, so a player can see trouble coming and learn why it happened.

**Event types**

- **Shocks:** heat waves, droughts, price spikes, grid failures, supply cuts.
- **Opportunities:** a tech breakthrough, an investor offer, a partner asking for a deal.
- **Political:** elections, protests, scandals, a cabinet member's agenda.
- **Diplomatic:** summit invitations, pressure from a bloc, a counterpart defaulting.
- **Climate impacts:** floods, crop failures, and migration that grow with global warming.

**Event structure.** Each event has a trigger, two or three choices with different costs, and often a delayed follow-up. Chains make cause and effect visible: a coal-region protest can lead to a retraining fund, which later unlocks a clean-industry hub, or to a strike that hits output two turns later.

**Advisers.** A small cabinet (finance, energy, foreign affairs, industry) has traits and agendas. Their traits unlock or block certain choices, which gives events a human face and a way to differentiate countries.

| Example event | Trigger | Choices |
| --- | --- | --- |
| Coal region protests | Coal plants closing in a high-unemployment region | Fund retraining (capital); delay closure (emissions); ignore it (approval, political capital) |
| Heat wave strains the grid | Hot year with demand above reserves | Emergency gas imports; rolling blackouts; ask a neighbor for power (a favor owed) |
| Mineral export curbs | A supplier restricts a key mineral | Negotiate a pact; switch technology; stockpile |
| Partner can't repay | An FX shock hits a debtor in one of your deals | Restructure; seize collateral; write it off |
| Investor offers green premium | A buyer wants cleaner supply from a partner | Co-fund the project; take the premium; decline |
| Election year | Democracy reaches its election turn | Cut energy prices; run on a climate record; split the difference |

**MVP scope.** About 40 events and four advisers, with each event tested for whether the choices are all costly and none is obviously best.

## AI nations and the path to a mock UN

AI nations follow exactly the same rules and actions as the player, so the single-player game is a 20-player mock UN with 19 seats filled by AI. When you later let humans take those seats, the rules do not change.

- **Rule-based first.** Each AI nation scores its options by its own agenda (growth, security, climate leadership, fossil defense) and its trust in you. This is cheap, repeatable, and tunable, and it lets you replay a seed.
- **Personalities.** Give each nation a stance, such as green leader, fossil defender, opportunist, or cautious follower, so behavior is readable and the player can learn to work with each one.
- **Hidden information.** Players see what a nation reports, not always what it does. Verifying a claim costs influence, which makes trust something to earn.
- **No LLM for now.** AI nations are fully deterministic, so any run can be replayed from its seed. A language-model layer is a possible later addition, not part of the first versions.

**Path to multiplayer**

1. Single player against AI (this document).
2. A few humans among AI seats, with timed negotiation rounds.
3. A full 20-seat mock UN for classrooms, with a facilitator view and debrief tools. The EU can split into member states here.

## UI and map

The screen follows the Crusader Kings layout: a world map in the center, your government and cabinet on the left (abstract roles, no real people), a resource bar across the top, and pinned alerts and pending deals on the right. The map is 2D with a few light 3D touches.

- **World map with map modes:** toggle emissions, grid mix, trade flows, relations, and climate risk, like the political and terrain modes in a grand strategy game.
- **Country view:** zoom into your country's regions, where plants, grids, and factories appear as small 3D models you can click to build or retire.
- **Resource bar:** capital, political capital, influence, tech points, emissions against budget, and a global temperature gauge.
- **Deal screen:** a clear term sheet with price, currency, duration, collateral, and exit, plus the partner's trust level and likely response.
- **Event pop-ups:** a short story, two or three choices, and the cost of each shown before you click.
- **Stocktake screen:** every nation's pledge and progress on one chart, with consequences listed.
- **End-of-turn report:** what changed and why, so cause and effect stay legible.

**Platform:** web first. A join link with no install is the easiest path into classrooms and for friends to try it, and it fits the later mock UN.

## MVP scope and build order

The first version proves one thing: that winning for your country and getting the world to net zero are both achievable, and that they pull against each other in interesting ways.

| In the MVP | Later |
| --- | --- |
| 2D map with light 3D, web build | Richer 3D, mobile |
| 6 playable and about 10 AI nations | All 16 playable; EU split into members |
| 100 quarterly turns, 2025 to 2050 | Scenarios and shorter formats |
| 5 resources, 4 deal types, tariffs, 1 bloc | All deal types, more blocs |
| About 40 events, 4 advisers | Large event library |
| Rule-based AI | Language-model negotiation |
| Single player | Cooperative and 20-seat mock UN |

**Build order**

1. **Headless simulation (Python).** Model the world, six nations, emissions, and energy mix with no interface. Run bots through it to check that both clean and fossil strategies are viable and that the score formula creates real tension.
2. **Balance harness.** Automated runs across countries and strategies to tune the curves, as with the Convoy agent sandbox.
3. **Minimal interface.** Map, resource bar, and turn flow, with no art polish.
4. **Deals.** Four deal types and AI acceptance logic.
5. **Events and advisers.** About 40 events with chains.
6. **Stocktake, scoring, and endings.** The full loop end to end.
7. **Playtest.** Run sessions with classmates and note where players stop caring.
8. **Then:** more countries, then the mock UN.

## Where to go deeper and open questions

The design depends most on four areas that need more work before building, and the open questions below.

**Where to go deeper**

1. **The deal engine.** How an AI nation values a deal (its agenda, trust, currency risk, and alternatives) decides whether deals feel smart or arbitrary. This is the highest-leverage system to design.
2. **Fair share of the carbon budget.** The rule is based on emissions and updates through the game. Still to design: how the share updates each quarter, and how clearly players can see their standing against it.
3. **Calibration against real data.** Decide how closely country cards track reality and which datasets you will use, since every country's difficulty depends on these numbers.
4. **Fun versus teaching.** A game that teaches accurately is slower than one that is fun, so decide what you will give up when they conflict.

**Decided**

- Countries start from their approximate 2025 economic and energy state.
- The game runs 2025 to 2050 at one turn per quarter, 100 turns, with save and resume, quiet turns fast-forwarded, and a shorter annual mode for classes.
- The four C's are guiding principles for building the game, not a player-facing frame.
- Leaders are abstract government cards; no real people.
- Tone is educational, with the fun coming from strategic push and pull.
- Web first.
- The EU is one player for now.
- AI nations are deterministic, with no LLM for now, and follow their real stated climate pledges directionally, not exactly. *(Changed 2026-11-07: they follow assumed target paths based on each nation's general policy stance over the last 10-20 years, not real pledges; see `data/targets.yaml`.)*
- GDP is a single number that funds capital, the master lever spent on building, research, influence, and deals.
- Fair share of the carbon budget is based on emissions and updates through the game.
- Bonus points for first to net zero, the largest emissions reduction, the breakthrough technology the world adopts most, and the most impactful trade deal for emissions.
- Unused action slots build up, with no cap, because late in the game there is little time left to use them.
- Deal emissions credit is split: host 1 to 1, financier about 0.75 to 1.
- Technology adoption is measured by the share of nations using it, and the inventor earns a financial boost, a tech boost, and credit at about 0.6 to 1.

**Defaults picked by Claude, easy to change**

- Bonuses are flat points on top of the score, because they are easier to read and balance than a multiplier stacked on the score.
- Annual mode runs the same rules at four quarters per turn, so there is one ruleset to build and balance.
- The first simulation models each country at national level, with regions added later.

**Decided 2026-11-08 (M4 planning, with the user)**

- Clean slate on diplomacy: every pair of nations starts at neutral trust with no tariffs or sanctions. Nations keep their real 2025 energy state and general economic output; no real-world trade restrictions carry over.
- Trade is a major system: goods trade between all nations (gravity model on real export openness) and a clean-tech equipment trade (solar, wind, batteries) from manufacturers, starting from approximate real 2024 manufacturing shares.
- Carbon credits trade on a market whose price is set by supply and demand in the game. Credits score less than real reductions: real cuts 1.0, directly financed projects 0.75, other nations using your technology 0.6, purchased credits 0.25 (placeholders). Buying credits is a fallback move. Nations below their fair share earn their surplus as sellable credits.
- The climate goal is 1.5 degC: fair shares come from the remaining 1.5 degC budget, and the World Multiplier is 1.0 at 1.5 degC. Excellent global play should be able to bring warming below its 2025 level by 2050, through deep cuts, falling short-lived (non-CO2) warming, and late-game carbon removal.
- Domestic economy carries as much weight as trade: taxes, tax credits, supply chains and manufacturing, employment and retraining, and industrial policy (M4b).
- Elections every four years for the player, in every playable nation. Losing one does not end the game: an opposition (the AI with the nation's default personality) governs for one term, then the player returns. AI-led nations keep the same leaders. Fallen Government (stability collapse) still ends the game.
- The Nation Index gains a fifth component, climate contribution, scored with the credit weights above.
- Fair share at the stocktake: every nation's allowance follows the same 1.5 degC-consistent pathway applied to its own 2025 emissions (about halved by 2030, zero by 2050), rather than a share of the remaining global budget, which runs out around 2030. Credits are earned for emissions below the same pathway.

**To tune in the simulation**

- [ ] Credit ratios: host 1 to 1, financier 0.75 to 1, technology inventor 0.6 to 1.
- [ ] Bonus size for each achievement.
- [ ] Whether annual mode needs its own balance pass.
