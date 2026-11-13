// The advisors: short tips that teach the game as it unfolds, Civilization-style. Each tip says
// who gives it, when it applies, a few sentences with live whole numbers, optional questions
// with answers, and a "Show me" that opens or highlights the right part of the screen.
//
import { WAVES } from "./unlocks.js";
import { ORDERS } from "./orders.js";

// Tips teach; they never decide. Everything they say is taken from docs/PLAYTEST.md and the
// order catalogue; numbers come from the screen.

export const ADVISORS = {
  chief: { name: "Chief of Staff", look: { skin: "#c58c63", hair: "#2a2522", style: "short", suit: "#283244", neck: "tie", glasses: true, scene: "city" }, color: "#16a34a" },
  treasury: { name: "Treasury Advisor", look: { skin: "#f0c9a8", hair: "#b5793f", style: "bun", suit: "#3a3530", neck: "collar", scene: "city" }, color: "#c99a06" },
  energy: { name: "Energy Advisor", look: { skin: "#8d5a3b", hair: "#1c1a19", style: "bob", suit: "#2d3a33", neck: "scarf", scene: "solar" }, color: "#e8590c" },
  climate: { name: "Climate Advisor", look: { skin: "#e3b48d", hair: "#5b3a24", style: "sidepart", suit: "#26402f", neck: "open", scene: "forest" }, color: "#2f9e44" },
  foreign: { name: "Foreign Advisor", look: { skin: "#d9a77c", hair: "#9a9690", style: "receding", suit: "#2a2f3d", neck: "tie", glasses: true, scene: "port" }, color: "#1c7ed6" },
};

// h: { sc (the screen), world, money, whole, pct, nation, income, solar1, allOrders }

// A wave of new orders (web/static/unlocks.js), announced by the advisor who knows them best.
const niceName = (t) => t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
function unlockTip(turn) {
  const w = WAVES.find((x) => x.turn === turn);
  return {
    id: `unlock_${turn}`, who: w.who, show: `orders_${turn}`, title: w.title,
    when: (h) => !h.allOrders && h.sc.turn >= turn,
    body: () => `${w.line} Each is now in its menu on the left:
      <div class="tip-orders">${w.types.map((t) => `<span class="locked-chip">${(ORDERS[t] || {}).icon || "◆"} ${niceName(t)}</span>`).join("")}</div>`,
  };
}

// Quarters until the next election ("2028Q4" against the current "2025Q2").
const qn = (label) => { const m = /(\d{4})\s*Q(\d)/.exec(label || ""); return m ? +m[1] * 4 + +m[2] : null; };
const toElection = (h) => { const a = qn(h.sc.election.next), b = qn(h.sc.quarter); return a != null && b != null ? a - b : null; };
export const TIPS = [
  {
    id: "welcome", who: "chief", when: () => true, show: "realm",
    title: "Welcome to office",
    body: (h) => `You lead <b>${h.nation}</b> from 2025 to 2049. Each turn is one quarter, 100 in all.
      Warming is <b>${h.sc.world.warming.toFixed(2)} °C</b> now. If it reaches <b>${h.sc.world.collapse_at} °C</b>, the game
      ends and every nation loses. Keep the world below it and the world wins; then the nation that did
      the <b>most to cut emissions</b>, for its size, is Champion. Your <b>goals</b> on the right show where to start.`,
    ask: [
      ["How is the score worked out?", "Mostly impact (three quarters): the CO2 you cut at home, or helped cut abroad, as a share of your own 2025 emissions. The rest is prosperity: growth, reliable energy, approval, prices and clean-tech industry against your own start. Harder countries get a multiplier."],
      ["How can I lose?", "Three ways, each ending the game with a score of 0: warming reaching 2 °C (averaged over a year), losing an election (every four years, the first in 2028 Q4), or your government falling when stability drops too low after blackouts and low approval."],
      ["Why not just cut everything at once?", "Voters judge growth, jobs and prices. Cut too fast and you lose office, and the game. The winner cuts the most while staying in power."],
    ],
  },
  {
    id: "resources", who: "treasury", when: (h) => h.sc.turn >= 1, show: "resources",
    title: "What you have to spend",
    body: (h) => `Your resources run along the top. <b>💰 Capital</b> is ${h.money(h.sc.resources.capital)}, earning about
      ${h.money(h.income / 4)} a quarter: it pays for building, research and deals. An order you plan
      takes its cost off at once, and gives it back if you remove it. <b>🏛 Political capital</b> is
      ${h.whole(h.sc.resources.political_capital)}, earning about 4 a year (more when approval is high): it pays for unpopular
      moves such as a carbon price or closing plants. Each quarter you can give <b>3 orders at home and 2 abroad</b>;
      unused ones carry over, up to 6 and 4.`,
    ask: [
      ["Where does capital come from?", "Mostly an energy budget of 2% of GDP a year, plus fuel exports and carbon revenue, less tax cuts, tax credits and interest. Hover Capital in the top bar for the breakdown."],
      ["What is influence?", "Your standing abroad, bought with capital. You never need it to trade, but the more you hold, the more nations offer you deals and the easier they are to persuade. Talks spend it, and unused influence fades slowly."],
    ],
  },
  {
    id: "market", who: "energy", when: (h) => h.opened.has("build"), show: "build",
    title: "The market builds; you steer",
    body: (h) => `Private investors already build power every quarter to keep up with demand, choosing the cheapest
      source. Today <b>${h.pct(h.sc.energy.clean_share)}</b> of your supply is clean. Your own builds come on top.
      A good first move is <b>solar</b>: it is usually the cheapest and comes online in a year.
      ${h.solar1 ? `Solar for 1% of your energy costs about <b>${h.money(h.solar1)}</b>; you have ${h.money(h.sc.resources.capital)}.` : ""}
      Open Build, choose Build capacity, pick Solar and a size you can afford: the card shows the cost before you order.`,
    ask: [
      ["Why not build only clean power at once?", "Capital is limited and voters judge growth, jobs and prices. Players who spent everything on clean power in the first term often lost the 2028 election."],
      ["Can wind and solar run everything?", "Only so much variable power can be used. Grid and storage (Build) and electrification (Treasury) raise that limit."],
    ],
  },
  {
    id: "carbon", who: "climate", when: (h) => h.opened.has("policy"), show: "carbon",
    title: "Steer the market with a carbon price",
    body: (h) => `A carbon price makes fossil plants dearer, so the market builds clean ones, and it raises revenue.
      It also raises energy prices, which voters feel, and raising it costs political capital (1 for every $10).
      Your price is <b>$${h.whole(h.sc.energy.carbon_price)}/t</b>. Start modest; a <b>rebate</b> hands the revenue back
      to households and softens the price rise.`,
    ask: [
      ["What else steers the market?", "Subsidies now, under Policy. Tax credits and a ban on new fossil plants open later in your term."],
      ["Why $25 a tonne?", "It is the entry price of the carbon club, which gives cheaper deal finance among members."],
    ],
  },
  {
    id: "endturn", who: "chief", when: () => false, show: "endturn", // the first-year goals cover it
    title: "End the quarter",
    body: () => `Your orders wait in <b>This quarter's orders</b> on the right, and each is checked as you add it.
      When you are ready, press <b>End quarter</b>. Your orders happen in the listed order, then the world moves:
      the market builds, the economy grows, warming updates and the other nations act.`,
    ask: [["What does Skip a year do?", "Ends four quarters in a row with no orders. Handy once your policies are set."]],
  },
  {
    id: "dispatch", who: "chief", when: (h) => h.sc.turn >= 1, show: "modes",
    title: "Reading the world",
    body: () => `Each quarter ends with a dispatch of what happened. The <b>map modes</b> on the left recolour the
      world by emissions, clean share, trust in you, the carbon club, score and events. Click any nation or region
      for its panel and the moves you can make toward it.`,
  },
  {
    id: "offers", who: "foreign", when: (h) => h.sc.deals.inbox.length > 0, show: "outliner",
    title: "You have an offer",
    body: (h) => `${h.sc.deals.inbox.length === 1 ? "A nation has" : "Nations have"} offered you a clean-energy deal: they pay to
      build a plant in your country, and you repay or share its output. Offers wait in <b>Offers to you</b> on the
      right. Press Answer to see the terms, then accept, refuse or counter. Offers expire after a few quarters.`,
    ask: [["Is accepting a good idea?", "It adds clean power without spending your capital now, but you owe repayments or a share. A nation can host deals up to half its energy demand."]],
  },
  unlockTip(2),
  {
    id: "research", who: "energy", when: (h) => h.sc.turn >= 2, show: "research",
    title: "Research the future",
    body: () => `The research tree makes solar, batteries and wind cheaper and unlocks small reactors, advanced
      fission and fusion. More funding gets a technology done sooner, but never faster than its minimum time.
      Once any nation finishes one, it costs everyone else less to research, and you can buy or sell licences.`,
  },
  {
    id: "diplomacy", who: "foreign", when: (h) => h.sc.turn >= 3, show: "diplomacy",
    title: "Trust opens doors",
    body: () => `Trust decides who deals with you. <b>Talks</b> raise a nation's trust (5 influence; buy influence
      under Treasury). Influence you hold also draws offers your way and makes nations easier to persuade. <b>Deals</b> build clean power abroad, earn returns and climate credit. The <b>carbon
      club</b> (a carbon price of $25/t or more) gives cheaper deal finance and lets members tariff laggards.`,
  },
  unlockTip(4),
  {
    id: "regions", who: "climate", when: (h) => h.sc.turn >= 4, show: "world",
    title: "The rest of the world",
    body: () => `The softly tinted regions are not playable, but their emissions count toward warming, and they cut
      slowly unless helped. <b>Finance region</b> lends cheaply for solar or wind there: it costs you a little,
      earns climate credit for the cut and wins the region's trust. Each region can take only so much a year.`,
  },
  unlockTip(8),
  {
    id: "event", who: "climate", when: (h) => h.sc.events.open.length > 0, show: "event",
    title: "A country faces a choice",
    body: (h) => `${h.sc.events.open.length === 1 ? "An event is" : "Events are"} open (the ⚠ alert at the top). Any nation can
      pledge to a shared fund. If it reaches its target by the deadline the bad outcome is avoided and those who paid
      gain trust and climate credit. If not, every pledge is refunded, so pledging is safe. Other nations rarely
      fill a fund alone.`,
  },
  {
    id: "vote", who: "chief", when: (h) => h.sc.election.expected_vote != null, show: "vote",
    title: "Watch your vote",
    body: (h) => `Your expected vote is now <b>${h.whole(h.sc.election.expected_vote * 100)}%</b> for the election in
      ${h.sc.election.next}. You need 50%; aim for <b>54%</b>, because a random swing can take away 4 points. Growth
      matters most, then jobs, energy prices and tax rises, averaged over the term, so act early.
      ${h.sc.election.expected_vote < 0.5 ? "<b>At this level you would lose today.</b> There is time, but start now." : ""}`,
    ask: [["How do I raise it?", "A rebate on carbon revenue, a lower carbon price, retraining fossil workers, avoiding blackouts and cutting taxes all help. Building and factories add jobs. Hover Next vote for the breakdown."]],
  },
  {
    id: "vote_low", who: "chief", show: "vote",
    when: (h) => h.sc.election.expected_vote != null && h.sc.election.expected_vote < 0.52 && toElection(h) != null && toElection(h) <= 6,
    title: "The vote is slipping",
    body: (h) => `The election is ${toElection(h)} quarters away and your expected vote is <b>${h.whole(h.sc.election.expected_vote * 100)}%</b>.
      Below 50% you lose office and the game. Changes take quarters to show in the term average, so act now: a carbon rebate, retraining, a pause on
      closing plants or price rises, or a tax cut.`,
  },
  {
    id: "warming_high", who: "climate", when: (h) => h.sc.world.warming_year >= h.sc.world.collapse_warning, show: "world",
    title: "Close to the line",
    body: (h) => `Warming has averaged <b>${h.sc.world.warming_year.toFixed(2)} °C</b> over the year. At <b>${h.sc.world.collapse_at} °C</b> the game ends and every
      nation loses, including you. Your own cuts are not enough now: finance clean power in the regions, fill
      event funds and push others with talks and the carbon club.`,
  },
  {
    id: "blackout", who: "energy", when: (h) => h.sc.energy.shortfall_share > 0, show: "build",
    title: "Blackouts",
    body: (h) => `<b>${h.whole(h.sc.energy.shortfall_share * 100) || "Under 1"}%</b> of demand went unmet. Blackouts drag growth and
      erode stability, and if stability falls too low the government falls. Build fast: solar and gas take a year
      or two, storage a few months.`,
  },
  {
    id: "slots_full", who: "treasury", when: (h) => h.sc.turn >= 2 && (h.sc.resources.slots.domestic ?? 0) >= 6, show: "build",
    title: "Orders going to waste",
    body: () => `You have banked the most home orders you can hold (6). Unused orders from now on are lost, so
      put them to work: build, set policy or fund a programme.`,
  },
];
