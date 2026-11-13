// Energy Game - local web interface (W1). Every number shown comes from the server (sim.view);
// this file holds no game rules.
import { WorldMap, MODES } from "./map.js";
import { VIGNETTE } from "./vignettes.js";
import { chronicle } from "./charts.js";
import { PLAYABLE_COLOR, PERSONALITY, SOURCE_COLOR, nationTint, NATION_TINT_FAMILY, REGION_TINT } from "./owners.js";
import { LEADERS, leaderPortrait, skyColor, portrait, skyOf } from "./leaders.js";
import { ADVISORS, TIPS } from "./tutorial.js";
import { ORDERS, FX, SOURCE_ICON, DEAL_ICON, DEAL_LINE } from "./orders.js";
import { WAVES, isOpen, opensAt } from "./unlocks.js";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const S = { meta: null, data: null, plan: [], checks: [], map: null, menu: null, panel: null, drawer: null, lastRegions: null };

// ---------- formatting ----------

const money = (t) => {
  if (t == null || Number.isNaN(t)) return "-";
  const b = t * 1000, sign = b < 0 ? "−" : "";
  if (Math.abs(b) >= 10000) return `${sign}$${Math.round(Math.abs(b) / 1000)} tn`;
  if (Math.abs(b) >= 1000) return `${sign}$${(Math.abs(b) / 1000).toFixed(1)} tn`;
  if (b !== 0 && Math.abs(b) < 0.5) return `${sign}under $1 bn`;
  return `${sign}$${Math.round(Math.abs(b))} bn`;
};
const pct = (x, d = 0) => (x == null ? "-" : `${(x * 100).toFixed(d)}%`);
const spct = (x, d = 1) => (x == null ? "-" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
const num = (x, d = 1) => (x == null ? "-" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const NAMES = { smr: "Small modular reactors", ccs: "Carbon capture", hvdc_supergrid: "HVDC supergrid", euu: "EU" };
const nice = (s) => NAMES[s] || String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
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
  else if (S.drawer) closeDrawer();
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
  const fresh = !S.data || S.data.name !== data.name || S.data.screen.turn !== data.screen.turn;
  S.data = data;
  if (fresh) restorePlan();
  for (const id of ["topbar", "outliner", "rail", "endturn", "legend"]) $(`#${id}`).classList.remove("hidden");
  S.map.update(data.world);
  renderAll();
  if (fresh && S.drawer) drawDrawer(); // a new quarter: refresh the open orders with new costs
  if (fresh) runTips();
  checkPlan();
}

// Alerts sit centred over the open stretch of map between the left side (rail, drawer or
// panel) and the outliner on the right.
function placeAlerts() {
  const vis = (id) => { const e = $(id); return e && !e.classList.contains("hidden") ? e.getBoundingClientRect() : null; };
  const left = Math.max(...["#rail", "#drawer", "#panel"].map((id) => vis(id)?.right || 0));
  const right = vis("#outliner")?.left || window.innerWidth;
  $("#alerts").style.left = `${(left + right) / 2}px`;
  placeTip();
}
window.addEventListener("resize", () => S.data && placeAlerts());

// ---------- advisors: tips that teach the game as it unfolds ----------

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window: tips just repeat */ } },
};
const tipsKey = () => `tips:seen:${S.data.name}`;
const tipsOff = () => store.get("tips:off", false);
function tipHelpers() {
  const sc = S.data.screen, inc = sc.resources.income_per_year || {};
  const income = ["budget", "fossil_exports", "carbon", "tariffs", "tax", "tax_credits", "interest"].reduce((a, k) => a + (inc[k] || 0), 0);
  const solar = (sc.energy.costs || {}).solar;
  return { sc, world: S.data.world, money, whole, pct, nation: nationName(sc.country), income, allOrders: allOrders(), solar1: solar ? solar.unit_cost * (sc.energy.demand || 0) * 0.01 : 0 };
}
function dueTips() {
  if (!S.data || S.data.screen.over) return [];
  const seen = new Set(store.get(tipsKey(), [])), h = tipHelpers();
  return TIPS.filter((t) => { if (seen.has(t.id)) return false; try { return t.when(h); } catch { return false; } });
}
function runTips() {
  if (tipsOff()) return closeTipCard();
  const due = dueTips();
  if (due.length) showTip(due[0], due.length); else closeTipCard();
}
function markSeen(id) { store.set(tipsKey(), [...new Set([...store.get(tipsKey(), []), id])]); }
function closeTipCard() { $("#tip").classList.add("hidden"); $("#tip").innerHTML = ""; clearGlow(); }
function glow(sel) { clearGlow(); const e = $(sel); if (e) e.classList.add("tut-glow"); }
function clearGlow() { document.querySelectorAll(".tut-glow").forEach((e) => e.classList.remove("tut-glow")); }

// "Show me": open or light up the part of the screen a tip is about
const SHOW = {
  realm: () => openRealm(),
  resources: () => glow("#resources"),
  build: () => actionWindow(MENU.build.title, MENU.build.actions, "build_capacity", {}, "build"),
  carbon: () => actionWindow(MENU.policy.title, MENU.policy.actions, "set_carbon_price", {}, "policy"),
  endturn: () => glow("#endturn"),
  modes: () => glow("#mapmodes"),
  outliner: () => glow("#outliner"),
  research: () => researchWindow(),
  diplomacy: () => actionWindow(MENU.diplomacy.title, MENU.diplomacy.actions, "open_talks", {}, "diplomacy"),
  world: () => actionWindow(MENU.world.title, MENU.world.actions, "finance_region", {}, "world"),
  event: () => actionWindow(MENU.world.title, MENU.world.actions, "pledge_to_event", {}, "world"),
  vote: () => { openRealm("vote"); glow("#world-stats"); },
  ...Object.fromEntries(WAVES.map((w) => [`orders_${w.turn}`, () => actionWindow(w.title, w.types, null, {}, null)])),
};

// ---------- orders that open over the first two years (web/static/unlocks.js) ----------

const ordersKey = () => `orders:all:${S.data ? S.data.name : ""}`;
function allOrders() { return !!store.get(ordersKey(), false); }
const orderOpen = (t) => isOpen(t, S.data ? S.data.screen.turn : 0, allOrders());
function quarterOf(turn) { return `${2025 + Math.floor(turn / 4)} Q${(turn % 4) + 1}`; }
function lockedNote(types) {
  if (!types.length) return "";
  const by = {};
  types.forEach((t) => (by[opensAt(t)] = [...(by[opensAt(t)] || []), t]));
  return `<div class="locked-note"><div class="locked-head">🔒 More orders open as your government settles in</div>
    ${Object.entries(by).map(([turn, ts]) => `<div class="locked-row"><b>${quarterOf(+turn)}</b> ${ts.map((t) => `<span class="locked-chip">${(ORDERS[t] || {}).icon || "◆"} ${esc(nice(t))}</span>`).join("")}</div>`).join("")}
    <div class="muted" style="font-size:12px;margin-top:4px">Experienced? Open them all now under Advice.</div></div>`;
}

function showTip(t, count = 1, manual = false) {
  const a = ADVISORS[t.who];
  const el = $("#tip");
  clearGlow();
  el.classList.remove("hidden");
  el.style.setProperty("--ac", a.color);
  el.innerHTML = `<div class="tip-portrait" style="background:${skyOf(a.color)}">${portrait(a.look, a.color, a.name)}</div>
    <div class="tip-main">
      <div class="tip-who"><span>${esc(a.name)}</span>${count > 1 ? `<span class="muted">1 of ${count}</span>` : ""}</div>
      <div class="tip-title">${esc(t.title)}</div>
      <div class="tip-body">${t.body(tipHelpers())}</div>
      ${t.ask ? `<div class="tip-asks">${t.ask.map(([q, ans], i) => `<button class="tip-q" data-i="${i}">${esc(q)}</button><div class="tip-a hidden" data-a="${i}">${esc(ans)}</div>`).join("")}</div>` : ""}
      <div class="tip-foot">${manual ? "" : `<button class="linkish" id="tip-off">Turn tips off</button>`}<span class="spacer"></span>
        ${t.show ? `<button class="btn small" id="tip-show">Show me</button>` : ""}<button class="btn primary small" id="tip-ok">${count > 1 ? "Next ▸" : "Got it"}</button></div>
    </div>`;
  el.querySelectorAll(".tip-q").forEach((b) => (b.onclick = () => {
    const ans = el.querySelector(`[data-a="${b.dataset.i}"]`);
    ans.classList.toggle("hidden");
    b.classList.toggle("open", !ans.classList.contains("hidden"));
  }));
  if (t.show) $("#tip-show").onclick = () => { SHOW[t.show](); };
  $("#tip-ok").onclick = () => { markSeen(t.id); if (manual) closeTipCard(); else runTips(); };
  if (!manual) $("#tip-off").onclick = () => { store.set("tips:off", true); closeTipCard(); toast("Tips are off. Turn them back on under Advice."); };
  placeTip();
}

// The card sits at the bottom, centred over the open map between the left-hand panels and
// the end-turn box.
function placeTip() {
  const el = $("#tip");
  if (!el || el.classList.contains("hidden")) return;
  const vis = (id) => { const e = $(id); return e && !e.classList.contains("hidden") ? e.getBoundingClientRect() : null; };
  const left = Math.max(...["#rail", "#drawer", "#panel", "#legend"].map((id) => vis(id)?.right || 0)) + 12;
  const right = (vis("#endturn")?.left || window.innerWidth) - 12;
  const w = Math.max(300, Math.min(620, right - left));
  el.style.width = `${w}px`;
  el.style.left = `${Math.max(left, (left + right) / 2 - w / 2)}px`;
}

function adviceWindow() {
  S.menu = "advice"; renderMenubar();
  const seen = new Set(store.get(tipsKey(), [])), due = new Set(dueTips().map((t) => t.id));
  const groups = Object.entries(ADVISORS).map(([k, a]) => [k, a, TIPS.filter((t) => t.who === k)]);
  const win = openWindow({
    title: "Your advisors", wide: true, onClose: () => { S.menu = null; renderMenubar(); },
    body: `<p class="summary-text">Your advisors speak up when something needs your attention. Read any tip again here.</p>
      <div class="advice-grid">${groups.map(([k, a, ts]) => `<div class="advice-col">
        <div class="advice-head"><div class="advice-face" style="background:${skyOf(a.color)}">${portrait(a.look, a.color, a.name)}</div><b>${esc(a.name)}</b></div>
        ${ts.map((t) => `<button class="advice-tip" data-tip-id="${t.id}"><span>${esc(t.title)}</span><span class="muted">${seen.has(t.id) ? "read" : due.has(t.id) ? "new" : "later"}</span></button>`).join("")}
      </div>`).join("")}</div>
      <div class="row" style="margin-top:12px;gap:14px"><label class="row" style="gap:6px"><input type="checkbox" id="tips-on" ${tipsOff() ? "" : "checked"}> Show tips as they come up</label>
        <button class="btn small" id="tips-reset">Start the tips again</button>
        <label class="row" style="gap:6px"><input type="checkbox" id="orders-all" ${allOrders() ? "checked" : ""}> Open every order now (orders otherwise open over the first two years)</label></div>`,
  });
  $("#orders-all", win).onchange = (ev) => { store.set(ordersKey(), ev.target.checked); renderMenubar(); refreshDrawer(); };
  win.querySelectorAll("[data-tip-id]").forEach((b) => (b.onclick = () => {
    closeWindows();
    showTip(TIPS.find((t) => t.id === b.dataset.tipId), 1, true);
  }));
  $("#tips-on", win).onchange = (ev) => { store.set("tips:off", !ev.target.checked); if (ev.target.checked) { closeWindows(); runTips(); } else closeTipCard(); };
  $("#tips-reset", win).onclick = () => { store.set(tipsKey(), []); store.set("tips:off", false); closeWindows(); runTips(); };
}

function renderAll() {
  refreshDrawer();
  renderTopbar();
  renderAlerts();
  renderOutliner();
  renderModes();
  renderMenubar();
  renderEndturn();
  if (S.panel) S.panel();
  placeAlerts();
}

// ---------- top bar ----------

// Capital the planned orders will spend (each order's checked cost), so the top bar shows what is
// left the moment an order is added, and gives it back when the order is removed.
function plannedSpend() {
  return S.plan.reduce((a, _, i) => { const c = S.checks[i]; return a + (c && c.ok ? ((c.cost && c.cost.capital) || 0) + (c.reserve || 0) : 0); }, 0);
}

function renderTopbar() {
  const sc = S.data.screen, me = sc.country, r = sc.resources;
  $("#realm-crest").outerHTML = `<div id="realm-crest">${crest(me)}</div>`;
  $("#realm-name").textContent = nationName(me);
  const diff = S.meta.nations[me].difficulty.replace(/_/g, " ");
  $("#realm-sub").textContent = `${diff} country · ${sc.difficulty} world`;
  $("#realm").onclick = () => openRealm();

  const used = slotsUsed();
  const inc = r.income_per_year || {};
  const q = (v) => money((v || 0) / 4);
  const incRows = [
    ["Energy budget (2% of GDP)", q(inc.budget)], ["Fossil exports", q(inc.fossil_exports)],
    ["Carbon revenue", q(inc.carbon)], ["Tariffs", q(inc.tariffs)], ["Tax change", q(inc.tax)],
    ["Tax credits", q(inc.tax_credits)], ["Interest on new debt", q(inc.interest)],
  ].filter(([, v]) => !/^(\$0 bn|under \$1 bn)$/.test(v));
  const total = ["budget", "fossil_exports", "carbon", "tariffs", "tax", "tax_credits", "interest"]
    .reduce((a, k) => a + (inc[k] || 0), 0);
  const spend = plannedSpend(), left = r.capital - spend;
  const capTip = ttTable("Capital", [["In hand", money(r.capital)], ...(spend > 0 ? [["Planned orders", `−${money(spend)}`], ["Left to spend", `<b>${money(left)}</b>`]] : []),
    ...incRows.map(([k, v]) => [k, v]), ["Income a quarter", `<b>${money(total / 4)}</b>`]],
    (inc.borrowed > 0 ? `Your tax cut also borrows ${money(inc.borrowed / 4)} a quarter; new local debt so far ${money(r.local_debt_new)}. ` : "") +
    "Capital pays for building, research, deals and most programmes. Orders you plan are taken off at once; remove one to get it back.");
  const pcTip = ttTable("Political capital", [], "Pays for unpopular moves: raising the carbon price, closing plants early, raising taxes, permitting reform, a fossil ban or an activity cap.");
  const slotTip = (k) => ttTable(`${nice(k)} actions`, [["Banked this quarter", r.slots[k] ?? 0], ["Planned", used[k] || 0]],
    k === "domestic" ? "3 a quarter, unused ones bank up to 6." : "2 a quarter, unused ones bank up to 4.");
  const res = [
    ["Capital", money(left), spend > 0 ? `−${money(spend)} planned` : `+${money(total / 4)} / quarter`, capTip],
    ["Political cap.", num(r.political_capital, 0), "", pcTip],
    ["Influence", num(r.influence, 0), "for talks", ttTable("Influence", [], "Bought with capital; spent on diplomatic talks.")],
    ["Domestic", `${(r.slots.domestic ?? 0) - (used.domestic || 0)}/${r.slots.domestic ?? 0}`, "slots left", slotTip("domestic")],
    ["Diplomatic", `${(r.slots.diplomatic ?? 0) - (used.diplomatic || 0)}/${r.slots.diplomatic ?? 0}`, "slots left", slotTip("diplomatic")],
  ];
  $("#resources").innerHTML = res.map(([k, v, d, t]) =>
    `<div class="res" ${tip(t)}><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join("");

  const w = sc.world, s = sc.score, el = sc.election;
  const wy = w.warming_year, lo = w.start_warming, warmFrac = Math.max(0, Math.min(1, (wy - lo) / (w.collapse_at - lo)));
  const warnFrac = (w.collapse_warning - lo) / (w.collapse_at - lo);
  const warmTip = ttTable("Global warming", [["Year average", `${num(wy, 2)} °C`], ["This quarter", `${num(w.warming, 2)} °C`], ["Five years ago", w.warming_5y_ago ? `${num(w.warming_5y_ago, 2)} °C` : "-"],
    ["Collapse at", `${w.collapse_at} °C`], ["Room left", `${num(Math.max(0, w.collapse_at - wy), 2)} °C`],
    ["World CO2", w.global_emissions ? `${num(w.global_emissions / 1000, 1)} Gt/yr` : "-"]],
  `If warming, averaged over a year, reaches ${w.collapse_at} °C the game ends and every nation loses. Stay below it to 2049 and the world wins. Seasons move each quarter's figure up and down.`);
  const scoreTip = s ? ttTable("Score", [["Score now", num(s.score_if_ended_now, 0)], ["Rank", `${s.rank} of 16`],
    ["Impact", num(s.impact, 0)], ["  your CO2, on average", belowStart(s.yearly_cut)], ["Prosperity", num(s.prosperity, 0)],
    ["× country difficulty", s.difficulty_multiplier]],
  `Score = difficulty × (${s.weights[0] * 100}% impact + ${s.weights[1] * 100}% prosperity). First place at the end is Champion.`) : "";
  const vote = el.expected_vote;
  const voteTip = el.next ? ttTable(`Election ${el.next}`, [["Expected vote", vote == null ? "from next quarter" : num(vote, 3)],
    ["Needed", el.needed], ["Random swing", `± ${el.swing_range}`],
    ...Object.entries(el.parts || {}).map(([k, v]) => [nice(k), (v >= 0 ? "+" : "") + num(v, 3)])], "Aim for 0.54 or more: the swing can take away 0.04.") : "";
  $("#world-stats").innerHTML = `
    <div class="res gauge" ${tip(warmTip)}><div class="k">Warming</div><div class="v ${wy >= w.collapse_warning ? "bad" : ""}">${num(wy, 2)} °C</div>
      <div class="d">collapse at ${w.collapse_at} °C</div>
      <div class="bar"><div class="fill ${wy >= w.collapse_warning ? "hot" : ""}" style="width:${warmFrac * 100}%"></div><div class="tick" style="left:${warnFrac * 100}%"></div></div></div>
    <div class="res" ${tip(voteTip)}><div class="k">Next vote</div><div class="v ${vote != null && vote < 0.52 ? "bad" : vote != null && vote < 0.54 ? "warn" : ""}">${vote == null ? "—" : num(vote * 100, 1) + "%"}</div><div class="d">${el.next || "none"}</div></div>
    <div class="res" ${tip(scoreTip)}><div class="k">Score</div><div class="v">${s ? num(sc.over ? s.score : s.score_if_ended_now, 0) : "—"}</div><div class="d">${s ? `rank ${s.rank} of 16` : ""}</div></div>`;
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
  const wd = sc.world;
  if (!sc.over && wd.warming_year >= wd.collapse_warning) out.push({ ico: "🌡", cls: "danger", tip: ttTable("Warming is near the collapse line", [["Year average", `${num(wd.warming_year, 2)} °C`], ["Collapse at", `${wd.collapse_at} °C`]], "At the line the game ends and every nation loses. Cut, finance cuts abroad, and fill event funds."), go: () => ledgerWindow("chronicle") });
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
  const spec = (S.meta.catalogue[a.type] || {}).params || {};
  const part = ([k, v]) => {
    if (v === "max") return "all you can afford";
    if (typeof v === "boolean") return v ? "on" : "off";
    if (typeof v === "string") {
      if (S.meta.nations[v]) return nationName(v);
      if (S.meta.regions[v]) return regionName(v);
      return `${SOURCE_ICON[v] ? SOURCE_ICON[v] + " " : ""}${nice(v)}`;
    }
    if (typeof v !== "number") return "";
    if (a.type === "propose_deal" && a.deal_type === "factory_partnership") {
      if (k === "amount") return `${money(v)} of output a year`;
      if (k === "capital_share") return `you fund ${whole(v * 100)}%`;
      if (k === "power") return v > 0 ? `${shareOf(v, (S.data.world.nations[a.target] || {}).demand || myDemand())} of their energy as power` : "";
      if (k === "share") return `${whole(v * 100)}% of earnings`;
    }
    if (a.type === "propose_deal" && k === "markup") return `${whole(v * 100)}% markup`;
    if (a.type === "propose_deal" && k === "amount") {
      return a.deal_type === "climate_loan" ? money(v) : `${shareOf(v, (S.data.world.nations[a.target] || {}).demand || myDemand())} of their energy`;
    }
    if (k === "rate" && a.type === "propose_deal") return `${whole(v * 100)}% a year`;
    if (k === "share" && a.type === "propose_deal") return `${whole(v * 100)}% of profit`;
    if (k === "price" && a.type === "propose_deal") return `$${whole(v)}/GJ`;
    if (k === "duration") return `${whole(v / 4)} years`;
    const u = unitOf(a.type, k, spec[k] || "", null);
    if (u.unit === "$ bn") return money(v);
    if (u.unit.startsWith("% of your energy")) return `${shareOf(v, myDemand())} of your energy`;
    if (u.unit.startsWith("%")) return `${whole(v / u.scale)}${u.unit}`;
    return `${whole(v / u.scale)}${u.unit ? " " + u.unit : ""}`;
  };
  const hidden = a.type === "propose_deal" ? ["type", "collateral", "exit_penalty", "currency"] : ["type"];
  const p = Object.entries(a).filter(([k]) => !hidden.includes(k)).map(part).filter(Boolean).join(" · ");
  return `<span class="plan-ico">${(ORDERS[a.type] || {}).icon || "◆"}</span><b>${esc(nice(a.type))}</b>${p ? ` <span class="muted">${esc(p)}</span>` : ""}`;
}

function renderOutliner() {
  const sc = S.data.screen;
  const planRows = S.plan.length ? S.plan.map((a, i) => {
    const c = S.checks[i];
    const status = !c ? `<span class="muted">checking…</span>` : c.ok
      ? `<span class="good">✓</span> <span class="muted">${c.reserve ? "" : Object.entries(c.cost || {}).filter(([, v]) => v).map(([k, v]) => k === "capital" ? money(v) : `${whole(v)} ${k.replace("_", " ")}`).join(", ") || "free"}${c.note ? `${c.reserve ? "" : "; "}${esc(humane(c.note))}` : ""}</span>`
      : `<span class="bad">✗ ${esc(humane(c.reason))}</span>`;
    return `<div class="plan-item"><div class="what">${describe(a)}<div class="why">${status}</div></div><button class="icon-btn" data-rm="${i}" title="Remove">✕</button></div>`;
  }).join("") : `<div class="muted" style="padding:6px 2px">Nothing planned. Choose orders from the menus on the left, or click a nation.</div>`;
  const inbox = sc.deals.inbox.map((d) => `<div class="plan-item"><div class="what"><b>${d.id}</b> ${nice(d.type)} <span class="muted">${esc(nationName(d.financier))} → ${esc(nationName(d.host))}, ${esc(d.terms.source || "")}</span>${d.can_answer ? "" : `<div class="why muted">answer from next quarter</div>`}</div>${d.can_answer ? `<button class="btn small" data-deal="${d.id}">Answer</button>` : ""}</div>`).join("");
  const evs = sc.events.open.map((e) => `<div class="plan-item"><div class="what"><b>${e.id}</b> ${nice(e.type)} in ${esc(regionName(e.region))}<div class="why muted">${pct(e.pledged / e.target)} of ${money(e.target)} · until ${e.deadline}${e.you_pledged ? ` · you ${money(e.you_pledged)}` : ""}</div></div><button class="btn small" data-ev="${e.id}">Open</button></div>`).join("");
  const notes = (sc.notices || []).filter((n) => !n.startsWith("Score ")).slice(0, 8).map((n) => `<div class="plan-item"><div class="what" style="font-size:12.5px">${esc(n)}</div></div>`).join("");
  $("#outliner").innerHTML = `
    <div class="sec-head"><span>This quarter's orders</span><span class="muted" style="font-size:12px">${S.plan.length} planned</span></div>
    <div class="sec-body">${planRows}</div>
    ${standings()}
    ${inbox ? `<div class="sec-head"><span>Offers to you</span></div><div class="sec-body">${inbox}</div>` : ""}
    ${evs ? `<div class="sec-head"><span>Event funds</span></div><div class="sec-body">${evs}</div>` : ""}
    ${notes ? `<div class="sec-head"><span>Dispatches</span></div><div class="sec-body">${notes}</div>` : ""}`;
  $("#outliner").querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { S.plan.splice(+b.dataset.rm, 1); checkPlan(); }));
  $("#outliner").querySelectorAll("[data-deal]").forEach((b) => (b.onclick = () => dealWindow(b.dataset.deal)));
  $("#outliner").querySelectorAll("[data-ev]").forEach((b) => (b.onclick = () => eventWindow(sc.events.open.find((e) => e.id === b.dataset.ev))));
  $("#outliner").querySelectorAll("[data-board]").forEach((r) => (r.onclick = () => openNation(r.dataset.board)));
  const fold = $("#board-fold");
  if (fold) fold.onclick = () => { S.boardOpen = !boardOpen(); try { localStorage.setItem("board:open", S.boardOpen ? "1" : "0"); } catch { /* storage unavailable */ } renderOutliner(); };
}

// The public standings: every nation's rank, Impact (its climate contribution for its size) and
// its economy, which other governments can see. Folded, it keeps the top three and you.
function boardOpen() {
  if (S.boardOpen == null) { try { S.boardOpen = localStorage.getItem("board:open") !== "0"; } catch { S.boardOpen = true; } }
  return S.boardOpen;
}
function standings() {
  const sc = S.data.screen, nations = S.data.world.nations;
  if (!sc.leaders.length) return `<div class="sec-head"><span>Standings</span></div><div class="sec-body muted" style="font-size:12.5px">Ranks appear after your first quarter.</div>`;
  const open = boardOpen();
  const rows = sc.leaders.filter((l, i) => open || i < 3 || l.nation === sc.country).map((l) => {
    const n = nations[l.nation] || {}, me = l.nation === sc.country;
    const g = n.growth_year ?? n.growth ?? 0;
    const t = ttTable(nationName(l.nation), [["Rank", `${l.rank} of 16`], ["Score", num(l.score, 0)], ["Impact", num(l.impact, 0)], ["Prosperity", num(l.prosperity, 0)],
      ["CO2 vs 2025", spct(n.emissions_change, 0)], ["Clean energy", pct(n.clean_share)], ["GDP a quarter", money(n.gdp / 4)], ["GDP vs 2025", spct(n.gdp_vs_2025, 0)], ["Growth, last year", spct(g, 1)]],
    "Impact: CO2 cut at home or helped cut abroad, for the nation's size. 50 = no change.");
    return `<tr class="${me ? "me" : ""}" data-board="${l.nation}" ${tip(t)}><td class="r">${l.rank}</td><td class="nm">${crestMini(l.nation)}${esc(nationName(l.nation))}</td>
      <td class="imp"><i style="width:${Math.max(0, Math.min(100, l.impact))}%"></i><span>${num(l.impact, 0)}</span></td>
      <td class="num ${g < 0 ? "bad" : ""}">${spct(g, 1)}</td><td class="num">${money(n.gdp / 4)}</td></tr>`;
  }).join("");
  return `<div class="sec-head"><span>Standings</span><button class="link-btn" id="board-fold">${open ? "Show top three" : "Show all 16"}</button></div>
    <div class="sec-body board"><table><tr class="muted"><td></td><td>Nation</td><td>Impact</td><td class="num">Growth</td><td class="num" title="GDP a quarter">GDP/q</td></tr>${rows}</table></div>`;
}

let checkSeq = 0;
async function checkPlan() {
  const seq = ++checkSeq;
  savePlan();
  S.checks = [];
  renderOutliner(); renderTopbar(); renderEndturn();
  if (!S.plan.length || S.data.screen.over) return;
  const res = await fetch("/api/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actions: S.plan }) }).then((r) => r.json());
  if (seq !== checkSeq) return;
  S.checks = res.results || [];
  renderOutliner(); renderTopbar(); renderEndturn(); renderAlerts();
}

const planKey = () => S.data && `plan:${S.data.name}:${S.data.screen.turn}`;
function savePlan() {
  try { localStorage.setItem(planKey(), JSON.stringify(S.plan)); } catch { /* storage unavailable */ }
}
function restorePlan() {
  try {
    const saved = JSON.parse(localStorage.getItem(planKey()) || "[]");
    if (Array.isArray(saved)) S.plan = saved;
  } catch { S.plan = []; }
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
  advice: { ico: "🎓", lbl: "Advice", title: "Your advisors" },
};

function renderMenubar() {
  $("#menubar").innerHTML = Object.entries(MENU).map(([k, m]) =>
    `<button class="menu-btn ${S.menu === k ? "active" : ""} ${m.actions && S.data && !m.actions.some(orderOpen) ? "locked" : ""}" data-menu="${k}"><span class="ico">${m.ico}</span><span class="lbl">${m.lbl}</span></button>`).join("");
  $("#menubar").querySelectorAll(".menu-btn").forEach((b) => (b.onclick = () => openMenu(b.dataset.menu)));
}

function renderEndturn() {
  const sc = S.data.screen;
  const bad = S.checks.filter((c) => c && !c.ok).length;
  $("#endturn").innerHTML = sc.over
    ? `<button class="btn primary big" id="end-btn">The game is over</button>`
    : `<div class="meta"><span>${sc.quarter}</span><span>${S.plan.length} orders${bad ? ` · <span class="bad">${bad} refused</span>` : ""}</span></div>
       <button class="btn primary big" id="end-btn" ${tip(ttTable("End the quarter", [], "Your orders resolve in the listed order, then the world moves: the market builds, the economy grows, warming updates, and the other nations act."))}>End quarter ▸</button>
       <div class="row" style="gap:6px"><button class="btn small" id="wait-1" style="flex:1">Skip a year</button><button class="btn small" id="text-view" style="flex:1">Text screen</button></div>
       <button class="btn small" id="games">Saves &amp; new game</button>`;
  $("#end-btn").onclick = () => (sc.over ? gameOverWindow() : endQuarter());
  if (!sc.over) {
    $("#wait-1").onclick = () => skipYear();
    $("#text-view").onclick = () => textWindow();
    $("#games").onclick = async () => { S.meta = await api("/api/meta"); newGameWindow(); };
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
  S.menu = S.drawer ? S.drawer.menu : null;
  renderMenubar();
}

function openWindow({ title, body, foot = "", doc = false, wide = false, onClose }) {
  hideTip();
  $("#windows").innerHTML = `<div class="window ${doc ? "document" : "chrome"} ${wide === "x" ? "xwide" : wide ? "wide" : ""}">
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

// The impact measure in words: the average credit-weighted cut against 2025.
function belowStart(cut) {
  const v = Math.round(Math.abs(cut) * 100);
  return v === 0 ? "the same as 2025" : `${v}% ${cut > 0 ? "below" : "above"} 2025`;
}

function endingText(s) {
  const w = S.data.screen.world, first = S.data.screen.leaders[0];
  const by = {
    "Champion": `The world held warming below ${w.collapse_at} °C, and no nation did more for it than yours. You finish first.`,
    "Shared Victory": `The world held warming below ${w.collapse_at} °C. ${first ? esc(nationName(first.nation)) : "Another nation"} did the most for it; you finish ${s ? s.rank : "-"} of 16.`,
    "Climate Collapse": `Warming reached ${w.collapse_at} °C. Every nation has lost, whatever it built. The score is zero.`,
    "Voted Out": "Your government lost the election and left office. The score is zero.",
    "Fallen Government": "Unrest brought your government down. The score is zero.",
  };
  return s ? by[s.ending] || "" : "";
}

function gameOverWindow() {
  const s = S.data.screen.score;
  openWindow({
    doc: true, title: "The record of your government",
    body: `<div class="event-title">${esc(s ? s.ending : "The game is over")}</div>
      <p class="event-text">${endingText(s)}</p>
      <p class="event-text">Final score <b>${s ? num(s.score, 0) : "-"}</b>, rank ${s ? s.rank : "-"} of 16. World warming ${num(S.data.screen.world.warming_year, 2)} °C (year average).</p>
      ${s && s.honours.length ? `<p class="event-text">Honours: ${s.honours.map((h) => esc(nice(h))).join(", ")}.</p>` : ""}
      <h3>${s && s.ending === "Climate Collapse" ? "Standings when the world collapsed" : "Final standings"}</h3><ol class="report-list">${S.data.screen.leaders.map((l) => `<li>${esc(nationName(l.nation))}${l.nation === S.data.screen.country ? " (you)" : ""} — ${num(l.score, 0)} <span class="muted">· impact ${num(l.impact, 0)}</span></li>`).join("")}</ol>`,
    foot: `<button class="btn primary" id="ng">New game</button>`,
  });
  $("#ng").onclick = () => newGameWindow();
}

function textWindow() {
  openWindow({ wide: true, title: "The full text screen", body: `<pre style="white-space:pre-wrap;font-size:12.5px;margin:0">${esc(S.data.text)}</pre>` });
}

function newGameWindow() {
  const m = S.meta, P = m.profiles;
  const order = m.profile_order; // easiest first
  let pick = order[0];
  let tab = "new";
  const groups = [];
  for (const id of order) {
    const d = P[id].difficulty;
    if (!groups.length || groups[groups.length - 1].d !== d) groups.push({ d, ids: [] });
    groups[groups.length - 1].ids.push(id);
  }
  const pips = (d) => {
    const n = { easy: 1, easy_to_medium: 2, medium: 2, hard: 3 }[d] || 1;
    return `<span class="pips" title="${esc(nice(d))}">${[1, 2, 3].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
  };
  const list = groups.map((g) => `<div class="ng-group"><span>${esc(nice(g.d))}</span><span>score ×${P[g.ids[0]].score_multiplier}</span></div>
    ${g.ids.map((id) => `<button class="ng-row" data-c="${id}">${crest(id)}<span class="ng-row-text"><span class="n">${esc(P[id].name)}</span><span class="a">${esc(P[id].archetype)}</span></span>${pips(P[id].difficulty)}</button>`).join("")}`).join("");
  const saves = m.saves.length
    ? m.saves.map((s) => `<div class="ng-save">${crest(s.country)}<div class="ng-row-text"><span class="n">${esc(s.name)}</span><span class="a">${esc(m.nations[s.country]?.name || s.country)} · seed ${s.seed} · ${s.difficulty || "normal"} world · ${s.quarters_played} quarters played</span></div><button class="btn small" data-load="${esc(s.name)}">Continue</button></div>`).join("")
    : `<p class="muted">No saved games yet.</p>`;

  hideTip();
  $("#windows").innerHTML = `<div class="window chrome ng">
    <div class="win-head"><h2>Choose your nation</h2><span class="ng-goal">2025 to 2049 · keep the world below 2 °C, and be the nation that did the most to get there</span><button class="icon-btn" id="win-x" title="Close">✕</button></div>
    <div class="ng-body">
      <div class="ng-portrait" id="ng-portrait"></div>
      <div class="ng-list">
        <div class="tabs ng-tabs"><button class="tab" data-tab="new">New game</button><button class="tab" data-tab="saves">Saved (${m.saves.length})</button></div>
        <div class="ng-scroll" id="ng-new">${list}</div>
        <div class="ng-scroll hidden" id="ng-saves">${saves}</div>
      </div>
      <div class="ng-detail" id="ng-detail"></div>
    </div>
    <div class="win-foot"><div class="ng-settings" id="ng-settings">
        <label>World <select id="ng-diff">${m.difficulties.map((d) => `<option ${d === "normal" ? "selected" : ""}>${d}</option>`).join("")}</select></label>
        <label>Seed <input id="ng-seed" type="number" value="${1 + Math.floor(Math.random() * 999)}"></label>
        <label>Save name <input id="ng-name" placeholder="optional"></label>
      </div><span class="muted ng-foot-note hidden" id="ng-foot-note">Saved games continue where you left off.</span><button class="btn primary" id="ng-go">Take office</button></div>
  </div>`;
  $("#veil").classList.remove("hidden");
  const win = $("#windows .window");
  const close = () => closeWindows();
  if (S.data) { $("#win-x").onclick = close; $("#veil").onclick = close; } else { $("#win-x").remove(); $("#veil").onclick = null; }

  const show = (id) => {
    pick = id;
    const p = P[id], L = LEADERS[id], pers = PERSONALITY[p.personality] || ["", ""];
    win.querySelectorAll(".ng-row").forEach((b) => b.classList.toggle("active", b.dataset.c === id));
    $("#ng-portrait").style.background = skyColor(id);
    $("#ng-portrait").innerHTML = `${leaderPortrait(id, { label: `${L.title} of ${p.name}` })}
      <div class="ng-plate" style="--nc:${colorOf(id)}"><div class="t">${esc(L.title)}</div><div class="n">${esc(p.name)}</div></div>`;
    $("#ng-detail").innerHTML = `
      <div class="ng-title">${crest(id, true)}<div><h2>${esc(p.name)}</h2><div class="ng-arch">${esc(p.archetype)}</div>
        <div class="ng-tags"><span class="tag">${pips(p.difficulty)} ${esc(nice(p.difficulty))}</span><span class="tag">Score ×${p.score_multiplier}</span></div></div></div>
      <h3>Strengths</h3><ul class="ng-points pro">${p.pros.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <h3>Weaknesses</h3><ul class="ng-points con">${p.cons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <h3>In 2025</h3><div class="ng-figs">${p.figures.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div>
      <p class="ng-ai"><b>If the computer leads it:</b> ${esc(pers[0])}. ${esc(pers[1])}</p>`;
    $("#ng-detail").scrollTop = 0;
    $("#ng-go").textContent = `Take office: ${p.name}`;
  };
  const setTab = (t) => {
    tab = t;
    win.querySelectorAll(".ng-tabs .tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
    $("#ng-new").classList.toggle("hidden", t !== "new");
    $("#ng-settings").classList.toggle("hidden", t !== "new");
    $("#ng-saves").classList.toggle("hidden", t !== "saves");
    $("#ng-go").classList.toggle("hidden", t !== "new");
    $("#ng-foot-note").classList.toggle("hidden", t === "new");
  };
  win.querySelectorAll(".ng-row").forEach((b) => (b.onclick = () => show(b.dataset.c)));
  win.querySelectorAll(".ng-tabs .tab").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  win.querySelectorAll("[data-load]").forEach((b) => (b.onclick = async () => {
    try { S.plan = []; setData(await api("/api/load", { name: b.dataset.load })); closeWindows(); } catch (e) {
      toast(/different data files/.test(e.message) ? "This save was made under older game rules, so it cannot be continued. Start a new game." : e.message, 5000);
    }
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
  show(pick);
  setTab(tab);
}

// ---------- action windows ----------

function openMenu(key) {
  if (key === "ledger") return ledgerWindow();
  if (key === "advice") return adviceWindow();
  if (key === "research") return researchWindow();
  if (S.drawer && S.drawer.menu === key) return closeDrawer(); // a second click folds it away
  actionWindow(MENU[key].title, MENU[key].actions, null, {}, key);
}

// The orders drawer: a tall panel beside the left rail listing one category's orders. Each
// order unfolds in place into its form; only one is open at a time.
function actionWindow(title, types, first, preset, menu = null) {
  closeWindows();
  if (S.panel) closePanel();
  const open = types.filter(orderOpen), locked = types.filter((t) => !orderOpen(t));
  S.drawer = { title, types: open, locked, open: open.includes(first) ? first : null, preset, menu };
  S.menu = menu;
  renderMenubar();
  drawDrawer();
}

// After a turn (or the Advice switch), a menu drawer picks up orders that have just opened.
function refreshDrawer() {
  const d = S.drawer;
  if (!d || !d.menu || !MENU[d.menu].actions) return;
  const locked = MENU[d.menu].actions.filter((t) => !orderOpen(t));
  if (locked.length === (d.locked || []).length) return;
  d.types = MENU[d.menu].actions.filter(orderOpen);
  d.locked = locked;
  drawDrawer(); // redraw in place, leaving any open window (the dispatch) alone
}

function closeDrawer() {
  $("#drawer").classList.add("hidden");
  $("#drawer").innerHTML = "";
  S.drawer = null;
  S.menu = null;
  renderMenubar();
  placeAlerts();
}

function drawDrawer() {
  const d = S.drawer, cat = S.meta.catalogue, el = $("#drawer");
  const ico = d.menu ? MENU[d.menu].ico : "✎";
  el.classList.remove("hidden");
  el.innerHTML = `<div class="panel-head"><span class="drawer-ico">${ico}</span><div class="titles"><h2>${esc(d.title)}</h2><div class="sub">${d.types.length ? `${d.types.length} order${d.types.length > 1 ? "s" : ""} · choose one to open it` : "Not open yet"}</div></div><button class="icon-btn" id="d-x" title="Close">✕</button></div>
    <div class="panel-body drawer-body">${d.types.map((t) => {
      const o = ORDERS[t] || {}, [pi, pl] = payWith(cat[t].cost);
      return `<div class="acc" data-t="${t}">
      <button class="acc-head"><span class="acc-ico">${o.icon || "◆"}</span><span class="acc-text"><span class="t">${esc(nice(t))}</span><span class="line">${esc(o.line || "")}</span>
        <span class="acc-tags"><span class="tag">${cat[t].slot === "domestic" ? "🏠 Home" : "🌐 Abroad"}</span><span class="tag">${pi} ${pl}</span></span></span><span class="chev">▸</span></button>
      <div class="acc-body"></div></div>`;
    }).join("")}${lockedNote(d.locked || [])}</div>`;
  $("#d-x").onclick = closeDrawer;
  placeAlerts();
  el.querySelectorAll(".acc-head").forEach((b) => (b.onclick = () => {
    const t = b.parentElement.dataset.t;
    unfold(d.open === t ? null : t);
  }));
  const unfold = (t) => {
    d.open = t;
    el.querySelectorAll(".acc").forEach((a) => {
      const on = a.dataset.t === t;
      a.classList.toggle("open", on);
      const body = $(".acc-body", a);
      if (on) { renderForm(body, t, d.preset, { compact: true }); a.scrollIntoView({ block: "nearest" }); }
      else body.innerHTML = "";
    });
  };
  unfold(d.open || (d.types.length === 1 ? d.types[0] : null));
}

const shortCost = (c) => String(c).replace(/\s*\(see the cost table in `show`\)/, "").replace(/`show`/g, "the screen");

function rangeOf(desc) {
  const m = /(-?\d+(?:\.\d+)?)\s*(?:\([^)]*\))?\s*to\s*(-?\d+(?:\.\d+)?)/.exec(desc);
  return m ? [+m[1], +m[2]] : null;
}

// ---------- order forms: picture tiles, whole-number units, a Civ-style result card ----------

const whole = (x) => (x == null || Number.isNaN(+x) ? "-" : Math.round(+x).toLocaleString());
const years = (q) => (q % 4 === 0 ? `${q / 4} yr${q === 4 ? "" : "s"}` : q < 4 ? `${q} qtr${q > 1 ? "s" : ""}` : `${Math.round(q / 4)} yrs`);
const halfPct = (p) => {
  if (p >= 10) return `${whole(p)}%`;
  const r = Math.round(p * 2) / 2;
  if (r === 0) return p > 0 ? "under ½%" : "0%";
  return `${Math.floor(r) || ""}${r % 1 ? "½" : ""}%`;
};
const shareOf = (ej, demand) => halfPct((ej / demand) * 100);
const chip = (ico, text, cls = "") => `<span class="fx ${cls}"><i>${ico}</i>${esc(text)}</span>`;
const fxChips = (keys = [], cls = "") => keys.map((k) => chip(FX[k][0], FX[k][1], cls)).join("");
const humane = (text) => String(text)
  .replace(/(-?\d+(?:\.\d+)?)\s*T\$/g, (_, x) => money(+x))
  .replace(/(-?\d+(?:\.\d+)?) capital\b/g, (_, x) => `${money(+x)} of capital`) // capital is in T$
  .replace(/(of capital, has )(-?\d+(?:\.\d+)?)/g, (_, a, x) => `${a}${money(+x)}`)
  .replace(/\d+\.\d+/g, (x) => (Math.abs(+x) >= 1 ? whole(+x) : String(+(+x).toPrecision(1))));
const SIZE_TYPES = ["build_capacity", "retire_capacity", "build_grid_storage", "retrofit_ccs"];
const myDemand = () => S.data.screen.energy.demand || 1;

function payWith(cost) {
  const c = String(cost);
  if (c.includes("political")) return ["🏛", "Political capital"];
  if (c.includes("influence")) return ["🎖", "Influence"];
  if (/capital|price|penalty/.test(c)) return ["💰", "Capital"];
  return ["✓", "Free"];
}

// Which unit a number is shown in. Values the player types are whole numbers in these units;
// `scale` turns them back into the game's own units when the order is sent.
function unitOf(type, name, desc, form) {
  const val = (n) => {
    const e = form && form.querySelector(`[name="${n}"]`);
    if (!e) return null;
    try { return JSON.parse(e.value || "null"); } catch { return e.value; }
  };
  const cap = Math.max(0, (S.data.screen.resources.capital || 0) - plannedSpend());
  const bnChips = () => [...new Set([0.1, 0.25, 0.5].map((f) => Math.round(cap * f * 1000)).filter((v) => v >= 1))];
  const d = String(desc);
  if (name === "amount" && SIZE_TYPES.includes(type)) return { unit: "% of your energy", scale: myDemand() / 100, chips: [0.5, 1, 2, 5], half: true };
  if (type === "propose_deal" && name === "amount") {
    if (val("deal_type") === "climate_loan") return { unit: "$ bn", scale: 0.001, chips: bnChips(), dyn: true };
    const host = S.data.world.nations[(form && form.querySelector('[name="target"]') || {}).value];
    return { unit: "% of their energy", scale: ((host && host.demand) || 1) / 100, chips: [1, 2, 5], dyn: true };
  }
  if (name === "__term") {
    const dt = type === "respond_deal" ? (S.data.screen.deals.inbox.find((x) => x.id === val("deal_id")) || {}).type : val("deal_type");
    if (dt === "energy_as_a_service") return { unit: "$ per GJ", scale: 1, dyn: true };
    if (dt === "equity_for_energy") return { unit: "% of profit", scale: 0.01, dyn: true };
    return { unit: "% a year", scale: 0.01, dyn: true };
  }
  if (type === "set_tax_credit" && name === "rate") {
    return val("kind") === "manufacturing" ? { unit: "% of sales", scale: 0.01, dyn: true } : { unit: "$ per GJ", scale: 1, dyn: true };
  }
  if (d.includes("T$")) return { unit: "$ bn", scale: 0.001, chips: bnChips() };
  if (d.includes("MtCO2")) return { unit: d.includes("/yr") ? "Mt CO2 a year" : "Mt CO2", scale: 1 };
  if (d.includes("factory units")) return { unit: "factory lines", scale: 1, chips: [1, 2, 5] };
  if (d.includes("$/t") || name === "max_price" || name === "min_price") return { unit: "$ per tonne", scale: 1 };
  if (type === "set_tax_rate") return { unit: "points of GDP", scale: 0.01 };
  if (name === "duration") return { unit: "years", scale: 4 };
  if (name === "year") return { unit: "", scale: 1 };
  if (type === "make_pledge" && name === "target") return { unit: "% of 2025 emissions", scale: 0.01, chips: [80, 50, 25, 0] };
  if (type === "set_permitting") return { unit: "% reform", scale: 0.01, chips: [0, 25, 50, 100] };
  if (/share|level|collateral|exit_penalty/.test(name) || /\b0 to (0\.\d|1)\b/.test(d)) return { unit: "%", scale: 0.01 };
  return { unit: "", scale: 1 };
}

function tileInfo(type, v) {
  const sc = S.data.screen, cost = (sc.energy.costs || {})[v], src = (S.data.world.sources || {})[v];
  const lines = [];
  if (["build_capacity", "build_grid_storage", "set_subsidy", "finance_region", "propose_deal"].includes(type) && cost) {
    if (type !== "propose_deal" && type !== "finance_region") lines.push(`${money(cost.unit_cost * myDemand() * 0.01)} per 1%`);
    if (cost.lcoe != null) lines.push(`$${whole(cost.lcoe)}/GJ power`);
  }
  if (type === "retire_capacity") lines.push(`you have ${shareOf((sc.energy.capacity || {})[v] || 0, myDemand())}`);
  if (src && ["build_capacity", "build_grid_storage", "finance_region", "propose_deal"].includes(type)) lines.push(`⏱ ${years(src.quarters)}`);
  const tag = src ? (src.category === "fossil" ? `<span class="tile-tag dirty">CO2</span>` : src.category === "enabler" ? "" : `<span class="tile-tag clean">clean</span>`) : "";
  return { lines, tag };
}

// Sources in a familiar order: clean first, fossil next, technologies still to research last.
const TILE_ORDER = ["solar", "onshore_wind", "offshore_wind", "hydro", "nuclear", "geothermal", "bioenergy", "storage", "long_duration_storage",
  "grid", "electrolysers", "gas", "coal", "oil", "wind", "smr", "advanced_fission", "enhanced_geothermal", "fusion"];
const SOURCE_NEEDS = { smr: "small_modular_reactors", advanced_fission: "advanced_fission", enhanced_geothermal: "enhanced_geothermal", fusion: "fusion" };
const locked = (v) => {
  const need = SOURCE_NEEDS[v];
  return need ? !(S.data.screen.research.find((r) => r.tech === need) || {}).have : false;
};

function tilesControl(type, name, values, value) {
  const rank = (v) => { const i = TILE_ORDER.indexOf(v); return (locked(v) ? 100 : 0) + (i < 0 ? 50 : i); };
  values = name === "deal_type" ? values : [...values].sort((a, b) => rank(a) - rank(b));
  const sel = JSON.stringify(values.includes(value) ? value : values.find((v) => !locked(v)) ?? values[0]);
  return `<input type="hidden" name="${name}" data-kind="list" value="${esc(sel)}"><div class="tiles" data-for="${name}">${values.map((v) => {
    const { lines, tag } = tileInfo(type, v);
    const icon = name === "deal_type" ? DEAL_ICON[v] : SOURCE_ICON[v] || "◆";
    const sub = name === "deal_type" ? `<span class="tile-sub">${esc(DEAL_LINE[v] || "")}</span>` : lines.map((l) => `<span class="tile-sub">${esc(l)}</span>`).join("");
    const lock = name !== "deal_type" && locked(v);
    return `<button type="button" class="tile ${JSON.stringify(v) === sel ? "on" : ""} ${lock ? "locked" : ""}" data-v="${esc(JSON.stringify(v))}" ${lock ? 'title="Needs research first"' : ""}>${lock ? `<span class="tile-tag lock">🔒</span>` : tag}<span class="tile-ico">${icon}</span><span class="tile-name">${esc(nice(v))}</span>${sub}</button>`;
  }).join("")}</div>`;
}

function segControl(name, values, value, label = nice) {
  const sel = JSON.stringify(values.includes(value) ? value : values[0]);
  return `<input type="hidden" name="${name}" data-kind="list" value="${esc(sel)}"><div class="seg" data-for="${name}">${values.map((v) =>
    `<button type="button" class="${JSON.stringify(v) === sel ? "on" : ""}" data-v="${esc(JSON.stringify(v))}">${esc(label(v))}</button>`).join("")}</div>`;
}

function control(type, name, spec, value, form) {
  const sc = S.data.screen, me = sc.country;
  const opt = (v, l, sel) => `<option value="${esc(v)}" ${sel ? "selected" : ""}>${esc(l)}</option>`;
  if (type === "set_tax_credit" && name === "tech") {
    const m = /generation: \[([^\]]*)\]; manufacturing: \[([^\]]*)\]/.exec(String(spec));
    const parse = (s) => s.split(",").map((x) => x.trim().replace(/'/g, ""));
    return { tiles: true, html: (kind) => tilesControl(type, name, parse(kind === "manufacturing" ? m[2] : m[1]), value) };
  }
  if (Array.isArray(spec)) {
    let list = spec;
    if (type === "retire_capacity") list = spec.filter((v) => (sc.energy.capacity || {})[v] > 0);
    const allSources = list.every((v) => SOURCE_ICON[v]);
    // Sales and factory partnerships are made at the trade table (Open talks), not here.
    if (name === "deal_type") list = list.filter((v) => !["equipment_sale", "factory_partnership"].includes(v));
    if (name === "deal_type" || (allSources && list.length <= 15 && type !== "invest_research")) return tilesControl(type, name, list, value);
    if (typeof list[0] === "boolean") return segControl(name, list, value, (v) => (v ? "On" : "Off"));
    if (list.length <= 4) return segControl(name, list, value);
    const label = name === "region" ? regionName : nice;
    return `<select name="${name}" data-kind="list">${list.map((v) => opt(JSON.stringify(v), label(v), JSON.stringify(v) === JSON.stringify(value))).join("")}</select>`;
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
    return list.length ? `<select name="${name}" data-kind="str">${list.map((x) => opt(x.id, `${x.id} ${nice(x.type)} (${nationName(x.financier)} → ${nationName(x.host)})`, x.id === value)).join("")}</select>` : `<div class="muted">None.</div>`;
  }
  if (d.includes("technology")) {
    const techs = type === "set_license_price" ? sc.research.filter((r) => r.have && !r.licensed) : sc.research;
    return techs.length ? `<select name="${name}" data-kind="str">${techs.map((r) => opt(r.tech, r.name, r.tech === value)).join("")}</select>` : `<div class="muted">You have researched nothing to sell yet.</div>`;
  }
  if (d.includes("list of nation")) return null;
  return { num: true, canMax: d.includes('"max"'), value, desc: d };
}

function numControl(type, name, c, form) {
  const u = unitOf(type, name, c.desc, form);
  const isMax = c.value === "max";
  let v = "";
  const round = (x) => (u.half ? Math.round(x * 2) / 2 : Math.round(x));
  if (!isMax && c.value != null && c.value !== "") v = round(+c.value / u.scale);
  if (v === 0 && +c.value > 0) v = ""; // an example too small to show as a whole number
  if (v === "" && !isMax) v = u.chips ? u.chips[0] : 1;
  if (type === "set_tax_credit" && name === "rate" && !v) v = 1;
  return `<div class="amt"><input name="${name}" data-kind="num" data-scale="${u.scale}" type="number" step="${u.half ? 0.5 : 1}" value="${esc(v)}" ${isMax ? "disabled" : ""}>
      <span class="unit" data-unit="${name}">${esc(u.unit)}</span></div>
    <div class="chips" data-chips="${name}">${(u.chips || []).map((x) => `<button type="button" data-set="${x}">${u.unit.startsWith("%") ? halfPct(x) : x}</button>`).join("")}${c.canMax ? `<label class="maxchip"><input type="checkbox" data-max="${name}" ${isMax ? "checked" : ""}> Max</label>` : ""}</div>`;
}

function renderForm(el, type, preset, { compact = false } = {}) {
  const spec = S.meta.catalogue[type], info = ORDERS[type] || {};
  const ex = spec.example || {};
  const FIELD_ORDER = {
    propose_deal: ["target", "deal_type", "source", "amount", "rate | price | share | markup", "duration", "currency", "collateral", "exit_penalty"],
    set_tax_credit: ["kind", "tech", "rate"],
  };
  const order = FIELD_ORDER[type];
  // choices first (what), then amounts (how much); the server sends parameters alphabetically
  const AMOUNTS = ["amount", "level", "share", "rate", "price", "min_price", "max_price", "year", "duration", "on", "response"];
  const rankOf = (n) => (order ? order.indexOf(n) : AMOUNTS.includes(n) || (type === "make_pledge" && n === "target") ? 1 : 0);
  const params = Object.entries(spec.params).sort(([a], [b]) => rankOf(a) - rankOf(b));
  const LEVEL = { set_carbon_price: "Carbon price", set_tax_rate: "Tax change", set_permitting: "Reform", set_activity_cap: "Cap on heavy industry", set_tariff: "Tariff" };
  const LABEL = { amount: "Size", source: "Source", kind: "Kind", deal_type: "Deal", target: type === "make_pledge" ? "Target" : "Nation",
    level: LEVEL[type] || "Level", on: "Ban new fossil plants", tech: "Technology", bloc: "Club", deal_id: "Deal", event_id: "Event",
    share: type === "rebate" ? "Share handed back" : type === "set_subsidy" ? "Share of cost paid" : type === "set_domestic_content" ? "Share made at home" : "Share",
    max_price: "Highest price", min_price: "Lowest price", rate: type === "set_tax_credit" ? "Credit" : "Rate" };
  el.innerHTML = `${compact ? "" : `<h2 style="font-size:20px">${esc(nice(type))}</h2>`}
    ${info.gives || info.takes ? `<div class="fx-rows">${info.gives ? `<div class="fx-row"><span class="fx-k">Gives</span>${fxChips(info.gives, "good")}</div>` : ""}${info.takes ? `<div class="fx-row"><span class="fx-k">Takes</span>${fxChips(info.takes, "bad")}</div>` : ""}</div>` : ""}
    ${dealPreface(type, preset)}
    <form id="af"></form>
    <div class="result" id="af-check"><span class="muted">Checking…</span></div>
    <div class="row between" style="margin-top:10px"><button type="button" class="linkish" id="af-more">ⓘ Details</button><button class="btn primary" id="af-add">Add to orders</button></div>
    <div class="details hidden" id="af-details"><p>${esc(shortCost(spec.summary))}</p>${info.note ? `<p>${esc(info.note)}</p>` : ""}<p class="muted">Cost: ${esc(shortCost(spec.cost))} · ${esc(spec.slot)} slot</p></div>`;
  const form = $("#af", el);
  // fields: built in order so later fields can read earlier ones (deal type, kind)
  const rows = [];
  for (const [pname, desc] of params) {
    if (pname.startsWith("tech, capital_share")) continue; // factory partnerships: the trade table
    const name = pname.startsWith("rate | price | share") ? "__term" : pname;
    if (name === "__term" && type === "respond_deal") {
      rows.push({ name, html: () => numControl(type, name, { desc: "", value: null }, form), label: "Counter terms", hint: "only if you counter" });
      continue;
    }
    if (name === "__term") {
      const TERM_DEFAULT = { equipment_on_credit: 0.06, climate_loan: 0.03, energy_as_a_service: 15, equity_for_energy: 0.3 };
      const dealType = () => JSON.parse((form.querySelector('[name="deal_type"]') || { value: "null" }).value);
      rows.push({ name, html: () => numControl(type, name, { desc: "", value: TERM_DEFAULT[dealType()] ?? ex.rate }, form), label: "Terms" });
      continue;
    }
    const c = control(type, name, desc, preset[name] ?? ex[name], form);
    if (c === null) continue;
    let html;
    if (c && c.num) html = () => numControl(type, name, c, form);
    else if (c && c.tiles) html = () => c.html(JSON.parse((form.querySelector('[name="kind"]') || { value: '"generation"' }).value));
    else html = () => c;
    rows.push({ name, html, label: LABEL[name] || nice(name) });
  }
  form.innerHTML = rows.map((r) => `<div class="field" data-field="${r.name}"><label>${esc(r.label)}${r.hint ? ` <span class="muted">(${esc(r.hint)})</span>` : ""}</label><div class="field-c">${r.html()}</div></div>`).join("");
  // fields whose unit or choices depend on another field are redrawn when that field changes
  const redraw = (names) => names.forEach((n) => {
    const r = rows.find((x) => x.name === n);
    const box = form.querySelector(`[data-field="${n}"] .field-c`);
    if (r && box) box.innerHTML = r.html();
  });
  const DEPENDS = { target: ["amount"], deal_type: ["amount", "__term"], kind: ["tech", "rate"], deal_id: ["__term"] };
  if (["propose_deal", "respond_deal", "set_tax_credit"].includes(type)) redraw([...new Set(Object.values(DEPENDS).flat())]);

  const build = () => {
    const act = { type };
    form.querySelectorAll("[name]").forEach((inp) => {
      const n = inp.name;
      if (inp.dataset.kind === "list") act[n] = JSON.parse(inp.value);
      else if (inp.dataset.kind === "str") act[n] = inp.value;
      else if (inp.dataset.kind === "num") {
        const box = form.querySelector(`[data-max="${n}"]`);
        if (box && box.checked) act[n] = "max";
        else if (inp.value !== "") act[n] = +(+inp.value * +inp.dataset.scale).toPrecision(6);
        else if (type === "set_license_price" && n === "price") act[n] = null;
      }
    });
    if ("__term" in act) {
      const term = act.__term; delete act.__term;
      const dt = act.deal_type || (S.data.screen.deals.inbox.find((x) => x.id === act.deal_id) || {}).type;
      const key = termKey(dt);
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
    if (!r) { box.className = "result bad"; box.innerHTML = `<div class="r-head">✗ ${esc(res.error || "Could not check")}</div>`; return; }
    box.className = `result ${r.ok ? "ok" : "bad"}`;
    const costs = Object.entries(r.cost || {}).filter(([, v]) => v).map(([k, v]) =>
      k === "capital" ? chip("💰", money(v)) : k === "political_capital" ? chip("🏛", `${whole(v)} political capital`) : k === "influence" ? chip("🎖", `${whole(v)} influence`) : chip("•", `${whole(v)} ${k.replace(/_/g, " ")}`)).join("");
    box.innerHTML = `<div class="r-head">${r.ok ? "✓ Ready to order" : `✗ ${esc(humane(r.reason))}`}</div>
      ${r.ok ? `<div class="r-row"><span class="fx-k">Costs</span>${costs || chip("✓", "nothing now")}</div>` : ""}
      ${r.ok ? payoff(type, r.action) : ""}${r.ok && r.note ? `<div class="r-note">${esc(humane(r.note))}</div>` : ""}`;
  };
  const onChange = (ev) => {
    const t = ev.target;
    if (t.dataset && t.dataset.max) { const inp = form.querySelector(`[name="${t.dataset.max}"]`); if (inp) inp.disabled = t.checked; }
    const n = t.name || (t.closest("[data-for]") || {}).dataset?.for;
    if (n && DEPENDS[n]) redraw(DEPENDS[n]);
    preview();
  };
  form.addEventListener("input", preview);
  form.addEventListener("change", onChange);
  form.addEventListener("click", (ev) => {
    const tile = ev.target.closest("[data-v]");
    if (tile) {
      const wrap = tile.parentElement, name = wrap.dataset.for;
      wrap.querySelectorAll("[data-v]").forEach((b) => b.classList.toggle("on", b === tile));
      form.querySelector(`[name="${name}"]`).value = tile.dataset.v;
      if (DEPENDS[name]) redraw(DEPENDS[name]);
      preview();
      return;
    }
    const set = ev.target.closest("[data-set]");
    if (set) {
      const name = set.parentElement.dataset.chips, inp = form.querySelector(`[name="${name}"]`);
      inp.value = set.dataset.set; inp.disabled = false;
      const mx = form.querySelector(`[data-max="${name}"]`); if (mx) mx.checked = false;
      preview();
    }
  });
  form.addEventListener("submit", (ev) => ev.preventDefault());
  $("#af-more", el).onclick = () => $("#af-details", el).classList.toggle("hidden");
  $("#af-add", el).onclick = () => { addToPlan(build()); };
  preview();
}

// What the order buys, in whole numbers, from the screen's own figures.
function payoff(type, a) {
  const sc = S.data.screen, src = (S.data.world.sources || {})[a.source || a.kind];
  const out = [];
  if (type === "build_capacity" && a.amount > 0) {
    const cost = (sc.energy.costs || {})[a.source] || {};
    out.push(chip("⚡", `+${shareOf(a.amount, myDemand())} of your energy`, "good"));
    if (src) out.push(chip("⏱", `online in ${years(src.quarters)}`));
    if (cost.lcoe != null) out.push(chip("💲", `$${whole(cost.lcoe)}/GJ (your average $${whole(sc.energy.price)})`));
    if (src) out.push(src.category === "fossil" ? chip("🏭", "burns fossil fuel", "bad") : chip("🌱", "no CO2", "good"));
  } else if (type === "retire_capacity" && a.amount > 0) {
    out.push(chip("⚡", `−${shareOf(a.amount, myDemand())} of your energy`, "bad"));
    if (src && src.category === "fossil") out.push(chip("🌱", "less CO2", "good"));
  } else if (type === "build_grid_storage" && a.amount > 0) {
    out.push(chip("⚡", `+${shareOf(a.amount, myDemand())} more wind and solar usable`, "good"));
    if (src) out.push(chip("⏱", `ready in ${years(src.quarters)}`));
  } else if (type === "finance_region" && src) {
    out.push(chip("⏱", `built in ${years(src.quarters)}`), chip("🌱", "cuts the region's CO2", "good"));
  } else {
    return "";
  }
  return `<div class="r-row"><span class="fx-k">Gives</span>${out.join("")}</div>`;
}

const DEAL_TYPES = {
  equipment_on_credit: ["Equipment on credit", "You build the plant in their country; they repay cost plus interest (rate) over the duration once it runs. Risk: default if their hard currency runs out."],
  climate_loan: ["Climate loan", "You lend cash (amount in T$) that builds the plant at their cost; repaid with interest. Usually concessional."],
  energy_as_a_service: ["Energy as a service", "You own and run the plant; they pay a price per GJ it can produce. Steady income; they can exit by paying the penalty."],
  equity_for_energy: ["Equity for energy", "You take a share of the plant's operating margin. No fixed payments, so no default, but the plant can fail if the host becomes unreliable."],
};

const DEAL_HOST = {
  equipment_on_credit: "They build the plant in your country; you repay its cost plus interest over the duration once it runs. If your hard currency runs out you default and lose trust.",
  climate_loan: "They lend the cash to build the plant at your cost; you repay it with interest.",
  energy_as_a_service: "They own and run the plant in your country; you pay the price per GJ it can produce, and can exit by paying the penalty.",
  equity_for_energy: "They build the plant and take a share of its operating margin. No fixed payments, but the plant can fail if your country becomes unreliable.",
};

function dealPreface(type, preset) {
  if (type === "propose_deal") {
    return `<p class="muted small-note">They answer next quarter and may counter. Every deal earns climate credit for the cut it makes and builds trust.</p>`;
  }
  if (type === "respond_deal") {
    const d = S.data.screen.deals.inbox.find((x) => x.id === preset.deal_id);
    if (!d) return "";
    const t = d.terms, host = d.host === S.data.screen.country;
    const hostDemand = (S.data.world.nations[d.host] || {}).demand || myDemand();
    const rows = [["Deal", `${DEAL_ICON[d.type] || ""} ${nice(d.type)}`], ["From", `${nationName(d.financier)} → ${nationName(d.host)}`],
      ["Source", `${SOURCE_ICON[t.source] || ""} ${nice(t.source || "")}`],
      ["Size", d.type === "climate_loan" ? money(t.amount) : `${shareOf(t.amount, hostDemand)} of ${host ? "your" : "their"} energy`],
      ["Length", `${whole(t.duration / 4)} years`],
      ...("rate" in t ? [["Interest", `${whole(t.rate * 100)}% a year`]] : []), ...("price" in t ? [["Price", `$${whole(t.price)}/GJ`]] : []),
      ...("share" in t ? [["Their share", `${whole(t.share * 100)}%`]] : []), ["Collateral", `${whole(t.collateral * 100)}%`],
      ["Exit penalty", `${whole(t.exit_penalty * 100)}%`], ["Expires", d.expires]];
    const why = host ? DEAL_HOST[d.type] : DEAL_LINE[d.type];
    return `<div class="offer-terms">${rows.map(([k, v]) => `<div class="stat"><span class="k">${k}</span><span>${esc(v)}</span></div>`).join("")}</div>
      <p class="muted small-note">${esc(why)}</p>`;
  }
  return "";
}

function dealWindow(id) {
  const d = S.data.screen.deals.inbox.find((x) => x.id === id);
  if (!d) return actionWindow("Answer an offer", ["respond_deal"], "respond_deal", { deal_id: id });
  talksWindow(d.financier === S.data.screen.country ? d.host : d.financier, "offer", { deal: id });
}

// ---------- diplomacy: a meeting with another nation's leader, and the trade table ----------
//
// Clicking a nation offers one thing, Open talks. The meeting shows their leader and mood (their
// trust in you), and offers talks, a tariff (or lifting yours), a trade, and answers to their
// offers. The trade table composes the game's deal types from what each side gives, and asks
// the server (/api/negotiate) how they would answer, what they would take, and what it does for
// each side's Impact. Nothing is decided here: each choice becomes an order for this quarter.

const MOODS = [[0.65, "Friendly", "good"], [0.45, "Wary", ""], [-1, "Cold", "bad"]];
const moodOf = (t) => MOODS.find(([min]) => (t ?? 0.5) >= min);
const GREETING = {
  Friendly: "Good to see you. Our door is open. What do you have in mind?",
  Wary: "We are listening. Say what you came to say.",
  Cold: "You have not given us much reason to trust you. Make it worth our while.",
};
const REPLY = {
  accept: "That works for us. Send it, and we will sign next quarter.",
  counter: "Close. Move the terms a little and we have a deal.",
  refuse: "We cannot accept that.",
  invalid: "That is not something we can sign.",
};
// What each side can put on the table, and the deal type each pairing makes.
const GIVES = {
  build: { ico: "☀️", name: "A plant you build", sub: "Panels and turbines from your own factories when they have room" },
  capital: { ico: "💰", name: "Capital", sub: "A loan that builds clean plant there" },
  plant: { ico: "🏭", name: "A plant you run", sub: "You own it; they buy its power" },
  factory: { ico: "🏗", name: "Fund a factory", sub: "A clean-tech factory line in their country" },
};
const GETS = {
  cash: { ico: "💵", name: "Cash now", sub: "They buy the plant outright" },
  repay: { ico: "📈", name: "Repayments with interest", sub: "Back over the years, plus interest" },
  share: { ico: "🤝", name: "A share of its earnings", sub: "Paid while it does well; it can fail" },
  price: { ico: "⚡", name: "A price for its power", sub: "Per unit of power it can make" },
};
const PAIRS = {
  "build/cash": "equipment_sale", "build/repay": "equipment_on_credit", "build/share": "equity_for_energy",
  "capital/repay": "climate_loan", "plant/price": "energy_as_a_service", "factory/share": "factory_partnership",
};
const TERM = {
  rate: { unit: "% a year", step: 1, toUnit: (v) => v * 100, fromUnit: (u) => u / 100, label: "Interest" },
  share: { unit: "%", step: 5, toUnit: (v) => v * 100, fromUnit: (u) => u / 100, label: "Your share of the earnings" },
  price: { unit: "$ per GJ", step: 1, toUnit: (v) => v, fromUnit: (u) => u, label: "Price" },
  markup: { unit: "% over your cost", step: 5, toUnit: (v) => v * 100, fromUnit: (u) => u / 100, label: "Your markup" },
};
const FACTORY_LINES = { solar: ["☀️", "Solar panels"], wind: ["🌬", "Wind turbines"], storage: ["🔋", "Batteries"] };
const LINE_SOURCES = ["solar", "onshore_wind", "offshore_wind"]; // what factory lines make panels and turbines for
const OFFER_LINE = {
  equipment_on_credit: "a clean plant built in your country. You repay its cost with interest.",
  climate_loan: "a loan that builds clean plant in your country. You repay it with interest.",
  energy_as_a_service: "a plant we build and run in your country. You pay for its power.",
  equity_for_energy: "a plant in your country, for a share of its profit.",
};
// The same terms seen from the host's side, when another nation offers you a deal.
const THEIR_TERM = { rate: "Interest you pay", share: "Their share of the profit", price: "Price you pay for the power" };
const termKey = (dt) => ({ energy_as_a_service: "price", equity_for_energy: "share", equipment_sale: "markup", factory_partnership: "share" })[dt] || "rate";

function talksWindow(id, view = "talk", opt = {}) {
  closeDrawer();
  const sc = S.data.screen, v = S.data.world.nations[id], L = LEADERS[id] || {};
  const [, mood, moodCls] = moodOf(v.trust_in_you);
  const win = openWindow({
    title: `Talks with ${esc(nationName(id))}`, wide: "x",
    body: `<div class="dip">
      <div class="dip-left">
        <div class="dip-portrait" style="background:${skyOf(colorOf(id))}">${leaderPortrait(id, { color: colorOf(id), label: `${L.title || "Leader"} of ${nationName(id)}` })}</div>
        <div class="dip-name"><b>${esc(L.title || "Leader")}</b> of ${esc(nationName(id))}</div>
        <div class="dip-mood ${moodCls}">${mood}</div>
        <div class="dip-facts">
          <div><span>Their trust in you</span><b>${whole((v.trust_in_you ?? 0.5) * 100)}</b></div>
          <div><span>Your tariff on them</span><b>${pct(v.your_tariff)}</b></div>
          <div><span>Their tariff on you</span><b>${pct(v.their_tariff)}</b></div>
          <div><span>Carbon club</span><b>${v.club ? "member" : "outside"}</b></div>
          <div><span>Rank</span><b>${v.rank ? `${v.rank} of 16` : "-"}</b></div>
        </div>
      </div>
      <div class="dip-right" id="dip-right"></div></div>`,
  });
  const right = $("#dip-right", win);
  const say = (line) => `<div class="dip-say">“${esc(line)}”</div>`;
  const lockNote = (t) => !orderOpen(t) ? `opens ${quarterOf(opensAt(t))}` : "";
  const planned = (pred) => S.plan.some(pred);

  const talk = (line = GREETING[mood] + (v.their_tariff > 0 ? ` Our tariff on your goods stands at ${pct(v.their_tariff)}.` : "")) => {
    const offers = sc.deals.inbox.filter((d) => d.financier === id);
    const opts = [];
    const infl = sc.resources.influence, need = (S.meta.catalogue.open_talks.cost.match(/[\d.]+/) || [5])[0];
    const talksPlanned = planned((a) => a.type === "open_talks" && a.target === id);
    opts.push({ k: "talks", t: "Let us build trust.", s: `Hold talks: their trust rises · ${need} influence`,
      off: lockNote("open_talks") || (talksPlanned ? "already planned" : infl < +need ? `needs ${need} influence (you have ${whole(infl)}; buy it under Treasury)` : "") });
    const club = v.club && sc.world.club.includes(sc.country);
    if (v.your_tariff > 0) opts.push({ k: "lift", t: "We will lift our tariff on your goods.", s: "Trade recovers and they trust you more", off: lockNote("lift_tariff") || (planned((a) => a.type === "lift_tariff" && a.target === id) ? "already planned" : "") });
    else opts.push({ k: "tariff", t: "Your goods will face a tariff.", s: "Protects your industry; costs their trust", off: lockNote("set_tariff") || (club ? "carbon club members cannot tariff each other" : "") });
    opts.push({ k: "trade", t: "I have a proposal.", s: "Open the trade table", off: lockNote("propose_deal") });
    offers.forEach((d) => opts.push({ k: `offer:${d.id}`, t: `About your offer of ${nice(d.type).toLowerCase()}…`, s: `${SOURCE_ICON[d.terms.source] || ""} ${nice(d.terms.source || "")} · expires ${d.expires}`, off: d.can_answer ? "" : "you can answer from next quarter" }));
    opts.sort((x, y) => (x.off ? 1 : 0) - (y.off ? 1 : 0)); // what you can do now comes first
    opts.push({ k: "bye", t: "Farewell.", s: "" });
    right.innerHTML = `${say(line)}<div class="dip-opts">${opts.map((o, i) => `<button class="dip-opt" data-k="${o.k}" ${o.off ? "disabled" : ""}><span class="n">${i + 1}</span><span><b>${esc(o.t)}</b>${o.s || o.off ? `<span class="s">${esc(o.off || o.s)}</span>` : ""}</span></button>`).join("")}</div>`;
    right.querySelectorAll(".dip-opt").forEach((b) => (b.onclick = () => {
      const k = b.dataset.k;
      if (k === "bye") return closeWindows();
      if (k === "talks") { addToPlan({ type: "open_talks", target: id }); return talk("We welcome the talks. Let us keep talking."); }
      if (k === "lift") { addToPlan({ type: "lift_tariff", target: id }); return talk("A wise step. Our traders will be glad."); }
      if (k === "tariff") return tariff();
      if (k === "trade") return trade();
      if (k.startsWith("offer:")) return offer(k.slice(6));
    }));
  };

  const tariff = () => {
    const max = 0.5;
    right.innerHTML = `${say("A tariff? That will cost you our trust, and we may answer in kind.")}<div class="dip-opts">
      ${[0.1, 0.25, max].map((l, i) => `<button class="dip-opt" data-l="${l}"><span class="n">${i + 1}</span><span><b>A ${pct(l)} tariff on their goods.</b><span class="s">${l >= max ? "The highest allowed" : l >= 0.25 ? "A strong signal" : "A warning shot"}</span></span></button>`).join("")}
      <button class="dip-opt" data-l="back"><span class="n">←</span><span><b>Let me reconsider.</b></span></button></div>`;
    right.querySelectorAll(".dip-opt").forEach((b) => (b.onclick = () => {
      if (b.dataset.l === "back") return talk();
      addToPlan({ type: "set_tariff", target: id, level: +b.dataset.l });
      talk("So be it. We will remember this.");
    }));
  };

  // The trade table.
  const T = opt.trade || { give: "build", get: "repay", source: "solar", size: 1, years: 5, term: null, line: "solar", fsize: 10, cshare: 100, power: 0 };
  const trade = () => {
    const dt = PAIRS[`${T.give}/${T.get}`];
    const key = termKey(dt), tm = TERM[key];
    const costs = sc.energy.costs || {};
    if (T.term == null) T.term = { rate: 8, share: 50, markup: 15 }[key] ?? Math.round((costs[T.source] || {}).lcoe || 8);
    let sources = S.meta.catalogue.propose_deal.params.source.filter((s) => !locked(s))
      .sort((a, b) => TILE_ORDER.indexOf(a) - TILE_ORDER.indexOf(b));
    if (dt === "equipment_sale") sources = sources.filter((s) => LINE_SOURCES.includes(s));
    if (!sources.includes(T.source)) T.source = sources[0];
    const capLeft = Math.max(0, sc.resources.capital - plannedSpend());
    const sizeChips = T.give === "capital" ? [...new Set([0.1, 0.25, 0.5].map((f) => Math.max(1, Math.round(capLeft * f * 1000))))] : [0.5, 1, 2, 5];
    const sizeUnit = T.give === "capital" ? "$ bn" : "% of their energy";
    const tile = (group, k, o, on, off) => `<button type="button" class="tile ${on ? "on" : ""}" data-${group}="${k}" ${off ? "disabled" : ""}><span class="tile-ico">${o.ico}</span><span class="tile-name">${esc(o.name)}</span><span class="tile-sub">${esc(o.sub)}</span></button>`;
    const chips = (name, vals, cur, fmt) => `<div class="chips">${vals.map((x) => `<button type="button" class="${x === cur ? "on" : ""}" data-${name}="${x}">${fmt(x)}</button>`).join("")}${vals.includes(cur) ? "" : `<button type="button" class="on">${fmt(cur)}</button>`}</div>`;
    const giveBody = T.give === "factory" ? `
          <div class="trade-label">Factory line</div>
          <div class="tiles small">${Object.entries(FACTORY_LINES).map(([k, [ico, name]]) => `<button type="button" class="tile ${k === T.line ? "on" : ""}" data-line="${k}"><span class="tile-ico">${ico}</span><span class="tile-name">${esc(name)}</span></button>`).join("")}</div>
          <div class="trade-label">Size ($ bn of output a year)</div>
          ${chips("fsize", [5, 10, 25], T.fsize, (x) => `$${x} bn`)}
          <div class="trade-label">Your share of the cost (they pay the rest)</div>
          ${chips("cshare", [25, 50, 75, 100], T.cshare, (x) => `${x}%`)}
          <div class="trade-label">Cheap clean power from you (lowers its costs)</div>
          ${chips("power", [0, 0.5, 1], T.power, (x) => (x ? `${x}% of their energy` : "None"))}` : `
          <div class="trade-label">Built with</div>
          <div class="tiles small">${sources.map((s) => `<button type="button" class="tile ${s === T.source ? "on" : ""}" data-source="${s}"><span class="tile-ico">${SOURCE_ICON[s] || "◆"}</span><span class="tile-name">${esc(nice(s))}</span></button>`).join("")}</div>
          <div class="trade-label">How much (${sizeUnit})</div>
          ${chips("size", sizeChips, T.size, (x) => T.give === "capital" ? `$${whole(x)} bn` : `${x}%`)}`;
    right.innerHTML = `<div class="trade">
      <div class="trade-cols">
        <div class="trade-col"><h3>You give</h3>
          <div class="tiles">${Object.entries(GIVES).map(([k, o]) => tile("give", k, o, k === T.give)).join("")}</div>
          ${giveBody}
        </div>
        <div class="trade-col"><h3>They give</h3>
          <div class="tiles">${Object.entries(GETS).map(([k, o]) => tile("get", k, o, k === T.get, !PAIRS[`${T.give}/${k}`])).join("")}</div>
          <div class="trade-label">${tm.label} (${tm.unit})</div>
          <div class="stepper"><button type="button" data-step="-1">−</button><b>${whole(T.term)}</b><button type="button" data-step="1">+</button></div>
          ${dt === "equipment_sale" ? "" : `<div class="trade-label">For</div>${chips("years", [3, 5, 10], T.years, (x) => `${x} years`)}`}
        </div>
      </div>
      <div class="trade-verdict" id="tv">${say("Let us see…")}</div>
      <div class="trade-sum" id="ts"></div>
      <div class="row between" style="margin-top:10px"><button class="btn" id="t-back">← Back</button>
        <span class="row" style="gap:8px"><button class="btn" id="t-take">What would it take?</button><button class="btn primary" id="t-go">Propose this trade</button></span></div></div>`;
    const redraw = () => trade();
    right.querySelectorAll("[data-give]").forEach((b) => (b.onclick = () => {
      T.give = b.dataset.give;
      if (!PAIRS[`${T.give}/${T.get}`]) T.get = Object.keys(GETS).find((g) => PAIRS[`${T.give}/${g}`]);
      T.size = T.give === "capital" ? Math.max(1, Math.round(capLeft * 0.25 * 1000)) : 1; T.term = null; redraw();
    }));
    right.querySelectorAll("[data-get]").forEach((b) => (b.onclick = () => { T.get = b.dataset.get; T.term = null; redraw(); }));
    right.querySelectorAll("[data-source]").forEach((b) => (b.onclick = () => { T.source = b.dataset.source; if (key === "price") T.term = null; redraw(); }));
    right.querySelectorAll("[data-line]").forEach((b) => (b.onclick = () => { T.line = b.dataset.line; redraw(); }));
    for (const k of ["size", "years", "fsize", "cshare", "power"]) {
      right.querySelectorAll(`[data-${k}]`).forEach((b) => (b.onclick = () => { T[k] = +b.dataset[k]; redraw(); }));
    }
    right.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => { T.term = Math.max(0, T.term + +b.dataset.step * tm.step); redraw(); }));
    $("#t-back", right).onclick = () => talk();
    const action = () => {
      if (dt === "factory_partnership") {
        return { type: "propose_deal", target: id, deal_type: dt, tech: T.line, amount: T.fsize / 1000, capital_share: T.cshare / 100,
          power: (T.power / 100) * (v.demand || 1), share: tm.fromUnit(T.term), duration: T.years * 4 };
      }
      const a = { type: "propose_deal", target: id, deal_type: dt, source: T.source, duration: T.years * 4, collateral: 0.2, exit_penalty: 0.3 };
      a.amount = T.give === "capital" ? T.size / 1000 : (T.size / 100) * (v.demand || 1);
      if (dt !== "equity_for_energy") a.currency = "hard";
      a[key] = tm.fromUnit(T.term);
      return a;
    };
    let last = null;
    const seq = (S.tradeSeq = (S.tradeSeq || 0) + 1);
    const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
    wait(150).then(() => (seq === S.tradeSeq ? api("/api/negotiate", { action: action() }) : null)).then((r) => {
      if (!r) return;
      if (seq !== S.tradeSeq) return;
      last = r;
      const ans = r.ok ? r.answer : "invalid";
      $("#tv", right).innerHTML = `<div class="dip-verdict ${ans}">${say(r.ok ? REPLY[ans] : `${REPLY.invalid} (${humane(r.reason)})`)}</div>`;
      $("#t-go", right).disabled = !r.ok || ans === "refuse";
      $("#t-take", right).disabled = !r.ok || ans === "accept" || !r.would_take;
      if (!r.ok) { $("#ts", right).innerHTML = ""; return; }
      const imp = r.impact || {}, mine = imp[sc.country] || 0, theirs = imp[id] || 0;
      const perQ = `${money(r.payment_per_year / 4)} a quarter for ${r.years} years (about ${money(r.payment_per_year * r.years)} in all)`;
      let rows;
      if (dt === "factory_partnership") {
        rows = [
          ["You pay when they sign", `${money(r.cost)} (your ${pct(T.cshare / 100)} of the factory)`],
          ["They pay when they sign", money(r.host_pays)],
          ...(r.power_cost_per_year > 0 ? [["Your clean power costs you", `${money(r.power_cost_per_year / 4)} a quarter`]] : []),
          ["They pay you, at today's sales", perQ],
          ["It opens", quarterOf(r.online_turn)],
          ["Your stake", pct(r.stake)],
          ["Chance the factory lasts the deal", `${pct(r.survival)} <span class="muted">(less the less you fund and the poorer the host: their income is ${pct(r.development)} of the average)</span>`],
        ];
      } else if (dt === "equipment_sale") {
        rows = [
          ["They pay you when they sign", money(r.price)],
          ["It costs you to build", money(r.cost)],
          ["Your profit", money(r.price - r.cost)],
          ["Clean power it adds", `${shareOf(r.capacity, v.demand || 1)} of their energy, from ${quarterOf(r.online_turn)}`],
        ];
      } else {
        rows = [
          ["You pay when they sign", money(r.cost)],
          [dt === "equity_for_energy" ? "They pay you, at today's prices" : "They pay you", perQ],
          ["Clean power it adds", `${shareOf(r.capacity, v.demand || 1)} of their energy, from ${quarterOf(r.online_turn)}`],
        ];
        if (r.survival != null) rows.push(["Chance the plant lasts the deal", pct(r.survival)]);
      }
      if (r.equipment_value > 0) {
        rows.push(["Panels and turbines", r.from_your_factories
          ? `made in your factories (${money(r.equipment_value)} of sales for you)`
          : `bought on the world market: your factories have room for only ${money(r.spare_output)} more this year`]);
      }
      $("#ts", right).innerHTML = `<table class="trade-table">${rows.map(([k, x]) => `<tr><td>${esc(k)}</td><td>${x}</td></tr>`).join("")}</table>
        <div class="trade-impact"><span>Projected Impact by 2049</span>
          <b class="${mine > 0 ? "good" : ""}">You ${mine >= 0 ? "+" : ""}${num(mine, 1)}</b>
          <b class="${theirs > 0 ? "good" : ""}">${esc(nationName(id))} ${theirs >= 0 ? "+" : ""}${num(theirs, 1)}</b></div>`;
    }).catch((e) => { $("#tv", right).innerHTML = say(e.message); });
    $("#t-take", right).onclick = () => {
      if (!last || !last.would_take) return;
      const w = last.would_take;
      T.term = Math.floor(tm.toUnit(w[key]));
      if (dt === "factory_partnership") T.fsize = Math.floor(w.amount * 1000);
      else if (T.give === "capital") T.size = Math.floor(w.amount * 1000);
      else T.size = Math.floor((w.amount / (v.demand || 1)) * 100 * 2) / 2;
      redraw();
    };
    $("#t-go", right).onclick = () => {
      addToPlan(action());
      talk("We will study it and answer next quarter.");
    };
  };

  // Their offer to you: the terms from your side, your answer, and a counter with a live verdict.
  const offer = (did) => {
    const d = sc.deals.inbox.find((x) => x.id === did);
    if (!d) return talk();
    const key = termKey(d.type), tm = TERM[key], t = d.terms;
    let counter = Math.floor(tm.toUnit(t[key]) * 0.8);
    const draw = (preview = null, verdict = null) => {
      const imp = (preview && preview.impact) || {};
      const size = d.type === "climate_loan" ? money(t.amount) : shareOf(t.amount, myDemand()) + " of your energy";
      right.innerHTML = `${say(`We offer you ${OFFER_LINE[d.type] || nice(d.type)}`)}
        <div class="trade-cols">
          <div class="trade-col"><h3>They give</h3><div class="offer-item">${SOURCE_ICON[t.source] || "◆"} ${esc(nice(t.source))} · ${size}</div></div>
          <div class="trade-col"><h3>You give</h3><div class="offer-item">${GETS[{ rate: "repay", share: "share", price: "price" }[key]].ico} ${THEIR_TERM[key]}: <b>${whole(tm.toUnit(t[key]))}</b> ${tm.unit} for ${whole(t.duration / 4)} years</div></div>
        </div>
        ${preview ? `<div class="trade-impact"><span>Projected Impact by 2049</span><b class="good">You +${num(imp[sc.country] || 0, 1)}</b><b>${esc(nationName(id))} +${num(imp[id] || 0, 1)}</b></div>
          <p class="muted" style="font-size:12.5px">You would pay ${money((preview.payment_per_year || 0) / 4).replace(/^\$/, "about $")} a quarter${key === "share" ? " at today's prices" : ""}.</p>` : ""}
        <div class="dip-opts">
          <button class="dip-opt" data-r="accept"><span class="n">1</span><span><b>We accept.</b><span class="s">The plant is built in your country</span></span></button>
          <button class="dip-opt" data-r="refuse"><span class="n">2</span><span><b>No, thank you.</b></span></button>
        </div>
        <div class="trade-label">Or counter: ${THEIR_TERM[key].toLowerCase()} (${tm.unit})</div>
        <div class="row" style="gap:10px"><div class="stepper"><button type="button" data-step="-1">−</button><b>${whole(counter)}</b><button type="button" data-step="1">+</button></div>
          ${verdict ? `<span class="dip-verdict ${verdict}">${verdict === "accept" ? "They would take it." : "They would refuse."}</span>` : ""}
          <button class="btn" id="o-counter">Send counter</button></div>
        <div style="margin-top:10px"><button class="btn" id="o-back">← Back</button></div>`;
      right.querySelectorAll("[data-r]").forEach((b) => (b.onclick = () => {
        addToPlan({ type: "respond_deal", deal_id: did, response: b.dataset.r });
        talk(b.dataset.r === "accept" ? "Excellent. We will begin at once." : "A pity. Perhaps another time.");
      }));
      right.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => { counter = Math.max(0, counter + +b.dataset.step * tm.step); ask(); }));
      $("#o-counter", right).onclick = () => {
        addToPlan({ type: "respond_deal", deal_id: did, response: "counter", [key]: tm.fromUnit(counter) });
        talk("We will consider your counter and reply next quarter.");
      };
      $("#o-back", right).onclick = () => talk();
    };
    const ask = () => api("/api/negotiate", { deal_id: did, counter: tm.fromUnit(counter) }).then((r) => draw(r, r.answer)).catch(() => draw());
    ask();
  };

  if (view === "offer" && opt.deal) offer(opt.deal);
  else if (view === "trade") trade();
  else talk();
}


// ---------- ledger ----------

function researchWindow() {
  S.menu = "research"; renderMenubar();
  const sc = S.data.screen, techs = S.meta.techs;
  const row = Object.fromEntries(sc.research.map((r) => [r.tech, r]));
  const depth = {};
  const d = (t) => (depth[t] ??= techs[t].requires.length ? 1 + Math.max(...techs[t].requires.map(d)) : 0);
  Object.keys(techs).forEach(d);
  const cols = [];
  const unlocks = (t) => Object.values(techs).some((x) => x.requires.includes(t));
  const byName = Object.keys(techs).sort((a, b) => techs[a].name.localeCompare(techs[b].name));
  for (const t of byName) (cols[depth[t]] ??= []).push(t);
  // In a two-column tier, put technologies that unlock others in the right-hand column, next to
  // the tier they lead to, so their arrows do not cross other cards.
  cols.forEach((c, i) => {
    if (c.length <= 5) return;
    const lead = c.filter(unlocks), rest = c.filter((t) => !unlocks(t)), out = [];
    while (lead.length || rest.length) { out.push(rest.shift() ?? lead.shift()); if (lead.length) out.push(lead.shift()); else if (rest.length) out.push(rest.shift()); }
    cols[i] = out.filter(Boolean);
  });
  const card = (t) => {
    const r = row[t], spec = techs[t];
    const state = r.have ? (r.licensed ? "licensed" : "researched") : r.blocked ? "locked" : r.progress > 0 ? "underway" : "open";
    const offer = r.offers[0];
    const label = { researched: "Researched", licensed: "Licensed", locked: "Locked", underway: `${pct(r.progress)} done`, open: "Not started" }[state];
    return `<div class="tech-card ${state}" data-tech="${t}">
      <div class="row between"><b>${esc(spec.name)}</b><span class="tech-state">${label}</span></div>
      <div class="meter" style="margin:5px 0"><i style="width:${(r.have ? 1 : r.progress) * 100}%"></i></div>
      <div class="tech-gives">${esc(r.gives.map((g) => g.replace(/_/g, " ")).join(" · "))}</div>
      <div class="muted" style="font-size:12px">${money(r.cost_now)} in all · at least ${spec.min_quarters} quarters${spec.earliest_year ? ` · not before ${spec.earliest_year}` : ""}${r.first ? ` · first: ${esc(nationName(r.first[0]))}` : ""}</div>
      ${state === "locked" ? `<div class="warn" style="font-size:12px">${esc(String(r.blocked).replace(/_/g, " "))}</div>` : ""}
      <div class="row" style="gap:6px;margin-top:6px">
        ${!r.have && !r.blocked ? `<button class="btn small" data-fund="${t}" ${tip(ttTable("Fund this quarter", [["Most that speeds it", money(r.useful_now)]], "Adds a 'max' order: it spends up to what speeds the research, if you can afford it."))}>Fund</button>` : ""}
        ${!r.have && offer ? `<button class="btn small" data-buy="${t}" data-seller="${offer[0]}">Licence from ${esc(offer[0])} · ${money(offer[1])}</button>` : ""}
        ${r.have && !r.licensed ? `<button class="btn small" data-sell="${t}">${r.my_price == null ? "Offer licences" : `Selling at ${money(r.my_price)}`}</button>` : ""}
      </div></div>`;
  };
  const win = openWindow({
    title: "The research tree", wide: "x", onClose: () => { S.menu = null; renderMenubar(); },
    body: `<p class="summary-text" style="margin-top:0">Research finishes no faster than its minimum time; more money brings you closer to it. Anything another nation has finished costs you 40% less, and patents expire ten years after the first completion. Arrows show what each technology needs first.</p>
      <div class="tech-tree" id="tree">${cols.map((c, i) => `<div class="tech-col ${c.length > 5 ? "two" : ""}"><div class="tech-col-head">${["Foundations: no prerequisites", "Second wave", "Third wave", "Frontier"][i] || `Tier ${i + 1}`}</div>${c.map(card).join("")}</div>`).join("")}<svg class="tech-links" id="tree-links"></svg></div>`,
  });
  requestAnimationFrame(() => {
    const tree = $("#tree", win), svg = $("#tree-links", win);
    const box = tree.getBoundingClientRect();
    svg.setAttribute("width", tree.scrollWidth);
    svg.setAttribute("height", tree.scrollHeight);
    let paths = "";
    for (const [t, spec] of Object.entries(techs)) {
      const to = tree.querySelector(`[data-tech="${t}"]`).getBoundingClientRect();
      for (const req of spec.requires) {
        const from = tree.querySelector(`[data-tech="${req}"]`).getBoundingClientRect();
        const x1 = from.right - box.left, y1 = from.top + from.height / 2 - box.top;
        const x2 = to.left - box.left, y2 = to.top + to.height / 2 - box.top;
        const mx = (x1 + x2) / 2;
        paths += `<path d="M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2 - 6} ${y2}" /><path d="M${x2 - 8} ${y2 - 4} L${x2} ${y2} L${x2 - 8} ${y2 + 4}" />`;
      }
    }
    svg.innerHTML = paths;
  });
  win.querySelectorAll("[data-fund]").forEach((b) => (b.onclick = () => addToPlan({ type: "fund_research", tech: b.dataset.fund, amount: "max" })));
  win.querySelectorAll("[data-buy]").forEach((b) => (b.onclick = () => addToPlan({ type: "buy_license", tech: b.dataset.buy, seller: b.dataset.seller })));
  win.querySelectorAll("[data-sell]").forEach((b) => (b.onclick = () => actionWindow("Sell licences", ["set_license_price"], "set_license_price", { tech: b.dataset.sell })));
}

function ledgerWindow(tab = "standings") {
  S.menu = "ledger"; renderMenubar();
  const sc = S.data.screen;
  const rows = sc.leaders.map((l, i) => `<tr><td>${i + 1}</td><td>${crestMini(l.nation)} ${esc(nationName(l.nation))}${l.nation === sc.country ? " <span class='good'>(you)</span>" : ""}</td><td style="text-align:right">${num(l.score, 0)}</td><td style="text-align:right">${num(l.impact, 0)}</td><td style="text-align:right">${num(l.prosperity, 0)}</td><td style="text-align:right">${spct(S.data.world.nations[l.nation].emissions_change, 0)}</td><td style="text-align:right">${pct(S.data.world.nations[l.nation].clean_share)}</td></tr>`).join("");
  const races = sc.races.map((r) => `<tr><td>${esc(nice(r.race))}</td><td>${r.leader ? esc(nationName(r.leader)) : "<span class='muted'>no one yet</span>"}</td><td class="muted">${esc(r.measure || "")}</td></tr>`).join("");
  const tabs = [["standings", "Standings"], ["chronicle", "Chronicle"]];
  const win = openWindow({
    title: "The ledger", wide: true, onClose: () => { S.menu = null; renderMenubar(); },
    body: `<div class="tabs" style="margin:-6px -6px 12px">${tabs.map(([k, l]) => `<button class="tab ${k === tab ? "active" : ""}" data-tab="${k}">${l}</button>`).join("")}</div><div id="ledger-body"></div>`,
  });
  const body = $("#ledger-body", win);
  if (tab === "chronicle") chronicle(body, S.data.world.history);
  else body.innerHTML = `<div style="display:grid;grid-template-columns:1.2fr 1fr;gap:18px">
      <div><h3>Standings</h3><table style="width:100%;border-collapse:collapse;font-size:14px"><tr class="muted"><td>#</td><td>Nation</td><td style="text-align:right">Score</td><td style="text-align:right">Impact</td><td style="text-align:right">Prosperity</td><td style="text-align:right">CO2 vs 2025</td><td style="text-align:right">Clean</td></tr>${rows}</table></div>
      <div><h3>How the game is won</h3><p class="summary-text">If warming, averaged over a year, reaches ${sc.world.collapse_at} °C, every nation loses. Stay below it to 2049 and the world wins; then the nation with the highest score is Champion.</p>
      <h3>How the score works</h3><p class="summary-text">Score = your country's difficulty × (${sc.score ? sc.score.weights[0] * 100 : 75}% impact + ${sc.score ? sc.score.weights[1] * 100 : 25}% prosperity). <b>Impact</b> is the CO2 you cut, or helped cut abroad, as a share of your own 2025 emissions, so a small nation can beat a large one. <b>Prosperity</b> is growth, secure energy, approval, prices and clean-tech industry against your own start.</p>
      <h3>Honours</h3><p class="muted" style="font-size:12.5px">Unscored firsts and bests.</p><table style="width:100%;font-size:13px">${races}</table></div></div>`;
  win.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => ledgerWindow(b.dataset.tab)));
}
const crestMini = (id) => `<i class="swatch" style="background:${colorOf(id)}"></i>`;

// ---------- side panel: nations, regions, your realm ----------

function closePanel() { $("#panel").classList.add("hidden"); S.panel = null; S.map.select(null); placeAlerts(); }

function panelShell(head, tabs, active, body) {
  if (S.drawer) closeDrawer();
  $("#panel").classList.remove("hidden");
  $("#panel").innerHTML = `<div class="panel-head">${head}<button class="icon-btn" id="p-x">✕</button></div>
    ${tabs.length ? `<div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${k === active ? "active" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>` : ""}
    <div class="panel-body">${body}</div>`;
  $("#p-x").onclick = closePanel;
  placeAlerts();
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
    const body = `<p class="summary-text">${esc(pers[1])}</p>
      <div class="stat-grid">
        <div class="stat"><span class="k">GDP a quarter</span><span>${money(v.gdp / 4)}</span></div>
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
      ${offers.length ? `<h3>Offers between you</h3>${offers.map((d) => `<div class="plan-item"><div class="what"><b>${d.id}</b> ${nice(d.type)}, ${esc(nice(d.terms.source || ""))}<div class="why muted">${d.can_answer ? "Open talks to answer" : "answer from next quarter"}</div></div></div>`).join("")}` : ""}
      ${active.length ? `<h3>Active deals</h3>${active.map((d) => `<div class="plan-item"><div class="what"><b>${d.id}</b> ${nice(d.type)} ${esc(nice(d.terms.source || ""))}</div></div>`).join("")}` : ""}
      <button class="btn primary big talks-btn" id="open-talks">🤝 Open talks</button>`;
    panelShell(head, [], null, body);
    $("#open-talks").onclick = () => talksWindow(id);
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
        <div class="stat"><span class="k">GDP a quarter</span><span>${money(v.gdp / 4)}</span></div>
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
    $("#panel").querySelectorAll("[data-research]").forEach((b) => (b.onclick = () => researchWindow()));
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
      <div class="stat"><span class="k">GDP a quarter</span><span>${money(ec.gdp / 4)}</span></div>
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
    ${s ? `<h3>Score ${num(s.score_if_ended_now, 0)} · rank ${s.rank} of 16</h3>
      <div class="vote-row"><span>Impact</span><div class="meter"><i style="width:${s.impact}%"></i></div><span style="text-align:right">${num(s.impact, 0)}</span></div>
      <p class="muted" style="font-size:12.5px">Your CO2 has averaged ${belowStart(s.yearly_cut)} so far, counting cuts you helped make abroad at a discount. 50 means no change.</p>
      <div class="vote-row"><span>Prosperity</span><div class="meter"><i style="width:${s.prosperity}%"></i></div><span style="text-align:right">${num(s.prosperity, 0)}</span></div>
      ${comp}<p class="muted" style="font-size:12.5px">Impact counts ${s.weights[0] * 100}%, prosperity ${s.weights[1] * 100}%. 0.5 means no change from your 2025 start.</p>` : ""}`;
}

boot().catch((e) => { console.error(e); toast(`Could not start: ${e.message}`, 8000); });
