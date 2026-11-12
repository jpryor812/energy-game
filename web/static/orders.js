// How each order looks in the orders drawer: an icon, one short line, and what it gives and
// takes. The full rules stay one click away (the catalogue text); these are the summary layer.
// The page still decides nothing: costs and refusals come from the server's check.

// gives / takes use a small vocabulary of icons
export const FX = {
  power: ["⚡", "Power"], clean: ["🌱", "Less CO2"], warming: ["🌡", "Less warming"], capital: ["💰", "Capital"],
  growth: ["📈", "Growth"], approval: ["🙂", "Approval"], votes: ["🗳", "Votes"], jobs: ["👷", "Jobs"],
  trust: ["🤝", "Trust"], influence: ["🎖", "Influence"], prices: ["💲", "Energy prices"], exports: ["📦", "Exports"],
  speed: ["⏩", "Faster building"], tech: ["⚗", "Technology"], credit: ["🏅", "Climate credit"], safety: ["🛡", "Less damage"],
  demand: ["📉", "Less demand"], trade: ["🚢", "Trade"], revenue: ["💰", "Revenue"],
  pc: ["🏛", "Political capital"], relief: ["💲", "Softer price rises"], buildcost: ["💲", "Build costs"],
  cheaper: ["🏷", "Cheaper equipment"], finance: ["🏦", "Cheaper deal finance"],
};

export const ORDERS = {
  // build
  build_capacity: { icon: "⚡", line: "Build power plants of one kind.", gives: ["power"], note: "Clean sources also cut CO2 once fossil plants run less." },
  build_grid_storage: { icon: "🔋", line: "Grid and storage so more wind and solar can be used.", gives: ["power", "clean"] },
  retire_capacity: { icon: "🚫", line: "Close plants now.", gives: ["clean"], takes: ["pc", "approval", "jobs", "power"] },
  retrofit_ccs: { icon: "🫧", line: "Capture 90% of the CO2 from coal or gas plants.", gives: ["clean"] },
  build_removal: { icon: "🌀", line: "Machines that pull CO2 out of the air.", gives: ["clean"], takes: ["power"] },
  build_factory: { icon: "🏗", line: "A factory line for solar, wind or batteries.", gives: ["jobs", "exports", "cheaper"] },
  // policy
  set_carbon_price: { icon: "🏷", line: "Put a price on each tonne of CO2.", gives: ["revenue", "clean"], takes: ["prices", "pc"] },
  rebate: { icon: "💸", line: "Hand carbon revenue back to households.", gives: ["relief"], takes: ["revenue"] },
  set_subsidy: { icon: "🎁", line: "Pay part of a source's cost so the market builds more.", gives: ["power"], takes: ["capital"] },
  set_tax_credit: { icon: "🧾", line: "Pay per unit of power made or kit sold.", gives: ["power", "jobs"], takes: ["capital"] },
  set_tax_rate: { icon: "🏛", line: "Raise or cut taxes.", gives: ["capital"], takes: ["growth", "votes", "pc"] },
  set_fossil_ban: { icon: "⛔", line: "Stop all new fossil plants.", gives: ["clean"], takes: ["pc"] },
  set_permitting: { icon: "📜", line: "Faster permits for plants, grid and storage.", gives: ["speed"], takes: ["votes", "pc"] },
  set_activity_cap: { icon: "🏭", line: "Cap energy-heavy industry.", gives: ["demand", "clean"], takes: ["growth", "approval", "pc"] },
  set_domestic_content: { icon: "🏠", line: "Require equipment made at home.", gives: ["jobs"], takes: ["buildcost"] },
  // treasury
  invest_efficiency: { icon: "💡", line: "Use less energy for each dollar of GDP.", gives: ["demand", "clean"] },
  electrification_program: { icon: "🔌", line: "Electrify transport, heat and industry.", gives: ["clean"] },
  fund_retraining: { icon: "🎓", line: "Retrain fossil workers.", gives: ["votes"] },
  adaptation_spend: { icon: "🛡", line: "Protect against climate damage.", gives: ["safety"] },
  methane_abatement: { icon: "💨", line: "Plug methane leaks.", gives: ["warming"] },
  invest_research: { icon: "🔬", line: "Make an existing source cheaper for you.", gives: ["tech", "growth"] },
  buy_influence: { icon: "🎖", line: "Turn capital into influence for talks.", gives: ["influence"] },
  // research
  fund_research: { icon: "⚗", line: "Fund a technology on the tree.", gives: ["tech"] },
  buy_license: { icon: "📄", line: "Buy a finished technology from another nation.", gives: ["tech"] },
  set_license_price: { icon: "🏷", line: "Sell licences to your technology.", gives: ["capital"] },
  // diplomacy
  propose_deal: { icon: "🤝", line: "Offer a clean-energy deal to another nation.", gives: ["credit", "trust", "revenue"] },
  respond_deal: { icon: "✉", line: "Answer an offer made to you." },
  exit_deal: { icon: "🚪", line: "Leave a power deal, paying its penalty.", takes: ["capital"] },
  open_talks: { icon: "💬", line: "Hold talks to raise a nation's trust in you.", gives: ["trust"], takes: ["influence"] },
  set_tariff: { icon: "🧱", line: "Tariff a nation's goods.", gives: ["revenue"], takes: ["trust", "trade"] },
  lift_tariff: { icon: "🔓", line: "Remove a tariff you set.", gives: ["trust", "trade"] },
  join_bloc: { icon: "🌐", line: "Join the carbon club (needs a $25/t carbon price).", gives: ["finance"] },
  leave_bloc: { icon: "↩", line: "Leave the carbon club." },
  make_pledge: { icon: "🎯", line: "Promise an emissions cut by a year.", note: "Breaking it costs trust with everyone." },
  buy_credits: { icon: "🛒", line: "Buy carbon credits (a quarter of a real cut).", gives: ["credit"], takes: ["capital"] },
  sell_credits: { icon: "🪙", line: "Sell carbon credits you hold.", gives: ["capital"] },
  // the world
  finance_region: { icon: "🌍", line: "Lend for clean power in a region abroad.", gives: ["credit", "trust", "clean"] },
  pledge_to_event: { icon: "🆘", line: "Back an open event's fund (refunded if it falls short).", gives: ["credit", "trust"] },
  fund_forests: { icon: "🌳", line: "Pay into the global forest fund.", gives: ["clean", "credit"] },
};

export const SOURCE_ICON = {
  solar: "☀️", onshore_wind: "🌬", offshore_wind: "🌊", hydro: "💧", nuclear: "⚛️", smr: "⚛️",
  advanced_fission: "⚛️", fusion: "✨", geothermal: "🌋", enhanced_geothermal: "🌋", bioenergy: "🌿",
  gas: "🔥", coal: "🪨", oil: "🛢", grid: "🗼", storage: "🔋", long_duration_storage: "🔋",
  electrolysers: "💧", wind: "🌬", carbon_removal: "🌀",
};

export const DEAL_ICON = { equipment_on_credit: "🏗", climate_loan: "🏦", energy_as_a_service: "🔌", equity_for_energy: "📊" };
export const DEAL_LINE = {
  equipment_on_credit: "You build the plant; they repay cost plus interest.",
  climate_loan: "You lend cash; they build and repay with interest.",
  energy_as_a_service: "You own the plant; they pay for its power.",
  equity_for_energy: "You take a share of the plant's profit.",
};
