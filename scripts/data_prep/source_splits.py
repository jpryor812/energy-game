"""Split shares for M11: wind -> onshore and offshore; other renewables -> bioenergy and
geothermal. Used by build_countries.py (and by split_sources_m11.py, which applied the split
once to the existing data/countries.yaml).

The Energy Institute / OWID data gives wind as one figure and geothermal inside a residual with
bioenergy. These shares are UNSOURCED APPROXIMATE values for 2024, entered by hand:

- Offshore share of wind generation: rough installed offshore capacity (GWEC/IRENA order of
  magnitude) with offshore's higher capacity factor. To be checked against Ember or IRENA
  country data.
- Geothermal share of "other renewables": approximate 2024 geothermal generation (TWh) x 0.009
  EJ per TWh (substitution method) over the nation's other-renewables primary energy. To be
  checked against IRENA or Ember.

Nations not listed have no offshore wind and no geothermal.
"""

from __future__ import annotations

OFFSHORE_SHARE = {
    "CHN": 0.10,
    "EUU": 0.13,
    "GBR": 0.55,
    "JPN": 0.03,
    "VNM": 0.12,  # near-shore (intertidal) wind counted as offshore
}
GEOTHERMAL_SHARE = {
    "USA": 0.044,
    "IDN": 0.17,
    "MEX": 0.36,
    "JPN": 0.04,
    "EUU": 0.019,
    "RUS": 0.02,
}
WORLD = {"offshore": 0.09, "geothermal": 0.046}

SPLITS = {
    "wind": (("onshore_wind", "offshore_wind"), OFFSHORE_SHARE, "offshore"),
    "other_renewables": (("bioenergy", "geothermal"), GEOTHERMAL_SHARE, "geothermal"),
}

NOTE = (
    "M11 split of the Energy Institute {old} figure: {share:.3g} {what} share (unsourced "
    "approximate, scripts/data_prep/source_splits.py)."
)


def split(nid: str | None, values: dict[str, float]) -> dict[str, float]:
    """Replace `wind` and `other_renewables` with their two parts. `nid` None uses world shares."""
    out = dict(values)
    for old, ((first, second), shares, key) in SPLITS.items():
        if old not in out:
            continue
        total = out.pop(old)
        share = WORLD[key] if nid is None else shares.get(nid, 0.0)
        out[first] = total * (1 - share)
        out[second] = total * share
    return out


def share(nid: str, new: str) -> tuple[str, float, str] | None:
    """(old source, share of it that `new` takes, what the share is) for a split source."""
    for old, ((first, second), shares, key) in SPLITS.items():
        if new in (first, second):
            s = shares.get(nid, 0.0)
            return old, (s if new == second else 1 - s), key
    return None
