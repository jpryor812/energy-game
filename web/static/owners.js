// Which modelled nation or rest-of-world region each map shape belongs to, and its colours.
// Shapes are matched by name in world-atlas (Natural Earth 1:50m). Region membership follows
// scripts/data_prep/build_regions.py; unlisted shapes (Antarctica, uninhabited territories) are
// drawn as neutral land.

const list = (s) => s.split("|");

const NATIONS = {
  USA: list("United States of America|Puerto Rico|Guam|U.S. Virgin Is.|American Samoa|N. Mariana Is."),
  GBR: list("United Kingdom|Isle of Man|Jersey|Guernsey"),
  JPN: list("Japan"),
  EUU: list(
    "Austria|Belgium|Bulgaria|Croatia|Cyprus|Czechia|Denmark|Estonia|Finland|France|Germany|" +
    "Greece|Hungary|Ireland|Italy|Latvia|Lithuania|Luxembourg|Malta|Netherlands|Poland|" +
    "Portugal|Romania|Slovakia|Slovenia|Spain|Sweden|Åland|N. Cyprus"),
  CHN: list("China"),
  BRA: list("Brazil"),
  AUS: list("Australia|Ashmore and Cartier Is.|Norfolk Island"),
  SAU: list("Saudi Arabia"),
  RUS: list("Russia"),
  IND: list("India|Siachen Glacier"),
  IDN: list("Indonesia"),
  VNM: list("Vietnam"),
  ZAF: list("South Africa"),
  NGA: list("Nigeria"),
  CAN: list("Canada"),
  MEX: list("Mexico"),
};

const REGIONS = {
  LAC: list(
    "Aruba|Anguilla|Argentina|Antigua and Barb.|Bahamas|Belize|Bolivia|Barbados|Bermuda|Chile|" +
    "Colombia|Costa Rica|Cuba|Curaçao|Dominica|Dominican Rep.|Ecuador|Grenada|Guatemala|Guyana|" +
    "Honduras|Haiti|Jamaica|St. Kitts and Nevis|Saint Lucia|Montserrat|Nicaragua|Panama|Peru|" +
    "Paraguay|El Salvador|Suriname|Sint Maarten|Turks and Caicos Is.|Trinidad and Tobago|" +
    "Uruguay|St. Vin. and Gren.|Venezuela|British Virgin Is.|Cayman Is.|Falkland Is.|" +
    "St-Martin|St-Barthélemy|S. Geo. and the Is."),
  MEA: list(
    "United Arab Emirates|Bahrain|Algeria|Egypt|Iran|Iraq|Israel|Jordan|Kuwait|Lebanon|Libya|" +
    "Morocco|Oman|Palestine|Qatar|Syria|Tunisia|Yemen|W. Sahara"),
  SSA: list(
    "Angola|Burundi|Benin|Burkina Faso|Botswana|Central African Rep.|Côte d'Ivoire|Cameroon|" +
    "Dem. Rep. Congo|Congo|Comoros|Cabo Verde|Djibouti|Eritrea|Ethiopia|Gabon|Ghana|Guinea|" +
    "Gambia|Guinea-Bissau|Eq. Guinea|Kenya|Liberia|Lesotho|Madagascar|Mali|Mozambique|" +
    "Mauritania|Mauritius|Malawi|Namibia|Niger|Rwanda|Sudan|Senegal|Saint Helena|Sierra Leone|" +
    "Somalia|Somaliland|S. Sudan|São Tomé and Principe|eSwatini|Seychelles|Chad|Togo|Tanzania|" +
    "Uganda|Zambia|Zimbabwe"),
  SEA: list(
    "Afghanistan|Bangladesh|Bhutan|Sri Lanka|Maldives|Nepal|Pakistan|Brunei|Cambodia|Laos|" +
    "Myanmar|Malaysia|Philippines|Singapore|Thailand|Timor-Leste|Br. Indian Ocean Ter."),
  EAP: list(
    "Hong Kong|South Korea|Macao|Mongolia|North Korea|Taiwan|Cook Is.|Fiji|Micronesia|Kiribati|" +
    "Marshall Is.|New Caledonia|Niue|Nauru|New Zealand|Palau|Papua New Guinea|Fr. Polynesia|" +
    "Solomon Is.|Tonga|Vanuatu|Wallis and Futuna Is.|Samoa|Pitcairn Is."),
  EUR: list(
    "Albania|Andorra|Bosnia and Herz.|Belarus|Switzerland|Faeroe Is.|Greenland|Iceland|" +
    "Liechtenstein|Monaco|Moldova|Macedonia|Montenegro|Norway|San Marino|" +
    "St. Pierre and Miquelon|Serbia|Turkey|Ukraine|Vatican|Kosovo"),
  CAS: list("Armenia|Azerbaijan|Georgia|Kazakhstan|Kyrgyzstan|Tajikistan|Turkmenistan|Uzbekistan"),
};

export const OWNER = {};
for (const [id, names] of Object.entries(NATIONS)) for (const n of names) OWNER[n] = { kind: "nation", id };
for (const [id, names] of Object.entries(REGIONS)) for (const n of names) OWNER[n] = { kind: "region", id };

// Playable nations: strong heraldic colours.
export const PLAYABLE_COLOR = {
  USA: "#2d5b9a",
  EUU: "#5a4a9e",
  CHN: "#b3342c",
  IND: "#d3842a",
  RUS: "#3c7a4c",
  VNM: "#23857f",
};

// Everything else is tinted by its part of the world: regions softly, the ten computer-run
// nations a little stronger in the same hue so they read as actors you can deal with.
export const REGION_TINT = {
  LAC: "#b9c39b",
  MEA: "#d9c497",
  SSA: "#cfac86",
  SEA: "#aac09a",
  EAP: "#a6bcbd",
  EUR: "#bcb0c4",
  CAS: "#cdaea3",
  NAM: "#b7bfcb",
};

// The tint family each computer-run nation sits in.
export const NATION_TINT_FAMILY = {
  GBR: "EUR", JPN: "EAP", BRA: "LAC", AUS: "EAP", SAU: "MEA", IDN: "SEA",
  ZAF: "SSA", NGA: "SSA", CAN: "NAM", MEX: "LAC",
};

export function nationTint(id) {
  const base = d3.hsl(REGION_TINT[NATION_TINT_FAMILY[id]]);
  base.s = Math.min(1, base.s + 0.18);
  base.l = Math.max(0, base.l - 0.12);
  return base.formatHex();
}

export const NEUTRAL_LAND = "#cfc6b2";

export const PERSONALITY = {
  green_leader: ["Green leader", "Pushes decarbonisation hard and funds others' transitions."],
  fossil_defender: ["Fossil defender", "Protects fuel exports and resists costly climate policy."],
  opportunist: ["Opportunist", "Follows the money: builds what pays and deals where it gains."],
  cautious_follower: ["Cautious follower", "Moves when its peers move, rarely first."],
};

export const SOURCE_COLOR = {
  coal: "#4a4038", oil: "#6e5233", gas: "#a8875a", nuclear: "#b88bc4", hydro: "#4f86b8",
  onshore_wind: "#7fb2a8", offshore_wind: "#5b9a9c", solar: "#e3bf45", bioenergy: "#7e9a4f",
  geothermal: "#c76b4c", smr: "#a07cc0", advanced_fission: "#8d6db0", fusion: "#e07fb0",
  enhanced_geothermal: "#b5583d",
};
