// Orders open in waves over the first two years of office, so the first quarter offers a
// handful of clear choices instead of all 39 at once (decided with the user 2026-11-12). This
// paces the web interface only: the simulation, the AI nations and the text game allow every
// order from the start, and a player can open them all at once under Advice.

export const ALWAYS = ["respond_deal", "exit_deal", "pledge_to_event"]; // answered when they come up

export const WAVES = [
  {
    turn: 0, who: "chief", title: "Your first orders",
    types: ["build_capacity", "build_grid_storage", "set_carbon_price", "rebate", "set_subsidy", "invest_efficiency", "fund_research", "open_talks"],
  },
  {
    turn: 2, who: "treasury", title: "New orders: programmes and partners",
    line: "Programmes that protect jobs and growth, and the first deals and clubs abroad.",
    types: ["retire_capacity", "set_tax_rate", "electrification_program", "fund_retraining", "propose_deal", "buy_influence", "join_bloc", "leave_bloc"],
  },
  {
    turn: 4, who: "foreign", title: "New orders: the wider world",
    line: "Finance for the regions, pledges and carbon credits, tariffs, licences, factories and more ways to cut methane.",
    types: ["finance_region", "make_pledge", "buy_credits", "sell_credits", "set_tariff", "lift_tariff", "buy_license", "set_license_price", "set_tax_credit", "methane_abatement", "adaptation_spend", "build_factory"],
  },
  {
    turn: 8, who: "climate", title: "New orders: bold measures",
    line: "The strongest levers: a fossil ban, permitting reform, carbon capture and removal, forests and a cap on heavy industry.",
    types: ["retrofit_ccs", "build_removal", "set_fossil_ban", "set_permitting", "set_activity_cap", "set_domestic_content", "fund_forests", "invest_research"],
  },
];

const OPENS = Object.fromEntries(WAVES.flatMap((w) => w.types.map((t) => [t, w.turn])));

/** The turn an order opens (0 for orders that are always open or not paced). */
export const opensAt = (type) => (ALWAYS.includes(type) ? 0 : OPENS[type] ?? 0);

/** Whether an order is open at this turn; `all` opens everything. */
export const isOpen = (type, turn, all) => all || opensAt(type) <= turn;
