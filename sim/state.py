"""World state: plain dataclasses that round-trip through JSON.

The engine is functions over these objects. `to_dict` / `from_dict` are explicit per class so the
saved format is stable and readable; `World.hash()` is the digest used by determinism tests.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from sim import canonical

STATE_VERSION = 1


@dataclass
class Pledge:
    target_emissions: float
    year: int
    made_turn: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Pledge:
        return cls(
            target_emissions=float(d["target_emissions"]),
            year=int(d["year"]),
            made_turn=int(d["made_turn"]),
        )


@dataclass
class Construction:
    """Capacity under construction; comes online at `complete_turn`."""

    source: str
    amount: float
    complete_turn: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Construction:
        return cls(
            source=d["source"], amount=float(d["amount"]), complete_turn=int(d["complete_turn"])
        )


@dataclass
class Deal:
    id: str
    type: str
    financier: str
    host: str
    terms: dict[str, Any]
    status: str
    start_turn: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Deal:
        return cls(
            id=d["id"],
            type=d["type"],
            financier=d["financier"],
            host=d["host"],
            terms=dict(d["terms"]),
            status=d["status"],
            start_turn=int(d["start_turn"]),
        )


@dataclass
class Nation:
    id: str
    playable: bool
    personality: str | None = None
    gdp: float = 0.0
    population: float = 0.0
    capital: float = 0.0
    political_capital: float = 0.0
    influence: float = 0.0
    tech_points: float = 0.0
    fx_reserves: float = 0.0
    debt_hard: float = 0.0
    debt_local: float = 0.0
    approval: float = 0.0
    stability: float = 0.0
    energy_intensity: float = 0.0
    demand: float = 0.0
    capacity: dict[str, float] = field(default_factory=dict)
    pipeline: list[Construction] = field(default_factory=list)
    carbon_price: float = 0.0
    subsidies: dict[str, float] = field(default_factory=dict)
    tariffs: dict[str, float] = field(default_factory=dict)
    emissions: float = 0.0
    cumulative_emissions: float = 0.0
    fair_share_budget: float = 0.0
    slots_banked: dict[str, int] = field(default_factory=dict)
    pledge: Pledge | None = None
    # M1 energy and economy outputs (rates are per year; see docs/ASSUMPTIONS.md "Units").
    supply: dict[str, float] = field(default_factory=dict)
    shortfall: float = 0.0
    curtailment: float = 0.0
    energy_price: float = 0.0
    fossil_production: dict[str, float] = field(default_factory=dict)
    fossil_exports: dict[str, float] = field(default_factory=dict)
    fossil_imports: dict[str, float] = field(default_factory=dict)
    export_revenue: float = 0.0
    growth: float = 0.0
    climate_damage: float = 0.0
    base: dict[str, float] = field(default_factory=dict)
    # M2 policy state and action effects.
    research: dict[str, float] = field(default_factory=dict)
    rebate: float = 0.0
    activity_cap: float = 0.0
    adaptation: float = 0.0
    efficiency_spent: float = 0.0
    pending_writeoff: float = 0.0
    carbon_revenue: float = 0.0
    clean_built: float = 0.0
    import_dependence: float = 0.0

    _FLOATS = (
        "gdp", "population", "capital", "political_capital", "influence", "tech_points",
        "fx_reserves", "debt_hard", "debt_local", "approval", "stability", "energy_intensity",
        "demand", "carbon_price", "emissions", "cumulative_emissions", "fair_share_budget",
        "shortfall", "curtailment", "energy_price", "export_revenue", "growth", "climate_damage",
        "rebate", "activity_cap", "adaptation", "efficiency_spent", "pending_writeoff",
        "carbon_revenue", "clean_built", "import_dependence",
    )  # fmt: skip
    _FLOAT_MAPS = (
        "capacity", "subsidies", "tariffs", "supply", "fossil_production", "fossil_exports",
        "fossil_imports", "base", "research",
    )  # fmt: skip

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Nation:
        return cls(
            id=d["id"],
            playable=bool(d["playable"]),
            personality=d["personality"],
            **{name: float(d[name]) for name in cls._FLOATS},
            **{name: {k: float(v) for k, v in d[name].items()} for name in cls._FLOAT_MAPS},
            pipeline=[Construction.from_dict(c) for c in d["pipeline"]],
            slots_banked={k: int(v) for k, v in d["slots_banked"].items()},
            pledge=Pledge.from_dict(d["pledge"]) if d["pledge"] is not None else None,
        )


@dataclass
class World:
    t: int
    seed: int
    nations: dict[str, Nation]
    global_cumulative_emissions: float = 0.0
    global_emissions: float = 0.0
    warming: float = 0.0
    base: dict[str, float] = field(default_factory=dict)
    tech_state: dict[str, float] = field(default_factory=dict)
    blocs: dict[str, list[str]] = field(default_factory=dict)
    deals: dict[str, Deal] = field(default_factory=dict)
    trust: dict[str, dict[str, float]] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["version"] = STATE_VERSION
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> World:
        if d.get("version") != STATE_VERSION:
            raise ValueError(f"unsupported state version {d.get('version')!r}")
        return cls(
            t=int(d["t"]),
            seed=int(d["seed"]),
            nations={k: Nation.from_dict(v) for k, v in d["nations"].items()},
            global_cumulative_emissions=float(d["global_cumulative_emissions"]),
            global_emissions=float(d["global_emissions"]),
            warming=float(d["warming"]),
            base={k: float(v) for k, v in d["base"].items()},
            tech_state={k: float(v) for k, v in d["tech_state"].items()},
            blocs={k: list(v) for k, v in d["blocs"].items()},
            deals={k: Deal.from_dict(v) for k, v in d["deals"].items()},
            trust={a: {b: float(x) for b, x in row.items()} for a, row in d["trust"].items()},
            history=[dict(h) for h in d["history"]],
        )

    def to_json(self, *, indent: int | None = 2) -> str:
        return canonical.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> World:
        return cls.from_dict(json.loads(text))

    def hash(self) -> str:
        return canonical.digest(self.to_dict())
