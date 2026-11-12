// The Chronicle: small multiples of the game so far, one measure per chart (one y-axis each),
// a shared quarter axis and a crosshair synced across all of them, plus a table view.

const LINE = "#c6a76a";
const REF = "#8d8576";
const GRID = "rgba(236, 227, 207, 0.08)";
const TEXT = "#a49b88";

export const SERIES = [
  { key: "warming", title: "World warming", unit: "°C", fmt: (v) => v.toFixed(2),
    refs: [[1.5, "1.5 °C: full world multiplier"], [1.6, "1.6 °C: Champion line"]] },
  { key: "global_emissions", title: "World CO2", unit: "Gt/yr", fmt: (v) => (v / 1000).toFixed(1), scale: 1 / 1000,
    note: "quarterly rate; heating and cooling seasons make it swing" },
  { key: "emissions", title: "Your CO2", unit: "Mt/yr", fmt: (v) => Math.round(v).toLocaleString(),
    note: "quarterly rate; heating and cooling seasons make it swing" },
  { key: "gdp", title: "Your GDP", unit: "$ tn", fmt: (v) => v.toFixed(2) },
  { key: "approval", title: "Approval", unit: "%", fmt: (v) => (v * 100).toFixed(0), scale: 100 },
  { key: "capital", title: "Capital in hand", unit: "$ bn", fmt: (v) => (v * 1000).toFixed(0), scale: 1000 },
];

export function chronicle(el, history) {
  if (!history.length) {
    el.innerHTML = `<p class="muted">The chronicle starts after your first quarter.</p>`;
    return;
  }
  el.innerHTML = `<div class="row between" style="margin-bottom:8px"><span class="muted">${history[0].label} to ${history[history.length - 1].label} · hover any chart to read every chart at that quarter</span>
    <button class="btn small" id="ch-toggle">Show as table</button></div>
    <div id="ch-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px"></div>
    <div id="ch-table" class="hidden" style="max-height:420px;overflow:auto"></div>`;
  const grid = el.querySelector("#ch-grid");
  const charts = SERIES.map((s) => {
    const box = document.createElement("div");
    grid.appendChild(box);
    return small(box, history, s);
  });
  const sync = (i) => charts.forEach((c) => c.show(i));
  charts.forEach((c) => (c.onhover = sync));
  sync(history.length - 1);

  const table = el.querySelector("#ch-table");
  table.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr class="muted"><td>Quarter</td>${SERIES.map((s) => `<td style="text-align:right">${s.title} (${s.unit})</td>`).join("")}</tr>
    ${history.slice().reverse().map((h) => `<tr><td>${h.label}</td>${SERIES.map((s) => `<td style="text-align:right">${s.fmt(h[s.key])}</td>`).join("")}</tr>`).join("")}</table>`;
  el.querySelector("#ch-toggle").onclick = (ev) => {
    const showTable = table.classList.toggle("hidden") === false;
    grid.classList.toggle("hidden", showTable);
    ev.target.textContent = showTable ? "Show as charts" : "Show as table";
  };
}

function small(box, history, s) {
  const W = 290, H = 150, m = { t: 8, r: 10, b: 20, l: 40 };
  const scale = s.scale || 1;
  const vals = history.map((h) => h[s.key] * scale);
  const refVals = (s.refs || []).map(([v]) => v * scale);
  let lo = d3.min([...vals, ...refVals]), hi = d3.max([...vals, ...refVals]);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08;
  const floor = lo >= 0 ? Math.max(0, lo - pad) : lo - pad;
  const x = d3.scaleLinear([0, Math.max(1, history.length - 1)], [m.l, W - m.r]);
  const y = d3.scaleLinear([floor, hi + pad], [H - m.b, m.t]).nice(4);

  box.innerHTML = `<div class="row between"><span style="font-family:var(--display);font-weight:700;color:var(--brass)">${s.title}</span>
    <span class="num" data-read style="font-size:13px"></span></div>${s.note ? `<div class="muted" style="font-size:11px;margin-top:-2px">${s.note}</div>` : ""}`;
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%")
    .attr("role", "img").attr("aria-label", `${s.title}, ${s.unit}`);
  const yt = y.ticks(4);
  svg.append("g").selectAll("line").data(yt).join("line").attr("x1", m.l).attr("x2", W - m.r)
    .attr("y1", y).attr("y2", y).attr("stroke", GRID);
  svg.append("g").selectAll("text").data(yt).join("text").attr("x", m.l - 6).attr("y", y).attr("dy", "0.32em")
    .attr("text-anchor", "end").attr("fill", TEXT).attr("font-size", 10).text((v) => d3.format("~s")(v));
  const years = history.map((h, i) => [h.label, i]).filter(([l]) => l.endsWith("Q1") && +l.slice(0, 4) % 5 === 0);
  svg.append("g").selectAll("text").data(years).join("text").attr("x", ([, i]) => x(i)).attr("y", H - 5)
    .attr("text-anchor", "middle").attr("fill", TEXT).attr("font-size", 10).text(([l]) => l.slice(0, 4));
  for (const [v, label] of s.refs || []) {
    const yy = y(v * scale);
    svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", yy).attr("y2", yy)
      .attr("stroke", REF).attr("stroke-dasharray", "4 3").attr("stroke-width", 1);
    svg.append("text").attr("x", W - m.r).attr("y", yy - 3).attr("text-anchor", "end").attr("fill", TEXT)
      .attr("font-size", 9).text(label);
  }
  const line = d3.line().x((d, i) => x(i)).y((d) => y(d)).curve(d3.curveMonotoneX);
  svg.append("path").attr("d", line(vals)).attr("fill", "none").attr("stroke", LINE).attr("stroke-width", 2)
    .attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
  const cross = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).attr("stroke", "rgba(236,227,207,0.35)");
  const dot = svg.append("circle").attr("r", 4).attr("fill", LINE).attr("stroke", "#161d27").attr("stroke-width", 2);
  const read = box.querySelector("[data-read]");
  const chart = {
    onhover: null,
    show(i) {
      const v = vals[i];
      cross.attr("x1", x(i)).attr("x2", x(i));
      dot.attr("cx", x(i)).attr("cy", y(v));
      read.innerHTML = `<b>${s.fmt(history[i][s.key])}</b> <span class="muted">${s.unit} · ${history[i].label}</span>`;
    },
  };
  svg.append("rect").attr("x", m.l).attr("y", 0).attr("width", W - m.l - m.r).attr("height", H)
    .attr("fill", "transparent")
    .on("mousemove", (ev) => {
      const [px] = d3.pointer(ev);
      const i = Math.max(0, Math.min(history.length - 1, Math.round(x.invert(px))));
      if (chart.onhover) chart.onhover(i);
    })
    .on("mouseleave", () => chart.onhover && chart.onhover(history.length - 1));
  return chart;
}
