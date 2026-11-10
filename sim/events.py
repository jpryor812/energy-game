"""Events (M15b): minor-nation choices with shared funds, plus the M5 shocks (sim.shocks).

A minor-nation event (data/events.yaml) opens in a rest-of-world region: an oil discovery, a
rainforest concession, a coal-power plan, or an adaptation appeal. Any nation can pledge capital
toward its fund (`pledge_to_event`) until the deadline:

- If pledges reach the target, the event is funded at the end of that quarter: the bad outcome
  is avoided, contributors gain the region's trust in proportion to what they paid (sim.regions
  `trust_per_trillion`), and each earns financed climate credit for its share of the CO2
  avoided, every quarter to the end of the game.
- If the deadline passes first, pledges are refunded and the outcome happens: the oil is
  developed (more CO2, a richer region), the forest is logged (land-use CO2), the coal plants
  are built, or the region loses GDP and trusts everyone less.

Pledges are refunded on failure, so pledging risks nothing but tied-up capital; the tension is
who pays. New events draw from the "events" stream, keyed by turn, so a seed replays exactly.
"""

from __future__ import annotations

from typing import Any

from sim import rng, shocks
from sim.config import Config
from sim.state import World

OPEN, FUNDED, FAILED = "open", "funded", "failed"


def _e(cfg: Config, name: str) -> Any:
    return cfg.value("events", f"events.{name}")


def _t(cfg: Config, kind: str, name: str) -> Any:
    return cfg.value("events", f"events.types.{kind}.{name}")


def types(cfg: Config) -> list[str]:
    return sorted(cfg.events["events"]["types"])


def find(world: World, eid: str) -> dict[str, Any] | None:
    return next((e for e in world.minor_events if e["id"] == eid), None)


def open_events(world: World) -> list[dict[str, Any]]:
    return [e for e in world.minor_events if e["status"] == OPEN]


def pledged(event: dict[str, Any]) -> float:
    return sum(event["pledges"].values())


def remaining(event: dict[str, Any]) -> float:
    return max(0.0, event["target"] - pledged(event))


def text(cfg: Config, event: dict[str, Any]) -> str:
    kind = event["type"]
    spec = cfg.events["events"]["types"][kind]
    values = {k: v["value"] for k, v in spec.items() if isinstance(v, dict) and "value" in v}
    region = cfg.regions["regions"][event["region"]]["name"]
    return spec["text"].format(region=region, gdp=values.get("gdp_boost", 0.0), **values)


def avoided_co2(cfg: Config, event: dict[str, Any]) -> float:
    """MtCO2/yr a funded event avoids (net of leakage for fuel kept in the ground)."""
    kind = event["type"]
    if kind == "oil_discovery":
        return _t(cfg, kind, "co2") * (1 - _e(cfg, "leakage"))
    if kind == "rainforest":
        return _t(cfg, kind, "co2")
    if kind == "coal_pipeline":
        return _t(cfg, kind, "energy") * cfg.reg(event["region"], "fossil_ef")
    return 0.0


def pledge(world: World, nid: str, eid: str, amount: float) -> None:
    event = find(world, eid)
    event["pledges"][nid] = event["pledges"].get(nid, 0.0) + amount


# --- the turn ------------------------------------------------------------------------------------


def _fund(cfg: Config, world: World, event: dict[str, Any]) -> None:
    event["status"] = FUNDED
    event["closed"] = world.t
    r = world.regions[event["region"]]
    per_tn = cfg.tune("regions.trust_per_trillion")
    if event["type"] == "adaptation_appeal":
        per_tn *= _t(cfg, "adaptation_appeal", "trust_bonus")
    for nid in sorted(event["pledges"]):
        r.trust[nid] = min(1.0, r.trust.get(nid, 0.5) + per_tn * event["pledges"][nid])
    if event["type"] == "coal_pipeline":
        r.clean += _t(cfg, "coal_pipeline", "energy")  # solar instead


def _fail(cfg: Config, world: World, event: dict[str, Any]) -> None:
    event["status"] = FAILED
    event["closed"] = world.t
    for nid in sorted(event["pledges"]):  # refunds
        world.nations[nid].capital += event["pledges"][nid]
    r = world.regions[event["region"]]
    kind = event["type"]
    if kind == "oil_discovery":
        co2 = _t(cfg, kind, "co2")
        r.extra_co2 += co2
        r.emissions += co2
        r.fossil_production += co2 / cfg.reg(event["region"], "fossil_ef")
        r.gdp *= 1 + _t(cfg, kind, "gdp_boost")
    elif kind == "rainforest":
        world.base["land_use_extra"] = world.base.get("land_use_extra", 0.0) + _t(cfg, kind, "co2")
    elif kind == "coal_pipeline":
        r.fossil += _t(cfg, kind, "energy")
    elif kind == "adaptation_appeal":
        r.gdp *= 1 - _t(cfg, kind, "gdp_loss")
        for nid in sorted(r.trust):
            r.trust[nid] = max(0.0, r.trust[nid] - _e(cfg, "trust_hit"))


def _credit(cfg: Config, world: World, dt: int) -> None:
    """Contributors to funded events earn financed credit for their share of the CO2 avoided."""
    weight = cfg.tune("credits.weight_financed")
    for event in world.minor_events:
        if event["status"] != FUNDED:
            continue
        total = pledged(event)
        avoided = avoided_co2(cfg, event)
        if total <= 0 or avoided <= 0:
            continue
        for nid in sorted(event["pledges"]):
            n = world.nations[nid]
            credit = weight * avoided * event["pledges"][nid] / total * dt / 4
            n.climate_credit["financed"] = n.climate_credit.get("financed", 0.0) + credit


def _maybe_open(cfg: Config, world: World, dt: int) -> dict[str, Any] | None:
    if world.t < _e(cfg, "first_turn") or len(open_events(world)) >= _e(cfg, "max_open"):
        return None
    if world.t + int(_e(cfg, "deadline")) > int(cfg.tune("time.turns")):
        return None  # too late in the game to resolve
    draw = rng.stream(world.seed, "events", world.t, "minor")
    if draw.random() >= min(1.0, _e(cfg, "rate") * dt):
        return None
    kinds = types(cfg)
    weights = [_t(cfg, k, "weight") for k in kinds]
    pick = draw.random() * sum(weights)
    kind = kinds[-1]
    for k, wgt in zip(kinds, weights, strict=True):
        if pick < wgt:
            kind = k
            break
        pick -= wgt
    allowed = [r for r in cfg.events["events"]["types"][kind]["regions"] if r in world.regions]
    region = allowed[int(draw.random() * len(allowed))]
    event = {
        "id": f"E{len(world.minor_events) + 1}",
        "type": kind,
        "region": region,
        "target": _t(cfg, kind, "target"),
        "opened": world.t + 1,  # pledges from next quarter
        "deadline": world.t + int(_e(cfg, "deadline")),
        "status": OPEN,
        "closed": -1,
        "pledges": {},
    }
    world.minor_events.append(event)
    return event


def apply_minor(world: World, cfg: Config, dt: int) -> list[dict[str, Any]]:
    """Resolve open events (funded or past the deadline), credit funded ones, maybe open one."""
    log = []
    for event in open_events(world):
        if remaining(event) <= 1e-12:
            _fund(cfg, world, event)
            log.append({"type": "minor_event", "id": event["id"], "status": FUNDED})
        elif world.t >= event["deadline"]:
            _fail(cfg, world, event)
            log.append({"type": "minor_event", "id": event["id"], "status": FAILED})
    _credit(cfg, world, dt)
    new = _maybe_open(cfg, world, dt)
    if new:
        log.append({"type": "minor_event", "id": new["id"], "status": OPEN})
    return log


def on_turn(world: World, cfg: Config, dt: int = 1) -> list[dict[str, Any]]:
    """Called once per turn, after the scoring snapshot. Returns what happened."""
    return shocks.apply(world, cfg, dt) + apply_minor(world, cfg, dt)
