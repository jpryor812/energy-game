// Engraved-style line vignettes for event windows (inline SVG, drawn in the parchment ink).
const INK = "#0f6b33";
const frame = (inner) => `<svg viewBox="0 0 600 120" width="100%" height="120" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
  <defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
    <line x1="0" y1="0" x2="0" y2="6" stroke="${INK}" stroke-opacity="0.12" stroke-width="1.2"/></pattern></defs>
  <rect x="1" y="1" width="598" height="118" fill="url(#hatch)" stroke="${INK}" stroke-opacity="0.35"/>
  <line x1="20" y1="100" x2="580" y2="100" stroke="${INK}" stroke-opacity="0.5"/>
  <g fill="none" stroke="${INK}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${inner}</g></svg>`;

const derrick = (x, s = 1) => `<g transform="translate(${x},100) scale(${s})">
  <path d="M-18 0 L0 -78 L18 0 M-13 -20 L13 -20 M-9 -40 L9 -40 M-5 -58 L5 -58 M-13 -20 L9 -40 M13 -20 L-9 -40 M-9 -40 L5 -58 M9 -40 L-5 -58"/>
  <path d="M-4 -78 L4 -78 L0 -86 Z"/></g>`;
const tree = (x, s = 1) => `<g transform="translate(${x},100) scale(${s})">
  <path d="M0 0 L0 -26"/><path d="M-22 -26 C-30 -40 -18 -56 -6 -52 C-4 -66 14 -66 16 -52 C30 -54 32 -34 20 -28 C14 -22 -14 -20 -22 -26 Z"/></g>`;
const stack = (x, s = 1) => `<g transform="translate(${x},100) scale(${s})">
  <path d="M-30 0 L-30 -30 L-10 -30 L-10 -70 L4 -70 L4 -30 L30 -30 L30 0"/>
  <path d="M-3 -78 C-14 -86 -6 -96 6 -94 C14 -104 30 -98 26 -88 C38 -86 34 -74 22 -76" stroke-opacity="0.7"/></g>`;
const waves = (x) => `<g transform="translate(${x},100)">
  ${[0, 1, 2].map((i) => `<path d="M-120 ${-8 - i * 12} C-100 ${-18 - i * 12} -80 ${2 - i * 12} -60 ${-8 - i * 12} S-20 ${2 - i * 12} 0 ${-8 - i * 12} S40 ${2 - i * 12} 60 ${-8 - i * 12} S100 ${2 - i * 12} 120 ${-8 - i * 12}"/>`).join("")}
  <path d="M-40 -50 L-40 -80 L-10 -95 L20 -80 L20 -50"/><path d="M-30 -62 L-30 -72 L-20 -72 L-20 -62 Z"/></g>`;
const sun = (x) => `<g transform="translate(${x},40)"><circle r="10"/>${[0, 45, 90, 135, 180, 225, 270, 315].map((a) =>
  `<line x1="${Math.cos(a * Math.PI / 180) * 15}" y1="${Math.sin(a * Math.PI / 180) * 15}" x2="${Math.cos(a * Math.PI / 180) * 22}" y2="${Math.sin(a * Math.PI / 180) * 22}"/>`).join("")}</g>`;

export const VIGNETTE = {
  oil_discovery: frame(derrick(240) + derrick(320, 0.8) + derrick(380, 0.6) + `<path d="M120 100 C200 92 420 92 500 100" stroke-opacity="0.5"/>`),
  rainforest: frame([140, 190, 240, 300, 360, 410, 460].map((x, i) => tree(x, 0.8 + (i % 3) * 0.15)).join("")),
  coal_pipeline: frame(stack(250) + stack(330, 0.85) + sun(470)),
  adaptation_appeal: frame(waves(300)),
};
