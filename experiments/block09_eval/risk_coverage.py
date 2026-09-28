"""Block 9, Metric 3: the risk-coverage curve for one saved run.

- Question (CONTEXT §12, metric 3): how much does the run's error rate fall as
  it is allowed to abstain more? The two knobs that buy abstention are the
  adjudicator's edit-distance thresholds and the re-ask budget.
- Re-judges transcripts that are already on disk. No audio, no model, no
  network, and nothing is written into runs/ -- the recorded run is evidence,
  and an experiment that edits its evidence is worth nothing.
- The saved run is replayed, not re-performed. A setting can only consume
  attempts the trainee actually made: where a wider re-ask budget would have
  asked for a fourth read that was never recorded, the item is counted as
  abstaining and reported under "truncated". Those rows are a lower bound on
  coverage, not a measurement of it.

Definitions. The three that differ from score.py are marked, because the
difference is the point of this script:

  covered       the setting committed to a verdict: match, mismatch or
                not_in_schematic. DIFFERS from score.py, where an abstain is
                a flag and so counts as catching a fault planted under it.
                A curve that scored abstention as detection would have no
                trade-off left to plot.
  coverage      covered / items walked.
  risk          errors / covered, counted PER POSITION. DIFFERS from score.py,
                which scores per fault row, so a label swap counts once
                however many positions it occupies.
  error         on a covered position: a planted fault the setting called
                `match` (a silent miss), or a flag where nothing was planted
                (a false flag). Known-miss positions (detectable != yes in
                faults.csv) are excluded from both numerator and denominator,
                exactly as in score.py.
  detection,
  precision     score.py's own numbers, recomputed on the re-judged verdicts
                by calling score.score(), so the two files cannot drift apart.

Run:
    uv run python experiments/block09_eval/risk_coverage.py runs/20260927-130613
    uv run python experiments/block09_eval/risk_coverage.py runs/20260927-130613 \
        --csv data/processed/risk_coverage.csv
    uv run python experiments/block09_eval/risk_coverage.py runs/20260927-130613 \
        --lang de                      # the thesis plate, as a vector PDF
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from redlining.adjudicate import (
    ABSTAIN,
    MISMATCH,
    NOT_IN_SCHEMATIC,
    PART_EDIT_MAX,
    TAG_EDIT_MAX,
    Adjudicator,
)
from redlining.normalise import normalise_tag
from redlining.paths import DECISIONS, PROCESSED, SCHEMATIC
from redlining.report import FLAGGED
from redlining.score import load_faults, positions, score
from redlining.session import MAX_REASKS, parse_counts

FAULTS = DECISIONS / "faults.csv"
PNG = PROCESSED / "risk_coverage.png"
PDF_DE = PROCESSED / "risiko_abdeckung.pdf"

# A committed flag. Abstain is deliberately absent -- see the docstring.
FLAG_OUTCOMES = {MISMATCH, NOT_IN_SCHEMATIC}

# The swept settings. TAG_EDIT_MAX from 0 (never blame the microphone: an
# unknown tag is always reported as not-in-schematic) up to 3 (blame it as far
# out as the tags themselves are long).
TAG_EDIT_SWEEP = (0, 1, 2, 3)
REASK_SWEEP = (0, 1, 2)

# Categorical slots 1-3 of the project palette, validated for all pairs in
# both modes. One hue per re-ask budget; the hue follows the budget, not the
# line's rank, so adding a setting never repaints the others.
SERIES_COLOURS = ("#2a78d6", "#eb6834", "#1baf7a")
INK = "#0b0b0b"
INK_SOFT = "#52514e"
SURFACE = "#fcfcfb"
GRID = "#e6e5e1"

CM = 1 / 2.54

# Two figures from one set of numbers. "en" is the working figure: it carries
# its own title, subtitle and caveat, because it is read on its own in a
# terminal or a slide. "de" is the thesis plate to the FAPS rules -- Arial
# 10 pt, 16 cm wide, decimal comma, no frame, and no text at all that the
# LaTeX caption should be carrying instead. The numbers plotted are the same;
# only the plotting differs.
LANGS = {
    "en": {
        "out": PNG,
        "figsize": (7.4, 4.8),
        "surface": SURFACE, "ink": INK, "ink_soft": INK_SOFT, "grid": GRID,
        "markers": ("o", "o", "o"),
        "chrome": True,            # title, subtitle and footer note
        "comma": False,
        "rc": {},
        "fs": {"axis": 9, "tick": 8.5, "point": 8, "legend": 8.5},
        "x": "coverage - positions the run committed a verdict on (%)",
        "y": "risk - wrong verdicts among them (%)",
        "legend": "re-ask budget",
        "budget_join": ",",
        "budget_noun": "re-ask",       # German drops it: the legend title says it
        "threshold": "d≤{t}",
        "threshold_join": ",",
        "operating": f"as run: d≤{TAG_EDIT_MAX}, {MAX_REASKS} re-asks",
    },
    "de": {
        "out": PDF_DE,
        "figsize": (16 * CM, 9.5 * CM),
        # Colour is left to carry the one thing it encodes -- the re-ask
        # budget. Every piece of text is black, the grid is neutral, and the
        # two series also differ in marker shape so the plate survives a
        # greyscale print.
        "surface": "#ffffff", "ink": "#000000", "ink_soft": "#000000",
        "grid": "#d9d9d9",
        "markers": ("o", "s", "^"),
        "chrome": False,
        "comma": True,
        "rc": {"font.family": "sans-serif", "font.sans-serif": ["Arial"],
               "font.size": 10, "pdf.fonttype": 42, "ps.fonttype": 42},
        "fs": {"axis": 10, "tick": 10, "point": 10, "legend": 10},
        "x": "Abdeckung in %",
        "y": "Risiko in %",
        "legend": "Wiederholungsanfragen",
        "budget_join": " und ",
        "threshold": "d ≤ {t}",
        # " / ", not ",": with a decimal comma on the axes, "d <= 0,1" reads
        # as the number 0,1 rather than as the two thresholds 0 and 1.
        "threshold_join": " / ",
        "operating": "Einstellung D7",
    },
}


def load_transcripts(run_dir: Path) -> tuple[dict, dict[str, list[dict]]]:
    """Load one run's verdicts and every attempt behind them.

    report.json keeps only the verdict that stands, so the earlier attempts --
    the ones a smaller re-ask budget would have had to stop on -- are read from
    attempts.jsonl beside it. Without that file a re-ask sweep would be
    invented rather than replayed, so its absence is fatal.

    Args:
        run_dir: A run folder, e.g. runs/20260927-130613.

    Returns:
        (report, attempts_by_item): the parsed report.json, and each walked
        item's attempts ordered by attempt_no. A repeated attempt_no (a page
        reload re-recording the same attempt) keeps the last record.
    """
    report_path = run_dir / "report.json"
    if not report_path.exists():
        raise SystemExit(f"no report.json in {run_dir}")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    by_item: dict[str, dict[int, dict]] = {}
    for rec in report.get("items", []):
        by_item.setdefault(rec["item"], {})[rec["attempt_no"]] = rec

    attempts_path = run_dir / "attempts.jsonl"
    if not attempts_path.exists():
        raise SystemExit(
            f"no attempts.jsonl in {run_dir}. report.json holds only the "
            "verdict that stands, so the attempts a smaller re-ask budget "
            "would have stopped on are not there. Nothing to sweep."
        )
    for line in attempts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec["item"] in by_item:          # ignore items the report never verdicted
            by_item[rec["item"]][rec["attempt_no"]] = rec

    return report, {item: [d[n] for n in sorted(d)] for item, d in by_item.items()}


def is_part_mode(rec: dict) -> bool:
    """Whether a device attempt read a part number rather than a tag.

    Args:
        rec: One recorded attempt.

    Returns:
        True for a part-mode device read (CONTEXT §7), False for tag mode.
    """
    return rec["kind"] != "strip" and "part" in rec.get("expected", {})


def rejudge(adj: Adjudicator, rec: dict):
    """Re-judge one recorded attempt with this adjudicator's thresholds.

    The raw transcript goes back through the project's own normaliser, so the
    replay reproduces the run when the thresholds are left at their defaults --
    asserted in verify_replay(), not assumed.

    Args:
        adj: Adjudicator built at the setting under test.
        rec: One recorded attempt.

    Returns:
        The Verdict this setting would have reached.
    """
    if rec["kind"] == "strip":
        return adj.judge_strip(rec["item"], parse_counts(rec["raw_transcript"]))
    if is_part_mode(rec):
        # Read.raw glued the part number and the rating line into one string
        # with " | ", and nothing records which side was empty. Splitting it
        # back is a guess, and a guess here would silently mis-score the run.
        raise SystemExit(
            f"{rec['item']} was read in part mode. This script replays tag and "
            "strip reads only: the saved raw transcript joins the part number "
            "and the rating line, and recovering the two fields from it would "
            "be guesswork. Re-run the sweep when part-mode attempts are logged "
            "as separate fields."
        )
    t = normalise_tag(rec["raw_transcript"])
    return adj.judge_tag(rec["item"], t.value, t.well_formed)


def walk(adj: Adjudicator, attempts: list[dict], max_reasks: int) -> dict:
    """Replay one item under one setting: re-ask on abstain until the budget ends.

    Args:
        adj: Adjudicator built at the setting under test.
        attempts: The item's recorded attempts, in order.
        max_reasks: Silent re-asks allowed after an abstain.

    Returns:
        Dict with the standing record and verdict, the attempts used, and
        `truncated`: True when the setting still had a re-ask left but the run
        recorded no further read, so this abstain is a floor, not a finding.
    """
    budget = max_reasks + 1
    used = 0
    # A verdict that is not an abstain ends the item: the run does not get to
    # look at a later recording just because one exists. Stopping on the first
    # non-abstain is what makes the replay reproduce the run at the defaults.
    for rec in attempts[:budget]:
        verdict = rejudge(adj, rec)
        used += 1
        if verdict.outcome != ABSTAIN:
            break
    truncated = verdict.outcome == ABSTAIN and used == len(attempts) < budget
    return {"record": rec, "verdict": verdict, "attempts_used": used,
            "truncated": truncated}


def rejudged_report(report: dict, walks: dict[str, dict]) -> dict:
    """Rebuild a report.json-shaped dict from the re-judged verdicts.

    Nothing is written; this exists so score.score() can be called on the
    replay and the two files cannot drift apart. The original report is not
    mutated.

    Args:
        report: The run's parsed report.json.
        walks: Item -> walk() result.

    Returns:
        A report dict with the same summary fields and re-judged items.
    """
    items = []
    for rec in report["items"]:
        w = walks[rec["item"]]
        v = w["verdict"]
        items.append({**rec,
                      "attempt_no": w["attempts_used"],
                      "normalised": str(v.read),
                      "outcome": v.outcome,
                      "reason": v.reason,
                      "flagged": v.outcome in FLAGGED})
    abstains = sum(1 for i in items if i["outcome"] == ABSTAIN)
    return {**report,
            "items": items,
            "abstain_rate": abstains / max(len(items), 1),
            "over_abstain_ceiling": (abstains / max(len(items), 1)
                                     > report.get("abstain_ceiling", 0.10))}


def evaluate(report: dict, attempts_by_item: dict[str, list[dict]],
             faults: list[dict], adj: Adjudicator, max_reasks: int) -> dict:
    """Score one setting: coverage and per-position risk, plus score.py's metrics.

    Args:
        report: The run's parsed report.json.
        attempts_by_item: Each item's recorded attempts, in order.
        faults: Rows from faults.csv.
        adj: Adjudicator built at the thresholds under test.
        max_reasks: Silent re-asks allowed after an abstain.

    Returns:
        One row of the table.
    """
    walks = {item: walk(adj, attempts, max_reasks)
             for item, attempts in attempts_by_item.items()}

    planted = {p for f in faults
               if f["detectable"].strip().lower() == "yes"
               for p in positions(f)}
    carried = {p for f in faults
               if f["detectable"].strip().lower() != "yes"
               for p in positions(f)}

    walked = list(walks)
    covered = [i for i in walked if walks[i]["verdict"].outcome != ABSTAIN]
    # Known-miss positions are carried by the study: nothing there is scoreable
    # either way, so they leave the denominator as well as the numerator.
    scoreable = [i for i in covered if i not in carried]

    silent_misses = [i for i in scoreable if i in planted
                     and walks[i]["verdict"].outcome not in FLAG_OUTCOMES]
    false_flags = [i for i in scoreable if i not in planted
                   and walks[i]["verdict"].outcome in FLAG_OUTCOMES]

    s = score(rejudged_report(report, walks), faults)

    return {
        "tag_edit_max": adj.tag_edit_max,
        "part_edit_max": adj.part_edit_max,
        "max_reasks": max_reasks,
        "attempts": sum(w["attempts_used"] for w in walks.values()),
        "walked": len(walked),
        "covered": len(covered),
        "coverage": len(covered) / len(walked) if walked else None,
        "abstain_rate": 1 - (len(covered) / len(walked)) if walked else None,
        "truncated": sum(1 for w in walks.values() if w["truncated"]),
        "scoreable": len(scoreable),
        "silent_misses": len(silent_misses),
        "false_flags_pos": len(false_flags),
        "risk": ((len(silent_misses) + len(false_flags)) / len(scoreable)
                 if scoreable else None),
        "planted_rows": s["planted"],
        "caught": s["caught"],
        "detection_rate": s["detection_rate"],
        "precision": s["precision"],
        "silent_miss_items": sorted(silent_misses),
        "false_flag_items": sorted(false_flags),
    }


def verify_replay(report: dict, rows: list[dict],
                  attempts_by_item: dict[str, list[dict]],
                  adj: Adjudicator) -> list[str]:
    """Check the replay against the run, and the sweep against itself.

    Three things are asserted rather than assumed:
      1. at the defaults the replay reproduces every outcome the run recorded;
      2. the part-number threshold cannot move a verdict in a run with no
         part-mode read -- so its column being constant is a property of the
         run, not a bug in the sweep;
      3. the baseline row's numbers equal score.py's on the untouched report.

    Args:
        report: The run's parsed report.json.
        rows: The swept table.
        attempts_by_item: Each item's recorded attempts, in order.
        adj: Adjudicator at the default thresholds.

    Returns:
        Lines describing what was checked, for printing under the table.
    """
    out = []

    recorded = {r["item"]: r["outcome"] for r in report["items"]}
    replayed = {item: walk(adj, a, MAX_REASKS)["verdict"].outcome
                for item, a in attempts_by_item.items()}
    differs = {i for i in recorded if recorded[i] != replayed[i]}
    out.append(f"  replay at the defaults reproduces "
               f"{len(recorded) - len(differs)}/{len(recorded)} recorded "
               f"outcomes" + (f" -- DIFFERS at {sorted(differs)}" if differs
                              else ""))

    part_items = [r["item"] for r in report["items"] if is_part_mode(r)]
    if part_items:
        out.append(f"  {len(part_items)} part-mode item(s): PART_EDIT_MAX is "
                   f"live and is NOT swept here")
    else:
        probe = {
            p: {i: walk(Adjudicator.from_export(SCHEMATIC, part_edit_max=p,
                                                tag_edit_max=TAG_EDIT_MAX),
                        a, MAX_REASKS)["verdict"].outcome
                for i, a in attempts_by_item.items()}
            for p in (0, 1, 2, 3)
        }
        inert = all(v == probe[PART_EDIT_MAX] for v in probe.values())
        out.append(f"  no part-mode read in this run (tag mode throughout), so "
                   f"PART_EDIT_MAX cannot move a verdict: checked at 0/1/2/3 "
                   f"-- {'identical' if inert else 'NOT identical, investigate'}"
                   f". Held at {PART_EDIT_MAX} and left out of the sweep.")

    baseline = next((r for r in rows
                     if r["tag_edit_max"] == TAG_EDIT_MAX
                     and r["max_reasks"] == MAX_REASKS), None)
    if baseline:
        live = score(report, load_faults(FAULTS))
        same = (baseline["caught"] == live["caught"]
                and baseline["detection_rate"] == live["detection_rate"]
                and baseline["precision"] == live["precision"])
        out.append(f"  baseline row ({TAG_EDIT_MAX}, {MAX_REASKS}) matches "
                   f"score.py on the untouched report: "
                   f"{'yes' if same else 'NO, investigate'}")
    return out


def pct(x, places: int = 1) -> str:
    """Format a ratio as a percentage, or 'n/a'.

    Args:
        x: Ratio in 0..1, or None.
        places: Decimal places.

    Returns:
        e.g. "97.1%".
    """
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


def table(rows: list[dict], report: dict) -> str:
    """Render the sweep as a fixed-width table.

    Args:
        rows: Swept settings from evaluate().
        report: The run's parsed report.json.

    Returns:
        The table, ready to print.
    """
    head = ("tag_max reasks  atts   cov     abst    risk    miss  ff   "
            "caught  det     prec")
    L = [f"Run {report['run_id']} - {report['items_verdicted']} items walked, "
         f"{report['total_attempts']} attempts recorded",
         f"Thresholds swept: TAG_EDIT_MAX {list(TAG_EDIT_SWEEP)} x "
         f"MAX_REASKS {list(REASK_SWEEP)}"
         f"  (defaults {TAG_EDIT_MAX}, {MAX_REASKS})",
         "",
         head, "-" * len(head)]
    for r in rows:
        star = " *" if (r["tag_edit_max"] == TAG_EDIT_MAX
                        and r["max_reasks"] == MAX_REASKS) else "  "
        L.append(
            f"{r['tag_edit_max']:>4}{star}{r['max_reasks']:>5}"
            f"{r['attempts']:>7}"
            f"{pct(r['coverage']):>8}{pct(r['abstain_rate']):>8}"
            f"{pct(r['risk']):>8}"
            f"{r['silent_misses']:>6}{r['false_flags_pos']:>4}"
            f"{r['caught']:>6}/{r['planted_rows']:<2}"
            f"{pct(r['detection_rate'], 0):>6}{pct(r['precision'], 0):>7}"
        )
    L += ["", "  * the settings this run was performed at.",
          "  cov/abst/risk/miss/ff are per position; caught/det/prec are "
          "score.py's per-row numbers.",
          "  risk = (silent misses + false flags) / covered positions, "
          "known-miss positions excluded."]

    truncated = [r for r in rows if r["truncated"]]
    if truncated:
        L += ["",
              "  Truncated rows -- the setting had a re-ask left but the run "
              "recorded no further read, so these coverages are floors:"]
        for r in truncated:
            L.append(f"    tag_max {r['tag_edit_max']}, reasks "
                     f"{r['max_reasks']}: {r['truncated']} item(s)")
    return "\n".join(L)


def merge_runs(values: list, join: str = ",") -> str:
    """Collapse settings that landed on one point: [0, 1] -> "0,1".

    Args:
        values: Settings that share a point or a line, in order.
        join: What to put between them ("," in English, " und " in German).

    Returns:
        One label. A single value is returned unchanged.
    """
    return join.join(str(v) for v in values)


def series_label(budgets: list[int], style: dict) -> str:
    """Name one line by the re-ask budgets that share it.

    Args:
        budgets: The budgets this line stands for, in order.
        style: The language's entry in LANGS.

    Returns:
        "1,2 re-asks" in English; "1 und 2" in German, where the legend title
        already says what the numbers count.
    """
    joined = merge_runs(budgets, style["budget_join"])
    noun = style.get("budget_noun")
    if not noun:
        return joined
    return f"{joined} {noun}" + ("" if budgets == [1] else "s")


def curves(rows: list[dict], style: dict) -> list[dict]:
    """Fold the sweep into the lines and markers a plot can actually show.

    Settings that reach the same numbers reach the same pixel. Left as they
    are, the later series paints over the earlier one and the figure claims
    fewer settings were tried than were. So identical settings are merged and
    say so in their label: "1,2 re-asks" is the finding, not a shortcut.

    Args:
        rows: Swept settings from evaluate().
        style: The language's entry in LANGS, for the labels.

    Returns:
        One dict per distinct line: budgets, label, and its points (each with
        coverage, risk and the thresholds that share it).
    """
    lines: list[dict] = []
    for reasks in REASK_SWEEP:
        series = [r for r in rows
                  if r["max_reasks"] == reasks and r["risk"] is not None]
        if not series:
            continue
        points: list[dict] = []
        for r in sorted(series, key=lambda r: r["tag_edit_max"]):
            here = (r["coverage"], r["risk"])
            if points and points[-1]["xy"] == here:
                points[-1]["thresholds"].append(r["tag_edit_max"])
            else:
                points.append({"xy": here, "thresholds": [r["tag_edit_max"]]})
        shape = tuple(p["xy"] for p in points)
        same = next((ln for ln in lines if ln["shape"] == shape), None)
        if same:
            same["budgets"].append(reasks)
        else:
            lines.append({"shape": shape, "budgets": [reasks], "points": points})

    for ln in lines:
        ln["label"] = series_label(ln["budgets"], style)
    return lines


def decimal_comma(decimals: int):
    """Build a tick formatter that writes 95.7 the German way, as "95,7".

    Every tick on an axis gets the same number of decimals, so 6 prints as
    "6,0" beside "5,8" rather than breaking the column.

    Args:
        decimals: Decimal places, taken from the ticks matplotlib chose.

    Returns:
        A function matplotlib can use as a tick formatter.
    """
    def fmt(value: float, _pos=None) -> str:
        return f"{value:.{decimals}f}".replace(".", ",")
    return fmt


def tick_decimals(ticks) -> int:
    """How many decimals the busiest of these ticks needs.

    Args:
        ticks: Tick locations on one axis.

    Returns:
        The largest decimal count any tick needs, 0 if they are all integers.
    """
    return max((len(f"{t:g}".partition(".")[2]) for t in ticks), default=0)


def figure(rows: list[dict], report: dict, out: Path, lang: str = "en") -> Path:
    """Draw the risk-coverage curve, one line per distinct re-ask budget.

    Risk on y, coverage on x, so down-and-left-to-right is the trade: a
    setting buys a lower error rate by committing to fewer verdicts. Every
    marker carries the thresholds that reach it, so identity never rests on
    colour alone, and coverage is clipped at 100% because there is no such
    thing as covering more positions than were walked.

    The German plate drops the title, the subtitle and the footer note: under
    the FAPS rules those belong in the LaTeX caption, and a figure that
    repeats its caption is a figure that will disagree with it later.

    Args:
        rows: Swept settings from evaluate().
        report: The run's parsed report.json.
        out: Where to write the figure. The suffix picks the format, so a
            .pdf path gets vector output.
        lang: A key of LANGS: "en" for the working figure, "de" for the
            thesis plate.

    Returns:
        The path written.

    Raises:
        SystemExit: The language's font is not installed, which matplotlib
            would otherwise paper over by silently substituting another.
    """
    import matplotlib
    matplotlib.use("Agg")                      # no display in a run script
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.ticker import FuncFormatter

    style = LANGS[lang]
    wanted = style["rc"].get("font.sans-serif")
    if wanted:
        # A thesis plate set in the wrong typeface is a silent failure that
        # survives all the way to the printer. Refuse instead.
        installed = {f.name for f in font_manager.fontManager.ttflist}
        missing = [f for f in wanted if f not in installed]
        if missing:
            raise SystemExit(
                f"font(s) {', '.join(missing)} not installed, and matplotlib "
                "would quietly substitute another. Install the font, or draw "
                "the figure in a language whose style does not ask for it."
            )

    with plt.rc_context(style["rc"]):
        lines = curves(rows, style)
        surface, ink, ink_soft = (style["surface"], style["ink"],
                                  style["ink_soft"])
        grid, fs = style["grid"], style["fs"]

        fig, ax = plt.subplots(figsize=style["figsize"], dpi=200)
        fig.patch.set_facecolor(surface)
        fig.patch.set_linewidth(0)             # no frame around the figure
        ax.set_facecolor(surface)

        for n, ln in enumerate(lines):
            colour = SERIES_COLOURS[n % len(SERIES_COLOURS)]
            marker = style["markers"][n % len(style["markers"])]
            xs = [p["xy"][0] * 100 for p in ln["points"]]
            ys = [p["xy"][1] * 100 for p in ln["points"]]
            # Line and markers in one call, so the legend handle carries the
            # marker too: the shape repeats what colour says, and the plate
            # still reads when the thesis is printed in greyscale.
            ax.plot(xs, ys, color=colour, linewidth=2, zorder=3,
                    marker=marker, markersize=7, markeredgecolor=surface,
                    markeredgewidth=1.6, label=ln["label"])
            for p, x, y in zip(ln["points"], xs, ys):
                thresholds = merge_runs(p["thresholds"],
                                        style["threshold_join"])
                ax.annotate(style["threshold"].format(t=thresholds), (x, y),
                            textcoords="offset points", xytext=(0, 12),
                            ha="center", fontsize=fs["point"], color=ink_soft,
                            zorder=5)

        star = next((r for r in rows if r["tag_edit_max"] == TAG_EDIT_MAX
                     and r["max_reasks"] == MAX_REASKS
                     and r["risk"] is not None), None)
        if star:
            ax.annotate(style["operating"],
                        (star["coverage"] * 100, star["risk"] * 100),
                        textcoords="offset points", xytext=(-14, -26),
                        ha="right", fontsize=fs["point"], color=ink, zorder=6,
                        arrowprops=dict(arrowstyle="-", color=ink_soft,
                                        linewidth=0.8, shrinkA=0, shrinkB=6))

        ax.set_xlabel(style["x"], fontsize=fs["axis"], color=ink_soft,
                      labelpad=9)
        ax.set_ylabel(style["y"], fontsize=fs["axis"], color=ink_soft,
                      labelpad=9)

        covs = [r["coverage"] for r in rows if r["risk"] is not None]
        risks = [r["risk"] for r in rows if r["risk"] is not None]
        if style["chrome"]:
            # Title and subtitle are drawn on the figure, not the axes, so a
            # long subtitle cannot squeeze the plot sideways.
            fig.text(0.017, 0.975,
                     f"Risk against coverage, run {report['run_id']}",
                     fontsize=12, color=ink, va="top")
            # Both scales are zoomed hard -- the whole sweep fits inside a
            # point of each axis. Say so in numbers, or the slope reads as a
            # finding it is not.
            fig.text(0.017, 0.918,
                     f"Across all {len(rows)} settings coverage spans "
                     f"{pct(min(covs))}-{pct(max(covs))} and risk "
                     f"{pct(min(risks))}-{pct(max(risks))}.\n"
                     "Both axes are zoomed to that span: neither knob moves "
                     "either by half a point.",
                     fontsize=8, color=ink_soft, va="top", linespacing=1.5)

        ax.grid(True, color=grid, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
            ax.spines[side].set_linewidth(0.8)
        ax.tick_params(colors=ink_soft, labelsize=fs["tick"], length=0)

        xs = [c * 100 for c in covs]
        ys = [r * 100 for r in risks]
        span_x = max(max(xs) - min(xs), 1.0)
        span_y = max(max(ys) - min(ys), 0.5)
        # 100% is the ceiling: covering more positions than were walked is not
        # a thing, and an axis running past it would invite the eye to
        # extrapolate.
        ax.set_xlim(min(xs) - span_x * 0.6, min(100 + span_x * 0.12,
                                                max(xs) + span_x * 0.12))
        ax.set_ylim(min(ys) - span_y * 1.1, max(ys) + span_y * 0.9)

        # After the limits, so the decimals come from the ticks that will
        # actually be drawn.
        if style["comma"]:
            for axis in (ax.xaxis, ax.yaxis):
                axis.set_major_formatter(FuncFormatter(
                    decimal_comma(tick_decimals(axis.get_ticklocs()))))

        legend = ax.legend(title=style["legend"], frameon=False,
                           fontsize=fs["legend"], loc="lower left",
                           labelcolor=ink_soft, handlelength=1.6,
                           borderpad=0.1)
        legend.get_title().set_fontsize(fs["legend"])
        legend.get_title().set_color(ink_soft)

        if style["chrome"]:
            fig.text(0.008, 0.015,
                     f"One cabinet, {report['items_verdicted']} positions, "
                     "faults planted by the author. Abstain is an abstention "
                     "here, not a flag: it leaves coverage, so no setting can "
                     "lower its risk by abstaining onto a fault.",
                     fontsize=6.8, color=ink_soft, wrap=True)

        out.parent.mkdir(parents=True, exist_ok=True)
        rect = (0, 0.05, 1, 0.86) if style["chrome"] else (0, 0, 1, 1)
        fig.tight_layout(rect=rect)
        fig.savefig(out, facecolor=surface, edgecolor="none")
    plt.close(fig)
    return out


def reading(rows: list[dict], report: dict) -> list[str]:
    """State what the sweep found, derived from the rows rather than asserted.

    Args:
        rows: Swept settings from evaluate().
        report: The run's parsed report.json.

    Returns:
        Lines for printing under the table.
    """
    kind_of = {r["item"]: r["kind"] for r in report["items"]}
    scored = [r for r in rows if r["risk"] is not None]
    if not scored:
        return ["  nothing was covered at any setting; there is no curve."]

    points = {(r["coverage"], r["risk"]) for r in scored}
    covs = [r["coverage"] for r in scored]
    risks = [r["risk"] for r in scored]
    L = [f"  {len(points)} distinct (coverage, risk) point(s) across "
         f"{len(rows)} settings: coverage {pct(min(covs))}-{pct(max(covs))}, "
         f"risk {pct(min(risks))}-{pct(max(risks))}."]

    errors = [set(r["silent_miss_items"]) | set(r["false_flag_items"])
              for r in scored]
    persistent = set.intersection(*errors)
    movable = set.union(*errors) - persistent

    if persistent:
        base = next((r for r in scored if r["tag_edit_max"] == TAG_EDIT_MAX
                     and r["max_reasks"] == MAX_REASKS), scored[0])
        L.append(f"  {len(persistent)} position(s) are wrong at EVERY setting "
                 "swept:")
        for item in sorted(persistent):
            role = ("silent miss" if item in base["silent_miss_items"]
                    else "false flag")
            L.append(f"    {item:<8} {kind_of.get(item, '?'):<7} {role}")
        if {kind_of.get(i) for i in persistent} == {"strip"}:
            L.append("  All of them are strip counts. The edit-distance "
                     "thresholds read tags and part numbers, and a wrong count "
                     "is committed rather than abstained, so no setting in this "
                     "sweep can reach these. The floor under the curve is a "
                     "counting problem, not an abstention one.")
    if movable:
        L.append(f"  {len(movable)} position(s) change with the setting: "
                 + ", ".join(sorted(movable)))
    return L


def write_csv(rows: list[dict], path: Path) -> None:
    """Write the sweep as a CSV, list columns joined with spaces.

    Args:
        rows: Swept settings from evaluate().
        path: Output CSV.
    """
    flat = [{k: (" ".join(v) if isinstance(v, list) else v)
             for k, v in r.items()} for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def main() -> None:
    """CLI: sweep the settings over one saved run, print the table, draw the PNG."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path,
                    help="a run folder, e.g. runs/20260927-130613")
    ap.add_argument("--faults", type=Path, default=FAULTS)
    ap.add_argument("--export", type=Path, default=SCHEMATIC)
    ap.add_argument("--lang", choices=sorted(LANGS), default="en",
                    help="'en': the working figure, with its own title and "
                         "caveat, as a PNG. 'de': the thesis plate to the FAPS "
                         "rules -- Arial 10 pt, 16 cm, decimal comma, no text "
                         "the LaTeX caption should carry -- as a vector PDF")
    ap.add_argument("--out", type=Path,
                    help="where to write the figure; the suffix picks the "
                         f"format (default {PNG.name} for en, "
                         f"{PDF_DE.name} for de)")
    ap.add_argument("--csv", type=Path, help="also write the table as a CSV")
    ap.add_argument("--no-figure", action="store_true",
                    help="table only; do not draw the figure")
    ap.add_argument("--part-edit-max", type=int, default=PART_EDIT_MAX,
                    help=f"held fixed, not swept (default {PART_EDIT_MAX}); "
                         "it moves nothing in a tag-mode run")
    args = ap.parse_args()

    report, attempts_by_item = load_transcripts(args.run_dir)
    faults = load_faults(args.faults)

    adjudicators = {t: Adjudicator.from_export(args.export,
                                               part_edit_max=args.part_edit_max,
                                               tag_edit_max=t)
                    for t in TAG_EDIT_SWEEP}
    rows = [evaluate(report, attempts_by_item, faults, adjudicators[t], k)
            for t in TAG_EDIT_SWEEP for k in REASK_SWEEP]

    print()
    print(table(rows, report))

    print("\nChecked:")
    print("\n".join(verify_replay(report, rows, attempts_by_item,
                                  adjudicators[TAG_EDIT_MAX])))

    print("\nReading:")
    print("\n".join(reading(rows, report)))

    if args.csv:
        write_csv(rows, args.csv)
        print(f"\n  wrote {args.csv}")
    if not args.no_figure:
        out = args.out or LANGS[args.lang]["out"]
        print(f"  wrote {figure(rows, report, out, args.lang)}")
    print()


if __name__ == "__main__":
    main()
