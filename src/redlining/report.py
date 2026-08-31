"""Block 8: the run log, the flag queue, and the report.

Two rules from CONTEXT.md §4, and they are structural here, not advisory:

  1. Flags are APPEND-ONLY. There is no delete method, no close method, no
     status field a trainee can set to 'resolved'. Grep this file for 'delete'
     or 'remove' -- there is nothing to find. A trainee closing a flag is a
     trainee performing sign-off.
  2. The report contains ALL items, not only flags. Without the matches there
     is no false-flag rate, and the false-flag rate is the number that decides
     whether anyone trusts this system.

Attempts are written to a JSON Lines file opened in append mode and fsynced,
so a crash mid-run keeps everything already recorded.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path("runs")
FLAGGED = {"mismatch", "not_in_schematic", "abstain"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Attempt:
    item: str
    kind: str
    band: int
    attempt_no: int              # 3 attempts on one item is itself a signal
    spoken_prompt: str           # what the trainee heard -- location only
    raw_transcript: str          # BLOCK_GUIDE: always keep the raw
    normalised: str
    well_formed: bool
    confidence: float | None
    audio_path: str | None
    outcome: str
    reason: str
    expected: dict = field(default_factory=dict)
    at: str = field(default_factory=_now)


@dataclass
class Annotation:
    """The trainee's account of a flag. Additive only."""
    item: str
    kind: str                    # 'i_misspoke' | 'part_looks_wrong' | 'note'
    text: str
    at: str = field(default_factory=_now)


class RunLog:
    """Append-only run store. Instantiating it creates runs/<timestamp>/."""

    def __init__(self, root: Path = RUNS, run_id: str | None = None):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = Path(root) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "audio").mkdir(exist_ok=True)
        self.attempts_path = self.dir / "attempts.jsonl"
        self.annotations_path = self.dir / "annotations.jsonl"
        self._attempts: list[Attempt] = []
        self._annotations: list[Annotation] = []
        self.started_at = _now()
        self.duration_s: float | None = None

    def _append(self, path: Path, payload: dict) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def record(self, attempt: Attempt) -> None:
        self._attempts.append(attempt)
        self._append(self.attempts_path, asdict(attempt))

    def annotate(self, annotation: Annotation) -> None:
        """The only thing a trainee may add to a flag. It cannot subtract."""
        self._annotations.append(annotation)
        self._append(self.annotations_path, asdict(annotation))

    # ------------------------------------------------------------------ views
    @property
    def final_attempts(self) -> list[Attempt]:
        """Last attempt per item -- the verdict that stands."""
        last: dict[str, Attempt] = {}
        for a in self._attempts:
            last[a.item] = a
        return list(last.values())

    @property
    def flags(self) -> list[Attempt]:
        return [a for a in self.final_attempts if a.outcome in FLAGGED]

    def annotations_for(self, item: str) -> list[Annotation]:
        return [n for n in self._annotations if n.item == item]

    # ---------------------------------------------------------------- outputs
    def write_report(self, expected_items: int = 100,
                     duration_s: float | None = None) -> Path:
        finals = self.final_attempts
        counts: dict[str, int] = {}
        for a in finals:
            counts[a.outcome] = counts.get(a.outcome, 0) + 1

        abstain_rate = counts.get("abstain", 0) / max(len(finals), 1)

        report = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": _now(),
            "duration_s": duration_s,
            "items_expected": expected_items,
            "items_verdicted": len(finals),
            "complete": len(finals) == expected_items,
            "outcomes": counts,
            "abstain_rate": round(abstain_rate, 4),
            "abstain_ceiling": 0.10,          # CONTEXT §8 working ceiling
            "over_abstain_ceiling": abstain_rate > 0.10,
            "total_attempts": len(self._attempts),
            "items_taking_three_attempts": sorted(
                {a.item for a in self._attempts if a.attempt_no >= 3}),
            "items": [
                {**asdict(a),
                 "flagged": a.outcome in FLAGGED,
                 "annotations": [asdict(n) for n in self.annotations_for(a.item)]}
                for a in sorted(finals, key=lambda x: (x.band, x.item))
            ],
        }

        path = self.dir / "report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        self._write_markdown(report)
        return path

    def _write_markdown(self, report: dict) -> None:
        """A reviewer should be able to act on this without asking a question."""
        L = [f"# Inspection run {report['run_id']}", ""]
        dur = report.get("duration_s")
        dur_txt = f"{round(dur)}s" if dur else "duration not recorded"
        L.append(f"Cabinet 20160387 · {report['items_verdicted']} of "
                 f"{report['items_expected']} items · {dur_txt}")
        L.append("")
        L.append("**Advisory only. This run passes or fails nothing. "
                 "A qualified person reviews every flag and signs off.**")
        L.append("")
        L.append("| outcome | n |")
        L.append("|---|---|")
        for k, v in sorted(report["outcomes"].items()):
            L.append(f"| {k} | {v} |")
        L.append("")
        if report["over_abstain_ceiling"]:
            L.append(f"> Abstain rate {report['abstain_rate']:.1%} is above the "
                     "10% working ceiling (CONTEXT §8).")
            L.append("")
        if report["items_taking_three_attempts"]:
            L.append("Items that consumed three attempts — illegible label, or "
                     "noise: " + ", ".join(report["items_taking_three_attempts"]))
            L.append("")

        flags = [i for i in report["items"] if i["flagged"]]
        L.append(f"## Flags ({len(flags)})")
        L.append("")
        if not flags:
            L.append("None.")
        for i in flags:
            L.append(f"### {i['item']} · band {i['band']} · {i['outcome']}")
            L.append(f"- Location given: {i['spoken_prompt']}")
            L.append(f"- Heard: `{i['raw_transcript']}`")
            L.append(f"- Normalised: `{i['normalised']}`")
            exp = i["expected"]
            shown = (exp.get("part") or exp.get("counts")
                     or (exp.get("tag") if not exp.get("part") else None) or "")
            if exp.get("part") and exp.get("rating"):
                shown = f"{exp['part']} {exp['rating']}"
            L.append(f"- Schematic expects: `{shown}`")
            L.append(f"- Reason: {i['reason']}")
            L.append(f"- Audio: {i['audio_path'] or 'not retained'}")
            for n in i["annotations"]:
                L.append(f"- Trainee ({n['kind']}): {n['text']}")
            L.append("")

        L.append(f"## All {len(report['items'])} items")
        L.append("")
        L.append("| item | band | outcome | heard | expected |")
        L.append("|---|---|---|---|---|")
        for i in report["items"]:
            exp = (i["expected"].get("part") or i["expected"].get("counts")
                   or i["expected"].get("tag") or "")
            L.append(f"| {i['item']} | {i['band']} | {i['outcome']} | "
                     f"`{i['normalised']}` | `{exp}` |")
        L.append("")
        L.append("_Matches are included deliberately: without them there is no "
                 "false-flag rate._")

        (self.dir / "report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    log = RunLog(root=Path("runs"))
    log.record(Attempt(
        item="-8F7", kind="device", band=1, attempt_no=1,
        spoken_prompt="left frame, row 3, position 5",
        raw_transcript="a nine f zero three one one six",
        normalised="A9F03116", well_formed=True, confidence=0.91,
        audio_path=None, outcome="mismatch",
        reason="reads A9F03116, schematic expects A9F03110",
        expected={"part": "A9F03110", "rating": "C60N1P10AB"}))
    log.record(Attempt(
        item="-8F8", kind="device", band=1, attempt_no=1,
        spoken_prompt="left frame, row 3, position 6",
        raw_transcript="a nine f zero three one one zero",
        normalised="A9F03110", well_formed=True, confidence=0.95,
        audio_path=None, outcome="match", reason="both values agree",
        expected={"part": "A9F03110", "rating": "C60N1P10AB"}))
    log.annotate(Annotation("-8F7", "part_looks_wrong",
                            "label says B16, schematic wants B10"))
    p = log.write_report(expected_items=2, duration_s=41.0)
    print(f"wrote {p}")
    print(f"flags: {[a.item for a in log.flags]}")
    print("no close/delete path exists:",
          not any(m.startswith(("delete", "remove", "close"))
                  for m in dir(RunLog)))