"""Energy jobs and how their changes move approval.

Jobs (millions) in four groups:

- fossil: fossil-fuel supply, proportional to fossil production (IEA World Energy Employment
  2025: 18.4 million fossil supply jobs in 2024);
- clean_ops: running non-fossil plants, proportional to non-fossil supply;
- construction: building any energy capacity, proportional to capacity completed per year;
- manufacturing: clean-tech factories, proportional to factory sales.

Each step, the change in jobs moves approval: fossil losses count `fossil_loss_weight` times
more (they are concentrated in particular regions), softened by the nation's retraining stock.
Elections (sim.elections) use the same weighted job change over a whole term.
"""

from __future__ import annotations

from sim import energy
from sim.config import FUELS, Config
from sim.state import Nation, World


def _j(cfg: Config, name: str) -> float:
    return cfg.tune(f"jobs.{name}")


def count(cfg: Config, n: Nation) -> dict[str, float]:
    clean_supply = sum(v for s, v in n.supply.items() if not energy.is_fossil(cfg, s))
    return {
        "fossil": _j(cfg, "fossil_per_ej") * sum(n.fossil_production.get(f, 0.0) for f in FUELS),
        "clean_ops": _j(cfg, "clean_ops_per_ej") * clean_supply,
        "construction": _j(cfg, "construction_per_ej") * n.build_rate,
        "manufacturing": _j(cfg, "manufacturing_per_trillion") * sum(n.factory_sales.values()),
    }


def retraining_relief(cfg: Config, n: Nation) -> float:
    """Share of the fossil-loss penalty retraining removes."""
    if n.retraining <= 0:
        return 0.0
    half = _j(cfg, "retraining_half_spend") * n.gdp
    return _j(cfg, "retraining_max") * n.retraining / (n.retraining + half)


def weighted_change(
    cfg: Config, n: Nation, before: dict[str, float], after: dict[str, float]
) -> float:
    """Job change as a share of the workforce, with fossil losses weighted up (and softened by
    retraining)."""
    workforce = _j(cfg, "workforce_share") * n.population
    fossil = after.get("fossil", 0.0) - before.get("fossil", 0.0)
    if fossil < 0:
        fossil *= _j(cfg, "fossil_loss_weight") * (1 - retraining_relief(cfg, n))
    others = sum(after.get(k, 0.0) - before.get(k, 0.0) for k in after if k != "fossil")
    return (fossil + others) / workforce if workforce > 0 else 0.0


def apply(world: World, cfg: Config) -> None:
    """Recount jobs and move approval by the weighted change since last step."""
    for nid in sorted(world.nations):
        n = world.nations[nid]
        now = count(cfg, n)
        if n.jobs:
            change = weighted_change(cfg, n, n.jobs, now)
            n.approval = min(1.0, max(0.0, n.approval + _j(cfg, "approval_per_workforce") * change))
        n.jobs = now
