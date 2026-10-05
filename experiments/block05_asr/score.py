"""Block 9, Track 1 (CONTEXT §12 metric 5): character error rate for spoken tags.

- Question: does Whisper hear the tag, and which character does it lose?
- Reference is the WALKER CARD -- what the trainee was told to say at each
  position -- not the schematic. The card already carries the planted faults,
  so a correctly heard "-9F9" at the -4F6 position scores as a hit here even
  though the adjudicator calls it a finding. Measuring against the schematic
  would charge the recogniser for the faults the study planted.
- The card is rebuilt from the sources it is printed from (checklist +
  faults.csv) and then checked against walker_card.txt, so the reference is
  the card the walker actually read rather than a retyping of it.
- Reads only. Nothing under runs/ is written or altered.

What this number is NOT. Both sides are put through normalise_tag first, so
this is the error rate of the pipeline the adjudicator sees -- recogniser plus
normaliser -- not of Whisper's raw output. "Minus one F one." is raw; "-1F1"
is what gets compared. A CER against the raw text would score the normaliser's
expansion rules, which is a different question and not this one.

Strips are excluded. The card's speak column holds a tag ("-X1") or a counting
instruction, but at a strip the trainee speaks counts ("L 3, N 1, PE 1"), so
there is no character-level reference to align against. Block 6 judges those on
the parsed counts; this metric cannot reach them.

Run:
    uv run python experiments/block05_asr/score.py runs/20260927-130613
    uv run python experiments/block05_asr/score.py runs/20260927-130613 --top 20
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from redlining.checklist import load_checklist
from redlining.normalise import normalise_tag
from redlining.paths import DECISIONS, ROOT
from redlining.walker_card import VERSIONS, card, load_overrides

FAULTS = DECISIONS / "faults.csv"
CARD = ROOT / "walker_card.txt"

LABEL_W = 26                   # width of the set-label column
HIT, SUB, DEL, INS = "hit", "sub", "del", "ins"
GAP = "∅"                      # the empty side of an insert or a delete


def reference_card(faults_path: Path, card_path: Path) -> tuple[dict, list[str]]:
    """Build the spoken reference for every device position, and check it.

    The card is regenerated from the checklist and faults.csv rather than
    parsed out of the printed table, then compared with the printed table. If
    the two disagree the walker read a card this run cannot reconstruct, and
    scoring against the reconstruction would be scoring against a fiction.

    Args:
        faults_path: faults.csv, the file that overwrites faulted positions.
        card_path: walker_card.txt as printed, if it is still on disk.

    Returns:
        ({tag: what the card told the walker to speak}, lines describing the
        check). Strip positions are not in the dict.

    Raises:
        SystemExit: The regenerated card differs from the printed one.
    """
    items = load_checklist()
    override = load_overrides(faults_path)
    notes = []

    if card_path.exists():
        printed = card_path.read_text(encoding="utf-8").splitlines()
        # Every known card version is tried, and ONE of them must match line
        # for line. The guard is as strict as it was -- an exact match is
        # still required -- but there is now more than one card to be exact
        # against: run 20260927-130613 was walked with v1 and a later run
        # will be walked with v2, which reworded the strip lines. Hard-coding
        # v1 would reject a v2 card as a fault-set drift, and hard-coding v2
        # would reject the card this run was actually read from.
        matched, differ = None, {}
        for version in VERSIONS:
            rebuilt = card(items, override, version=version)
            off = [n for n, (a, b) in enumerate(zip(rebuilt, printed), 1)
                   if a.rstrip() != b.rstrip()]
            if not off and len(rebuilt) == len(printed):
                matched = version
                break
            differ[version] = off or [f"length {len(rebuilt)}"
                                      f" vs {len(printed)}"]
        if matched is None:
            detail = "; ".join(f"v{v}: line(s) {d[:5]}"
                               for v, d in differ.items())
            raise SystemExit(
                f"the card rebuilt from {faults_path.name} matches no known "
                f"version of {card_path.name} ({detail}). The walker read a "
                "card this fault set no longer produces; the reference is not "
                "trustworthy and nothing is scored."
            )
        notes.append(f"  reference rebuilt from the checklist and "
                     f"{faults_path.name}, and it matches {card_path.name} "
                     f"line for line as card v{matched} "
                     f"({len(printed)} lines)")
    else:
        notes.append(f"  no {card_path.name} on disk; reference rebuilt from "
                     f"the checklist and {faults_path.name} and NOT checked "
                     "against the printed card")

    spoken = {i.tag: override.get(i.tag, i.tag)
              for i in items if i.kind != "strip"}
    strips = [i.tag for i in items if i.kind == "strip"]
    notes.append(f"  {len(spoken)} device position(s) scored; "
                 f"{len(strips)} strip(s) excluded -- a strip is spoken as "
                 "counts, so the card gives it no character reference")
    return spoken, notes


def load_attempts(run_dir: Path) -> tuple[dict, list[dict], list[dict]]:
    """Load the run's standing attempts and, where kept, every attempt.

    Args:
        run_dir: A run folder, e.g. runs/20260927-130613.

    Returns:
        (report, standing, every): the parsed report.json, the attempt that
        stands per item, and every recorded attempt. A repeated attempt_no
        (a page reload re-recording one attempt) keeps the last record. Where
        attempts.jsonl is missing, `every` is the standing set.
    """
    report_path = run_dir / "report.json"
    if not report_path.exists():
        raise SystemExit(f"no report.json in {run_dir}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    standing = list(report.get("items", []))

    attempts_path = run_dir / "attempts.jsonl"
    if not attempts_path.exists():
        return report, standing, standing

    seen: dict[tuple, dict] = {}
    for line in attempts_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            seen[(rec["item"], rec["attempt_no"])] = rec
    return report, standing, list(seen.values())


def align(ref: str, hyp: str) -> list[tuple[str, str, str]]:
    """Align two strings character by character at minimum edit cost.

    Args:
        ref: Reference string.
        hyp: Hypothesis string.

    Returns:
        One (op, ref_char, hyp_char) per step, in reading order. op is hit,
        sub, del (in the reference, not heard) or ins (heard, not in the
        reference); the absent side is "".
    """
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))

    ops: list[tuple[str, str, str]] = []
    i, j = n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            op = HIT if ref[i - 1] == hyp[j - 1] else SUB
            ops.append((op, ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append((DEL, ref[i - 1], ""))
            i -= 1
        else:
            ops.append((INS, "", hyp[j - 1]))
            j -= 1
    return ops[::-1]


def score_attempts(attempts: list[dict], spoken: dict) -> dict:
    """Align every device attempt against the card and total the errors.

    Args:
        attempts: Recorded attempts, any kind.
        spoken: {tag: what the card said to speak}, devices only.

    Returns:
        Counts, CER, per-reference-character tallies, the confusion Counter,
        and the attempts the normaliser rejected (listed, not dropped).
    """
    counts = Counter()
    per_char: dict[str, Counter] = {}
    confusions = Counter()
    ill_formed = []
    scored = 0

    for rec in attempts:
        if rec["item"] not in spoken:          # strips, and anything unwalked
            continue
        ref = normalise_tag(spoken[rec["item"]]).value
        heard = normalise_tag(rec["raw_transcript"])
        if not heard.well_formed:
            ill_formed.append((rec, ref, heard.value))
        scored += 1
        counts["ref_chars"] += len(ref)
        for op, r, h in align(ref, heard.value):
            counts[op] += 1
            if r:
                per_char.setdefault(r, Counter())[op] += 1
            if op != HIT:
                confusions[(r or GAP, h or GAP)] += 1

    errors = counts[SUB] + counts[DEL] + counts[INS]
    return {
        "attempts": scored,
        "ref_chars": counts["ref_chars"],
        "hit": counts[HIT], "sub": counts[SUB],
        "del": counts[DEL], "ins": counts[INS],
        "errors": errors,
        "cer": errors / counts["ref_chars"] if counts["ref_chars"] else None,
        "per_char": per_char,
        "confusions": confusions,
        "ill_formed": ill_formed,
    }


def pct(x, places: int = 1) -> str:
    """Format a ratio as a percentage, or 'n/a'.

    Args:
        x: Ratio in 0..1, or None.
        places: Decimal places.

    Returns:
        e.g. "1.4%".
    """
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


def overall_table(sets: list[tuple[str, dict]]) -> str:
    """Render the headline CER, one row per set of attempts.

    Args:
        sets: (label, score_attempts result) pairs.

    Returns:
        The table. The header is built from the same widths as the rows, so a
        label too long for its column cannot silently misalign one.
    """
    head = (f"  {'set':<{LABEL_W}}{'atts':>6}{'ref ch':>8}{'sub':>6}"
            f"{'del':>5}{'ins':>5}{'CER':>8}")
    L = [head, "  " + "-" * (len(head) - 2)]
    for label, s in sets:
        L.append(f"  {label:<{LABEL_W}}{s['attempts']:>6}{s['ref_chars']:>8}"
                 f"{s['sub']:>6}{s['del']:>5}{s['ins']:>5}"
                 f"{pct(s['cer']):>8}")
    return "\n".join(L)


def per_character_table(s: dict, quiet: bool) -> str:
    """Render accuracy per reference character, worst first, then rarest.

    Args:
        s: A score_attempts result.
        quiet: True to list only characters that were got wrong at least once.

    Returns:
        The table.
    """
    rows = []
    for ch, c in s["per_char"].items():
        seen = c[HIT] + c[SUB] + c[DEL]
        wrong = c[SUB] + c[DEL]
        rows.append({"char": ch, "seen": seen, "hit": c[HIT], "sub": c[SUB],
                     "del": c[DEL], "wrong": wrong,
                     "acc": c[HIT] / seen if seen else None})
    rows.sort(key=lambda r: (-r["wrong"], r["seen"], r["char"]))
    if quiet:
        rows = [r for r in rows if r["wrong"]]

    head = "  char  seen   hit   sub   del      acc"
    L = [head, "  " + "-" * (len(head) - 2)]
    for r in rows:
        L.append(f"  {r['char']:<6}{r['seen']:>4}{r['hit']:>6}{r['sub']:>6}"
                 f"{r['del']:>6}{pct(r['acc'], 1):>9}")
    if not rows:
        L.append("  (no reference character was got wrong)")
    return "\n".join(L)


def confusion_table(s: dict, top: int) -> str:
    """Render the characters most often confused, heard for spoken.

    Args:
        s: A score_attempts result.
        top: How many rows to show.

    Returns:
        The table.
    """
    head = "  spoken  ->  heard      n   of that character's reads"
    L = [head, "  " + "-" * (len(head) - 2)]
    for (r, h), n in s["confusions"].most_common(top):
        if r == GAP:
            share = "inserted; nothing was spoken there"
        else:
            c = s["per_char"].get(r, Counter())
            seen = c[HIT] + c[SUB] + c[DEL]
            share = f"{pct(n / seen, 0)} of {seen}" if seen else ""
        heard = "(nothing)" if h == GAP else h
        L.append(f"  {r:<8}    {heard:<9}{n:>4}   {share}")
    if not s["confusions"]:
        L.append("  (nothing was confused: every spoken character was heard "
                 "as itself)")
    return "\n".join(L)


def evidence(s: dict, floor: int) -> list[str]:
    """Name the characters too rarely spoken to support a claim either way.

    A character read correctly three times is not evidence that it is read
    correctly; it is evidence that it was barely tested.

    Args:
        s: A score_attempts result.
        floor: Reads below which a character is called thin.

    Returns:
        Lines for printing.
    """
    thin = sorted(((c[HIT] + c[SUB] + c[DEL], ch)
                   for ch, c in s["per_char"].items()
                   if c[HIT] + c[SUB] + c[DEL] < floor))
    if not thin:
        return []
    listed = ", ".join(f"{ch} ({n})" for n, ch in thin)
    return [f"  Thin evidence -- spoken fewer than {floor} times, so this run "
            f"says little about them either way:",
            f"    {listed}"]


def main() -> None:
    """CLI: align one run's transcripts against the walker card and report."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path,
                    help="a run folder, e.g. runs/20260927-130613")
    ap.add_argument("--faults", type=Path, default=FAULTS)
    ap.add_argument("--card", type=Path, default=CARD,
                    help="the printed walker card, checked against the rebuild")
    ap.add_argument("--top", type=int, default=15,
                    help="rows in the confusion table (default 15)")
    ap.add_argument("--evidence-floor", type=int, default=5,
                    help="reads below which a character is called thin "
                         "(default 5)")
    ap.add_argument("--all-characters", action="store_true",
                    help="list every reference character, not only the ones "
                         "got wrong")
    args = ap.parse_args()

    spoken, notes = reference_card(args.faults, args.card)
    report, standing, every = load_attempts(args.run_dir)

    s_standing = score_attempts(standing, spoken)
    s_every = score_attempts(every, spoken)
    well_formed = [rec for rec in every
                   if normalise_tag(rec["raw_transcript"]).well_formed]
    s_well = score_attempts(well_formed, spoken)

    print(f"\nRun {report['run_id']} - character error rate against the "
          f"walker card")
    print("\n".join(notes))
    print("  both sides normalised with normalise_tag: this is the pipeline "
          "the adjudicator sees, not Whisper's raw output")
    print()
    print(overall_table([
        ("standing attempt", s_standing),
        ("every attempt", s_every),
        ("every well-formed", s_well),
    ]))

    same = (s_standing["attempts"] == s_well["attempts"]
            and s_standing["cer"] == s_well["cer"])
    if same:
        print("\n  The standing and well-formed sets coincide: every attempt "
              "the normaliser rejected was re-asked and recovered.")

    if s_every["ill_formed"]:
        print(f"\n  {len(s_every['ill_formed'])} attempt(s) the normaliser "
              "rejected. They are scored in 'every attempt' above and left "
              "out of the tables below, because a decoder that repeats one "
              "token is a different failure from a misheard character and "
              "averaging the two hides both:")
        for rec, ref, value in s_every["ill_formed"]:
            print(f"    {rec['item']:<8} attempt {rec['attempt_no']}  "
                  f"card said {ref:<8} heard {len(value)} chars: "
                  f"{value[:28]}...")

    print("\nPer reference character"
          f" ({'all' if args.all_characters else 'errors only'}, "
          "well-formed attempts)")
    print(per_character_table(s_well, quiet=not args.all_characters))

    print("\nMost often confused (well-formed attempts)")
    print(confusion_table(s_well, args.top))

    lines = evidence(s_well, args.evidence_floor)
    if lines:
        print()
        print("\n".join(lines))
    print()


if __name__ == "__main__":
    main()
