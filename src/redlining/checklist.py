"""Block 3 (code half): join the walking order with the advisor's bands.

- Positions (data/walking_order.csv) come from Block 2 and can be regenerated.
- Bands (data/bands.csv) are advisor decisions -- never regenerated.
- Items are sorted band first, then physical position within the band.
- An item with no band is a hard failure, never silently defaulted to 4.
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
    """One checklist entry: something the trainee is sent to read.

    Attributes:
        tag: Device or strip tag, e.g. "-8F7" or "-X4".
        kind: "device" or "strip".
        detail: Device type, or e.g. "6 terminals" for a strip.
        spoken: Location-only prompt the trainee hears.
        frame: Frame name, e.g. "left frame".
        row: Rail row within the frame (1 = top).
        position: Position along the row, left to right.
        band: Priority band from bands.csv (lower = earlier).
    """
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
        """Sort key for physical walking order.

        Returns:
            (frame_rank, row, position). Unknown frames sort last.
        """
        try:
            frame_rank = FRAME_ORDER.index(self.frame)
        except ValueError:
            frame_rank = len(FRAME_ORDER)
        return (frame_rank, self.row, self.position)


def load_bands(path: Path = BANDS) -> dict[str, int]:
    """Load the advisor's bands from bands.csv.

    Device rows are keyed by type, strip rows by tag.

    Args:
        path: bands.csv location.

    Returns:
        Dict key -> band number.

    Raises:
        SystemExit: If the file is missing or any row has no band.
    """
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
    """Build the ordered checklist: walking order joined with bands.

    Args:
        walking: walking_order.csv from Block 2.
        bands_path: bands.csv from the advisor session.

    Returns:
        Items sorted by band, then walking order.

    Raises:
        SystemExit: If any item has no band (never defaulted).
    """
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
