"""Canonical JSON encoding and hashing.

Every byte the simulation writes goes through here, so identical states always produce identical
bytes. NaN and infinity are rejected outright.
"""

import hashlib
import json
from typing import Any


def dumps(obj: Any, *, indent: int | None = None) -> str:
    """Encode `obj` as JSON with sorted keys; compact unless `indent` is given."""
    separators = (",", ":") if indent is None else (",", ": ")
    return json.dumps(obj, sort_keys=True, separators=separators, indent=indent, allow_nan=False)


def digest(obj: Any) -> str:
    """SHA-256 hex digest of the compact canonical encoding of `obj`."""
    return hashlib.sha256(dumps(obj).encode("utf-8")).hexdigest()
