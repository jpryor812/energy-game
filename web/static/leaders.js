// Leader portraits: simple flat illustrations of an abstract head of government for each
// playable nation, standing in front of a scene of that nation's energy system. No real people.
// The same portraits are meant for the diplomacy screen later.

import { PLAYABLE_COLOR } from "./owners.js";

// Look of each abstract leader and the scene behind them (the scene follows the nation's 2025
// energy position: what it makes, burns or sells).
export const LEADERS = {
  USA: { title: "President", skin: "#e9bc98", hair: "#a7a39b", style: "sidepart", suit: "#1f2a3d", neck: "tie", scene: "oilcity" },
  EUU: { title: "Commission President", skin: "#f2cba9", hair: "#7a5233", style: "bob", suit: "#33304a", neck: "scarf", glasses: true, scene: "wind" },
  CHN: { title: "Premier", skin: "#e8bb90", hair: "#1e1e1e", style: "short", suit: "#252a31", neck: "tie", glasses: true, scene: "factory" },
  IND: { title: "Prime Minister", skin: "#a8724c", hair: "#1c1a19", style: "bun", suit: "#3b3a46", neck: "collar", scene: "solar" },
  RUS: { title: "President", skin: "#edc6a6", hair: "#c9c1b3", style: "receding", suit: "#2a2e2b", neck: "tie", scene: "pipeline" },
  VNM: { title: "Prime Minister", skin: "#d8a67c", hair: "#232120", style: "short", suit: "#26363a", neck: "open", glasses: false, scene: "port" },
};

const shade = (c, k) => d3.color(c).darker(k).formatHex();
const tint = (c, k) => d3.interpolateRgb(c, "#ffffff")(k);

let uid = 0;

// The sky colour at the top of a portrait, to fill any space above it.
export const skyColor = (id) => tint(PLAYABLE_COLOR[id] || "#16a34a", 0.5);

export function leaderPortrait(id, { label = "" } = {}) {
  const L = LEADERS[id];
  const col = PLAYABLE_COLOR[id] || "#16a34a";
  if (!L) return "";
  const k = `lp${++uid}`;
  return `<svg class="leader" viewBox="0 -110 240 410" role="img" aria-label="${label || `Leader of ${id}`}" preserveAspectRatio="xMidYMax slice">
    <defs>
      <linearGradient id="${k}-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${skyColor(id)}"/><stop offset="0.8" stop-color="${tint(col, 0.88)}"/>
      </linearGradient>
      <linearGradient id="${k}-suit" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${L.suit}"/><stop offset="1" stop-color="${shade(L.suit, 0.6)}"/>
      </linearGradient>
    </defs>
    <rect y="-110" width="240" height="410" fill="url(#${k}-sky)"/>
    <circle cx="186" cy="20" r="24" fill="#fff6c9" opacity="0.9"/>
    ${scene(L.scene, col)}
    ${backHair(L)}
    ${bust(L, col, k)}
    ${head(L)}
  </svg>`;
}

// ---------- scenes ----------
// Drawn on both sides of the leader, from the horizon (y 206) up into the sky.

function scene(kind, col) {
  const far = tint(shade(col, 0.4), 0.5), near = tint(shade(col, 0.9), 0.3);
  const ground = `<path d="M0 214 C60 200 120 206 240 196 L240 300 L0 300 Z" fill="${tint(col, 0.35)}"/>`;
  const s = {
    wind: [turbine(64, 206, 96, far), turbine(176, 204, 110, far), turbine(22, 210, 160, near), turbine(222, 206, 176, near)].join(""),
    solar: `${pylon(206, 206, 150, far)}${pylon(34, 206, 110, far)}<g fill="${near}">${solarRows(-6, 186)}${solarRows(160, 184)}</g>`,
    factory: `<g fill="${far}"><path d="M-4 206 L-4 140 L18 154 L18 140 L40 154 L40 140 L62 154 L62 206 Z"/><rect x="8" y="70" width="10" height="72"/><rect x="30" y="96" width="8" height="46"/></g>
      <g fill="#ffffff" opacity="0.75"><circle cx="13" cy="60" r="7"/><circle cx="22" cy="48" r="9"/><circle cx="34" cy="86" r="5"/><circle cx="40" cy="76" r="6"/></g>
      ${pylon(212, 206, 140, far)}<g fill="${near}">${solarRows(158, 184)}</g>`,
    oilcity: `<g fill="${far}">${[[160, 104, 16], [178, 70, 18], [198, 120, 14], [214, 40, 18], [232, 96, 16]].map(([x, y, w]) => `<rect x="${x}" y="${y}" width="${w}" height="${206 - y}"/>`).join("")}</g>
      <g fill="#ffffff" opacity="0.35">${[0, 1, 2, 3, 4, 5, 6, 7].map((i) => `<rect x="218" y="${52 + i * 18}" width="10" height="5"/>`).join("")}</g>
      ${pumpjack(36, 206, near)}`,
    pipeline: `<g fill="${far}">${[[14, 206, 64], [46, 200, 92], [196, 202, 84], [228, 206, 110]].map(([x, y, h]) => pine(x, y, h)).join("")}</g>
      <g fill="${near}"><path d="M150 206 L150 176 A26 10 0 0 1 202 176 L202 206 Z"/><rect x="-10" y="196" width="260" height="8" rx="4"/>${[10, 60, 180, 230].map((x) => `<rect x="${x}" y="203" width="4" height="10"/>`).join("")}</g>
      <path d="M78 206 L78 120" stroke="${far}" stroke-width="4"/><path d="M78 120 C70 108 82 100 78 88 C90 98 88 110 78 120 Z" fill="#f2a33a" opacity="0.85"/>`,
    port: `${crane(30, 206, 150, far, 1)}${crane(208, 206, 170, far, -1)}
      <g>${[[-4, 192, "#c2523c"], [18, 192, near], [40, 192, "#2f7fb0"], [8, 180, "#d7a33a"], [30, 180, "#c2523c"], [160, 192, near], [182, 192, "#c2523c"], [204, 192, "#2f7fb0"], [226, 192, "#d7a33a"], [192, 180, "#2f7fb0"], [214, 180, near]].map(([x, y, c]) => `<rect x="${x}" y="${y}" width="21" height="12" fill="${c}" opacity="0.85" stroke="#ffffff" stroke-width="0.8"/>`).join("")}</g>`,
  }[kind] || "";
  return `<g>${s}</g>${ground}`;
}

function turbine(x, y, h, c) {
  const hy = y - h, r = h * 0.4, w = Math.max(2, h / 40);
  const blades = [15, 135, 255].map((a) => {
    const t = (a * Math.PI) / 180;
    return `<line x1="${x}" y1="${hy}" x2="${x + r * Math.cos(t)}" y2="${hy + r * Math.sin(t)}"/>`;
  }).join("");
  return `<g stroke="${c}" stroke-linecap="round"><line x1="${x}" y1="${y}" x2="${x}" y2="${hy}" stroke-width="${w * 1.4}"/><g stroke-width="${w}">${blades}</g></g><circle cx="${x}" cy="${hy}" r="${w * 1.3}" fill="${c}"/>`;
}

function solarRows(x0, y0) {
  return [0, 1, 2].map((r) => [0, 1, 2].map((i) => {
    const x = x0 + i * 30 - r * 4, y = y0 + r * 9;
    return `<path d="M${x} ${y} l24 0 l4 7 l-24 0 Z"/>`;
  }).join("")).join("");
}

function pylon(x, y, h, c) {
  const t = y - h, w = h * 0.16;
  return `<g stroke="${c}" stroke-width="2" fill="none" stroke-linejoin="round">
    <path d="M${x - w} ${y} L${x} ${t} L${x + w} ${y}"/><path d="M${x - w * 1.6} ${t + h * 0.18} L${x + w * 1.6} ${t + h * 0.18}"/>
    <path d="M${x - w * 1.2} ${t + h * 0.36} L${x + w * 1.2} ${t + h * 0.36}"/><path d="M${x - w * 0.6} ${y - h * 0.3} L${x + w * 0.6} ${y - h * 0.55} M${x + w * 0.6} ${y - h * 0.3} L${x - w * 0.6} ${y - h * 0.55}"/></g>`;
}

function pumpjack(x, y, c) {
  return `<g stroke="${c}" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M${x - 16} ${y} L${x} ${y - 62} L${x + 16} ${y}"/><path d="M${x - 40} ${y - 70} L${x + 44} ${y - 54}"/>
    <path d="M${x + 30} ${y - 57} L${x + 30} ${y}"/></g>
    <path d="M${x - 50} ${y - 84} C${x - 34} ${y - 84} ${x - 30} ${y - 64} ${x - 36} ${y - 56} L${x - 46} ${y - 60} Z" fill="${c}"/>
    <circle cx="${x}" cy="${y - 62}" r="5" fill="${c}"/>`;
}

function pine(x, y, h) {
  const w = h * 0.3;
  return `<path d="M${x} ${y - h} L${x + w} ${y - h * 0.45} L${x + w * 0.5} ${y - h * 0.45} L${x + w * 1.2} ${y - 6} L${x - w * 1.2} ${y - 6} L${x - w * 0.5} ${y - h * 0.45} L${x - w} ${y - h * 0.45} Z"/><rect x="${x - 2}" y="${y - 8}" width="4" height="8"/>`;
}

function crane(x, y, h, c, dir) {
  const t = y - h, arm = 70 * dir, back = -26 * dir;
  return `<g stroke="${c}" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M${x - 8} ${y} L${x - 8} ${t + 20} M${x + 8} ${y} L${x + 8} ${t + 20}"/><path d="M${x - 8} ${y - h * 0.4} L${x + 8} ${y - h * 0.6}"/>
    <path d="M${x + back} ${t + 20} L${x + arm} ${t + 20}"/><path d="M${x} ${t} L${x + arm * 0.8} ${t + 20} M${x} ${t} L${x + back} ${t + 20}"/>
    <path d="M${x + arm * 0.7} ${t + 20} L${x + arm * 0.7} ${t + 70}" stroke-width="1.5"/></g>`;
}

// ---------- the leader ----------

function backHair(L) {
  if (L.style === "bob") {
    return `<path d="M74 196 C64 150 70 98 120 96 C170 98 176 150 166 196 Z" fill="${L.hair}"/>`;
  }
  return "";
}

function bust(L, col, k) {
  const neckwear = {
    tie: `<path d="M110 226 L120 238 L130 226 Z" fill="#ffffff"/><path d="M116 236 L124 236 L128 286 L120 296 L112 286 Z" fill="${col}"/><path d="M116 236 L124 236 L122 244 L118 244 Z" fill="${shade(col, 0.5)}"/>`,
    scarf: `<path d="M102 222 C112 236 128 236 138 222 L142 232 C130 246 110 246 98 232 Z" fill="${col}"/><path d="M124 240 L136 290 L124 292 L118 244 Z" fill="${shade(col, 0.3)}"/>`,
    collar: `<path d="M104 222 L120 250 L136 222 L132 220 L120 238 L108 220 Z" fill="#ffffff"/><circle cx="120" cy="256" r="3.5" fill="${col}"/>`,
    open: `<path d="M106 222 L120 246 L134 222 L130 220 L120 234 L110 220 Z" fill="#ffffff"/>`,
  }[L.neck];
  const pin = L.neck === "collar" ? "" : `<circle cx="158" cy="258" r="4" fill="${col}" stroke="#ffffff" stroke-width="1.2"/>`;
  return `
    <rect x="106" y="186" width="28" height="44" rx="8" fill="${shade(L.skin, 0.35)}"/>
    <path d="M26 300 C28 248 62 226 106 220 L120 250 L134 220 C178 226 212 248 214 300 Z" fill="url(#${k}-suit)"/>
    <path d="M106 220 L120 250 L104 268 L92 230 Z M134 220 L120 250 L136 268 L148 230 Z" fill="${shade(L.suit, 0.4)}" opacity="0.6"/>
    ${neckwear}${pin}`;
}

function head(L) {
  const skin = L.skin, hair = L.hair, line = shade(skin, 1.6);
  const hairTop = {
    short: `<path d="M80 150 C74 112 92 98 120 97 C148 98 166 112 160 150 C158 140 154 132 148 128 C136 124 112 122 96 128 C88 132 83 140 80 150 Z" fill="${hair}"/>`,
    sidepart: `<path d="M80 150 C74 110 92 97 122 97 C150 98 166 112 160 150 C158 138 154 130 146 126 C128 120 108 130 94 128 C86 134 82 142 80 150 Z" fill="${hair}"/><path d="M106 104 C112 112 124 118 140 120" stroke="${shade(hair, 0.6)}" stroke-width="1.5" fill="none"/>`,
    bob: `<path d="M82 142 C82 112 102 104 120 104 C146 104 158 118 158 140 C146 128 120 120 100 132 C92 136 86 140 82 142 Z" fill="${hair}"/>`,
    bun: `<circle cx="120" cy="100" r="15" fill="${hair}"/><path d="M82 146 C80 106 160 102 158 146 C150 124 136 116 120 116 C104 116 90 124 82 146 Z" fill="${hair}"/>`,
    receding: `<path d="M82 150 C80 128 86 118 94 114 C92 126 88 136 86 152 Z M158 150 C160 128 154 118 146 114 C148 126 152 136 154 152 Z" fill="${hair}"/>`,
  }[L.style];
  const glasses = L.glasses
    ? `<g fill="none" stroke="${shade(hair === "#1e1e1e" ? "#444444" : hair, 0.8)}" stroke-width="2"><rect x="95" y="141" width="21" height="16" rx="6"/><rect x="124" y="141" width="21" height="16" rx="6"/><path d="M116 148 L124 148"/></g>`
    : "";
  return `
    <ellipse cx="82" cy="154" rx="6" ry="10" fill="${shade(skin, 0.15)}"/>
    <ellipse cx="158" cy="154" rx="6" ry="10" fill="${shade(skin, 0.15)}"/>
    <ellipse cx="120" cy="150" rx="38" ry="46" fill="${skin}"/>
    ${hairTop}
    <g stroke="${shade(hair, 0.2)}" stroke-width="3" stroke-linecap="round"><path d="M98 138 L114 136"/><path d="M126 136 L142 138"/></g>
    <circle cx="106" cy="149" r="3.4" fill="#2b2420"/><circle cx="134" cy="149" r="3.4" fill="#2b2420"/>
    <path d="M120 152 L116 168 L122 168" fill="none" stroke="${line}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
    <path d="M108 177 Q120 185 132 177" fill="none" stroke="${line}" stroke-width="2.4" stroke-linecap="round"/>
    <g fill="#e06c5a" opacity="0.14"><circle cx="98" cy="166" r="7"/><circle cx="142" cy="166" r="7"/></g>
    ${glasses}`;
}
