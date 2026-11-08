"""Metrics over run histories, and the business-as-usual calibration table.

    python -m sim.report bau            # print the BAU calibration tables (markdown)

BALANCE_REPORT.md generation arrives in M5.
"""

from __future__ import annotations

import sys
from typing import Any

from sim import config, runner
from sim.config import Config
from sim.state import World

CHECKPOINTS = (0, 20, 60, 99)  # 2025Q1, 2030Q1, 2040Q1, 2049Q4


def annual(history: list[dict[str, Any]], year: int, key: str, nid: str | None = None) -> float:
    """Sum of a per-year rate over the four quarters of `year` / 4 (i.e. the annual average)."""
    recs = [h for h in history if h["label"].startswith(str(year))]
    if nid is None:
        return sum(h[key] for h in recs) / len(recs)
    return sum(h["nations"][nid][key] for h in recs) / len(recs)


def bau_world(cfg: Config, seed: int = 1) -> World:
    return runner.play(cfg, seed, cfg.playable_ids[0], "noop")


def bau_tables(cfg: Config, world: World) -> str:
    h = world.history
    years = (2025, 2030, 2040, 2049)
    out = ["### World", "", "| Metric | " + " | ".join(map(str, years)) + " |", "|---" * 5 + "|"]
    em = [annual(h, y, "global_emissions") / 1e3 for y in years]
    out.append("| Global CO2 (Gt/yr) | " + " | ".join(f"{v:.1f}" for v in em) + " |")
    warm = [next(r["warming"] for r in reversed(h) if r["label"].startswith(str(y))) for y in years]
    out.append("| Warming, end of year (degC) | " + " | ".join(f"{v:.2f}" for v in warm) + " |")
    out += ["", "### Nations", ""]
    out.append(
        "| Nation | GDP 2025 (T$) | GDP 2049 | Growth 2025-49 (%/yr) | CO2 2025 (Mt) "
        "| CO2 2030 | CO2 2040 | CO2 2049 | Fossil share 2025 | 2049 | Max shortfall |"
    )
    out.append("|---" * 11 + "|")
    for nid in cfg.nation_ids:
        g25, g49 = annual(h, 2025, "gdp", nid), annual(h, 2049, "gdp", nid)
        cagr = (g49 / g25) ** (1 / 24) - 1
        co2 = [annual(h, y, "emissions", nid) for y in (2025, 2030, 2040, 2049)]

        def fossil_share(year: int, nid: str = nid) -> float:
            recs = [r["nations"][nid]["supply"] for r in h if r["label"].startswith(str(year))]
            fossil = sum(s[f] for s in recs for f in ("coal", "oil", "gas"))
            total = sum(sum(s.values()) for s in recs)
            return fossil / total

        short = max(r["nations"][nid]["shortfall"] / r["nations"][nid]["demand"] for r in h)
        out.append(
            f"| {nid} | {g25:.2f} | {g49:.2f} | {cagr * 100:.1f} | "
            + " | ".join(f"{v:,.0f}" for v in co2)
            + f" | {fossil_share(2025):.0%} | {fossil_share(2049):.0%} | {short:.1%} |"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ["bau"]:
        print("usage: python -m sim.report bau", file=sys.stderr)
        return 2
    cfg = config.load()
    print(bau_tables(cfg, bau_world(cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
