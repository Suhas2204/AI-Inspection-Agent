"""Block 3, step 1: emit the 29 rows the advisor session ranks.

- 21 device types + 8 terminal strips = 29 rows.
- The band column is left empty on purpose: a human fills it in the advisor
  session. This script never guesses it.
- Reads data/processed/schematic.cleaned.json, writes data/decisions/bands.csv.
- Refuses to overwrite an existing bands.csv (it holds decisions).

Run:
    uv run python -m redlining.make_bands
"""

import csv
import json
import sys
from collections import Counter

from .paths import BANDS, SCHEMATIC

SRC = SCHEMATIC
OUT = BANDS

STRIP_TAGS = ["-X1", "-X2", "-X3", "-X4", "-X5", "-X6", "-X7", "-X8"]

EXPECTED_DEVICES = 92
EXPECTED_TERMINALS = 81
EXPECTED_DEVICE_TYPES = 21


def load(path):
    """Load the component records from a cleaned schematic export.

    Args:
        path: Cleaned JSON file.

    Returns:
        List of component records.
    """
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["components"]


def main():
    """Check the counts, then write bands.csv with an empty band column.

    Exits without writing if bands.csv already exists or the counts disagree
    with CONTEXT §6.
    """
    if OUT.exists():
        sys.exit(
            f"{OUT} already exists and holds advisor decisions. "
            "Delete it deliberately if you really mean to start over."
        )

    records = load(SRC)
    strips = set(STRIP_TAGS)
    devices = [r for r in records if r["designation"] not in strips]
    terminals = [r for r in records if r["designation"] in strips]

    # Gate checks. A surprise here is a finding, not something to code around.
    problems = []
    if len(devices) != EXPECTED_DEVICES:
        problems.append(f"devices: expected {EXPECTED_DEVICES}, got {len(devices)}")
    if len(terminals) != EXPECTED_TERMINALS:
        problems.append(f"terminals: expected {EXPECTED_TERMINALS}, got {len(terminals)}")
    if len({r["designation"] for r in devices}) != EXPECTED_DEVICES:
        problems.append("device tags are not unique — check the strip tag list")

    device_types = Counter(r["type"] for r in devices)
    if len(device_types) != EXPECTED_DEVICE_TYPES:
        problems.append(
            f"device types: expected {EXPECTED_DEVICE_TYPES}, got {len(device_types)}"
        )

    if problems:
        for p in problems:
            print("MISMATCH:", p, file=sys.stderr)
        sys.exit("Counts disagree with CONTEXT §6. Stop and reconcile before banding.")

    rows = []
    for type_name, count in sorted(device_types.items(), key=lambda kv: (-kv[1], kv[0])):
        refs = sorted({r["order_reference"] for r in devices if r["type"] == type_name})
        rows.append(
            {
                "row_kind": "device_type",
                "key": type_name,
                "order_reference": " | ".join(refs),
                "n_components": count,
                "band": "",
                "banded_by": "",
                "banded_on": "",
                "note": "",
            }
        )

    for tag in STRIP_TAGS:
        members = [r for r in terminals if r["designation"] == tag]
        kinds = Counter(r["type"] for r in members)
        rows.append(
            {
                "row_kind": "terminal_strip",
                "key": tag,
                "order_reference": "",
                "n_components": len(members),
                "band": "",
                "banded_by": "",
                "banded_on": "",
                "note": "; ".join(f"{k}×{n}" for k, n in kinds.most_common()),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    covered = sum(r["n_components"] for r in rows)
    print(f"{OUT}: {len(rows)} rows ({len(device_types)} device types + {len(STRIP_TAGS)} strips)")
    print(f"covering {covered} components — {len(devices)} devices + {len(terminals)} terminals")
    print("band column is empty. Fill it in the advisor session, not here.")


if __name__ == "__main__":
    main()
