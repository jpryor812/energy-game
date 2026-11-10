"""Build data/countries.yaml (and print derived global values) from downloaded source files.

This is a one-off data-preparation tool, not part of the simulation. It reads local copies of
the source files; it does no network access. Download them first (URLs in data/SOURCES.md) into
one directory laid out as:

    RAW/owid_energy/owid-energy-data.csv
    RAW/owid_co2/owid-co2-data.csv
    RAW/imf/{NGDPD,NGDP_RPCH,LP,GGXWDG_NGDP}.json
    RAW/wb/{FI.RES.TOTL.CD,DT.DOD.DPPG.CD,NE.EXP.GNFS.ZS}.json
    RAW/un/population-with-un-projections.csv

Usage:
    python scripts/data_prep/build_countries.py RAW > /tmp/derived.json

Structural fields (name, playable, archetype, ...) and hand-entered values (carbon price,
vulnerability, Nigeria's fallback build mix) come from the HAND table below; everything else is
computed from the files and tagged with its source key.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_splits import NOTE, share, split  # noqa: E402  (M11)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "countries.yaml"

TWH_TO_EJ = 0.0036
FUELS = ("coal", "oil", "gas")
SOURCES = ("coal", "oil", "gas", "nuclear", "hydro", "wind", "solar")
LIFESPAN = {"coal": 40, "oil": 30, "gas": 30, "nuclear": 50}  # mirrors data/techs.yaml
DATA_YEAR = "2024"
MIX_FROM, MIX_TO = "2019", "2024"
INTENSITY_FROM = 2014
LONG_RUN_GROWTH = 0.015

OWID_NAME = {
    "USA": "United States", "GBR": "United Kingdom", "JPN": "Japan",
    "EUU": "European Union (27)", "CHN": "China", "BRA": "Brazil", "AUS": "Australia",
    "SAU": "Saudi Arabia", "RUS": "Russia", "IND": "India", "IDN": "Indonesia",
    "VNM": "Vietnam", "ZAF": "South Africa", "NGA": "Nigeria", "CAN": "Canada", "MEX": "Mexico",
}  # fmt: skip
IMF_CODE = {k: ("EU" if k == "EUU" else k) for k in OWID_NAME}
EU27 = [
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia", "Denmark", "Estonia",
    "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia",
    "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania",
    "Slovakia", "Slovenia", "Spain", "Sweden",
]  # fmt: skip

# Hand-entered values. Carbon price: effective economy-wide $/tCO2, i.e. headline price x share of
# emissions covered, rounded. Vulnerability: relative index (1 = typical). Both unsourced
# approximate; see data/SOURCES.md.
HAND = {
    "USA": dict(issuer=True, carbon=3, vuln=0.8),
    "GBR": dict(issuer=True, carbon=20, vuln=0.6),
    "JPN": dict(issuer=True, carbon=2, vuln=0.8),
    "EUU": dict(issuer=True, carbon=32, vuln=0.7),
    "CHN": dict(issuer=False, carbon=5, vuln=1.0),
    "BRA": dict(issuer=False, carbon=0, vuln=1.2),
    "AUS": dict(issuer=True, carbon=2, vuln=1.0),
    "SAU": dict(issuer=False, carbon=0, vuln=1.3),
    "RUS": dict(issuer=False, carbon=0, vuln=0.7),
    "IND": dict(issuer=False, carbon=0, vuln=1.6),
    "IDN": dict(issuer=False, carbon=0.5, vuln=1.4),
    "VNM": dict(issuer=False, carbon=0, vuln=1.6),
    "ZAF": dict(issuer=False, carbon=2, vuln=1.3),
    "NGA": dict(issuer=False, carbon=0, vuln=1.8),
    "CAN": dict(issuer=True, carbon=20, vuln=0.6),
    "MEX": dict(issuer=False, carbon=1, vuln=1.2),
}
OTHER_NOTE = "Primary energy minus the listed sources (bioenergy, geothermal, other)."


def energy_value(nid, s, value, e_note, src_e):
    """An energy entry; M11 split sources note their (unsourced approximate) split share."""
    split_of = share(nid, s)
    if split_of is None:
        return tun(value, e_note, src_e, "EJ/yr")
    old, frac, what = split_of
    base = OTHER_NOTE if old == "other_renewables" else e_note
    exact = frac in (0.0, 1.0)
    note = base + " " + NOTE.format(old=old, share=1 - frac if s in ("onshore_wind", "bioenergy")
                                     else frac, what=what)  # fmt: skip
    return tun(value, note, src_e, "EJ/yr", "calibrated" if exact else "placeholder")


# Exports of goods and services, share of GDP. EU: extra-EU exports only (the World Bank EU
# figure includes trade between members). Nigeria: no recent World Bank value. Both unsourced
# approximate.
OPENNESS_OVERRIDE = {"EUU": 0.22, "NGA": 0.12}
# Approximate 2024 shares of world manufacturing (solar modules, wind turbines, batteries),
# unsourced approximate from IEA and industry reporting; the rest of the world makes the rest.
MANUFACTURING = {
    "solar": {"CHN": 0.80, "VNM": 0.05, "IND": 0.03, "USA": 0.02, "EUU": 0.01},
    "wind": {"CHN": 0.60, "EUU": 0.25, "USA": 0.05, "IND": 0.04},
    "storage": {"CHN": 0.75, "USA": 0.06, "JPN": 0.04, "EUU": 0.04},
}
SAU_HARD_DEBT_SHARE = 0.5  # of government debt; unsourced approximate (no IDS data)
NGA_FALLBACK_MIX = {"gas": 0.5, "solar": 0.3, "oil": 0.2}  # unsourced approximate


def load_csv(path: Path, key: tuple[str, str]) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return {(r[key[0]], r[key[1]]): r for r in csv.DictReader(fh)}


def num(row: dict[str, str], col: str) -> float:
    v = row.get(col, "")
    return float(v) if v not in ("", None) else 0.0


def wb_latest(path: Path) -> dict[str, tuple[str, float]]:
    rows = json.loads(path.read_text())[1] or []
    out: dict[str, tuple[str, float]] = {}
    for r in rows:
        if r["value"] is None:
            continue
        c = r["countryiso3code"]
        if c not in out or r["date"] > out[c][0]:
            out[c] = (r["date"], r["value"])
    return out


def tun(value, note, source=None, unit=None, status="calibrated"):
    d = {"value": round(value, 6) if isinstance(value, float) else value, "status": status}
    if unit:
        d["unit"] = unit
    if source:
        d["source"] = source
    d["note"] = note
    return d


def main(raw: Path) -> None:
    energy = load_csv(raw / "owid_energy" / "owid-energy-data.csv", ("country", "year"))
    co2 = load_csv(raw / "owid_co2" / "owid-co2-data.csv", ("country", "year"))
    imf = {i: json.loads((raw / "imf" / f"{i}.json").read_text())["values"][i]
           for i in ("NGDPD", "NGDP_RPCH", "LP", "GGXWDG_NGDP")}  # fmt: skip
    reserves = wb_latest(raw / "wb" / "FI.RES.TOTL.CD.json")
    ext_debt = wb_latest(raw / "wb" / "DT.DOD.DPPG.CD.json")
    openness = wb_latest(raw / "wb" / "NE.EXP.GNFS.ZS.json")
    un = load_csv(raw / "un" / "population-with-un-projections.csv", ("entity", "year"))

    world = energy[("World", DATA_YEAR)]
    wco2 = co2[("World", DATA_YEAR)]
    world_use = {s: num(world, f"{s}_consumption") * TWH_TO_EJ for s in SOURCES}
    world_primary = num(world, "primary_energy_consumption") * TWH_TO_EJ
    world_use["other_renewables"] = world_primary - sum(world_use.values())
    ef = {f: num(wco2, f"{f}_co2") / world_use[f] for f in FUELS}
    world_use = split(None, world_use)  # M11: onshore/offshore wind, bioenergy/geothermal
    hydro_factor = num(world, "hydro_consumption") / num(world, "hydro_electricity")
    solar_factor = num(world, "solar_consumption") / num(world, "solar_electricity")

    nations = {}
    data_co2 = {}
    modelled_use = {s: 0.0 for s in world_use}
    for nid, name in OWID_NAME.items():
        hand = HAND[nid]
        code = IMF_CODE[nid]
        year = DATA_YEAR
        e_now = energy[(name, year)]
        notes = {}
        if nid == "NGA":
            # No fuel breakdown in the Energy Institute data for Nigeria: fossil use is derived
            # from 2024 fuel CO2 / world emission factors; hydro and solar from electricity.
            year = "2023"
            e_now = energy[(name, year)]
            c = co2[(name, DATA_YEAR)]
            use = {f: num(c, f"{f}_co2") / ef[f] for f in FUELS}
            use["nuclear"] = use["wind"] = 0.0
            use["hydro"] = num(e_now, "hydro_electricity") * hydro_factor * TWH_TO_EJ
            use["solar"] = num(e_now, "solar_electricity") * solar_factor * TWH_TO_EJ
            primary = num(e_now, "primary_energy_consumption") * TWH_TO_EJ
            use["other_renewables"] = max(0.0, primary - sum(use.values()))
            notes["energy"] = (
                "Derived: fuel CO2 2024 / world emission factor; "
                "hydro, solar from 2023 electricity."
            )
        else:
            use = {s: num(e_now, f"{s}_consumption") * TWH_TO_EJ for s in SOURCES}
            primary = num(e_now, "primary_energy_consumption") * TWH_TO_EJ
            use["other_renewables"] = max(0.0, primary - sum(use.values()))
        use = split(nid, use)  # M11
        for s in use:
            modelled_use[s] += use[s]
        c_now = co2[(name, DATA_YEAR)]
        nation_ef = {f: num(c_now, f"{f}_co2") / use[f] for f in FUELS if use[f] > 0}
        data_co2[nid] = sum(num(c_now, f"{f}_co2") for f in FUELS)
        prod_row = energy[(name, DATA_YEAR)]
        production = {f: num(prod_row, f"{f}_production") * TWH_TO_EJ for f in FUELS}

        # BAU build mix: positive changes in use 2019 -> 2024 (Energy Institute via OWID).
        e_from, e_to = energy[(name, MIX_FROM)], energy[(name, MIX_TO)]
        retire = {}
        if nid == "NGA":
            mix = dict(NGA_FALLBACK_MIX)
            mix_note = "Unsourced approximate: no fuel breakdown for Nigeria."
        else:

            def use_at(row, s):
                if s == "other_renewables":
                    total = num(row, "primary_energy_consumption")
                    return total - sum(num(row, f"{x}_consumption") for x in SOURCES)
                return num(row, f"{s}_consumption")

            delta = {s: use_at(e_to, s) - use_at(e_from, s) for s in use}
            positive = {s: d for s, d in delta.items() if d > 0}
            total = sum(positive.values())
            mix = {s: d / total for s, d in sorted(positive.items())}
            mix_note = f"Share of positive change in use {MIX_FROM}-{MIX_TO} (energy_institute)."
            for s in ("coal", "oil", "gas", "nuclear"):
                a, b = use_at(e_from, s), use_at(e_to, s)
                if a > 0 and b < a:
                    rate = 1 - (b / a) ** (1 / 5)
                    if rate > 1 / LIFESPAN[s]:
                        retire[s] = rate
        mix = split(nid, mix)  # M11
        # Round mix to 4 dp and fix the largest share so the sum is exactly 1.
        mix = {s: round(v, 4) for s, v in mix.items() if round(v, 4) > 0}
        top = max(mix, key=mix.get)
        mix[top] = round(1 - sum(v for s, v in mix.items() if s != top), 4)

        gdp = imf["NGDPD"][code]["2025"] / 1e3
        growth = [imf["NGDP_RPCH"][code][str(y)] / 100 for y in range(2025, 2031)]
        g0 = sum(growth) / len(growth)
        g_end = min(g0, 0.5 * g0 + 0.5 * LONG_RUN_GROWTH)
        pop = imf["LP"][code]["2025"]
        if nid == "EUU":
            p25 = sum(
                num(un[(m, "2025")], "population__sex_all__age_all__variant_medium__projected")
                for m in EU27
            )
            p50 = sum(
                num(un[(m, "2050")], "population__sex_all__age_all__variant_medium__projected")
                for m in EU27
            )
        else:
            p25 = num(un[(name, "2025")], "population__sex_all__age_all__variant_medium__projected")
            p50 = num(un[(name, "2050")], "population__sex_all__age_all__variant_medium__projected")
        pop_growth = (p50 / p25) ** (1 / 25) - 1

        # Energy intensity trend: primary energy growth vs IMF real GDP growth, 2014-2024.
        if nid == "NGA":
            e0 = num(energy[(name, "2013")], "primary_energy_consumption")
            e1 = num(e_now, "primary_energy_consumption")
            yrs = range(2014, 2024)
        else:
            e0 = num(energy[(name, str(INTENSITY_FROM))], "primary_energy_consumption")
            e1 = num(e_now, "primary_energy_consumption")
            yrs = range(INTENSITY_FROM + 1, int(DATA_YEAR) + 1)
        gdp_ratio = 1.0
        for y in yrs:
            gdp_ratio *= 1 + imf["NGDP_RPCH"][code][str(y)] / 100
        decline = 1 - ((e1 / e0) / gdp_ratio) ** (1 / len(yrs))

        debt_total = imf["GGXWDG_NGDP"][code]["2025"] / 100 * gdp
        if hand["issuer"]:
            debt_hard, hard_note, hard_src = 0.0, "Borrows in its own reserve currency.", None
        elif nid in ext_debt:
            yr, v = ext_debt[nid]
            debt_hard = min(v / 1e12, debt_total)
            hard_note, hard_src = f"Public and publicly guaranteed external debt, {yr}.", "wb_ids"
        else:
            debt_hard = SAU_HARD_DEBT_SHARE * debt_total
            hard_note, hard_src = "Unsourced approximate: half of government debt.", None
        if hand["issuer"]:
            fx, fx_note, fx_src = 0.0, "Not tracked for reserve-currency issuers.", None
        else:
            yr, v = reserves[nid]
            fx, fx_note, fx_src = v / 1e12, f"Total reserves incl. gold, {yr}.", "wb_wdi"

        if nid in OPENNESS_OVERRIDE:
            open_v, open_note, open_src = OPENNESS_OVERRIDE[nid], "Unsourced approximate.", None
        else:
            yr, v = openness[nid]
            open_v, open_note, open_src = (
                v / 100,
                f"Exports of goods and services / GDP, {yr}.",
                "wb_wdi",
            )
        manuf = {t: shares[nid] for t, shares in MANUFACTURING.items() if nid in shares}

        src_e = "energy_institute"
        e_note = notes.get("energy", f"Primary energy use {year}, substitution method.")
        nations[nid] = {
            "hard_currency_issuer": hand["issuer"],
            "start": {
                "gdp": tun(gdp, "GDP 2025, current USD at market exchange rates.", "imf_weo", "T$"),
                "population": tun(pop, "Population 2025.", "imf_weo", "million"),
                "fx_reserves": tun(fx, fx_note, fx_src, "T$"),
                "debt_hard": tun(
                    debt_hard,
                    hard_note,
                    hard_src,
                    "T$",
                    "calibrated" if hard_src else "placeholder",
                ),
                "debt_local": tun(
                    debt_total - debt_hard,
                    "General government gross debt 2025 minus hard-currency debt.",
                    "imf_weo",
                    "T$",
                ),
                "carbon_price": tun(
                    float(hand["carbon"]),
                    "Unsourced approximate: headline price x coverage, 2025.",
                    None,
                    "$/tCO2",
                    "placeholder",
                ),
                "export_openness": tun(
                    open_v,
                    open_note,
                    open_src,
                    "share of GDP",
                    "calibrated" if open_src else "placeholder",
                ),
                "energy": {s: energy_value(nid, s, use[s], e_note, src_e) for s in use},
                "production": {
                    f: tun(production[f], f"Production {DATA_YEAR}.", src_e, "EJ/yr") for f in FUELS
                },
                "emission_factor": {
                    f: tun(v, f"Fuel CO2 / fuel use, {DATA_YEAR}.", "gcb", "MtCO2/EJ")
                    for f, v in nation_ef.items()
                },
            },
            "trend": {
                "g0_start": tun(g0, "Mean real GDP growth 2025-2030 (WEO projections).", "imf_weo"),
                "g0_end": tun(
                    g_end,
                    f"min(g0_start, halfway to {LONG_RUN_GROWTH}). Placeholder convergence rule.",
                    None,
                    None,
                    "placeholder",
                ),
                "population_growth": tun(
                    pop_growth, "Annual growth 2025-2050, medium variant.", "un_wpp"
                ),
                "intensity_decline": tun(
                    decline,
                    f"Annual fall in primary energy per unit real GDP, {yrs[0] - 1}-{yrs[-1]}.",
                    "energy_institute",
                ),
            },
            "climate": {
                "vulnerability": tun(
                    float(hand["vuln"]),
                    "Unsourced approximate relative index (1 = typical).",
                    None,
                    None,
                    "placeholder",
                )
            },
            "bau": {
                "mix": {
                    s: tun(
                        v,
                        mix_note,
                        None if nid == "NGA" else src_e,
                        None,
                        "placeholder" if nid == "NGA" else "calibrated",
                    )
                    for s, v in mix.items()
                },
            },
        }
        if manuf:
            nations[nid]["start"]["manufacturing_share"] = {
                t: tun(
                    v,
                    "Unsourced approximate share of world manufacturing, 2024.",
                    None,
                    None,
                    "placeholder",
                )
                for t, v in manuf.items()
            }
        if retire:
            nations[nid]["bau"]["retire_rate"] = {
                s: tun(r, f"Observed annual decline in use {MIX_FROM}-{MIX_TO}.", src_e)
                for s, r in sorted(retire.items())
            }

    write_yaml(nations)
    modelled_co2 = sum(data_co2.values())
    luc = [num(co2[("World", str(y))], "land_use_change_co2") for y in range(2015, 2025)]
    derived = {
        "emission_factor": ef,
        "global_installed": world_use,
        "coverage_share": {s: modelled_use[s] / world_use[s] for s in world_use},
        "rest_of_world_co2": sum(num(wco2, f"{f}_co2") for f in FUELS) - modelled_co2,
        "modelled_co2": modelled_co2,
        "other_fossil_co2": sum(
            num(wco2, c) for c in ("cement_co2", "flaring_co2", "other_industry_co2")
        ),
        "land_use_co2_mean_2015_2024": sum(luc) / len(luc),
        "world_co2_2024": num(wco2, "co2"),
        "world_primary_ej": world_primary,
    }
    json.dump(derived, sys.stdout, indent=2)
    print()


def fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(v)


def flow(d: dict) -> str:
    return "{" + ", ".join(f"{k}: {fmt(v)}" for k, v in d.items()) + "}"


def write_yaml(nations: dict) -> None:
    import yaml  # only needed to read the structural fields

    current = yaml.safe_load(OUT.read_text())["nations"]
    lines = [
        "# Nations in the simulation. IDs are ISO 3166-1 alpha-3; the EU uses the World Bank",
        "# aggregate code EUU. Archetype and difficulty are design intent from docs/DESIGN.md.",
        "#",
        "# GENERATED by scripts/data_prep/build_countries.py from the sources in data/SOURCES.md.",
        "# Edit structural fields here freely; regenerate numbers with the script. Personalities",
        "# (M3) are game archetypes based on each nation's energy-policy stance, not commentary.",
        "",
        "nations:",
    ]
    for nid in OWID_NAME:
        cur = current[nid]
        lines.append(f"  {nid}:")
        for key in ("name", "playable", "archetype", "difficulty", "personality"):
            v = cur.get(key)
            lines.append(f"    {key}: {'null' if v is None else fmt(v)}")
        data = nations[nid]
        lines.append(f"    hard_currency_issuer: {fmt(data['hard_currency_issuer'])}")
        for section in ("start", "trend", "climate", "bau"):
            lines.append(f"    {section}:")
            for k, v in data[section].items():
                if "value" in v:
                    lines.append(f"      {k}: {flow(v)}")
                else:
                    lines.append(f"      {k}:")
                    for k2, v2 in v.items():
                        lines.append(f"        {k2}: {flow(v2)}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
