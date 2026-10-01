"""Block 9: score one run against the planted faults.

    uv run python -m redlining.score runs/20260922-101500
    uv run python -m redlining.score runs/20260922-101500 --latex

Reads the run's report.json and data/decisions/faults.csv. Writes nothing:
a scorer that can alter a run is a scorer an examiner cannot trust.

Definitions, fixed here so the thesis and the code cannot disagree:

  planted     a row in faults.csv with detectable == yes. The denominator.
  known miss  detectable == no. Tag-only reading is blind to a wrong
              part under a correct label (CONTEXT s9), so these enter
              neither metric: not the denominator, and not the false
              flags either. A flag at one is reported on its own line.
  swap        a row carrying an optional item_b: one label-swap fault
              planted across two positions. One row, one place in the
              denominator, however many positions it occupies.
  caught      the run raised a flag at a planted position. A flag at
              either end of a swap catches it: finding one end is
              finding the swap.
  missed      the run walked every position of a planted fault and
              flagged none of them.
  not walked  a position was never reached, so the row cannot be scored
              either way. For a swap: one end unreached, the other
              walked and unflagged.
  false flag  a flag at a position carrying no planted fault at all.
              Neither end of a swap and no known-miss position can be
              a false flag: something was planted there, and charging
              the run for finding it would understate precision.
  precision   caught / (caught + false flags). Metric 1.

Precision here is provisional: a flag at an unplanted item is counted
false, but the walker may simply have misread a correct label. Only
replaying the audio settles that, so the adjudicated column stays blank
until a human fills faults.csv's `found` and the flag annotations.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DETECTABLE_YES = "yes"
BANDS = (1, 2, 3)


def load_run(run_dir: Path) -> dict:
    """Load one run's report.json.

    Args:
        run_dir: A run folder, e.g. runs/20260927-130613.

    Returns:
        The parsed report.

    Raises:
        SystemExit: The folder holds no report.json, so there is no run to
            score and guessing at one would be worse than stopping.
    """
    report = run_dir / "report.json"
    if not report.exists():
        raise SystemExit(f"no report.json in {run_dir}")
    return json.loads(report.read_text(encoding="utf-8"))


def load_faults(path: Path) -> list[dict]:
    """Load the planted fault set, refusing anything it cannot score.

    Args:
        path: faults.csv, as written by select_faults.

    Returns:
        One dict per fault row, in file order.

    Raises:
        SystemExit: The file is absent, empty, or lacks the `item` or
            `detectable` column. Each would silently empty the denominator,
            which reads as a perfect score rather than as a broken input.
    """
    if not path.exists():
        raise SystemExit(
            f"no faults file at {path}. Block 9 has not been planted yet; "
            "there is nothing to score."
        )
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} is empty")
    missing = {"item", "detectable"} - set(rows[0])
    if missing:
        raise SystemExit(f"{path} lacks column(s): {', '.join(sorted(missing))}")
    return rows


def positions(fault: dict) -> list[str]:
    """The positions a fault occupies: one, or two for a label swap.

    Args:
        fault: One row of faults.csv. item_b is optional; blank, absent, or
            equal to item means a single-position fault.

    Returns:
        The tags the fault was planted at, in card order.
    """
    first = fault["item"].strip()
    second = (fault.get("item_b") or "").strip()
    return [first, second] if second and second != first else [first]


def scoring_position(fault: dict, final: dict[str, dict]) -> str:
    """The position a row is scored at: the flagged end, else a walked one.

    A swap is one fault at two positions, so its band and its verdict are
    taken from the end that caught it. Finding one end is finding the swap.

    Args:
        fault: One row of faults.csv.
        final: Verdict per item, from flagged_items().

    Returns:
        The tag this row is scored at. Falls back to the first position when
        neither end was walked.
    """
    pos = positions(fault)
    for p in pos:
        if p in final and final[p].get("flagged"):
            return p
    return next((p for p in pos if p in final), pos[0])


def band_of(fault: dict, final: dict[str, dict]) -> str | None:
    """The priority band a fault row is credited to.

    Args:
        fault: One row of faults.csv.
        final: Verdict per item, from flagged_items().

    Returns:
        The band as a string, or None if the row was never walked and so
        belongs to no band's tally.
    """
    a = final.get(scoring_position(fault, final))
    return None if a is None else str(a.get("band"))


def flagged_items(report: dict) -> dict[str, dict]:
    """Final verdict per item. The last attempt is the one that stands.

    Args:
        report: A run's parsed report.json.

    Returns:
        Item tag -> the attempt whose verdict stands.
    """
    final: dict[str, dict] = {}
    for a in report.get("items", []):
        prev = final.get(a["item"])
        if prev is None or a["attempt_no"] >= prev["attempt_no"]:
            final[a["item"]] = a
    return final


def score(report: dict, faults: list[dict]) -> dict:
    """Score one run against the planted faults. Writes nothing.

    The definitions are the ones fixed in the module docstring: planted,
    caught, missed, not walked, false flag and known miss. They live here so
    the thesis and the code cannot disagree about them.

    Args:
        report: A run's parsed report.json.
        faults: Rows from faults.csv.

    Returns:
        Every metric plus the rows behind it, so a reader can check any
        number by looking at what it was computed from.
    """
    final = flagged_items(report)
    walked = set(final)

    planted = [f for f in faults if f["detectable"].strip().lower() == DETECTABLE_YES]
    known_miss = [f for f in faults if f["detectable"].strip().lower() != DETECTABLE_YES]
    # Every position of every planted fault, so that neither end of a
    # swap can be charged as a false flag.
    planted_positions = {p for f in planted for p in positions(f)}

    caught, missed, not_walked = [], [], []
    for f in planted:
        pos = positions(f)
        if any(p in walked and final[p].get("flagged") for p in pos):
            caught.append(f)            # one flag catches the whole row
        elif all(p in walked for p in pos):
            missed.append(f)
        else:
            not_walked.append(f)        # an unreached end is not a miss

    # A flag is false only where nothing at all was planted. Known-miss
    # positions are carried by the study, so they are out of this set as
    # well as out of the denominator.
    known_miss_positions = {p for f in known_miss for p in positions(f)}
    false_flags = [
        a for item, a in final.items()
        if a.get("flagged") and item not in planted_positions | known_miss_positions
    ]

    denom = len(caught) + len(missed)
    n_flags = len(caught) + len(false_flags)

    per_band = {}
    for b in BANDS:
        c = sum(1 for f in caught if band_of(f, final) == str(b))
        m = sum(1 for f in missed if band_of(f, final) == str(b))
        per_band[b] = {"caught": c, "missed": m,
                       "rate": c / (c + m) if (c + m) else None}

    known_miss_flagged = [
        f for f in known_miss
        if any(p in walked and final[p].get("flagged") for p in positions(f))
    ]

    return {
        "run_id": report.get("run_id"),
        "items_walked": len(walked),
        "items_expected": report.get("items_expected"),
        "complete": report.get("complete"),
        "duration_s": report.get("duration_s"),
        "abstain_rate": report.get("abstain_rate"),
        "abstain_ceiling": report.get("abstain_ceiling"),
        "planted": len(planted),
        "swaps": sum(1 for f in planted if len(positions(f)) > 1),
        "caught": len(caught),
        "missed": len(missed),
        "not_walked": len(not_walked),
        "detection_rate": len(caught) / denom if denom else None,
        "false_flags": len(false_flags),
        "precision": len(caught) / n_flags if n_flags else None,
        "per_band": per_band,
        "known_miss": len(known_miss),
        "known_miss_flagged": len(known_miss_flagged),
        "known_miss_flag_rows": known_miss_flagged,
        "caught_rows": caught,
        "missed_rows": missed,
        "not_walked_rows": not_walked,
        "false_flag_rows": false_flags,
    }


def pct(x) -> str:
    """Format a ratio as a whole-number percentage.

    Args:
        x: Ratio in 0..1, or None where the metric is undefined.

    Returns:
        e.g. "80%", or "n/a". A rate with an empty denominator prints as
        "n/a" rather than as 0%, which would read as a measured failure.
    """
    return "n/a" if x is None else f"{x * 100:.0f}%"


def label(fault: dict) -> str:
    """How a row prints: both ends of a swap, so a reader can find them.

    Args:
        fault: One row of faults.csv.

    Returns:
        The positions joined with "<->", e.g. "-8F7<->-8F8".
    """
    return "<->".join(positions(fault))


def report_text(s: dict) -> str:
    """Render the scorer's reading for a human.

    Lists every row a reviewer has to act on: known-miss flags, planted rows
    never walked, misses, and the false flags to replay before reporting.

    Args:
        s: The dict returned by score().

    Returns:
        The report, ready to print.
    """
    L = [
        f"Run {s['run_id']} - {s['items_walked']} of {s['items_expected']} items"
        f"{'' if s['complete'] else ' (INCOMPLETE)'}",
        "",
        "Metric 2 - fault detection",
        f"  planted (detectable) : {s['planted']}"
        + (f"  ({s['swaps']} label swap(s), each counted once)"
           if s["swaps"] else ""),
        f"  caught               : {s['caught']}",
        f"  missed               : {s['missed']}",
        f"  not walked           : {s['not_walked']}",
        f"  detection rate       : {pct(s['detection_rate'])}",
        "",
        "Metric 1 - redline precision (provisional, see module docstring)",
        f"  false flags          : {s['false_flags']}",
        f"  precision            : {pct(s['precision'])}",
        "",
        "Metric 3 - abstention",
        f"  abstain rate         : {pct(s['abstain_rate'])}"
        f"  (ceiling {pct(s['abstain_ceiling'])})",
        "",
        "By band",
    ]
    for b, v in s["per_band"].items():
        L.append(f"  band {b}: {v['caught']} caught, {v['missed']} missed"
                 f"  ({pct(v['rate'])})")
    L += [
        "",
        f"Known misses carried: {s['known_miss']} "
        f"(excluded from the denominator by design)",
    ]
    if s["known_miss_flagged"]:
        L.append("")
        L.append("Flagged at a known-miss position - counted in neither metric:")
        for f in s["known_miss_flag_rows"]:
            L.append(f"  {label(f):<12} {f.get('fault_class', '')}")
        L.append("  Read the audio before claiming a detection: tag-only "
                 "reading is blind here, so a flag is most likely an "
                 "unrelated misread.")
    if s["not_walked_rows"]:
        L.append("")
        L.append("Planted but not walked - the run is not scorable as it stands:")
        for f in s["not_walked_rows"]:
            L.append(f"  {label(f)}  {f.get('fault_class', '')}")
    if s["missed_rows"]:
        L.append("")
        L.append("Missed:")
        for f in s["missed_rows"]:
            L.append(f"  {label(f):<12} {f.get('fault_class', '')}")
    if s["false_flag_rows"]:
        L.append("")
        L.append("False flags - replay each before reporting:")
        for a in s["false_flag_rows"]:
            L.append(f"  {a['item']:<8} {a['outcome']:<10} {a.get('audio_path', '')}")
    return "\n".join(L)


def latex(s: dict) -> str:
    """Render the headline metrics as a LaTeX tabular for the thesis.

    Args:
        s: The dict returned by score().

    Returns:
        A tabular environment, to be wrapped in a table and captioned.
    """
    rows = [
        ("Items walked", f"{s['items_walked']} / {s['items_expected']}"),
        ("Planted faults (detectable)", str(s["planted"])),
        ("Caught", str(s["caught"])),
        ("Missed", str(s["missed"])),
        ("Detection rate", pct(s["detection_rate"])),
        ("False flags", str(s["false_flags"])),
        ("Redline precision", pct(s["precision"])),
        ("Abstention rate", pct(s["abstain_rate"])),
        ("Known misses (excluded)", str(s["known_miss"])),
    ]
    body = " \\\\\n".join(f"{k} & {v}" for k, v in rows)
    return (
        "\\begin{tabular}{lr}\n\\hline\n"
        f"{body} \\\\\n"
        "\\hline\n\\end{tabular}"
    )


def main() -> None:
    """CLI: score one run and print it as text, JSON or a LaTeX table."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--faults", type=Path,
                    default=Path("data/decisions/faults.csv"))
    ap.add_argument("--json", action="store_true", help="machine-readable")
    ap.add_argument("--latex", action="store_true", help="thesis table")
    args = ap.parse_args()

    s = score(load_run(args.run_dir), load_faults(args.faults))

    if args.json:
        drop = ("caught_rows", "missed_rows", "not_walked_rows",
                "false_flag_rows", "known_miss_flag_rows")
        print(json.dumps({k: v for k, v in s.items() if k not in drop}, indent=2))
    elif args.latex:
        print(latex(s))
    else:
        print(report_text(s))


if __name__ == "__main__":
    main()
