// Energy Game - local web interface (W1). Every number shown comes from the server (sim.view);
// this file holds no game rules.
import { WorldMap, MODES } from "./map.js";
import { VIGNETTE } from "./vignettes.js";
import { PLAYABLE_COLOR, PERSONALITY, SOURCE_COLOR, nationTint, NATION_TINT_FAMILY, REGION_TINT } from "./owners.js";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const S = { meta: null, data: null, plan: [], checks: [], map: null, menu: null, panel: null, lastRegions: null };

// ---------- formatting ----------

const money = (t) => {
  if (t == null || Number.isNaN(t)) return "-";
  const b = t * 1000;
  if (Math.abs(b) >= 1000) return `$${(b / 1000).toFixed(2)} tn`;
  if (Math.abs(b) >= 10) return `$${b.toFixed(0)} bn`;
  return `$${b.toFixed(1)} bn`;
};
const pct = (x, d = 0) => (x == null ? "-" : `${(x * 100).toFixed(d)}%`);
const spct = (x, d = 1) => (x == null ? "-" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
const num = (x, d = 1) => (x == null ? "-" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const nice = (s) => String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const nationName = (id) => (S.meta.nations[id] ? S.meta.nations[id].name.replace(/\s*\(.*\)/, "") : id);
const regionName = (id) => S.meta.regions[id] || id;
const colorOf = (id) => PLAYABLE_COLOR[id] || (NATION_TINT_FAMILY[id] ? nationTint(id) : "#888");
const crest = (id, large = false) =>
  `<div class="crest ${large ? "large" : ""}" style="background:linear-gradient(160deg, ${d3.color(colorOf(id)).brighter(0.4)}, ${d3.color(colorOf(id)).darker(0.6)})">${esc(id)}</div>`;

// ---------- API ----------

async function api(path, body) {
  const busy = $("#busy");
  const slow = setTimeout(() => busy.classList.remove("hidden"), 250);
  try {
    const res = await fetch(path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  } finally {
    clearTimeout(slow);
    busy.classList.add("hidden");
  }
}

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), ms);
}

// ---------- tooltip ----------

function tip(html) { return `data-tip="${esc(html)}"`; }
const hideTip = () => $("#tooltip").classList.add("hidden");
document.addEventListener("click", hideTip, true);
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  if ($("#windows").innerHTML) { const x = $("#win-x"); if (x) x.click(); }
  else if (S.panel) closePanel();
});
document.addEventListener("mouseover", (ev) => {
  const el = ev.target.closest("[data-tip]");
  const box = $("#tooltip");
  if (!el) { box.classList.add("hidden"); return; }
  box.innerHTML = el.dataset.tip;
  box.classList.remove("hidden");
});
document.addEventListener("mousemove", (ev) => {
  const box = $("#tooltip");
  if (box.classList.contains("hidden")) return;
  const w = box.offsetWidth, h = box.offsetHeight;
  box.style.left = `${Math.min(ev.clientX + 16, innerWidth - w - 8)}px`;
  box.style.top = `${Math.min(ev.clientY + 16, innerHeight - h - 8)}px`;
});
const ttTable = (title, rows, note) =>
  `<div class="tt-title">${esc(title)}</div><table>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join("")}</table>${note ? `<div class="muted" style="margin-top:4px">${esc(note)}</div>` : ""}`;

// ---------- boot ----------

async function boot() {
  S.meta = await api("/api/meta");
  S.map = new WorldMap($("#map"), {
    hover: mapHover,
    select: (kind, id) => (kind === "nation" ? openNation(id) : openRegion(id)),
    event: (rid) => openRegion(rid),
  });
  await S.map.load(S.meta);
  if (S.meta.current) {
    setData(await api("/api/state"));
  } else {
    newGameWindow();
  }
}

function setData(data) {
  S.data = data;
  for (const id of ["topbar", "outliner", "mapmodes", "menubar", "endturn", "legend"]) $(`#${id}`).classList.remove("hidden");
  S.map.update(data.world);
  renderAll();
  checkPlan();
}

function renderAll() {
  renderTopbar();
  renderAlerts();
  renderOutliner();
  renderModes();
  renderMenubar();
  renderEndturn();
  if (S.panel) S.panel();
}

// ---------- top bar ----------

function renderTopbar() {
  const sc = S.data.screen, me = sc.country, r = sc.resources;
  $("#realm-crest").outerHTML = `<div id="realm-crest">${crest(me)}</div>`;
  $("#realm-name").textContent = nationName(me);
  const diff = S.meta.nations[me].difficulty.replace(/_/g, " ");
  $("#realm-sub").textContent = `${diff} country · ${sc.difficulty} world`;
  $("#realm").onclick = () => openRealm();

  const used = slotsUsed();
  const inc = r.income_per_year || {};
  const incRows = [
    ["Energy budget (2% of GDP)", money(inc.budget)], ["Fossil exports", money(inc.fossil_exports)],
    ["Carbon revenue", money(inc.carbon)], ["Tariffs", money(inc.tariffs)], ["Tax change", money(inc.tax)],
    ["Tax credits", money(inc.tax_credits)], ["Interest on new debt", money(inc.interest)],
  ].filter(([, v]) => v !== "$0.0 bn");
  const total = ["budget", "fossil_exports", "carbon", "tariffs", "tax", "tax_credits", "interest"]
    .reduce((a, k) => a + (inc[k] || 0), 0);
  const capTip = ttTable("Capital", [...incRows, ["<b>Income a year</b>", `<b>${money(total)}</b>`]],
    (inc.borrowed > 0 ? `Your tax cut also borrows ${money(inc.borrowed)} a year; new local debt so far ${money(r.local_debt_new)}. ` : "") +
    "Capital pays for building, research, deals and most programmes.");
  const pcTip = ttTable("Political capital", [], "Pays for unpopular moves: raising the carbon price, closing plants early, raising taxes, permitting reform, a fossil ban or an activity cap.");
  const slotTip = (k) => ttTable(`${nice(k)} actions`, [["Banked this quarter", r.slots[k] ?? 0], ["Planned", used[k] || 0]],
    k === "domestic" ? "3 a quarter, unused ones bank up to 6." : "2 a quarter, unused ones bank up to 4.");
  const res = [
    ["Capital", money(r.capital), `${money(total)} / yr`, capTip],
    ["Political cap.", num(r.political_capital, 1), "", pcTip],
    ["Influence", num(r.influence, 1), "for talks", ttTable("Influence", [], "Bought with capital; spent on diplomatic talks.")],
    ["Domestic", `${(r.slots.domestic ?? 0) - (used.domestic || 0)}/${r.slots.domestic ?? 0}`, "slots left", slotTip("domestic")],
    ["Diplomatic", `${(r.slots.diplomatic ?? 0) - (used.diplomatic || 0)}/${r.slots.diplomatic ?? 0}`, "slots left", slotTip("diplomatic")],
  ];
  $("#resources").innerHTML = res.map(([k, v, d, t]) =>
    `<div class="res" ${tip(t)}><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join("");

  const w = sc.world, s = sc.score, el = sc.election;
  const warmFrac = Math.max(0, Math.min(1, (w.warming - 1.3) / (2.0 - 1.3)));
  const champFrac = (w.champion_at - 1.3) / 0.7;
  const warmTip = ttTable("Global warming", [["Now", `${num(w.warming, 2)} °C`], ["Five years ago", w.warming_5y_ago ? `${num(w.warming_5y_ago, 2)} °C` : "-"],
    ["Champion needs", `≤ ${w.champion_at} °C and falling`], ["World multiplier", num(w.world_multiplier, 2)],
    ["World CO2", w.global_emissions ? `${num(w.global_emissions / 1000, 1)} Gt/yr` : "-"]],
  "Your score is multiplied by the World Multiplier: 1.0 at 1.5 °C, falling to 0.1 at 2.5 °C.");
  const scoreTip = s ? ttTable("Score", [["Score now", num(s.score_if_ended_now, 1)], ["Rank", `${s.rank} of 16`],
    ["Absolute index", num(s.absolute_index, 1)], ["Nation index", num(s.nation_index, 1)],
    ["× country difficulty", s.difficulty_multiplier], ["× world multiplier", num(s.world_multiplier, 2)],
    ...Object.entries(s.components).map(([k, v]) => [`  ${k}`, num(v, 2)])], `Ending if the game ended now: ${s.ending}`) : "";
  const vote = el.expected_vote;
  const voteTip = el.next ? ttTable(`Election ${el.next}`, [["Expected vote", vote == null ? "from next quarter" : num(vote, 3)],
    ["Needed", el.needed], ["Random swing", `± ${el.swing_range}`],
    ...Object.entries(el.parts || {}).map(([k, v]) => [nice(k), (v >= 0 ? "+" : "") + num(v, 3)])], "Aim for 0.54 or more: the swing can take away 0.04.") : "";
  $("#world-stats").innerHTML = `
    <div class="res gauge" ${tip(warmTip)}><div class="k">Warming</div><div class="v ${w.warming > w.champion_at ? "bad" : ""}">${num(w.warming, 2)} °C</div>
      <div class="bar"><div class="fill" style="width:${warmFrac * 100}%"></div><div class="tick" style="left:${champFrac * 100}%"></div></div></div>
    <div class="res" ${tip(voteTip)}><div class="k">Next vote</div><div class="v ${vote != null && vote < 0.52 ? "bad" : vote != null && vote < 0.54 ? "warn" : ""}">${vote == null ? "—" : num(vote * 100, 1) + "%"}</div><div class="d">${el.next || "none"}</div></div>
    <div class="res" ${tip(scoreTip)}><div class="k">Score</div><div class="v">${s ? num(s.score_if_ended_now, 1) : "—"}</div><div class="d">${s ? `rank ${s.rank} of 16` : ""}</div></div>`;
  $("#date").textContent = sc.quarter.replace("Q", " · Q");
  $("#turn-of").textContent = `turn ${sc.turn + 1} of ${sc.turns}`;
}

// ---------- alerts ----------

function renderAlerts() {
  const sc = S.data.screen, out = [];
  const inbox = sc.deals.inbox.filter((d) => d.can_answer);
  if (inbox.length) out.push({ ico: "✉", cls: "urgent", n: inbox.length, tip: ttTable("Deal offers await you", inbox.map((d) => [`${d.id} ${nice(d.type)}`, `from ${d.financier === sc.country ? d.host : d.financier}`])), go: () => openNation(inbox[0].financier === sc.country ? inbox[0].host : inbox[0].financier, "relations") });
  const evs = sc.events.open.filter((e) => !e.pledgers.includes(sc.country));
  if (evs.length) out.push({ ico: "⚠", cls: "urgent", n: evs.length, tip: ttTable("Event funds are open", evs.map((e) => [`${e.id} ${nice(e.type)}`, `${pct(e.pledged / e.target)} pledged`])), go: () => eventWindow(evs[0]) });
  const el = sc.election;
  if (el.next && el.quarters_away <= 6) out.push({ ico: "⚖", cls: el.expected_vote != null && el.expected_vote < 0.53 ? "danger" : "", tip: ttTable(`Election in ${el.quarters_away} quarters`, [["Expected vote", el.expected_vote == null ? "-" : num(el.expected_vote, 3)]]), go: () => openRealm("vote") });
  const left = (sc.resources.slots.domestic || 0) + (sc.resources.slots.diplomatic || 0) - Object.values(slotsUsed()).reduce((a, b) => a + b, 0);
  if (left >= 4) out.push({ ico: "⌛", cls: "", tip: ttTable("Unused action slots", [["Slots free this quarter", left]], "Slots bank only up to 6 domestic and 4 diplomatic."), go: () => openMenu("build") });
  if (sc.resources.political_capital >= 20) out.push({ ico: "✦", cls: "", tip: ttTable("Political capital is piling up", [["Unspent", num(sc.resources.political_capital, 0)]], "It pays for a higher carbon price, early closures, permitting reform, a fossil ban or tax rises."), go: () => openMenu("policy") });
  if (sc.over) out.push({ ico: "♛", cls: "urgent", tip: ttTable("The game is over", [["Ending", sc.score ? sc.score.ending : "-"]]), go: () => gameOverWindow() });
  const box = $("#alerts");
  box.innerHTML = out.map((a, i) => `<button class="alert ${a.cls}" data-i="${i}" ${tip(a.tip)}>${a.ico}${a.n ? `<span class="count">${a.n}</span>` : ""}</button>`).join("");
  box.querySelectorAll(".alert").forEach((b) => (b.onclick = () => out[+b.dataset.i].go()));
}

// ---------- outliner ----------

function slotOf(type) { return (S.meta.catalogue[type] || {}).slot; }
function slotsUsed() {
  const used = { domestic: 0, diplomatic: 0 };
  S.plan.forEach((a, i) => {
    const c = S.checks[i];
    if (!c || c.ok) used[slotOf(a.type)] = (used[slotOf(a.type)] || 0) + 1;
  });
  return used;
}

function describe(a) {
  const p = Object.entries(a).filter(([k]) => k !== "type")
    .map(([k, v]) => `${nice(k).toLowerCase()} ${typeof v === "number" ? +v.toPrecision(4) : v}`).join(", ");
  return `<b>${esc(nice(a.type))}</b>${p ? ` <span class="muted">${esc(p)}</span>` : ""}`;
}

function renderOutliner() {
  const sc = S.data.screen;
  const planRows = S.plan.length ? S.plan.map((a, i) => {
    const c = S.checks[i];
    const status = !c ? `<span class="muted">checking…</span>` : c.ok
      ? `<span class="good">✓</span> <span class="muted">${Object.entries(c.cost || {}).filter(([, v]) => v).map(([k, v]) => k === "capital" ? money(v) : `${num(v, 1)} ${k.replace("_", " ")}`).join(", ") || "free"}${c.note ? `; ${esc(c.note)}` : ""}</span>`
      : `<span class="bad">✗ ${esc(c.reason)}</span>`;
    return `<div class="plan-item"><div class="what">${describe(a)}<div class="why">${status}</div></div><button class="icon-btn" data-rm="${i}" title="Remove">✕</button></div>`;
  }).join("") : `<div class="muted" style="padding:6px 2px">Nothing planned. Choose actions from the menu below, or click a nation.</div>`;
  const inbox = sc.deals.inbox.map((d) => `<div class="plan-item"><div class="what"><b>${d.id}</b> ${nice(d.type)} <span class="muted">${esc(nationName(d.financier))} → ${esc(nationName(d.host))}, ${esc(d.terms.source || "")}</span>${d.can_answer ? "" : `<div class="why muted">answer from next quarter</div>`}</div>${d.can_answer ? `<button class="btn small" data-deal="${d.id}">Answer</button>` : ""}</div>`).join("");
  const evs = sc.events.open.map((e) => `<div class="plan-item"><div class="what"><b>${e.id}</b> ${nice(e.type)} in ${esc(regionName(e.region))}<div class="why muted">${pct(e.pledged / e.target)} of ${money(e.target)} · until ${e.deadline}${e.you_pledged ? ` · you ${money(e.you_pledged)}` : ""}</div></div><button class="btn small" data-ev="${e.id}">Open</button></div>`).join("");
  const notes = (sc.notices || []).filter((n) => !n.startsWith("Score ")).slice(0, 8).map((n) => `<div class="plan-item"><div class="what" style="font-size:12.5px">${esc(n)}</div></div>`).join("");
  $("#outliner").innerHTML = `
    <div class="sec-head"><span>This quarter's orders</span><span class="muted" style="font-family:var(--body);font-size:12px">${S.plan.length} planned</span></div>
    <div class="sec-body">${planRows}</div>
    ${inbox ? `<div class="sec-head"><span>Offers to you</span></div><div class="sec-body">${inbox}</div>` : ""}
    ${evs ? `<div class="sec-head"><span>Event funds</span></div><div class="sec-body">${evs}</div>` : ""}
    ${notes ? `<div class="sec-head"><span>Dispatches</span></div><div class="sec-body">${notes}</div>` : ""}`;
  $("#outliner").querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { S.plan.splice(+b.dataset.rm, 1); checkPlan(); }));
  $("#outliner").querySelectorAll("[data-deal]").forEach((b) => (b.onclick = () => dealWindow(b.dataset.deal)));
  $("#outliner").querySelectorAll("[data-ev]").forEach((b) => (b.onclick = () => eventWindow(sc.events.open.find((e) => e.id === b.dataset.ev))));
}

let checkSeq = 0;
async function checkPlan() {
  const seq = ++checkSeq;
  S.checks = [];
  renderOutliner(); renderTopbar(); renderEndturn();
  if (!S.plan.length || S.data.screen.over) return;
  const res = await fetch("/api/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actions: S.plan }) }).then((r) => r.json());
  if (seq !== checkSeq) return;
  S.checks = res.results || [];
  renderOutliner(); renderTopbar(); renderEndturn(); renderAlerts();
}

function addToPlan(act) {
  S.plan.push(act);
  checkPlan();
  toast(`Ordered: ${nice(act.type)}`);
}

// ---------- map modes, menu, end turn ----------

function renderModes() {
  $("#mapmodes").innerHTML = Object.entries(MODES).map(([k, m]) =>
    `<button class="mode ${S.map.mode === k ? "active" : ""}" data-mode="${k}" ${tip(ttTable(m.name, [], m.tip))}>${m.icon}</button>`).join("");
  $("#mapmodes").querySelectorAll(".mode").forEach((b) => (b.onclick = () => { S.map.setMode(b.dataset.mode); renderModes(); }));
  $("#legend").innerHTML = S.map.legend();
}

const MENU = {
  build: { ico: "⚒", lbl: "Build", title: "Build and retire", actions: ["build_capacity", "build_grid_storage", "retire_capacity", "retrofit_ccs", "build_removal", "build_factory"] },
  policy: { ico: "⚖", lbl: "Policy", title: "Laws and levers", actions: ["set_carbon_price", "rebate", "set_subsidy", "set_tax_credit", "set_tax_rate", "set_fossil_ban", "set_permitting", "set_activity_cap", "set_domestic_content"] },
  treasury: { ico: "⛁", lbl: "Treasury", title: "Programmes and spending", actions: ["invest_efficiency", "electrification_program", "fund_retraining", "adaptation_spend", "methane_abatement", "invest_research", "buy_influence"] },
  research: { ico: "⚗", lbl: "Research", title: "Research and licences", actions: ["fund_research", "buy_license", "set_license_price"] },
  diplomacy: { ico: "⚜", lbl: "Diplomacy", title: "Diplomacy and markets", actions: ["propose_deal", "open_talks", "set_tariff", "lift_tariff", "join_bloc", "leave_bloc", "make_pledge", "buy_credits", "sell_credits", "respond_deal", "exit_deal"] },
  world: { ico: "◍", lbl: "The World", title: "The rest of the world", actions: ["finance_region", "pledge_to_event", "fund_forests"] },
  ledger: { ico: "♛", lbl: "Ledger", title: "The ledger" },
};

function renderMenubar() {
  $("#menubar").innerHTML = Object.entries(MENU).map(([k, m]) =>
    `<button class="menu-btn ${S.menu === k ? "active" : ""}" data-menu="${k}"><span class="ico">${m.ico}</span><span class="lbl">${m.lbl}</span></button>`).join("");
  $("#menubar").querySelectorAll(".menu-btn").forEach((b) => (b.onclick = () => openMenu(b.dataset.menu)));
}

function renderEndturn() {
  const sc = S.data.screen;
  const bad = S.checks.filter((c) => c && !c.ok).length;
  $("#endturn").innerHTML = sc.over
    ? `<button class="btn primary big" id="end-btn">The game is over</button>`
    : `<div class="meta"><span>${sc.quarter}</span><span>${S.plan.length} orders${bad ? ` · <span class="bad">${bad} refused</span>` : ""}</span></div>
       <button class="btn primary big" id="end-btn" ${tip(ttTable("End the quarter", [], "Your orders resolve in the listed order, then the world moves: the market builds, the economy grows, warming updates, and the other nations act."))}>End quarter ▸</button>
       <div class="row" style="gap:6px"><button class="btn small" id="wait-1" style="flex:1">Skip a year</button><button class="btn small" id="text-view" style="flex:1">Text screen</button></div>`;
  $("#end-btn").onclick = () => (sc.over ? gameOverWindow() : endQuarter());
  if (!sc.over) {
    $("#wait-1").onclick = () => skipYear();
    $("#text-view").onclick = () => textWindow();
  }
}

async function endQuarter() {
  closeWindows();
  const before = S.data;
  const data = await api("/api/turn", { actions: S.plan });
  S.plan = []; S.checks = [];
  setData(data);
  afterQuarters([data.report], before);
}

async function skipYear() {
  if (S.plan.length && !confirm("Skipping a year discards this quarter's orders. Continue?")) return;
  const before = S.data;
  const data = await api("/api/wait", { quarters: 4 });
  S.plan = []; S.checks = [];
  setData(data);
  afterQuarters(data.reports, before);
}

function afterQuarters(reports, before) {
  const queue = [];
  const elections = reports.filter((r) => r.election);
  const opened = S.data.screen.events.open.filter((e) => !before.screen.events.open.some((b) => b.id === e.id));
  reports.length && queue.push(() => reportWindow(reports, () => next()));
  for (const r of elections) queue.push(() => electionWindow(r, () => next()));
  for (const e of opened) queue.push(() => eventWindow(e, () => next()));
  if (S.data.screen.over) queue.push(() => gameOverWindow());
  const next = () => { const f = queue.shift(); if (f) f(); else closeWindows(); };
  next();
}

// ---------- windows ----------

function closeWindows() {
  $("#windows").innerHTML = "";
  $("#veil").classList.add("hidden");
  S.menu = null;
  renderMenubar();
}

function openWindow({ title, body, foot = "", doc = false, wide = false, onClose }) {
  hideTip();
  $("#windows").innerHTML = `<div class="window ${doc ? "document" : "chrome"} ${wide ? "wide" : ""}">
      <div class="win-head"><h2>${title}</h2><button class="icon-btn" id="win-x" title="Close">✕</button></div>
      <div class="win-body">${body}</div>${foot ? `<div class="win-foot">${foot}</div>` : ""}</div>`;
  $("#veil").classList.remove("hidden");
  const close = () => { closeWindows(); if (onClose) onClose(); };
  $("#win-x").onclick = close;
  $("#veil").onclick = close;
  return $("#windows .window");
}

function reportWindow(reports, done) {
  const last = reports[reports.length - 1];
  const results = reports.flatMap((r) => r.results);
  const notes = reports.flatMap((r) => r.notices).filter((n) => !n.startsWith("Score "));
  const scoreNote = [...last.notices].reverse().find((n) => n.startsWith("Score "));
  const title = reports.length > 1 ? `${reports[0].quarter} to ${last.quarter}` : last.quarter;
  const win = openWindow({
    doc: true, title: `Dispatches, ${title.replace(/Q/g, " Q")}`, onClose: done,
    body: `${results.length ? `<h3>Your orders</h3><ul class="report-list">${results.map((r) => `<li>${r.ok ? "✓" : "✗"} ${describe(r.action)}${r.ok ? "" : ` <span style="color:#8c2f1f">— ${esc(r.reason)}</span>`}</li>`).join("")}</ul>` : ""}
      <h3>News from the ministries</h3>${notes.length ? `<ul class="report-list">${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : `<p class="muted">A quiet quarter.</p>`}
      ${scoreNote ? `<p class="muted" style="margin-top:10px">${esc(scoreNote)}</p>` : ""}`,
    foot: `<button class="btn primary" id="ok">Continue</button>`,
  });
  $("#ok", win).onclick = () => { closeWindows(); done && done(); };
}

function electionWindow(r, done) {
  const e = r.election;
  const won = e.event === "won";
  const win = openWindow({
    doc: true, title: `The ${r.quarter.slice(0, 4)} election`, onClose: done,
    body: `<div class="event-title">${won ? "The government is returned" : "The government falls at the polls"}</div>
      <p class="event-text">${won ? `Voters return your government with <b>${num(e.vote * 100, 1)}%</b> of the vote. A new four-year term begins; growth, jobs, prices and taxes are measured afresh from today.` : `Your government wins only <b>${num(e.vote * 100, 1)}%</b> of the vote and leaves office. The game is over, with a score of zero.`}</p>`,
    foot: `<button class="btn primary" id="ok">${won ? "Onward" : "So it ends"}</button>`,
  });
  $("#ok", win).onclick = () => { closeWindows(); done && done(); };
}

function eventWindow(e, done) {
  if (!e) return;
  const sc = S.data.screen;
  const myGdp = S.data.world.nations[sc.country].gdp;
  const total = Object.values(S.data.world.nations).reduce((a, n) => a + n.gdp, 0);
  const fair = Math.min(e.needed, e.target * myGdp / total);
  const cap = sc.resources.capital;
  const choices = [
    { lbl: `Pledge our fair share, ${money(fair)}`, eff: "Your share of the 16 nations' GDP. Refunded if the fund falls short.", amt: fair },
    { lbl: `Pledge all it still needs, ${money(e.needed)}`, eff: "Funds it outright if nobody withdraws: trust and climate credit for your share.", amt: e.needed },
  ].filter((c) => c.amt > 0.00005);
  const win = openWindow({
    doc: true, title: `${nice(e.type)} · ${regionName(e.region)}`, onClose: done,
    body: `<div style="margin-bottom:8px">${VIGNETTE[e.type] || ""}</div><p class="event-text">${esc(e.text)}</p>
      <div class="stat-grid" style="margin-bottom:8px"><div class="stat"><span class="muted">Pledged</span><span>${money(e.pledged)} of ${money(e.target)}</span></div>
      <div class="stat"><span class="muted">Deadline</span><span>${e.deadline}</span></div>
      <div class="stat"><span class="muted">Nations pledging</span><span>${e.pledgers.length}</span></div>
      <div class="stat"><span class="muted">You have</span><span>${money(cap)}</span></div></div>
      ${e.you_pledged ? `<p class="muted">You have pledged ${money(e.you_pledged)}.</p>` : ""}
      ${choices.map((c, i) => `<button class="btn choice" data-c="${i}" ${c.amt > cap ? "disabled" : ""}>${c.lbl}<span class="eff">${c.eff}${c.amt > cap ? " (not enough capital this quarter)" : ""}</span></button>`).join("")}
      <button class="btn choice" data-c="none">Leave it to others<span class="eff">Keep your capital. If the fund falls short, the outcome happens.</span></button>`,
  });
  win.querySelectorAll("[data-c]").forEach((b) => (b.onclick = () => {
    if (b.dataset.c !== "none") addToPlan({ type: "pledge_to_event", event_id: e.id, amount: +choices[+b.dataset.c].amt.toPrecision(6) });
    closeWindows(); done && done();
  }));
}

function gameOverWindow() {
  const s = S.data.screen.score;
  openWindow({
    doc: true, title: "The record of your government",
    body: `<div class="event-title">${esc(s ? s.ending : "The game is over")}</div>
      <p class="event-text">Final score <b>${s ? num(s.score, 1) : "-"}</b>, rank ${s ? s.rank : "-"} of 16. World warming ${num(S.data.screen.world.warming, 2)} °C.</p>
      <h3>Final standings</h3><ol class="report-list">${S.data.screen.leaders.map((l) => `<li>${esc(nationName(l.nation))} — ${num(l.score, 1)}</li>`).join("")}</ol>`,
    foot: `<button class="btn primary" id="ng">New game</button>`,
  });
  $("#ng").onclick = () => newGameWindow();
}

function textWindow() {
  openWindow({ wide: true, title: "The full text screen", body: `<pre style="white-space:pre-wrap;font-size:12.5px;margin:0">${esc(S.data.text)}</pre>` });
}

function newGameWindow() {
  const m = S.meta;
  let pick = m.playable[0];
  const cards = m.playable.map((id) => {
    const n = m.nations[id], p = PERSONALITY[n.personality] || ["", ""];
    return `<button class="country-card ${id === pick ? "active" : ""}" data-c="${id}">${crest(id)}<div><div class="n">${esc(n.name)}</div><div class="d">${nice(n.difficulty)} · ${esc(p[0])} in the computer's hands</div></div></button>`;
  }).join("");
  const saves = m.saves.map((s) => `<div class="save-row"><span>${esc(s.name)} <span class="muted">${esc(s.country)}, seed ${s.seed}, ${s.quarters_played} quarters played</span></span><button class="btn small" data-load="${esc(s.name)}">Continue</button></div>`).join("");
  const win = openWindow({
    title: "A new government", wide: true,
    body: `<p class="summary-text">Lead one country's energy economy from 2025 to 2049, a quarter at a time. Your score is your nation's prosperity multiplied by how the world did on climate. Win elections, keep the lights on, and bring the world below 1.6 °C.</p>
      <h3>Choose your nation</h3><div class="country-cards">${cards}</div>
      <div class="row" style="margin-top:12px;gap:16px">
        <label class="muted">World <select id="ng-diff">${m.difficulties.map((d) => `<option ${d === "normal" ? "selected" : ""}>${d}</option>`).join("")}</select></label>
        <label class="muted">Seed <input id="ng-seed" type="number" value="${1 + Math.floor(Math.random() * 999)}" style="width:90px"></label>
        <label class="muted">Save name <input id="ng-name" placeholder="optional" style="width:150px"></label>
      </div>
      ${saves ? `<h3>Saved games</h3><div class="saves">${saves}</div>` : ""}`,
    foot: `<button class="btn primary" id="ng-go">Take office</button>`,
  });
  win.querySelectorAll(".country-card").forEach((b) => (b.onclick = () => {
    pick = b.dataset.c;
    win.querySelectorAll(".country-card").forEach((x) => x.classList.toggle("active", x === b));
  }));
  win.querySelectorAll("[data-load]").forEach((b) => (b.onclick = async () => {
    try { S.plan = []; setData(await api("/api/load", { name: b.dataset.load })); closeWindows(); } catch (e) { toast(e.message); }
  }));
  $("#ng-go").onclick = async () => {
    try {
      const body = { country: pick, seed: +$("#ng-seed").value, difficulty: $("#ng-diff").value };
      const name = $("#ng-name").value.trim();
      if (name) body.name = name;
      S.plan = [];
      setData(await api("/api/new", body));
      closeWindows();
      openRealm();
    } catch (e) { toast(e.message); }
  };
}

// ---------- action windows ----------

function openMenu(key) {
  if (key === "ledger") return ledgerWindow();
  S.menu = key; renderMenubar();
  actionWindow(MENU[key].title, MENU[key].actions, MENU[key].actions[0], {});
}

function actionWindow(title, types, first, preset) {
  const cat = S.meta.catalogue;
  const win = openWindow({
    title, wide: true,
    body: `<div class="action-layout"><div class="action-list">${types.map((t) => `<button class="action-item" data-t="${t}"><div class="t">${esc(nice(t))}</div><div class="slot">${cat[t].slot} · ${esc(shortCost(cat[t].cost))}</div></button>`).join("")}</div><div id="action-form"></div></div>`,
    onClose: () => { S.menu = null; renderMenubar(); },
  });
  const show = (t) => {
    win.querySelectorAll(".action-item").forEach((b) => b.classList.toggle("active", b.dataset.t === t));
    renderForm($("#action-form", win), t, preset);
  };
  win.querySelectorAll(".action-item").forEach((b) => (b.onclick = () => show(b.dataset.t)));
  show(first);
}

const shortCost = (c) => String(c).replace(/\s*\(see the cost table in `show`\)/, "").replace(/`show`/g, "the screen");

function rangeOf(desc) {
  const m = /(-?\d+(?:\.\d+)?)\s*(?:\([^)]*\))?\s*to\s*(-?\d+(?:\.\d+)?)/.exec(desc);
  return m ? [+m[1], +m[2]] : null;
}

function control(type, name, spec, value) {
  const sc = S.data.screen, me = sc.country;
  const opt = (v, l, sel) => `<option value="${esc(v)}" ${sel ? "selected" : ""}>${esc(l)}</option>`;
  if (Array.isArray(spec)) {
    return `<select name="${name}" data-kind="list">${spec.map((v) => opt(JSON.stringify(v), nice(v), JSON.stringify(v) === JSON.stringify(value))).join("")}</select>`;
  }
  const d = String(spec);
  if (d.includes("another nation")) {
    return `<select name="${name}" data-kind="str">${Object.keys(S.meta.nations).filter((n) => n !== me).map((n) => opt(n, nationName(n), n === value)).join("")}</select>`;
  }
  if (d.includes("open event")) {
    const evs = sc.events.open;
    return evs.length ? `<select name="${name}" data-kind="str">${evs.map((e) => opt(e.id, `${e.id} ${nice(e.type)} in ${regionName(e.region)}`, e.id === value)).join("")}</select>` : `<div class="muted">No event is open.</div>`;
  }
  if (d.includes("inbox") || d.includes("active deals")) {
    const list = d.includes("inbox") ? sc.deals.inbox : sc.deals.active;
    return list.length ? `<select name="${name}" data-kind="str">${list.map((x) => opt(x.id, `${x.id} ${nice(x.type)} (${x.financier} → ${x.host})`, x.id === value)).join("")}</select>` : `<div class="muted">None.</div>`;
  }
  if (d.includes("technology")) {
    const techs = type === "set_license_price" ? sc.research.filter((r) => r.have && !r.licensed) : sc.research;
    return techs.length ? `<select name="${name}" data-kind="str">${techs.map((r) => opt(r.tech, r.name, r.tech === value)).join("")}</select>` : `<div class="muted">You have researched nothing to sell yet.</div>`;
  }
  if (d.includes("list of nation")) return null;
  const range = rangeOf(d);
  const canMax = d.includes('"max"');
  const isMax = value === "max";
  const v = isMax ? "" : value ?? (range ? range[0] : "");
  return `<div class="row"><input name="${name}" data-kind="num" type="number" step="any" ${range ? `min="${range[0]}" max="${range[1]}"` : ""} value="${esc(v)}" ${isMax ? "disabled" : ""}>
    ${canMax ? `<label class="muted row" style="gap:4px;white-space:nowrap"><input type="checkbox" data-max="${name}" ${isMax ? "checked" : ""}> max</label>` : ""}</div>`;
}

function renderForm(el, type, preset) {
  const spec = S.meta.catalogue[type];
  const ex = spec.example || {};
  const params = Object.entries(spec.params);
  let rows = "";
  for (const [name, desc] of params) {
    if (name === "rate | price | share") {
      rows += `<div class="form-row"><label>Price term</label><div><input name="__term" data-kind="num" type="number" step="any" value="${ex.rate ?? ex.price ?? ex.share ?? ""}"></div><div class="hint">${esc(desc)} — the term that applies to the deal type</div></div>`;
      continue;
    }
    const val = preset[name] ?? ex[name];
    const c = control(type, name, desc, val);
    if (c === null) continue;
    rows += `<div class="form-row"><label>${esc(nice(name))}</label><div>${c}</div>${Array.isArray(desc) ? "" : `<div class="hint">${esc(desc)}</div>`}</div>`;
  }
  el.innerHTML = `<h2 style="font-size:20px">${esc(nice(type))}</h2><p class="summary-text">${esc(shortCost(spec.summary))}</p>
    <div class="muted" style="font-size:13px">Cost: ${esc(shortCost(spec.cost))} · ${spec.slot} slot</div><div class="brass-rule"></div>
    <form id="af">${rows}</form><div class="check-box" id="af-check"><span class="muted">Checking…</span></div>
    <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn primary" id="af-add">Add to this quarter's orders</button></div>`;
  const form = $("#af", el);
  const build = () => {
    const act = { type };
    form.querySelectorAll("[name]").forEach((inp) => {
      const n = inp.name;
      if (inp.dataset.kind === "list") act[n] = JSON.parse(inp.value);
      else if (inp.dataset.kind === "str") act[n] = inp.value;
      else if (inp.dataset.kind === "num") {
        const box = form.querySelector(`[data-max="${n}"]`);
        if (box && box.checked) act[n] = "max";
        else if (inp.value !== "") act[n] = +inp.value;
        else if (type === "set_license_price" && n === "price") act[n] = null;
      }
    });
    if ("__term" in act) {
      const term = act.__term; delete act.__term;
      const dt = act.deal_type || (S.data.screen.deals.inbox.find((x) => x.id === act.deal_id) || {}).type;
      const key = dt === "energy_as_a_service" ? "price" : dt === "equity_for_energy" ? "share" : "rate";
      if (type === "respond_deal" && act.response !== "counter") { /* no term */ } else if (term !== undefined) act[key] = term;
    }
    return act;
  };
  let seq = 0;
  const preview = async () => {
    const my = ++seq;
    const act = build();
    const res = await fetch("/api/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actions: [...S.plan, act] }) }).then((r) => r.json());
    if (my !== seq) return;
    const r = (res.results || []).slice(-1)[0];
    const box = $("#af-check", el);
    if (!r) { box.innerHTML = `<span class="bad">${esc(res.error || "Could not check")}</span>`; return; }
    const cost = Object.entries(r.cost || {}).filter(([, v]) => v).map(([k, v]) => k === "capital" ? money(v) : `${num(v, 1)} ${k.replace("_", " ")}`).join(", ");
    const amt = r.action.amount !== undefined && act.amount === "max" ? ` (max resolves to ${+Number(r.action.amount).toPrecision(4)})` : "";
    box.innerHTML = r.ok ? `<span class="good">✓ Possible after your other orders.</span> Costs ${cost || "nothing now"}${amt}.${r.note ? ` ${esc(r.note)}.` : ""}` : `<span class="bad">✗ ${esc(r.reason)}</span>`;
  };
  form.addEventListener("input", preview);
  form.addEventListener("change", (ev) => {
    if (ev.target.dataset.max) {
      const inp = form.querySelector(`[name="${ev.target.dataset.max}"]`);
      inp.disabled = ev.target.checked;
    }
    preview();
  });
  form.addEventListener("submit", (ev) => ev.preventDefault());
  $("#af-add", el).onclick = () => { addToPlan(build()); };
  preview();
}

function dealWindow(id) {
  actionWindow("Answer an offer", ["respond_deal"], "respond_deal", { deal_id: id });
}

// ---------- ledger ----------

function ledgerWindow() {
  S.menu = "ledger"; renderMenubar();
  const sc = S.data.screen;
  const rows = sc.leaders.map((l, i) => `<tr><td>${i + 1}</td><td>${crestMini(l.nation)} ${esc(nationName(l.nation))}${l.nation === sc.country ? " <span class='good'>(you)</span>" : ""}</td><td style="text-align:right">${num(l.score, 1)}</td><td style="text-align:right">${spct(S.data.world.nations[l.nation].emissions_change, 0)}</td><td style="text-align:right">${pct(S.data.world.nations[l.nation].clean_share)}</td></tr>`).join("");
  const races = sc.races.map((r) => `<tr><td>${esc(nice(r.race))}</td><td>${r.leader ? esc(nationName(r.leader)) : "<span class='muted'>no one yet</span>"}</td><td class="muted">${esc(r.measure || "")}</td></tr>`).join("");
  openWindow({
    title: "The ledger", wide: true, onClose: () => { S.menu = null; renderMenubar(); },
    body: `<div style="display:grid;grid-template-columns:1.2fr 1fr;gap:18px">
      <div><h3>Standings</h3><table style="width:100%;border-collapse:collapse;font-size:14px"><tr class="muted"><td>#</td><td>Nation</td><td style="text-align:right">Score</td><td style="text-align:right">CO2 vs 2025</td><td style="text-align:right">Clean</td></tr>${rows}</table></div>
      <div><h3>Bonus races</h3><table style="width:100%;font-size:13px">${races}</table>
      <h3>How the score works</h3><p class="summary-text">Score = (half your absolute standing + half your progress against your own 2025 start, times your country's difficulty) × the World Multiplier, plus bonuses. Top four with the world at or below 1.6 °C and cooling is Champion.</p></div></div>`,
  });
}
const crestMini = (id) => `<i class="swatch" style="background:${colorOf(id)}"></i>`;

// ---------- side panel: nations, regions, your realm ----------

function closePanel() { $("#panel").classList.add("hidden"); S.panel = null; S.map.select(null); }

function panelShell(head, tabs, active, body) {
  $("#panel").classList.remove("hidden");
  $("#panel").innerHTML = `<div class="panel-head">${head}<button class="icon-btn" id="p-x">✕</button></div>
    ${tabs.length ? `<div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${k === active ? "active" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>` : ""}
    <div class="panel-body">${body}</div>`;
  $("#p-x").onclick = closePanel;
}

function mapHover(ev, owner) {
  const box = $("#tooltip");
  if (!owner || !S.data) { box.classList.add("hidden"); return; }
  const v = owner.kind === "nation" ? S.data.world.nations[owner.id] : S.data.world.regions[owner.id];
  if (!v) return;
  const me = S.data.world.me;
  const rows = [["CO2", `${num(v.emissions, 0)} Mt (${spct(v.emissions_change, 0)})`], ["Clean energy", pct(v.clean_share)]];
  if (owner.kind === "nation" && owner.id !== me) rows.push(["Trusts you", num(v.trust_in_you, 2)], ["Score", v.score == null ? "-" : `${num(v.score, 1)} (rank ${v.rank})`]);
  if (owner.kind === "region") rows.push(["Trusts you", num(v.trust_in_you, 2)], ["Open events", v.open_events.length || "none"]);
  const name = owner.kind === "nation" ? nationName(owner.id) : regionName(owner.id);
  const sub = owner.kind === "nation" ? (owner.id === me ? "Your nation" : (S.meta.nations[owner.id].playable ? "Great power" : "Computer-run nation")) : "Rest-of-world region";
  box.innerHTML = ttTable(name, rows, `${sub} · click for details`);
  box.classList.remove("hidden");
  box.style.left = `${Math.min(ev.clientX + 16, innerWidth - box.offsetWidth - 8)}px`;
  box.style.top = `${Math.min(ev.clientY + 16, innerHeight - box.offsetHeight - 8)}px`;
}

function openNation(id, tab = "overview") {
  if (!S.data) return;
  if (id === S.data.screen.country) return openRealm();
  S.map.select("nation", id);
  const draw = () => {
    const v = S.data.world.nations[id], sc = S.data.screen, rel = sc.relations[id] || {};
    const pers = PERSONALITY[v.personality] || ["", ""];
    const head = `${crest(id, true)}<div class="titles"><h2>${esc(nationName(id))}</h2><div class="sub">${esc(pers[0])}${S.meta.nations[id].playable ? " · great power" : ""}</div></div>`;
    const offers = sc.deals.inbox.filter((d) => d.financier === id || d.host === id);
    const active = sc.deals.active.filter((d) => d.financier === id || d.host === id);
    const forSale = sc.research.filter((r) => r.offers.some(([s]) => s === id));
    const body = `<p class="summary-text">${esc(pers[1])}</p>
      <div class="stat-grid">
        <div class="stat"><span class="k">GDP</span><span>${money(v.gdp)}</span></div>
        <div class="stat"><span class="k">Growth</span><span>${spct(v.growth)}</span></div>
        <div class="stat"><span class="k">CO2</span><span>${num(v.emissions, 0)} Mt</span></div>
        <div class="stat"><span class="k">vs 2025</span><span class="${v.emissions_change < 0 ? "good" : "bad"}">${spct(v.emissions_change, 0)}</span></div>
        <div class="stat"><span class="k">Clean energy</span><span>${pct(v.clean_share)}</span></div>
        <div class="stat"><span class="k">Carbon price</span><span>$${num(v.carbon_price, 0)}/t</span></div>
        <div class="stat"><span class="k">Carbon club</span><span>${v.club ? "member" : "outside"}</span></div>
        <div class="stat"><span class="k">Score</span><span>${v.score == null ? "-" : `${num(v.score, 1)} (#${v.rank})`}</span></div>
      </div>
      <h3>Relations</h3>
      <div class="stat-grid">
        <div class="stat"><span class="k">Their trust in you</span><span>${num(v.trust_in_you, 2)}</span></div>
        <div class="stat"><span class="k">Your trust in them</span><span>${num(v.your_trust, 2)}</span></div>
        <div class="stat"><span class="k">Your tariff on them</span><span>${pct(v.your_tariff)}</span></div>
        <div class="stat"><span class="k">Their tariff on you</span><span>${pct(v.their_tariff)}</span></div>
      </div>
      ${offers.length ? `<h3>Offers between you</h3>${offers.map((d) => `<div class="plan-item"><div class="what"><b>${d.id}</b> ${nice(d.type)}, ${esc(d.terms.source || "")}</div>${d.can_answer ? `<button class="btn small" data-deal="${d.id}">Answer</button>` : ""}</div>`).join("")}` : ""}
      ${active.length ? `<h3>Active deals</h3>${active.map((d) => `<div class="plan-item"><div class="what"><b>${d.id}</b> ${nice(d.type)} ${esc(d.terms.source || "")}</div></div>`).join("")}` : ""}
      ${forSale.length ? `<h3>Licences they sell you</h3>${forSale.map((r) => `<div class="plan-item"><div class="what">${esc(r.name)} <span class="muted">${money(r.offers.find(([s]) => s === id)[1])}</span></div><button class="btn small" data-lic="${r.tech}">Buy</button></div>`).join("")}` : ""}
      <h3>Interactions</h3>
      <div class="interactions">
        ${interaction("propose_deal", "Offer a deal", "Finance clean energy in their country", { target: id })}
        ${interaction("open_talks", "Open talks", "Spend influence to raise their trust", { target: id })}
        ${interaction("set_tariff", "Impose a tariff", "Tax their goods; costs trust", { target: id })}
        ${interaction("lift_tariff", "Lift your tariff", "Remove a tariff you set", { target: id })}
      </div>`;
    panelShell(head, [], null, body);
    $("#panel").querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => {
      const p = JSON.parse(b.dataset.preset);
      actionWindow(`Toward ${nationName(id)}`, ["propose_deal", "open_talks", "set_tariff", "lift_tariff", "buy_license"], b.dataset.act, p);
    }));
    $("#panel").querySelectorAll("[data-deal]").forEach((b) => (b.onclick = () => dealWindow(b.dataset.deal)));
    $("#panel").querySelectorAll("[data-lic]").forEach((b) => (b.onclick = () => actionWindow("Buy a licence", ["buy_license"], "buy_license", { tech: b.dataset.lic, seller: id })));
  };
  S.panel = draw;
  draw();
}

function interaction(type, title, sub, preset) {
  return `<button class="interaction" data-act="${type}" data-preset="${esc(JSON.stringify(preset))}"><div class="t">${title}</div><div class="s">${sub}</div></button>`;
}

function openRegion(id) {
  if (!S.data) return;
  S.map.select("region", id);
  const draw = () => {
    const v = S.data.world.regions[id], sc = S.data.screen;
    const reg = sc.regions.find((r) => r.id === id) || {};
    const evs = sc.events.open.filter((e) => e.region === id);
    const head = `<div class="crest large" style="background:linear-gradient(160deg, ${d3.color(REGION_TINT[id]).brighter(0.2)}, ${d3.color(REGION_TINT[id]).darker(1.2)})">${id}</div><div class="titles"><h2>${esc(regionName(id))}</h2><div class="sub">Rest-of-world region · not playable</div></div>`;
    const body = `<p class="summary-text">Countries outside the sixteen, grouped. Their new energy gets cleaner as clean technology gets cheaper and the big economies cut, but they replace fossil plants only as they retire. You can lend for clean energy here, up to what the region can absorb.</p>
      <div class="stat-grid">
        <div class="stat"><span class="k">CO2</span><span>${num(v.emissions, 0)} Mt</span></div>
        <div class="stat"><span class="k">vs 2025</span><span class="${v.emissions_change < 0 ? "good" : "bad"}">${spct(v.emissions_change, 0)}</span></div>
        <div class="stat"><span class="k">Clean energy</span><span>${pct(v.clean_share)}</span></div>
        <div class="stat"><span class="k">Clean share of new energy</span><span>${pct(reg.clean_of_new_energy)}</span></div>
        <div class="stat"><span class="k">GDP</span><span>${money(v.gdp)}</span></div>
        <div class="stat"><span class="k">Growth</span><span>${spct(v.growth)}</span></div>
        <div class="stat"><span class="k">Trusts you</span><span>${num(v.trust_in_you, 2)}</span></div>
        <div class="stat"><span class="k">Most trusts</span><span>${reg.most_trusts ? esc(nationName(reg.most_trusts)) : "no one yet"}</span></div>
        <div class="stat"><span class="k">You have lent</span><span>${money(v.financed_by_you)}</span></div>
        <div class="stat"><span class="k">Can still absorb</span><span>${reg.room_tn ? money(Math.min(...Object.values(reg.room_tn))) : "-"}</span></div>
      </div>
      ${evs.length ? `<h3>Open event funds</h3>${evs.map((e) => `<div class="plan-item"><div class="what"><b>${e.id}</b> ${nice(e.type)}<div class="why muted">${pct(e.pledged / e.target)} of ${money(e.target)} · until ${e.deadline}</div></div><button class="btn small" data-ev="${e.id}">Open</button></div>`).join("")}` : ""}
      <h3>Interactions</h3>
      <div class="interactions">
        ${interaction("finance_region", "Lend for solar or wind", "Concessional loan: credit, trust, equipment sales", { region: id, source: "solar" })}
        ${interaction("fund_forests", "Pay into the forest fund", "Protect forests worldwide; wears off in ~5 years", {})}
      </div>`;
    panelShell(head, [], null, body);
    $("#panel").querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => actionWindow(regionName(id), ["finance_region", "pledge_to_event", "fund_forests"], b.dataset.act, JSON.parse(b.dataset.preset))));
    $("#panel").querySelectorAll("[data-ev]").forEach((b) => (b.onclick = () => eventWindow(sc.events.open.find((e) => e.id === b.dataset.ev))));
  };
  S.panel = draw;
  draw();
}

function openRealm(tab = "overview") {
  if (!S.data) return;
  const me = S.data.screen.country;
  S.map.select(null);
  let current = tab;
  const draw = () => {
    const sc = S.data.screen;
    const head = `${crest(me, true)}<div class="titles"><h2>${esc(nationName(me))}</h2><div class="sub">Your government · ${sc.quarter}</div></div>`;
    const tabs = [["overview", "Realm"], ["vote", "Elections"], ["energy", "Energy"], ["research", "Research"]];
    panelShell(head, tabs, current, realmTab(current));
    $("#panel").querySelectorAll(".tab").forEach((b) => (b.onclick = () => { current = b.dataset.tab; draw(); }));
    $("#panel").querySelectorAll("[data-research]").forEach((b) => (b.onclick = () => actionWindow("Research", ["fund_research", "buy_license", "set_license_price"], "fund_research", { tech: b.dataset.research, amount: "max" })));
  };
  S.panel = draw;
  draw();
}

function realmTab(tab) {
  const sc = S.data.screen, me = sc.country, ec = sc.economy, en = sc.energy, em = sc.emissions, s = sc.score;
  if (tab === "vote") {
    const el = sc.election;
    if (!el.next) return `<p class="muted">No election is due.</p>`;
    const parts = Object.entries(el.parts || {});
    const bars = parts.map(([k, v]) => {
      const w = Math.min(50, Math.abs(v) / 0.12 * 50);
      return `<div class="vote-row"><span>${nice(k)}</span><div class="vote-bar"><div class="zero"></div><div class="v" style="${v >= 0 ? `left:50%;width:${w}%;background:var(--good)` : `right:50%;width:${w}%;background:var(--bad)`}"></div></div><span style="text-align:right">${v >= 0 ? "+" : ""}${num(v, 3)}</span></div>`;
    }).join("");
    return `<div class="row between"><h3>Election ${el.next}</h3><span class="muted">in ${el.quarters_away} quarters</span></div>
      <div style="font-size:30px;font-family:var(--display);color:${el.expected_vote == null ? "var(--muted)" : el.expected_vote < 0.52 ? "var(--bad)" : "var(--brass-hi)"}">${el.expected_vote == null ? "Forecast from next quarter" : `${num(el.expected_vote * 100, 1)}% expected`}</div>
      <p class="muted">You need ${pct(el.needed)}. A random swing moves the result by up to about ${pct(el.swing_range, 1)}, so aim for 54% or more.</p>
      ${bars}
      ${el.growth_this_term != null ? `<h3>Growth this term</h3><div class="stat-grid"><div class="stat"><span class="k">Achieved</span><span>${pct(el.growth_this_term, 2)}/yr</span></div><div class="stat"><span class="k">Expected</span><span>${pct(el.growth_expected, 2)}/yr</span></div></div>` : ""}
      <h3>What moves the vote</h3><p class="summary-text">Growth against expectations (tax cuts, cheaper energy, no blackouts), energy jobs against last term (retraining softens fossil losses), energy prices (the carbon rebate), tax rises, and local opposition to permitting reform. All count as averages over the term, so act early.</p>`;
  }
  if (tab === "energy") {
    const supply = Object.entries(en.supply || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const tot = supply.reduce((a, [, v]) => a + v, 0) || 1;
    const building = Object.entries(en.building || {}).map(([s, b]) => `<div class="stat"><span class="k">${nice(s)}</span><span>${num(b.total, 2)} EJ</span></div>`).join("");
    return `<h3>Energy mix</h3><div class="mix">${supply.map(([k, v]) => `<span style="width:${v / tot * 100}%;background:${SOURCE_COLOR[k] || "#888"}" ${tip(ttTable(nice(k), [["Supply", `${num(v, 2)} EJ/yr`], ["Share", pct(v / tot, 1)]]))}></span>`).join("")}</div>
      <div class="legend-list">${supply.slice(0, 8).map(([k, v]) => `<span><i class="swatch" style="background:${SOURCE_COLOR[k] || "#888"}"></i>${nice(k)} ${pct(v / tot)}</span>`).join("")}</div>
      <div class="stat-grid" style="margin-top:10px">
        <div class="stat"><span class="k">Demand</span><span>${num(en.demand, 1)} EJ</span></div>
        <div class="stat"><span class="k">Shortfall</span><span class="${en.shortfall_share > 0 ? "bad" : ""}">${pct(en.shortfall_share, 1)}</span></div>
        <div class="stat"><span class="k">Curtailed</span><span>${num(en.curtailment, 2)} EJ</span></div>
        <div class="stat"><span class="k">Energy price</span><span>$${num(en.price, 2)}/GJ (${spct(en.price_vs_2025, 0)})</span></div>
        <div class="stat"><span class="k">Carbon price</span><span>$${num(en.carbon_price, 0)}/t</span></div>
        <div class="stat"><span class="k">Rebate</span><span>${pct(en.rebate)}</span></div>
        <div class="stat"><span class="k">Fossil ban</span><span>${en.fossil_ban ? "on" : "off"}</span></div>
        <div class="stat"><span class="k">Clean share</span><span>${pct(en.clean_share)}</span></div>
      </div>
      ${building ? `<h3>Under construction</h3><div class="stat-grid">${building}</div>` : ""}`;
  }
  if (tab === "research") {
    return `<p class="summary-text">Research finishes no faster than its minimum time; more money brings you closer to it. Anything someone already has costs 40% less.</p>` +
      sc.research.map((r) => `<div class="plan-item"><div class="what"><b>${esc(r.name)}</b> ${r.have ? `<span class="good">${r.licensed ? "licensed" : "researched"}</span>` : ""}
        <div class="meter" style="margin:4px 0"><i style="width:${r.progress * 100}%"></i></div>
        <div class="why muted">${esc(r.gives.join(", "))}${r.blocked && !r.have ? ` · <span class="warn">${esc(r.blocked)}</span>` : ""}${r.offers.length && !r.have ? ` · licence from ${esc(r.offers[0][0])} ${money(r.offers[0][1])}` : ""}</div></div>
        ${!r.have && !r.blocked ? `<button class="btn small" data-research="${r.tech}">Fund</button>` : ""}</div>`).join("");
  }
  const comp = s ? Object.entries(s.components).map(([k, v]) => `<div class="vote-row"><span>${nice(k)}</span><div class="meter"><i style="width:${v * 100}%"></i></div><span style="text-align:right">${num(v, 2)}</span></div>`).join("") : "";
  return `<div class="stat-grid">
      <div class="stat"><span class="k">GDP</span><span>${money(ec.gdp)}</span></div>
      <div class="stat"><span class="k">vs 2025</span><span>${spct(ec.gdp_vs_2025, 1)}</span></div>
      <div class="stat"><span class="k">Growth</span><span ${tip(ttTable("Growth", [], "This quarter at an annual rate; a disaster quarter shows its one-off loss."))}>${spct(ec.growth_annual, 2)}</span></div>
      <div class="stat"><span class="k">Tax change</span><span>${spct(ec.tax_change, 1)} of GDP</span></div>
      <div class="stat"><span class="k">Approval</span><span>${pct(ec.approval)}</span></div>
      <div class="stat"><span class="k">Stability</span><span class="${ec.stability < 0.3 ? "bad" : ""}">${pct(ec.stability)}</span></div>
    </div>
    <h3>Emissions</h3>
    <div class="stat-grid">
      <div class="stat"><span class="k">Now</span><span>${num(em.now, 0)} Mt</span></div>
      <div class="stat"><span class="k">vs 2025</span><span class="${em.vs_2025 < 0 ? "good" : "bad"}">${spct(em.vs_2025, 0)}</span></div>
      <div class="stat"><span class="k">Your target path</span><span>${num(em.target_path_now, 0)} Mt</span></div>
      <div class="stat"><span class="k">1.5 °C pathway</span><span>${num(em.pathway_1_5c_now, 0)} Mt</span></div>
      <div class="stat"><span class="k">Credits held</span><span>${num(em.credit_balance, 0)} Mt</span></div>
      <div class="stat"><span class="k">Pledge</span><span>${em.pledge ? `${num(em.pledge.target, 0)} Mt by ${em.pledge.year}` : "none"}</span></div>
    </div>
    ${s ? `<h3>Score ${num(s.score_if_ended_now, 1)} · rank ${s.rank}</h3>${comp}<p class="muted" style="font-size:12.5px">0.5 means no change from your 2025 start. Ending if the game ended now: ${esc(s.ending)}.</p>` : ""}`;
}

boot().catch((e) => { console.error(e); toast(`Could not start: ${e.message}`, 8000); });
