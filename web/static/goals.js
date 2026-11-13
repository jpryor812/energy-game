// First-year goals (onboarding, decided with the user 2026-11-12): instead of a lecture, a short
// checklist in three stages, each a few things worth doing with a line on why. Goals tick off
// from what the player has actually done (or its state); the next stage opens when one is done.
// The research behind it: fewer choices at first, objectives that say why, and help that appears
// when a thing is first met (docs/ASSUMPTIONS.md).
//
// g: { sc (the screen), played (Set of order kinds played), seen (Set of screens opened) }

export const STAGES = [
  {
    id: "first_year", title: "Your first year", who: "chief",
    goals: [
      { id: "clean", t: "Build clean power", show: "build",
        why: "Solar or wind for a sliver of your energy adds clean supply and jobs.",
        planned: (a) => a.type === "build_capacity" && a.clean, done: (g) => g.played.has("build_capacity:clean") },
      { id: "carbon", t: "Put a price on carbon", show: "carbon",
        why: "Even $10 a tonne steers the market toward clean power. A rebate softens prices.",
        planned: (a) => a.type === "set_carbon_price" && a.level > 0, done: (g) => g.sc.energy.carbon_price > 0 },
      { id: "quarter", t: "End your first quarter", show: "endturn",
        why: "Your orders happen, then the world moves.", done: (g) => g.sc.turn >= 1 },
    ],
  },
  {
    id: "settle", title: "Settle in", who: "foreign",
    goals: [
      { id: "trade", t: "Propose a trade", show: "talks",
        why: "Click a nation, open talks, make an offer. Trades build clean power abroad and earn Impact.",
        planned: (a) => a.type === "propose_deal", done: (g) => g.played.has("propose_deal") || g.sc.deals.active.length > 0 },
      { id: "research", t: "Fund research", show: "research",
        why: "Cheaper solar and batteries now, new kinds of power later.",
        planned: (a) => a.type === "fund_research", done: (g) => g.played.has("fund_research") },
      { id: "vote", t: "Check your vote", show: "vote",
        why: "Losing an election ends the game. Aim for 54% or more.", done: (g) => g.seen.has("vote") },
    ],
  },
  {
    id: "lead", title: "Lead abroad", who: "climate",
    goals: [
      { id: "region", t: "Finance clean power in a region", show: "world",
        why: "The rest of the world counts toward warming and cuts slowly unless helped.",
        planned: (a) => a.type === "finance_region", done: (g) => g.played.has("finance_region") },
      { id: "club", t: "Join the carbon club", show: "carbon",
        why: "A carbon price of $25 or more lets you join: cheaper finance among members.",
        planned: (a) => a.type === "join_bloc", done: (g) => g.sc.world.club.includes(g.sc.country) },
      { id: "impact", t: "Reach Impact 55", show: "realm",
        why: "Impact is three quarters of your score: cuts at home and abroad, for your size.",
        done: (g) => ((g.sc.score || {}).impact || 0) >= 55 },
    ],
  },
];

/** The first stage with a goal still open, and how far through it the player is. */
export function currentStage(g) {
  for (const [i, s] of STAGES.entries()) {
    const done = s.goals.filter((x) => safe(() => x.done(g))).length;
    if (done < s.goals.length) return { stage: s, index: i, done };
  }
  return null;
}

export const isDone = (goal, g) => safe(() => goal.done(g));
const safe = (f) => { try { return !!f(); } catch { return false; } };
