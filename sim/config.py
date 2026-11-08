"""Load and validate the YAML data files in `data/`.

Rule: every number in a data file must be a *tunable*, a mapping of the form

    value: <number or list>
    status: placeholder | calibrated
    note: <where the value came from>
    source: <optional citation key from data/SOURCES.md>
    unit: <optional unit>

Strings, booleans and nulls are structural (names, flags, categories) and may appear bare. A bare
number anywhere is a validation error, so magic numbers cannot slip into the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sim import canonical

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FILES = ("tuning", "techs", "countries", "events")
TUNABLE_STATUSES = frozenset({"placeholder", "calibrated"})
TUNABLE_KEYS = frozenset({"value", "status", "note", "source", "unit"})
PERSONALITIES = frozenset({"green_leader", "fossil_defender", "opportunist", "cautious_follower"})
SOURCE_CATEGORIES = frozenset({"fossil", "clean_dispatchable", "variable_renewable", "enabler"})
COUNTRY_REQUIRED = ("name", "playable", "archetype", "difficulty", "personality")


class ConfigError(ValueError):
    """Raised when a data file is malformed."""


@dataclass(frozen=True)
class Config:
    tuning: dict[str, Any]
    techs: dict[str, Any]
    countries: dict[str, Any]
    events: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in FILES}

    @property
    def hash(self) -> str:
        """Digest of all loaded data, recorded with each run for replay."""
        return canonical.digest(self.to_dict())

    def value(self, section: str, dotted_path: str) -> Any:
        """Return the `value` of the tunable at `dotted_path` in `section`."""
        node: Any = getattr(self, section)
        for part in dotted_path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise KeyError(f"{section}: no entry at '{dotted_path}'")
            node = node[part]
        if not _is_tunable(node):
            raise KeyError(f"{section}: '{dotted_path}' is not a tunable")
        return node["value"]

    @property
    def nation_ids(self) -> list[str]:
        return sorted(self.countries["nations"])

    @property
    def playable_ids(self) -> list[str]:
        return [i for i in self.nation_ids if self.countries["nations"][i]["playable"]]

    @property
    def source_ids(self) -> list[str]:
        return sorted(self.techs["sources"])


def load(data_dir: Path | str = DEFAULT_DATA_DIR) -> Config:
    data_dir = Path(data_dir)
    raw: dict[str, Any] = {}
    for name in FILES:
        path = data_dir / f"{name}.yaml"
        if not path.exists():
            raise ConfigError(f"missing data file: {path}")
        with path.open(encoding="utf-8") as fh:
            content = yaml.safe_load(fh)
        if content is None:
            content = {}
        if not isinstance(content, dict):
            raise ConfigError(f"{path.name}: top level must be a mapping")
        validate_tunables(content, path.name)
        raw[name] = content
    cfg = Config(**raw)
    _validate_countries(cfg)
    _validate_techs(cfg)
    return cfg


def _is_tunable(node: Any) -> bool:
    return isinstance(node, dict) and "value" in node


def _is_number(node: Any) -> bool:
    return isinstance(node, int | float) and not isinstance(node, bool)


def validate_tunables(node: Any, path: str) -> None:
    """Check every tunable is well formed and no number appears outside one."""
    if _is_tunable(node):
        extra = set(node) - TUNABLE_KEYS
        if extra:
            raise ConfigError(f"{path}: unknown tunable keys {sorted(extra)}")
        if node.get("status") not in TUNABLE_STATUSES:
            raise ConfigError(f"{path}: status must be one of {sorted(TUNABLE_STATUSES)}")
        note = node.get("note")
        if not isinstance(note, str) or not note.strip():
            raise ConfigError(f"{path}: tunable needs a non-empty note")
        if isinstance(node["value"], dict):
            raise ConfigError(f"{path}: tunable value cannot be a mapping")
        return
    if isinstance(node, dict):
        for key, child in node.items():
            validate_tunables(child, f"{path}.{key}")
    elif isinstance(node, list):
        for i, child in enumerate(node):
            validate_tunables(child, f"{path}[{i}]")
    elif _is_number(node):
        raise ConfigError(
            f"{path}: bare number {node!r}; wrap it in a tunable with status and note"
        )


def _validate_countries(cfg: Config) -> None:
    nations = cfg.countries.get("nations")
    if not isinstance(nations, dict) or not nations:
        raise ConfigError("countries.yaml: 'nations' must be a non-empty mapping")
    for nid, spec in nations.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"countries.yaml: {nid} must be a mapping")
        missing = [k for k in COUNTRY_REQUIRED if k not in spec]
        if missing:
            raise ConfigError(f"countries.yaml: {nid} missing {missing}")
        if not isinstance(spec["playable"], bool):
            raise ConfigError(f"countries.yaml: {nid}.playable must be true or false")
        personality = spec["personality"]
        if personality is not None and personality not in PERSONALITIES:
            raise ConfigError(f"countries.yaml: {nid}.personality '{personality}' is unknown")


def _validate_techs(cfg: Config) -> None:
    sources = cfg.techs.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ConfigError("techs.yaml: 'sources' must be a non-empty mapping")
    for sid, spec in sources.items():
        category = spec.get("category") if isinstance(spec, dict) else None
        if category not in SOURCE_CATEGORIES:
            raise ConfigError(
                f"techs.yaml: {sid}.category must be one of {sorted(SOURCE_CATEGORIES)}"
            )
