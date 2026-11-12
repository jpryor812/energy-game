// The world map: a painted political map with map modes, labels, selection and event markers.
import {
  OWNER, PLAYABLE_COLOR, REGION_TINT, NATION_TINT_FAMILY, nationTint, NEUTRAL_LAND,
} from "./owners.js";

const ATLAS = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json";

export const MODES = {
  political: { icon: "⚑", name: "Political", tip: "Nations and regions. Strong colours are the playable nations." },
  emissions: { icon: "☁", name: "Emissions", tip: "Change in CO2 since 2025: green cut, red grew." },
  clean: { icon: "☀", name: "Clean energy", tip: "Share of energy from clean sources." },
  trust: { icon: "✋", name: "Trust in you", tip: "How much each nation and region trusts you." },
  club: { icon: "⛓", name: "Carbon club", tip: "Members of the carbon club (gold) and the rest." },
  score: { icon: "♛", name: "Standing", tip: "Each nation's current score; the regions are not ranked." },
  events: { icon: "⚠", name: "Events", tip: "Regions with an open event fund." },
};

const emissionsScale = d3.scaleDiverging([-0.8, 0, 0.5], (t) => d3.interpolateRdYlGn(1 - t)).clamp(true);
const cleanScale = d3.scaleSequential([0, 0.9], d3.interpolate("#e9dfc3", "#2e7d4f")).clamp(true);
const trustScale = d3.scaleLinear([0, 0.5, 1], ["#9a3b2b", "#e7dcbc", "#2f6e55"]).clamp(true);
const scoreScale = d3.scaleSequential([40, 80], d3.interpolate("#e7dcbc", "#5a3f8f")).clamp(true);

export class WorldMap {
  constructor(el, handlers) {
    this.el = el;
    this.on = handlers;
    this.mode = "political";
    this.view = null;
    this.selected = null;
  }

  async load(meta) {
    this.meta = meta;
    const topo = await (await fetch(ATLAS)).json();
    this.topo = topo;
    const geoms = topo.objects.countries.geometries;
    for (const g of geoms) g.owner = OWNER[g.properties.name] || null;
    const keep = geoms.filter((g) => g.properties.name !== "Antarctica" &&
      !g.properties.name.startsWith("Fr. S. Antarctic") && !g.properties.name.startsWith("Heard I."));
    this.features = keep.map((g) => {
      const f = topojson.feature(topo, g);
      f.owner = g.owner;
      return f;
    });
    this.keepGeoms = keep;
    this.build();
    window.addEventListener("resize", () => this.build());
  }

  ownerKey(o) { return o ? `${o.kind}:${o.id}` : "none"; }

  build() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    this.el.innerHTML = "";
    const svg = d3.select(this.el).append("svg").attr("viewBox", `0 0 ${w} ${h}`);
    this.svg = svg;
    const defs = svg.append("defs");
    const oc = defs.append("radialGradient").attr("id", "ocean").attr("cx", "50%").attr("cy", "45%").attr("r", "75%");
    oc.append("stop").attr("offset", "0%").attr("stop-color", "#4fb6f0");
    oc.append("stop").attr("offset", "60%").attr("stop-color", "#2f95dc");
    oc.append("stop").attr("offset", "100%").attr("stop-color", "#1f74c0");
    const paper = defs.append("filter").attr("id", "paper").attr("x", 0).attr("y", 0).attr("width", "100%").attr("height", "100%");
    paper.append("feTurbulence").attr("type", "fractalNoise").attr("baseFrequency", 0.9).attr("numOctaves", 3).attr("seed", 7);
    paper.append("feColorMatrix").attr("values", "0 0 0 0 0.45  0 0 0 0 0.40  0 0 0 0 0.30  0 0 0 0.35 0");
    defs.append("filter").attr("id", "soften").append("feGaussianBlur").attr("stdDeviation", 2.2);
    const glow = defs.append("filter").attr("id", "glow").attr("x", "-20%").attr("y", "-20%").attr("width", "140%").attr("height", "140%");
    glow.append("feGaussianBlur").attr("stdDeviation", 2).attr("result", "b");
    const m = glow.append("feMerge");
    m.append("feMergeNode").attr("in", "b");
    m.append("feMergeNode").attr("in", "SourceGraphic");

    svg.append("rect").attr("width", w).attr("height", h).attr("fill", "url(#ocean)");
    const g = svg.append("g");
    this.g = g;

    const fc = { type: "FeatureCollection", features: this.features };
    const projection = d3.geoNaturalEarth1().fitExtent([[20, 70], [w - 20, h - 20]], fc);
    const path = d3.geoPath(projection);
    this.path = path;

    g.append("path").attr("class", "graticule").attr("d", path(d3.geoGraticule10()));
    const coast = topojson.mesh(this.topo, { type: "GeometryCollection", geometries: this.keepGeoms }, (a, b) => a === b);
    g.append("path").attr("class", "coast-glow").attr("d", path(coast));

    this.lands = g.append("g").selectAll("path").data(this.features).join("path")
      .attr("class", (d) => `land ${d.owner ? d.owner.kind : "neutral"}`)
      .attr("d", path)
      .on("mousemove", (ev, d) => this.on.hover(ev, d.owner))
      .on("mouseleave", () => this.on.hover(null, null))
      .on("click", (ev, d) => { if (d.owner) this.on.select(d.owner.kind, d.owner.id); });

    const geomColl = { type: "GeometryCollection", geometries: this.keepGeoms };
    const realm = topojson.mesh(this.topo, geomColl,
      (a, b) => a !== b && this.ownerKey(a.owner) !== this.ownerKey(b.owner));
    // A soft painted shade along realm borders, then the inked line itself.
    g.append("path").attr("class", "realm-shade").attr("d", path(realm));
    g.append("path").attr("class", "realm-border").attr("d", path(realm));

    this.playerBorder = g.append("path").attr("class", "player-border");
    this.selectBorder = g.append("path").attr("class", "selected-border");
    this.markers = g.append("g");
    this.labelsG = g.append("g");
    svg.append("rect").attr("width", w).attr("height", h).attr("filter", "url(#paper)")
      .attr("opacity", 0.22).style("mix-blend-mode", "multiply").style("pointer-events", "none");

    this.computeLabels();
    const zoom = d3.zoom().scaleExtent([1, 9]).translateExtent([[-w * 0.2, -h * 0.2], [w * 1.2, h * 1.2]])
      .on("zoom", (ev) => {
        g.attr("transform", ev.transform);
        this.k = ev.transform.k;
        this.drawLabels();
      });
    svg.call(zoom).on("dblclick.zoom", null);
    this.zoom = zoom;
    this.k = 1;
    if (this.view) this.update(this.view);
  }

  outline(kind, id) {
    const geoms = this.keepGeoms.filter((x) => x.owner && x.owner.kind === kind && x.owner.id === id);
    return geoms.length ? topojson.merge(this.topo, geoms) : null;
  }

  computeLabels() {
    const out = [];
    const ids = [
      ...Object.keys(this.meta.nations).map((id) => ["nation", id]),
      ...Object.keys(this.meta.regions).map((id) => ["region", id]),
    ];
    for (const [kind, id] of ids) {
      const merged = this.outline(kind, id);
      if (!merged) continue;
      const polys = merged.type === "MultiPolygon" ? merged.coordinates : [merged.coordinates];
      let best = null, bestA = 0;
      for (const p of polys) {
        const a = this.path.area({ type: "Polygon", coordinates: p });
        if (a > bestA) { bestA = a; best = p; }
      }
      const [x, y] = this.path.centroid({ type: "Polygon", coordinates: best });
      const raw = kind === "nation" ? this.meta.nations[id].name : this.meta.regions[id];
      const name = raw.replace(/\s*\(.*\)/, "");
      const size = Math.max(9, Math.min(30, Math.sqrt(bestA) / 6.5));
      out.push({ kind, id, x, y, name, size, area: bestA,
        playable: kind === "nation" && this.meta.nations[id].playable });
    }
    const nudge = { EUU: [-8, 6], USA: [6, 6], CAN: [0, 18], RUS: [20, 14], EUR: [0, -6],
      SEA: [-26, -12], EAP: [40, -6], LAC: [-6, 46], MEA: [10, 0], SSA: [0, 10], CAS: [0, -6],
      BRA: [8, -10] };
    for (const l of out) {
      const [dx, dy] = nudge[l.id] || [0, 0];
      l.x += dx; l.y += dy;
    }
    this.labels = out;
    this.drawLabels();
  }

  drawLabels() {
    if (!this.labels) return;
    const k = this.k || 1;
    const shown = this.labels.filter((l) => l.size * k >= 11 || l.playable);
    this.labelsG.selectAll("text").data(shown, (d) => d.kind + d.id).join("text")
      .attr("class", (d) => `label ${d.kind === "region" ? "region-label" : ""} ${d.playable ? "playable" : ""}`)
      .attr("x", (d) => d.x).attr("y", (d) => d.y)
      .attr("font-size", (d) => (d.kind === "region" ? d.size * 0.8 : d.size) / Math.sqrt(k))
      .attr("letter-spacing", (d) => `${(d.kind === "region" ? 0.05 : 0.18) * d.size / Math.sqrt(k)}px`)
      .text((d) => d.kind === "region" ? d.name : d.name.toUpperCase());
  }

  color(owner) {
    if (!owner) return NEUTRAL_LAND;
    const v = this.view;
    const rec = v && (owner.kind === "nation" ? v.nations[owner.id] : v.regions[owner.id]);
    const me = v && v.me;
    switch (this.mode) {
      case "emissions":
        return rec ? emissionsScale(rec.emissions_change) : NEUTRAL_LAND;
      case "clean":
        return rec ? cleanScale(rec.clean_share) : NEUTRAL_LAND;
      case "trust":
        if (owner.kind === "nation" && owner.id === me) return "#22c55e";
        return rec && rec.trust_in_you != null ? trustScale(rec.trust_in_you) : NEUTRAL_LAND;
      case "club":
        if (owner.kind === "region") return "#cfc6b2";
        return rec && rec.club ? "#22c55e" : "#b9b5ab";
      case "score":
        if (owner.kind === "region") return "#cfc6b2";
        return rec && rec.score != null ? scoreScale(rec.score) : NEUTRAL_LAND;
      case "events":
        if (owner.kind === "nation") return "#9c978b";
        return rec && rec.open_events.length ? "#e0a53f" : "#c9c1ad";
      default:
        if (owner.kind === "region") return REGION_TINT[owner.id];
        if (PLAYABLE_COLOR[owner.id]) return PLAYABLE_COLOR[owner.id];
        return NATION_TINT_FAMILY[owner.id] ? nationTint(owner.id) : NEUTRAL_LAND;
    }
  }

  legend() {
    const ramp = (scale, lo, hi, a, b) => {
      const stops = d3.range(0, 1.01, 0.1).map((t) => scale(lo + (hi - lo) * t)).join(",");
      return `<div class="ramp" style="background:linear-gradient(90deg,${stops})"></div>
        <div class="row between muted"><span>${a}</span><span>${b}</span></div>`;
    };
    const head = `<div class="disp" style="color:var(--brass-hi);font-size:11px">${MODES[this.mode].name}</div>`;
    switch (this.mode) {
      case "emissions": return head + ramp(emissionsScale, -0.8, 0.5, "−80% since 2025", "+50%");
      case "clean": return head + ramp(cleanScale, 0, 0.9, "0% clean", "90%");
      case "trust": return head + ramp(trustScale, 0, 1, "distrust", "trust");
      case "score": return head + ramp(scoreScale, 40, 80, "40", "80");
      case "club": return head + `<div class="legend-list"><span><i class="swatch" style="background:#22c55e"></i>member</span><span><i class="swatch" style="background:#b9b5ab"></i>outside</span></div>`;
      case "events": return head + `<div class="legend-list"><span><i class="swatch" style="background:#e0a53f"></i>open fund</span></div>`;
      default: return head + `<div class="legend-list">${Object.entries(PLAYABLE_COLOR).map(([k, c]) =>
        `<span><i class="swatch" style="background:${c}"></i>${k}</span>`).join("")}</div>
        <div class="muted" style="margin-top:4px">Muted tints: computer-run nations and the regions</div>`;
    }
  }

  update(view) {
    this.view = view;
    if (!this.lands) return;
    this.lands.attr("fill", (d) => this.color(d.owner));
    const mine = this.outline("nation", view.me);
    this.playerBorder.attr("d", mine ? this.path(mine) : null);
    this.drawSelection();
    const markers = Object.entries(view.regions).filter(([, r]) => r.open_events.length)
      .map(([id]) => this.labels.find((l) => l.kind === "region" && l.id === id)).filter(Boolean);
    const mk = this.markers.selectAll("g.event-marker").data(markers, (d) => d.id).join((enter) => {
      const gg = enter.append("g").attr("class", "event-marker");
      gg.append("circle").attr("class", "ring").attr("r", 6);
      gg.append("circle").attr("r", 7).attr("fill", "#e0a53f").attr("stroke", "#3a2610").attr("stroke-width", 1.2);
      gg.append("text").attr("text-anchor", "middle").attr("dy", "0.35em").attr("font-size", 10)
        .attr("font-weight", 700).attr("fill", "#2b1c0b").text("!");
      return gg;
    });
    mk.attr("transform", (d) => `translate(${d.x},${d.y + d.size * 0.9 + 8})`)
      .on("click", (ev, d) => { ev.stopPropagation(); this.on.event(d.id); });
  }

  setMode(mode) {
    this.mode = mode;
    if (this.view) this.update(this.view);
  }

  select(kind, id) {
    this.selected = kind ? { kind, id } : null;
    this.drawSelection();
  }

  drawSelection() {
    const s = this.selected;
    const o = s ? this.outline(s.kind, s.id) : null;
    this.selectBorder.attr("d", o ? this.path(o) : null);
  }
}
