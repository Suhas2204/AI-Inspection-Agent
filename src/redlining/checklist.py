"""Block 3 (code half): join the walking order with the advisor's bands.

Positions come from Block 2 and are regenerated freely. Bands come from the
advisor session and are NOT regenerated -- they are decisions, keyed by type.
This module joins them and sorts band first, physical position within band.

An item with no band is a hard failure. It is never defaulted to 4: a silent
default would put an unreviewed device at the bottom of the walk, and nobody
would ever notice.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

WALKING_ORDER = Path("data/walking_order.csv")
BANDS = Path("data/bands.csv")

FRAME_ORDER = ["left frame", "left side panel", "right frame",
               "right side panel", "no location in file"]


@dataclass(frozen=True)
class Item:
    tag: str
    kind: str            # 'device' | 'strip'
    detail: str          # device type, or '6 terminals'
    spoken: str          # what the trainee hears -- location only
    frame: str
    row: int
    position: int
    band: int

    @property
    def walk_key(self):
        try:
            frame_rank = FRAME_ORDER.index(self.frame)
        except ValueError:
            frame_rank = len(FRAME_ORDER)
        return (frame_rank, self.row, self.position)


def load_bands(path: Path = BANDS) -> dict[str, int]:
    """key -> band. Device rows key on type, strip rows key on tag."""
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Block 3 is not done: generate the 29 rows, "
            "then band them with your advisor."
        )
    bands, unbanded = {}, []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw = (row.get("band") or "").strip()
            if not raw:
                unbanded.append(row["key"])
                continue
            bands[row["key"]] = int(raw)
    if unbanded:
        raise SystemExit(
            f"{len(unbanded)} of the 29 rows carry no band: "
            f"{', '.join(unbanded[:5])}{' ...' if len(unbanded) > 5 else ''}\n"
            "Block 3's gate is not passed. Band them with your advisor first."
        )
    return bands


def load_checklist(walking: Path = WALKING_ORDER,
                   bands_path: Path = BANDS) -> list[Item]:
    bands = load_bands(bands_path)
    items, missing = [], []

    with open(walking, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["tag"] if row["kind"] == "strip" else row["detail"]
            if key not in bands:
                missing.append(f"{row['tag']} ({key})")
                continue
            items.append(Item(
                tag=row["tag"],
                kind=row["kind"],
                detail=row["detail"],
                spoken=row["spoken"],
                frame=row["frame"],
                row=int(row["row"]),
                position=int(row["position"]),
                band=bands[key],
            ))

    if missing:
        raise SystemExit(
            f"{len(missing)} item(s) have no band in {bands_path}: "
            f"{', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}\n"
            "A new type appeared, or bands.csv is stale. Do not default these."
        )

    # Band first, then walk order within the band.
    items.sort(key=lambda i: (i.band, i.walk_key))
    return items


if __name__ == "__main__":
    from collections import Counter
    items = load_checklist()
    print(f"{len(items)} checklist items")
    print("per band:", dict(sorted(Counter(i.band for i in items).items())))
    for i in items[:5]:
        print(f"  band {i.band}  {i.tag:8} {i.spoken}")
