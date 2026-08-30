"""Block 1: turn the raw export into the cleaned core set.

    220  records in schematic.json
    -42  mechanical filler
     -5  '- Kombination' assembly wrappers
    ----
    173  core  ->  92 devices + 81 terminals in 8 strips  ->  100 checklist items

Nothing is dropped silently. Every removed record is counted, given a reason,
and written to data/dropped.csv so the drop is auditable rather than trusted.

Run:
    uv run python -m redlining.loader
    uv run python -m redlining.loader --verify    # also diff against the existing
                                                  # cleaned file, if there is one

WARNING -- FILLER_TERMS below is the one part of this file that is a guess.
This module was written from BLOCK_GUIDE's description of the filler parts, not
from the raw export. Run it, read data/dropped.csv, and confirm that all 42
dropped records really are blanking covers, wire ridges, spacers and insulators
-- and that nothing real went with them. Correct the terms here if not.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

RAW = Path("data/schematic.json")
OUT = Path("data/schematic.cleaned.json")
DROPPED = Path("data/dropped.csv")

# Gate values. From CONTEXT §6, with the part-number count corrected: the 37 in
# BLOCK_GUIDE was computed before filler removal and is wrong.
EXPECT_RAW = 220
EXPECT_CORE = 173
EXPECT_DEVICES = 92
EXPECT_TERMINALS = 81
EXPECT_STRIPS = 8
EXPECT_PART_NUMBERS = 31

STRIP_TAGS = ["-X1", "-X2", "-X3", "-X4", "-X5", "-X6", "-X7", "-X8"]

# Mechanical filler. Matched case-insensitively against `type` and `designation`.
FILLER_TERMS = [
    "blindabdeck",      # blanking cover
    "abdeckung",        # cover
    "blanking",
    "aderleiste",       # wire ridge
    "distanzstuck", "distanzstück",   # spacer
    "isolierstuck", "isolierstück",   # insulator
    "endkappe",         # end cap
    "trennwand",        # partition
    "beschriftung",     # labelling strip
]

WRAPPER_TERM = "kombination"


def norm(s) -> str:
    return (s or "").strip().lower()


def is_filler(rec: dict) -> str | None:
    haystack = f"{norm(rec.get('type'))} {norm(rec.get('designation'))}"
    for term in FILLER_TERMS:
        if term in haystack:
            return f"mechanical filler ({term})"
    return None


def is_wrapper(rec: dict) -> str | None:
    if WRAPPER_TERM in norm(rec.get("designation")) or \
       WRAPPER_TERM in norm(rec.get("type")):
        return "assembly wrapper ('- Kombination')"
    return None


def load_raw(path: Path) -> tuple[dict, list[dict]]:
    if not path.exists():
        sys.exit(f"{path} not found. Put the raw export in data/ first.")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    records = data["components"] if isinstance(data, dict) else data
    return (data if isinstance(data, dict) else {}), records


def clean(records: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    core, dropped = [], []

    for rec in records:
        # Wrapper first. BLOCK_GUIDE: -1Q2 and -1Q3 each appear twice, once as a
        # wrapper and once as the real device. Keep the one with a part number.
        reason = is_wrapper(rec)
        if reason is None and not norm(rec.get("order_reference")):
            reason = "empty part number"
        if reason is None:
            reason = is_filler(rec)

        (dropped.append((rec, reason)) if reason else core.append(rec))

    return core, dropped


def summarise(core: list[dict]) -> dict:
    strips = set(STRIP_TAGS)
    devices = [r for r in core if r["designation"] not in strips]
    terminals = [r for r in core if r["designation"] in strips]
    return {
        "core": len(core),
        "devices": len(devices),
        "unique_device_tags": len({r["designation"] for r in devices}),
        "terminals": len(terminals),
        "strips": len({r["designation"] for r in terminals}),
        "part_numbers": len({r["order_reference"] for r in core}),
        "device_types": len({r["type"] for r in devices}),
        "checklist_items": len({r["designation"] for r in devices}) + len(
            {r["designation"] for r in terminals}),
    }


def write_dropped(dropped: list[tuple[dict, str]], path: Path = DROPPED) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["reason", "component_id", "designation", "type",
                    "order_reference", "location"])
        for rec, reason in dropped:
            w.writerow([reason, rec.get("component_id", ""),
                        rec.get("designation", ""), rec.get("type", ""),
                        rec.get("order_reference", ""), rec.get("location", "")])


def check_gate(raw_n: int, core: list[dict], dropped: list) -> list[str]:
    s = summarise(core)
    problems = []
    for name, got, want in [
        ("raw records", raw_n, EXPECT_RAW),
        ("core records", s["core"], EXPECT_CORE),
        ("devices", s["devices"], EXPECT_DEVICES),
        ("unique device tags", s["unique_device_tags"], EXPECT_DEVICES),
        ("terminals", s["terminals"], EXPECT_TERMINALS),
        ("strips", s["strips"], EXPECT_STRIPS),
        ("part numbers", s["part_numbers"], EXPECT_PART_NUMBERS),
        ("checklist items", s["checklist_items"], 100),
    ]:
        if got != want:
            problems.append(f"{name}: expected {want}, got {got}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--verify", action="store_true",
                    help="diff against the existing cleaned file")
    ap.add_argument("--force", action="store_true",
                    help="write the output even if the gate fails")
    args = ap.parse_args()

    meta, records = load_raw(args.raw)
    core, dropped = clean(records)
    write_dropped(dropped)

    print(f"{len(records)} raw records")
    for reason, n in Counter(r for _, r in dropped).most_common():
        print(f"  -{n:3d}  {reason}")
    print(f"  ----")
    s = summarise(core)
    for k, v in s.items():
        print(f"  {v:5d}  {k}")
    print(f"\ndrop log: {DROPPED}  -- read it. Confirm nothing real is in there.")

    problems = check_gate(len(records), core, dropped)
    if problems:
        print("\nGATE FAILED:")
        for p in problems:
            print(f"  {p}")
        print("\nFILLER_TERMS at the top of this file is the likely cause. "
              "Do not adjust the expected numbers to fit the code.")
        if not args.force:
            sys.exit(1)
    else:
        print("\nGate: all counts as expected.")

    payload = {
        "project_number": meta.get("project_number", ""),
        "total_components": len(core),
        "components": core,
    }
    args.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    print(f"wrote {args.out}")

    if args.verify and args.out.exists():
        prior = json.loads(args.out.read_text(encoding="utf-8"))
        a = {r["component_id"] for r in prior["components"]}
        b = {r["component_id"] for r in core}
        if a == b:
            print("verify: identical to the previous cleaned file.")
        else:
            print(f"verify: DIFFERS -- {len(a - b)} only in old, "
                  f"{len(b - a)} only in new")


if __name__ == "__main__":
    main()
