"""One-off (M11): split wind and other renewables in data/countries.yaml in place, using the
shares in source_splits.py. build_countries.py applies the same split when regenerating."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_splits import NOTE, SPLITS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "countries.yaml"
LINE = re.compile(
    r"^(?P<ind>\s+)(?P<key>wind|other_renewables): \{value: (?P<v>[-0-9.e]+), (?P<rest>.*)\}$"
)


def main() -> None:
    nation = section = None
    out = []
    for line in PATH.read_text().splitlines():
        m = re.match(r"^  ([A-Z]{3}):$", line)
        if m:
            nation = m.group(1)
        s = re.match(r"^\s+(energy|mix|manufacturing_share|production|retire_rate):$", line)
        if s:
            section = s.group(1)
        m = LINE.match(line)
        if not m or section not in ("energy", "mix"):
            out.append(line)
            continue
        old, value = m.group("key"), float(m.group("v"))
        (first, second), shares, what = SPLITS[old]
        share = shares.get(nation, 0.0)
        extra = " " + NOTE.format(old=old, share=share, what=what)
        rest = re.sub(r'note: "([^"]*)"', 'note: "\\1' + extra + '"', m.group("rest"))
        for new, v in ((first, value * (1 - share)), (second, value * share)):
            if section == "mix" and v <= 0:
                continue
            digits = 4 if section == "mix" else 6
            out.append(f"{m.group('ind')}{new}: {{value: {round(v, digits)}, {rest}}}")
    PATH.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
