"""Block 7: walk the checklist and run the inspection.

- Fixed sequence per item: prompt (location only) -> commit -> adjudicate
  -> reveal. The expected value is never shown before the verdict is fixed;
  any hint destroys the confirmation-bias protection of CONTEXT §7.
- Re-asks are silent ("please read it again"), at most two. Then the item is
  flagged and the run moves on. The run never stops.
- Input is pluggable: typed (default), scripted smoke test, or live microphone.

Run:
    uv run python -m redlining.session                 # typed input
    uv run python -m redlining.session --scripted      # smoke test, no keyboard
    uv run python -m redlining.session --live --kind strip --model small --speak
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .adjudicate import Adjudicator, ABSTAIN
from .checklist import Item, load_checklist
from .normalise import normalise_part, normalise_rating, normalise_tag
from .report import Annotation, Attempt, RunLog

MAX_REASKS = 2                    # 3 attempts total, per CONTEXT §7

TAG_MODE_WARNING = (
    "MODE: tag only. This checks that the right label is in the right\n"
    "place. It cannot detect a wrong part fitted under a correct label.\n")


@dataclass
class Read:
    """One spoken attempt, before anything has been judged.

    Attributes:
        tag_raw: Raw transcript of a spoken tag.
        part_raw: Raw transcript of a spoken part number.
        rating_raw: Raw transcript of a spoken rating line.
        counts_raw: Raw transcript of spoken strip counts.
        confidence: ASR confidence (0-1), if known.
        audio_path: Where the recording is stored, if any.
    """
    tag_raw: str = ""
    part_raw: str = ""
    rating_raw: str = ""
    counts_raw: str = ""
    confidence: float | None = None
    audio_path: str | None = None

    @property
    def raw(self) -> str:
        """All non-empty raw fields joined with " | "."""
        return " | ".join(x for x in (self.tag_raw, self.part_raw,
                                      self.rating_raw, self.counts_raw) if x)


class KeyboardInput:
    """Typed stand-in for the microphone. Same interface as LiveInput."""

    def __init__(self, mode: str = "tag"):
        """Set up typed input.

        Args:
            mode: "tag" to ask for the tag only, "part" for part number + rating line.
        """
        self.mode = mode

    def device(self, prompt: str, attempt: int) -> Read:
        """Ask for one device read on the keyboard.

        Args:
            prompt: Location-only prompt, shown on the first attempt.
            attempt: 1 for the first try; later tries get a silent re-ask.

        Returns:
            Read with tag_raw (tag mode) or part_raw + rating_raw (part mode).
        """
        if attempt == 1:
            print(f"\n  {prompt}")
        else:
            print("\n  Please read it again.")      # silent: no echo, no hint
        if self.mode == "tag":
            return Read(tag_raw=input("    tag: ").strip())
        part = input("    part number : ").strip()
        rating = input("    rating line: ").strip()
        return Read(part_raw=part, rating_raw=rating)

    def strip(self, prompt: str, attempt: int) -> Read:
        """Ask for one strip's terminal counts on the keyboard.

        Args:
            prompt: Location-only prompt, shown on the first attempt.
            attempt: 1 for the first try; later tries get a silent re-ask.

        Returns:
            Read with counts_raw, e.g. "N 8 L 8 PE 8".
        """
        if attempt == 1:
            print(f"\n  {prompt}")
        else:
            print("\n  Please count them again.")
        counts = input("    counts, e.g. 'N 8 L 8 PE 8': ").strip()
        return Read(counts_raw=counts)


WORD_DIGITS = {"ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
               "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10,
               "ELEVEN": 11, "TWELVE": 12, "THIRTEEN": 13, "FOURTEEN": 14,
               "FIFTEEN": 15, "SIXTEEN": 16, "SEVENTEEN": 17, "EIGHTEEN": 18,
               "NINETEEN": 19, "TWENTY": 20}
FUNCTIONS = {"N", "L", "PE", "BRACKET"}
GLUED_RE = re.compile(r"[A-Z]+|\d+")


def parse_counts(text: str) -> dict:
    """Turn spoken strip counts into a function -> count dict.

    - Accepts digits or number words ("N eight").
    - Splits glued tokens ("3L", "N1").
    - The count may come before or after its function ("3 L" or "L 3").
    - Only known functions (N, L, PE, BRACKET) become keys.

    Args:
        text: Raw counts transcript, e.g. "N 8 L 8 PE 8".

    Returns:
        Dict such as {"N": 8, "L": 8, "PE": 8}. Empty if nothing parsed.
    """
    raw = text.replace(",", " ").replace(":", " ").upper().split()
    toks: list[str] = []
    for t in raw:
        toks.extend(GLUED_RE.findall(t) or [t])

    out: dict = {}
    pending_key = pending_value = None
    for t in toks:
        value = int(t) if t.isdigit() else WORD_DIGITS.get(t)
        if t in FUNCTIONS:
            if pending_value is not None:
                out[t] = pending_value
                pending_value = None
            else:
                pending_key = t
        elif value is not None:
            if pending_key is not None:
                out[pending_key] = value
                pending_key = None
            else:
                pending_value = value
    return out


def run(items: list[Item], adj: Adjudicator, source, log: RunLog,
        max_reasks: int = MAX_REASKS, mode: str = "tag") -> None:
    """Walk every item (prompt, commit, adjudicate, log), then write the report.

    Args:
        items: Checklist items in walking order.
        adj: Adjudicator for the cabinet.
        source: Input with .device(prompt, attempt) and .strip(prompt, attempt).
        log: RunLog that receives every attempt.
        max_reasks: Silent re-asks allowed after an abstain.
        mode: "part" = part number + rating line (CONTEXT §7);
            "tag" = tag only -- simpler, and blind to a wrong part.
    """
    started = time.monotonic()

    for item in items:
        attempt_no = 0
        while True:
            attempt_no += 1

            # --- prompt: location only. The expected value is not consulted.
            if hasattr(source, "_tag"):
                source._tag = item.tag        # scripted input only
            read = (source.strip(item.spoken, attempt_no) if item.kind == "strip"
                    else source.device(item.spoken, attempt_no))

            # --- commit: normalise before anything is compared.
            if item.kind == "strip":
                verdict = adj.judge_strip(item.tag, parse_counts(read.counts_raw))
                normalised = str(parse_counts(read.counts_raw))
                well_formed = bool(parse_counts(read.counts_raw))
            elif mode == "tag":
                t = normalise_tag(read.tag_raw)
                normalised = t.value
                well_formed = t.well_formed
                verdict = adj.judge_tag(item.tag, t.value, t.well_formed)
            else:
                p = normalise_part(read.part_raw) if read.part_raw else None
                r = normalise_rating(read.rating_raw) if read.rating_raw else None
                normalised = " | ".join(x.value for x in (p, r) if x)
                well_formed = all(x.well_formed for x in (p, r) if x)
                verdict = adj.judge_device(
                    item.tag,
                    part=p.value if p else None,
                    rating=r.value if r else None,
                    part_well_formed=p.well_formed if p else True,
                    rating_well_formed=r.well_formed if r else True,
                )

            # --- adjudicate: record the attempt exactly as it stands.
            log.record(Attempt(
                item=item.tag, kind=item.kind, band=item.band,
                attempt_no=attempt_no, spoken_prompt=item.spoken,
                raw_transcript=read.raw, normalised=normalised,
                well_formed=well_formed, confidence=read.confidence,
                audio_path=read.audio_path, outcome=verdict.outcome,
                reason=verdict.reason, expected=verdict.expected,
            ))

            if verdict.outcome == ABSTAIN and attempt_no <= max_reasks:
                continue                       # silent re-ask, nothing revealed

            # --- reveal: only now, and only to the log. The run does not stop.
            break

    duration = time.monotonic() - started
    log.duration_s = duration
    log.write_report(expected_items=len(items), duration_s=duration)


def triage(log: RunLog) -> None:
    """End-of-run flag queue: let the trainee annotate each flag.

    Flags can only be annotated, never closed -- every flag reaches the reviewer.

    Args:
        log: RunLog whose flags are shown and annotated.
    """
    flags = log.flags
    print(f"\n{len(flags)} flag(s). You may add an account of each. "
          "You cannot close one; every flag reaches the reviewer.")
    for a in flags:
        print(f"\n  {a.item} · {a.outcome}\n    {a.reason}")
        print("    [1] I misspoke   [2] the part looks wrong   "
              "[3] note   [enter] skip")
        choice = input("    > ").strip()
        kinds = {"1": "i_misspoke", "2": "part_looks_wrong", "3": "note"}
        if choice in kinds:
            text = input("    detail: ").strip()
            log.annotate(Annotation(a.item, kinds[choice], text))


class ScriptedInput:
    """Smoke-test input that feeds the schematic's own correct values back in.

    Smoke test, NOT an evaluation: nothing is ever wrong, so it gives no
    detection rate. Block 9 is where real faults get planted.
    """

    _tag = ""

    def __init__(self, adj: Adjudicator):
        """Keep the adjudicator to look up correct values.

        Args:
            adj: Adjudicator whose schematic supplies the answers.
        """
        self.adj = adj

    def device(self, prompt: str, attempt: int) -> Read:
        """Return the correct tag, part number and rating for the current item.

        Args:
            prompt: Ignored.
            attempt: Ignored.

        Returns:
            Read filled from the schematic record of the current tag.
        """
        rec = self.adj.devices[self._tag]
        return Read(tag_raw=self._tag, part_raw=rec["order_reference"],
                    rating_raw=rec["type"])

    def strip(self, prompt: str, attempt: int) -> Read:
        """Return the correct terminal counts for the current strip.

        Args:
            prompt: Ignored.
            attempt: Ignored.

        Returns:
            Read with counts_raw built from the schematic, e.g. "N 8 L 8 PE 8".
        """
        counts = self.adj.expected_counts(self._tag)
        return Read(counts_raw=" ".join(f"{k} {v}" for k, v in counts.items()))


def main() -> None:
    """CLI: parse flags, build checklist and input source, run, triage, report."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="data/schematic.cleaned.json")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N items (smoke test only)")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--scripted", action="store_true",
                    help="smoke test: feed the schematic back in, no keyboard")
    ap.add_argument("--live", action="store_true",
                    help="use the microphone and local Whisper")
    ap.add_argument("--model", default="small",
                    help="faster-whisper size: tiny|base|small|medium|large-v3")
    ap.add_argument("--speak", action="store_true",
                    help="read prompts aloud (needs pyttsx3)")
    ap.add_argument("--mode", choices=["part", "tag"], default="tag",
                    help="'part': part number + rating line. "
                         "'tag': tag only -- cannot detect a wrong part")
    ap.add_argument("--kind", choices=["device", "strip", "all"], default="all",
                    help="restrict the run to one item kind")
    args = ap.parse_args()

    adj = Adjudicator.from_export(args.export)
    items = load_checklist()
    if args.kind != "all":
        items = [i for i in items if i.kind == args.kind]
    if args.limit:
        items = items[: args.limit]

    print(f"Cabinet 20160387 · {len(items)} items · band then position")
    print("Advisory only. This run passes or fails nothing.\n")

    log = RunLog(root=Path(args.runs_dir))
    if args.scripted:
        source = ScriptedInput(adj)
    elif args.live:
        from .audio_input import LiveInput
        source = LiveInput(log.dir / "audio", model_size=args.model,
                           speak=args.speak, mode=args.mode)
    else:
        source = KeyboardInput(args.mode)
    if args.mode == "tag":
        print(TAG_MODE_WARNING)
    run(items, adj, source, log, mode=args.mode)
    if not args.scripted:
        triage(log)
        # Re-emit so annotations appear. Keep the duration from the timed run.
        log.write_report(expected_items=len(items), duration_s=log.duration_s)
    print(f"\nReport: {log.dir / 'report.md'}")


if __name__ == "__main__":
    main()