"""Named, seeded random streams.

All randomness in the simulation comes from here. Streams are stateless: each draw site asks for a
generator keyed by (master seed, stream name, keys...), e.g. `stream(seed, "shocks", t, "IND")`.
The generator's seed is a SHA-256 hash of those inputs, so:

- the same inputs always give the same numbers, on any machine and any Python run;
- adding a draw in one place never shifts the numbers drawn anywhere else;
- there is no RNG state to save, so resuming a saved world replays exactly.

AI nations must never call this module.
"""

from __future__ import annotations

import hashlib
import json
import random

STREAMS = frozenset({"events", "shocks", "elections", "deals", "supply"})


def derive_seed(master_seed: int, name: str, *keys: int | str) -> int:
    if name not in STREAMS:
        raise ValueError(f"unknown RNG stream '{name}'; register it in sim.rng.STREAMS")
    payload = json.dumps([master_seed, name, *keys], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def stream(master_seed: int, name: str, *keys: int | str) -> random.Random:
    """A fresh generator for one draw site."""
    return random.Random(derive_seed(master_seed, name, *keys))
