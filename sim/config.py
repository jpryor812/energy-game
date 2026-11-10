"""Load and validate the YAML data files in `data/`.

Rule: every number in a data file must be a *tunable*, a mapping of the form

    value: <number or list>
    status: placeholder | calibrated
    note: <where the value came from>
    source: <optional citation key from data/SOURCES.md>
    unit: <optional unit>

Strings, booleans and nulls are structural (names, flags, categories) and may appear bare. A bare
number anywhere is a validation error, so magic numbers cannot slip into the data.

The loader also checks that every tunable the model reads is present, so a missing value fails at
load time rather than mid-run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sim import canonical

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FILES = ("tuning", "techs", "countries", "events", "targets", "research", "regions")
TUNABLE_STATUSES = frozenset({"placeholder", "calibrated"})
TUNABLE_KEYS = frozenset({"value", "status", "note", "source", "unit"})
PERSONALITIES = frozenset({"green_leader", "fossil_defender", "opportunist", "cautious_follower"})
SOURCE_CATEGORIES = frozenset(
    {"fossil", "clean_dispatchable", "variable_renewable", "enabler", "removal"}
)
FUELS = ("coal", "gas", "oil")
COUNTRY_REQUIRED = (
    "name",
    "playable",
    "archetype",
    "difficulty",
    "personality",
    "hard_currency_issuer",
)

# Tunables the model reads. Paths are relative to the file (tuning) or to one entry (techs,
# countries); "{source}" and "{fuel}" expand over the relevant ids.
REQUIRED_TUNING = (
    "time.start_year",
    "time.turns",
    "time.stocktake_interval",
    "seasonality.demand_factor",
    "energy.vre_base_absorb_share",
    "energy.vre_max_share_start",
    "energy.vre_max_share_end",
    "energy.clean_max_share_start",
    "energy.clean_max_share_end",
    "energy.fuel_price.{fuel}",
    "economy.capital_share_of_gdp",
    "economy.fossil_revenue_take",
    "economy.interest_rate_hard",
    "economy.interest_rate_local",
    "economy.shortfall_drag",
    "economy.price_drag",
    "economy.trade_elasticity",
    "economy.debt_drag",
    "economy.fx_passthrough",
    "politics.approval_start",
    "politics.approval_baseline",
    "politics.approval_reversion",
    "politics.approval_shortfall_hit",
    "politics.approval_price_hit",
    "politics.approval_damage_hit",
    "politics.stability_reversion",
    "climate.warming_start",
    "climate.tcre",
    "climate.ch4_warming",
    "climate.aerosol_warming",
    "climate.other_warming",
    "climate.ch4_lifetime",
    "climate.ch4_fossil_share",
    "climate.other_methane_trend",
    "climate.aerosol_trend",
    "climate.abatement_max_fossil",
    "climate.abatement_max_other",
    "climate.abatement_half_spend",
    "climate.forest_max_cut",
    "climate.forest_half_fund",
    "climate.damage_coefficient",
    "climate.rest_of_world_co2",
    "climate.rest_of_world_growth",
    "climate.land_use_co2",
    "climate.land_use_trend",
    "climate.other_fossil_co2",
    "slots.domestic_per_quarter",
    "slots.diplomatic_per_quarter",
    "slots.domestic_bank_cap",
    "slots.diplomatic_bank_cap",
    "market.cost_weight",
    "research.h2_cap_factor",
    "research.ccs_capture",
    "research.ccs_capital_cost",
    "ai.tech_research_share",
    "license.patent_years",
    "license.ai_markup",
    "license.ai_trust_premium",
    "license.ai_refuse_trust",
    "license.ai_license_share",
    "license.exclusion_trust_hit",
    "permitting.max_cut",
    "permitting.pc_per_level",
    "permitting.vote_weight",
    "permitting.approval_hit",
    "permitting.default_opposition",
    "permitting.habituation_quarters",
    "permitting.habituation_factor",
    "permitting.financing_share",
    "market.fast_horizon",
    "market.cost_temperature",
    "market.discount_rate",
    "market.reserve_margin",
    "research.max_cost_cut",
    "research.half_effect_spend",
    "research.points_per_trillion",
    "research.productivity",
    "research.productivity_cap",
    "economy.stranded_drag",
    "economy.rebate_price_relief",
    "politics.political_capital_start",
    "politics.pc_income_base",
    "politics.pc_income_approval",
    "climate.adaptation_max",
    "climate.adaptation_half_spend",
    "actions.carbon_price_max",
    "actions.carbon_pc_per_dollar",
    "actions.retire_pc_per_ej",
    "actions.retire_coal_multiplier",
    "actions.retire_approval_hit",
    "actions.stranded_value_share",
    "actions.max_subsidy",
    "actions.efficiency_max_gain",
    "actions.efficiency_scale",
    "actions.influence_per_trillion",
    "actions.fossil_ban_pc",
    "actions.activity_cap_max",
    "actions.activity_pc_cost",
    "actions.activity_gdp_ratio",
    "actions.activity_approval_hit",
    "scoring.weight_income",
    "scoring.weight_security",
    "scoring.weight_welfare",
    "scoring.weight_clean",
    "scoring.income_scale",
    "scoring.shortfall_zero",
    "scoring.import_scale",
    "scoring.price_scale",
    "scoring.clean_scale",
    "scoring.clean_share_floor",
    "scoring.world_good",
    "scoring.world_bad",
    "scoring.world_floor",
    "scoring.good_world_warming",
    "scoring.falling_years",
    "scoring.top_rank",
    "scoring.fallen_stability",
    "scoring.net_zero_share",
    "scoring.bonus_first_net_zero",
    "scoring.bonus_largest_reduction",
    "trade.world_gdp_2025",
    "trade.openness_floor",
    "trade.tariff_elasticity",
    "trade.export_growth_elasticity",
    "trade.tariff_price_drag",
    "trade.cleantech_growth_elasticity",
    "trade.supplier_switching",
    "trade.tariff_max",
    "diplomacy.trust_start",
    "diplomacy.trust_reversion",
    "diplomacy.talks_influence_cost",
    "diplomacy.talks_trust_gain",
    "diplomacy.tariff_trust_hit",
    "diplomacy.club_min_carbon_price",
    "diplomacy.club_rate_discount",
    "deals.proposal_expiry",
    "deals.host_capacity_cap",
    "deals.max_duration",
    "deals.currency_loss",
    "deals.signing_trust_gain",
    "deals.completion_trust_gain",
    "deals.default_trust_hit",
    "deals.exit_trust_hit",
    "deals.default_growth_hit",
    "deals.equity_hazard",
    "deals.hazard_instability",
    "deals.hazard_fx",
    "deals.hazard_distrust",
    "deals.hazard_default",
    "deals.recent_default_quarters",
    "deals.failure_trust_hit",
    "credits.start_price",
    "credits.drift",
    "credits.min_price",
    "credits.weight_real",
    "credits.weight_financed",
    "credits.weight_exported",
    "credits.exported_cut_lifespan",
    "credits.weight_purchased",
    "stocktake.target_warming",
    "stocktake.pathway_years",
    "stocktake.pathway_levels",
    "stocktake.tolerance",
    "stocktake.overshoot_trust_hit",
    "stocktake.undershoot_trust_gain",
    "stocktake.coalition_tariff_per_overshoot",
    "stocktake.coalition_tariff_max",
    "stocktake.pledge_trust",
    "scoring.weight_climate",
    "scoring.weight_absolute",
    "scoring.weight_relative",
    "scoring.abs_income_low",
    "scoring.abs_income_high",
    "scoring.abs_weight_income",
    "scoring.abs_weight_clean_share",
    "scoring.abs_weight_emissions",
    "scoring.abs_weight_security",
    "scoring.abs_weight_approval",
    "scoring.difficulty_easy",
    "scoring.difficulty_easy_to_medium",
    "scoring.difficulty_medium",
    "scoring.difficulty_hard",
    "scoring.bonus_largest_cut",
    "scoring.bonus_clean_gain",
    "scoring.climate_scale",
    "scoring.bonus_best_deal",
    "ai.personalities.{personality}.retaliation",
    "ai.personalities.{personality}.credit_value",
    "ai.personalities.{personality}.deal_affinity",
    "ai.deal_share",
    "ai.deal_reserve_years",
    "ai.deal_rate_premium",
    "ai.deal_duration",
    "ai.deal_collateral",
    "ai.deal_exit_penalty",
    "ai.currency_risk_weight",
    "ai.trust_weight",
    "ai.counter_margin",
    "ai.counter_rate_factor",
    "ai.counter_accept_share",
    "ai.host_growth_weight",
    "ai.credit_cover_share",
    "ai.club_affinity",
    "ai.max_payment_share",
    "ai.factory_share",
    "ai.electrification_share",
    "ai.ceiling_margin",
    "ai.methane_share",
    "ai.removal_share",
    "ai.forest_share",
    "ai.methane_horizon",
    "ai.equity_share_offer",
    "ai.removal_energy_cap",
    "ai.climate_loan_discount",
    "tax.min_change",
    "tax.max_change",
    "tax.growth_drag",
    "tax.approval_hit",
    "tax.pc_per_point",
    "tax.generation_credit_max",
    "tax.manufacturing_credit_max",
    "industry.world_capacity_solar",
    "industry.world_capacity_wind",
    "industry.world_capacity_storage",
    "industry.factory_capital_cost",
    "industry.factory_build_time",
    "industry.factory_lifespan",
    "industry.credit_competitiveness",
    "industry.domestic_content_penalty",
    "jobs.fossil_per_ej",
    "jobs.clean_ops_per_ej",
    "jobs.construction_per_ej",
    "jobs.construction_max_share",
    "jobs.manufacturing_per_trillion",
    "jobs.smoothing",
    "jobs.workforce_share",
    "jobs.fossil_loss_weight",
    "jobs.approval_per_workforce",
    "jobs.retraining_max",
    "jobs.retraining_half_spend",
    "industrial_policy.electrification_max_bonus",
    "industrial_policy.electrification_half_spend",
    "elections.first_turn",
    "elections.interval",
    "elections.incumbency",
    "elections.growth_weight",
    "elections.jobs_weight",
    "elections.price_weight",
    "elections.tax_weight",
    "elections.swing_sd",
    "elections.threshold",
    "scoring.loss_score",
    "shocks.disaster_rate",
    "shocks.disaster_threshold",
    "shocks.disaster_gdp_loss",
    "shocks.disaster_capacity_loss",
    "shocks.disaster_approval_hit",
    "shocks.disruption_rate",
    "shocks.disruption_severity",
    "shocks.disruption_min_quarters",
    "shocks.disruption_extra_quarters",
    "shocks.disruption_cost_penalty",
    "ai.personalities.{personality}.research_utility",
    "ai.personalities.{personality}.w_growth",
    "ai.personalities.{personality}.w_security",
    "ai.personalities.{personality}.w_emissions",
    "ai.personalities.{personality}.w_trust",
    "ai.personalities.{personality}.w_deals",
    "ai.personalities.{personality}.target_adherence",
    "ai.personalities.{personality}.carbon_price_max",
    "ai.personalities.{personality}.follow_strength",
    "ai.personalities.{personality}.budget_appetite",
    "ai.build_shares",
    "ai.carbon_steps",
    "ai.retire_shares",
    "ai.subsidy_share",
    "ai.research_share",
    "ai.efficiency_share",
    "ai.adaptation_share",
    "ai.rebate_share",
    "ai.capital_cost_weight",
    "ai.pc_cost_weight",
    "ai.carbon_response",
    "ai.gap_scale",
    "ai.emissions_weight_floor",
    "ai.security_margin",
    "ai.min_utility",
    "ai.region_share",
    "ai.event_utility",
    "ai.event_follow_share",
    "ai.personalities.{personality}.event_propensity",
    "ai.region_affinity",
    "regions.intensity_decline",
    "regions.fossil_lifespan",
    "regions.clean_lifespan",
    "regions.absorb_share",
    "regions.absorb_years",
    "regions.cost_response",
    "regions.club_pull",
    "regions.spread",
    "regions.spread_retire",
    "regions.cost_premium",
    "regions.loan_rate",
    "regions.loan_years",
    "regions.trust_start",
    "regions.trust_per_trillion",
    "regions.trust_pull",
)
REQUIRED_SOURCE = {
    "all": (
        "build_time",
        "permitting_share",
        "lifespan",
        "capital_cost",
        "learning_rate",
        "global_installed",
    ),
    "fossil": ("variable_cost", "emission_factor", "headroom", "coverage_share"),
    "clean_dispatchable": ("variable_cost", "emission_factor", "headroom", "coverage_share"),
    "variable_renewable": ("variable_cost", "emission_factor", "headroom", "coverage_share"),
    "enabler": (),
    "removal": ("energy_use",),
}
REQUIRED_NATION = (
    "start.gdp",
    "start.population",
    "start.fx_reserves",
    "start.debt_hard",
    "start.debt_local",
    "start.carbon_price",
    "start.export_openness",
    "start.energy.{energy_source}",
    "start.production.{fuel}",
    "trend.g0_start",
    "trend.g0_end",
    "trend.population_growth",
    "trend.intensity_decline",
    "climate.vulnerability",
)


class ConfigError(ValueError):
    """Raised when a data file is malformed."""


@dataclass(frozen=True)
class Config:
    tuning: dict[str, Any]
    techs: dict[str, Any]
    countries: dict[str, Any]
    events: dict[str, Any]
    targets: dict[str, Any]
    research: dict[str, Any]
    regions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in FILES}

    @property
    def hash(self) -> str:
        """Digest of all loaded data, recorded with each run for replay."""
        return canonical.digest(self.to_dict())

    def value(self, section: str, dotted_path: str) -> Any:
        """Return the `value` of the tunable at `dotted_path` in `section`."""
        return _lookup(getattr(self, section), dotted_path, section)

    def tune(self, dotted_path: str) -> Any:
        return _lookup(self.tuning, dotted_path, "tuning")

    def src(self, source: str, key: str) -> Any:
        return _lookup(self.techs["sources"][source], key, f"techs.{source}")

    def nat(self, nation: str, dotted_path: str) -> Any:
        return _lookup(self.countries["nations"][nation], dotted_path, f"countries.{nation}")

    def target_level(self, nation: str, year: float) -> float:
        """Assumed target emissions at `year`, as a share of 2025 energy CO2: linear from 1.0 at
        the start year through the waypoints, flat after the last."""
        spec = self.targets["targets"][nation]
        points = [(self.tune("time.start_year"), 1.0)]
        points += list(zip(spec["years"]["value"], spec["levels"]["value"], strict=True))
        if year >= points[-1][0]:
            return points[-1][1]
        for (y0, l0), (y1, l1) in zip(points, points[1:], strict=False):
            if y0 <= year <= y1:
                return l0 + (l1 - l0) * (year - y0) / (y1 - y0)
        return 1.0

    def level(self, difficulty: str, key: str) -> Any:
        """A world-difficulty setting, e.g. level("hard", "net_zero_year")."""
        return _lookup(
            self.tuning["difficulty"]["levels"][difficulty], key, f"difficulty.{difficulty}"
        )

    def nat_spec(self, nation: str) -> dict[str, Any]:
        return self.countries["nations"][nation]

    @property
    def nation_ids(self) -> list[str]:
        return sorted(self.countries["nations"])

    @property
    def playable_ids(self) -> list[str]:
        return [i for i in self.nation_ids if self.countries["nations"][i]["playable"]]

    @property
    def source_ids(self) -> list[str]:
        return sorted(self.techs["sources"])

    def category(self, source: str) -> str:
        return self.techs["sources"][source]["category"]

    @property
    def energy_source_ids(self) -> list[str]:
        """Sources that deliver energy (everything except enablers and carbon removal)."""
        return [s for s in self.source_ids if self.category(s) not in ("enabler", "removal")]

    @property
    def vre_ids(self) -> list[str]:
        return [s for s in self.source_ids if self.category(s) == "variable_renewable"]

    # --- research (M12) ---------------------------------------------------------------------

    def requires(self, source: str) -> str | None:
        """The research technology a nation needs to build `source`, if any."""
        return self.techs["sources"][source].get("requires")

    @property
    def start_source_ids(self) -> list[str]:
        """Energy sources that exist in 2025 (no research needed)."""
        return [s for s in self.energy_source_ids if not self.requires(s)]

    def start_energy(self, nation: str, source: str) -> float:
        """2025 use of a source (EJ/yr); zero for sources that need research."""
        if self.requires(source):
            return 0.0
        return self.nat(nation, f"start.energy.{source}")

    @property
    def tech_ids(self) -> list[str]:
        return sorted(self.research["techs"])

    def rtech(self, tech: str) -> dict[str, Any]:
        return self.research["techs"][tech]

    # --- regions (M15) ----------------------------------------------------------------------

    @property
    def region_ids(self) -> list[str]:
        return sorted(self.regions["regions"])

    def reg(self, region: str, key: str) -> Any:
        return _lookup(self.regions["regions"][region], key, f"regions.{region}")


def _lookup(node: Any, dotted_path: str, where: str) -> Any:
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"{where}: no entry at '{dotted_path}'")
        node = node[part]
    if not _is_tunable(node):
        raise KeyError(f"{where}: '{dotted_path}' is not a tunable")
    return node["value"]


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
    _validate_techs(cfg)
    _validate_countries(cfg)
    _validate_tuning(cfg)
    _validate_targets(cfg)
    _validate_difficulty(cfg)
    _validate_research(cfg)
    _validate_regions(cfg)
    _validate_events(cfg)
    return cfg


EVENT_FIELDS = {
    "oil_discovery": ("weight", "target", "co2", "gdp_boost"),
    "rainforest": ("weight", "target", "co2"),
    "coal_pipeline": ("weight", "target", "energy"),
    "adaptation_appeal": ("weight", "target", "gdp_loss", "trust_bonus"),
}


def _validate_events(cfg: Config) -> None:
    """Minor-nation events (M15b): known types, their tunables, text and regions."""
    spec = cfg.events.get("events")
    if not isinstance(spec, dict):
        raise ConfigError("events.yaml: 'events' must be a mapping")
    _require(spec, ["rate", "first_turn", "max_open", "deadline", "leakage", "trust_hit"], "events")
    for kind, t in spec.get("types", {}).items():
        if kind not in EVENT_FIELDS:
            raise ConfigError(f"events.yaml: unknown event type {kind}")
        _require(t, list(EVENT_FIELDS[kind]), f"events.{kind}")
        if not isinstance(t.get("text"), str):
            raise ConfigError(f"events.yaml: {kind} needs a text")
        regions = t.get("regions")
        if not regions or any(r not in cfg.regions["regions"] for r in regions):
            raise ConfigError(f"events.yaml: {kind} lists unknown or no regions")


REGION_REQUIRED = (
    "gdp", "growth", "population", "co2", "fossil_ef", "clean", "fossil", "clean_additions",
    "fossil_production", "vulnerability",
)  # fmt: skip


def _validate_regions(cfg: Config) -> None:
    """The rest-of-world regions (M15) and the sources nations can finance there."""
    regions = cfg.regions.get("regions")
    if not isinstance(regions, dict) or not regions:
        raise ConfigError("regions.yaml: 'regions' must be a non-empty mapping")
    for rid, spec in regions.items():
        if rid in cfg.countries["nations"]:
            raise ConfigError(f"regions.yaml: {rid} is also a nation id")
        _require(spec, list(REGION_REQUIRED), f"regions.{rid}")
    for key in ("finance_sources", "cost_sources"):
        for source in cfg.tuning["regions"][key]:
            if source not in cfg.techs["sources"] or cfg.requires(source):
                raise ConfigError(f"tuning: regions.{key} has unknown or gated source {source}")


def _validate_research(cfg: Config) -> None:
    """The tech tree (M12): known prerequisites, effects on known sources, and every gated
    source unlocked by the technology it names."""
    techs = cfg.research.get("techs")
    if not isinstance(techs, dict) or not techs:
        raise ConfigError("research.yaml: 'techs' must be a non-empty mapping")
    _require(cfg.research, ["spillover"], "research")
    for tid, spec in techs.items():
        _require(spec, ["cost", "min_quarters"], f"research.{tid}")
        for pre in spec.get("requires", []):
            if pre not in techs:
                raise ConfigError(f"research.yaml: {tid} requires unknown technology {pre}")
        effects = spec.get("effects", {})
        for kind in ("cost", "build_time"):
            for source in effects.get(kind, {}):
                if source not in cfg.techs["sources"]:
                    raise ConfigError(f"research.yaml: {tid} affects unknown source {source}")
                _require(effects[kind], [source], f"research.{tid}.effects.{kind}")
        for source in spec.get("unlocks", []):
            if cfg.techs["sources"].get(source, {}).get("requires") != tid:
                raise ConfigError(
                    f"research.yaml: {tid} unlocks {source}, which must say requires: {tid}"
                )
    for sid, spec in cfg.techs["sources"].items():
        need = spec.get("requires")
        if need and sid not in techs.get(need, {}).get("unlocks", []):
            raise ConfigError(f"techs.yaml: {sid} requires {need}, which does not unlock it")


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
        value = node["value"]
        if isinstance(value, dict):
            raise ConfigError(f"{path}: tunable value cannot be a mapping")
        for v in value if isinstance(value, list) else [value]:
            if _is_number(v) and not math.isfinite(v):
                raise ConfigError(f"{path}: value must be finite")
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


def _expand(paths: tuple[str, ...], cfg: Config) -> list[str]:
    out = []
    for p in paths:
        if "{personality}" in p:
            out.extend(p.replace("{personality}", x) for x in sorted(PERSONALITIES))
        elif "{fuel}" in p:
            out.extend(p.replace("{fuel}", f) for f in FUELS)
        elif "{energy_source}" in p:
            out.extend(p.replace("{energy_source}", s) for s in cfg.start_source_ids)
        else:
            out.append(p)
    return out


def _require(node: Any, paths: list[str], where: str) -> None:
    for p in paths:
        try:
            _lookup(node, p, where)
        except KeyError as exc:
            raise ConfigError(str(exc)) from None


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
        keys = REQUIRED_SOURCE["all"] + REQUIRED_SOURCE[category]
        _require(spec, list(keys), f"techs.{sid}")
    for fuel in FUELS:
        if sources.get(fuel, {}).get("category") != "fossil":
            raise ConfigError(f"techs.yaml: fossil source '{fuel}' is required")


def _validate_countries(cfg: Config) -> None:
    nations = cfg.countries.get("nations")
    if not isinstance(nations, dict) or not nations:
        raise ConfigError("countries.yaml: 'nations' must be a non-empty mapping")
    required = _expand(REQUIRED_NATION, cfg)
    for nid, spec in nations.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"countries.yaml: {nid} must be a mapping")
        missing = [k for k in COUNTRY_REQUIRED if k not in spec]
        if missing:
            raise ConfigError(f"countries.yaml: {nid} missing {missing}")
        for flag in ("playable", "hard_currency_issuer"):
            if not isinstance(spec[flag], bool):
                raise ConfigError(f"countries.yaml: {nid}.{flag} must be true or false")
        personality = spec["personality"]
        if personality is not None and personality not in PERSONALITIES:
            raise ConfigError(f"countries.yaml: {nid}.personality '{personality}' is unknown")
        _require(spec, required, f"countries.{nid}")
        _validate_bau(cfg, nid, spec)


def _validate_bau(cfg: Config, nid: str, spec: dict[str, Any]) -> None:
    mix = spec.get("bau", {}).get("mix")
    if not isinstance(mix, dict) or not mix:
        raise ConfigError(f"countries.{nid}: bau.mix must be a non-empty mapping")
    for s in mix:
        if s not in cfg.energy_source_ids:
            raise ConfigError(f"countries.{nid}: bau.mix has unknown energy source '{s}'")
    total = sum(_lookup(mix, s, f"countries.{nid}.bau.mix") for s in mix)
    if abs(total - 1.0) > 1e-6:
        raise ConfigError(f"countries.{nid}: bau.mix shares sum to {total}, not 1")
    for s in spec["bau"].get("retire_rate", {}) or {}:
        if s not in cfg.source_ids:
            raise ConfigError(f"countries.{nid}: bau.retire_rate has unknown source '{s}'")


def _validate_tuning(cfg: Config) -> None:
    _require(cfg.tuning, _expand(REQUIRED_TUNING, cfg), "tuning")
    factors = cfg.tune("seasonality.demand_factor")
    if not isinstance(factors, list) or len(factors) != 4:
        raise ConfigError("tuning: seasonality.demand_factor must list four quarterly factors")


DIFFICULTIES = ("easy", "normal", "hard")


def _validate_difficulty(cfg: Config) -> None:
    spec = cfg.tuning.get("difficulty", {})
    if spec.get("default") not in DIFFICULTIES:
        raise ConfigError(f"tuning: difficulty.default must be one of {DIFFICULTIES}")
    for level in DIFFICULTIES:
        _require(
            spec.get("levels", {}).get(level, {}),
            ["net_zero_year", "disasters", "disruptions", "disruption_length", "damage"],
            f"tuning.difficulty.levels.{level}",
        )


def _validate_targets(cfg: Config) -> None:
    targets = cfg.targets.get("targets")
    if not isinstance(targets, dict):
        raise ConfigError("targets.yaml: 'targets' must be a mapping")
    start = cfg.tune("time.start_year")
    for nid in cfg.nation_ids:
        spec = targets.get(nid)
        if not isinstance(spec, dict):
            raise ConfigError(f"targets.yaml: no target path for {nid}")
        _require(spec, ["years", "levels"], f"targets.{nid}")
        years, levels = spec["years"]["value"], spec["levels"]["value"]
        if not isinstance(years, list) or not isinstance(levels, list) or not years:
            raise ConfigError(f"targets.{nid}: years and levels must be non-empty lists")
        if len(years) != len(levels):
            raise ConfigError(f"targets.{nid}: years and levels differ in length")
        if any(b <= a for a, b in zip([start, *years], years, strict=False)):
            raise ConfigError(f"targets.{nid}: years must rise and come after {start}")
        if any(v < 0 for v in levels):
            raise ConfigError(f"targets.{nid}: levels must be non-negative")
    for nid in targets:
        if nid not in cfg.nation_ids:
            raise ConfigError(f"targets.yaml: unknown nation '{nid}'")
