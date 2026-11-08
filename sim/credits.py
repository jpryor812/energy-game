"""The carbon credit market.

Supply: each quarter, a nation earns credits (MtCO2) for emissions below the 1.5 degC pathway
applied to its own 2025 emissions, the same yardstick the stocktake uses.
Demand: nations buy credits to cover overshoot at the next stocktake (surrendered automatically)
and to score (`credits.weight_purchased` per tonne, less than real reductions).

Each quarter's buy and sell orders clear in one uniform-price call auction: buys sorted from the
highest limit, sells from the lowest, matched while the buyer's limit covers the seller's; the
price is the midpoint of the last matched pair. With orders on one side only, the price drifts
toward that side by `credits.drift`. Deterministic; ties break by nation id. A nation may
only buy or only sell in a quarter (sim.actions enforces this).

Units: amounts in MtCO2, prices in $/tCO2, money in T$ (1 Mt x $1/t = 1e-6 T$).
"""

from __future__ import annotations

from typing import Any

from sim.config import Config
from sim.state import World

T_DOLLARS_PER_MT_DOLLAR = 1e-6


def cost(amount: float, price: float) -> float:
    return amount * price * T_DOLLARS_PER_MT_DOLLAR


def issue(cfg: Config, world: World, dt: int) -> float:
    """Credit each nation's emissions below the 1.5 degC pathway this step; return the total."""
    from sim.diplomacy import pathway_level

    year = cfg.tune("time.start_year") + world.t / 4
    level = pathway_level(cfg, year, world.difficulty)
    total = 0.0
    for nid in sorted(world.nations):
        n = world.nations[nid]
        earned = max(0.0, level * n.base["emissions"] - n.emissions) * dt / 4
        n.credit_balance += earned
        total += earned
    return total


def clear(cfg: Config, world: World) -> dict[str, Any]:
    """Match this quarter's orders, move credits and money, set the price; return a log."""
    buys = sorted(
        (o for o in world.credit_orders if o["side"] == "buy"),
        key=lambda o: (-o["limit"], o["nation"]),
    )
    sells = sorted(
        (o for o in world.credit_orders if o["side"] == "sell"),
        key=lambda o: (o["limit"], o["nation"]),
    )
    remaining = {id(o): o["amount"] for o in buys + sells}
    matches = []
    bi = si = 0
    while bi < len(buys) and si < len(sells):
        b, s = buys[bi], sells[si]
        if b["limit"] < s["limit"]:
            break
        qty = min(remaining[id(b)], remaining[id(s)])
        matches.append((b, s, qty))
        remaining[id(b)] -= qty
        remaining[id(s)] -= qty
        if remaining[id(b)] <= 1e-12:
            bi += 1
        if remaining[id(s)] <= 1e-12:
            si += 1
    floor = cfg.tune("credits.min_price")
    if matches:
        last_b, last_s, _ = matches[-1]
        price = max(floor, (last_b["limit"] + last_s["limit"]) / 2)
        for b, s, qty in matches:
            buyer, seller = world.nations[b["nation"]], world.nations[s["nation"]]
            qty = min(qty, seller.credit_balance, buyer.capital / max(price * 1e-6, 1e-18))
            if qty <= 0:
                continue
            seller.credit_balance -= qty
            buyer.credit_balance += qty
            buyer.credits_bought += qty
            buyer.capital -= cost(qty, price)
            seller.capital += cost(qty, price)
        world.credit_price = price
    elif buys and not sells:
        world.credit_price *= 1 + cfg.tune("credits.drift")
    elif sells and not buys:
        world.credit_price = max(floor, world.credit_price * (1 - cfg.tune("credits.drift")))
    log = {
        "price": world.credit_price,
        "traded": sum(q for _, _, q in matches),
        "orders": len(world.credit_orders),
    }
    world.credit_orders = []
    return log
