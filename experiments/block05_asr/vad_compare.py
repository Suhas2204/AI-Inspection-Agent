"""Block 5, side experiment: what Silero VAD changes, measured rather than argued.

Re-transcribes every retained clip of one run twice -- once with
vad_filter=False and once with vad_filter=True -- and reports what moved.
The question behind it is the Block 7 note that strips -X3, -X6 and -X7
abstained on every attempt with an empty or "You" transcript: VAD is one
candidate cause and one candidate fix, and it could be either.

What is compared with what. Both sides are transcribed HERE, now, by the
same loaded model. The run's stored transcripts are not the baseline: no
run file records which model size produced them, so comparing against them
would fold a possible model change into the VAD effect. The stored text is
reported separately, as drift, and is never scored against.

The decode settings are copied from LocalTranscriber.transcribe because
that method hard-codes vad_filter. A copy can drift from its original
silently, so --mirror-check re-runs a sample through LocalTranscriber itself
and fails if a single character differs. Read that line of the output before
reading any other. Since 5 Oct 2026 LocalTranscriber sets vad_filter=True,
so it is the VAD-ON side that is mirrored (MIRROR_VAD); the comparison
itself is unchanged, because both sides were always decoded here.

Two CER rows exclude the clips where the decoder ran away (LOOP_ITEMS). One
runaway transcript is hundreds of characters of a single repeated token and
contributes insertions by the hundred, so the headline CER mostly measures
how often the decode failed. That is worth knowing and it is not the same
question as how well a tag is heard, so both are printed and the per-clip
table shows which clips carry the errors.

Nothing under runs/ is opened for writing, and the output folder is refused
if it lies inside runs/. The clips are evidence; this script only reads them.

Run:
    uv run python experiments/block05_asr/vad_compare.py
    uv run python experiments/block05_asr/vad_compare.py --limit 8
    uv run python experiments/block05_asr/vad_compare.py --model large-v3
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import statistics
import sys
import time
from pathlib import Path

from redlining.audio_input import LocalTranscriber
from redlining.paths import DECISIONS, PROCESSED, ROOT, RUNS

RUN = RUNS / "20260927-130613"
OUT = PROCESSED / "vad_compare"
MODEL_SIZE = "small"            # streamlit_input.MODEL_SIZE, the app's default

# Copied from LocalTranscriber.transcribe (src/redlining/audio_input.py).
# Everything except vad_filter must stay identical to it, or the two sides
# measure the model as well as the VAD. --mirror-check is what proves it.
DECODE = dict(
    beam_size=5,
    temperature=0.0,
    condition_on_previous_text=False,
    # NO initial_prompt, for the reason given in audio_input.py.
)

# LocalTranscriber.transcribe sets vad_filter=True as of 5 Oct 2026, so it is
# the VAD-ON side of this comparison that mirrors it. --mirror-check must
# compare against that side; pointed at the off side it would now fail on
# every clip VAD changes and say the decode settings had drifted, which is
# the one thing it exists to tell the truth about.
MIRROR_VAD = True

# The two clips of this run that sent the decoder into a loop. Their
# transcripts are hundreds of characters of one repeated token, so they
# contribute insertions by the hundred and the headline CER becomes a
# measure of how often the decoder ran away rather than of how well it
# hears a tag. Both numbers are worth having, so both are reported and
# neither replaces the other; see the excluded rows of the CER table.
#
# Named, not detected. normalise.runaway now flags exactly these two, but a
# hard-coded list is what makes the exclusion auditable: a reader can check
# it against the per-clip table below, where both sit far outside the rest.
# Every attempt at these items is excluded, including the clean re-reads --
# dropping a re-read that was heard correctly can only push the excluded CER
# up, so the row is not flattered by the exclusion.
LOOP_ITEMS = ("-7F9", "-12F4")

SILENCE_S = 3.0
NOISE_DBFS = -50.0              # low level: audible hiss, nothing like speech
SAMPLE_RATE = 16_000            # the whole corpus is 16 kHz mono 16-bit


def load_scorer():
    """Import score.py from this folder, by path.

    By path rather than by name: src/redlining/score.py is a different module
    with the same basename, and which one `import score` finds depends on
    sys.path order. This cannot pick the wrong one.

    Returns:
        The imported block05 score module.
    """
    path = Path(__file__).with_name("score.py")
    spec = importlib.util.spec_from_file_location("block05_score", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refuse_unsafe_output(out: Path, run: Path) -> None:
    """Stop if the output folder would write into the run being read.

    Args:
        out: Output folder.
        run: The run folder being read.

    Raises:
        SystemExit: If out is inside the run, or anywhere under runs/.
    """
    out, run = out.resolve(), run.resolve()
    for parent in (run, RUNS.resolve()):
        if out == parent or parent in out.parents:
            raise SystemExit(
                f"refusing to write into {parent}: the clips are the evidence "
                f"behind this run's flags. Pass --out somewhere else."
            )


def require_vad() -> str:
    """Check the VAD side can actually run, before anything is decoded.

    faster-whisper's Silero VAD is an ONNX model, so vad_filter=True needs
    onnxruntime to import. Without this check the run decodes its first clip
    without VAD, then dies on the first clip with it, which looks like a bug
    in this script rather than a missing runtime.

    Returns:
        A line naming the onnxruntime version in use.

    Raises:
        SystemExit: If onnxruntime is missing or will not load.
    """
    try:
        import onnxruntime
    except ImportError as exc:
        raise SystemExit(
            "vad_filter=True needs onnxruntime, and importing it failed:\n"
            f"  {exc}\n"
            "faster-whisper ships Silero VAD as an ONNX model, so there is no "
            "comparison to make without it. If the package is installed but "
            "will not load, the usual cause on Windows is a missing Microsoft "
            "Visual C++ Redistributable (x64); a forced reinstall of "
            "onnxruntime is the other thing to try. Nothing was transcribed."
        ) from exc
    return f"  onnxruntime {onnxruntime.__version__} loaded; VAD is available"


def load_attempts(run: Path) -> tuple[list[dict], int]:
    """Read the run's attempts and resolve each one's clip.

    The stored audio_path is absolute and was written on another machine's
    layout, so it is resolved by basename against this run's audio folder.

    A repeated (item, attempt_no) keeps the LAST record, which is what
    score.py does with the same file. This run has one: -7F9 attempt 1 is
    written twice, a page reload re-recording one attempt. Scored twice it
    counted that runaway decode twice and put this script's attempt total one
    above score.py's, so the two disagreed about the same run while both
    claiming to measure it.

    Args:
        run: A run folder.

    Returns:
        (attempts, collapsed): attempt dicts with an added "wav" Path, in
        first-seen order, one per (item, attempt_no); and how many records a
        later record replaced. Attempts whose clip is missing are kept here
        with wav=None and dropped by the caller.

    Raises:
        SystemExit: If the run has no attempts.jsonl.
    """
    path = run / "attempts.jsonl"
    if not path.exists():
        raise SystemExit(f"no attempts.jsonl in {run}")

    audio = run / "audio"
    seen: dict[tuple, dict] = {}
    kept = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        name = Path(rec.get("audio_path") or "").name
        rec["wav"] = (audio / name) if name and (audio / name).exists() else None
        seen[(rec["item"], rec["attempt_no"])] = rec
        kept += 1
    return list(seen.values()), kept - len(seen)


def transcribe(model, wav: Path, vad: bool) -> tuple[str, float | None, float]:
    """Transcribe one clip with the shared settings, with or without VAD.

    Args:
        model: A loaded faster-whisper WhisperModel.
        wav: The clip.
        vad: Whether to switch Silero VAD on, at its default VadOptions.

    Returns:
        (text, confidence, seconds). Confidence is the mean segment
        probability, as LocalTranscriber computes it.
    """
    started = time.perf_counter()
    segments, _info = model.transcribe(str(wav), language="en",
                                       vad_filter=vad, **DECODE)
    segs = list(segments)                      # the generator does the work
    elapsed = time.perf_counter() - started

    text = " ".join(s.text.strip() for s in segs).strip()
    logprobs = [s.avg_logprob for s in segs if s.avg_logprob is not None]
    conf = (round(math.exp(sum(logprobs) / len(logprobs)), 3)
            if logprobs else None)
    return text, conf, elapsed


def mirror_check(transcriber: LocalTranscriber, wavs: list[Path],
                 sample: int) -> list[str]:
    """Prove the copied settings still match LocalTranscriber's own.

    Args:
        transcriber: The loaded transcriber, used both ways.
        wavs: Clips to draw the sample from.
        sample: How many clips to check; 0 skips the check.

    Returns:
        Lines describing the outcome.

    Raises:
        SystemExit: If any clip decodes differently through the two paths.
    """
    if not sample:
        return ["  mirror check SKIPPED -- the copied decode settings in "
                "DECODE are unverified against audio_input.py"]


    side = "True" if MIRROR_VAD else "False"
    checked = wavs[:sample]
    for wav in checked:
        theirs, _conf = transcriber.transcribe(wav)
        mine, _c, _s = transcribe(transcriber.model, wav, vad=MIRROR_VAD)
        if theirs != mine:
            raise SystemExit(
                "mirror check FAILED. DECODE here no longer matches "
                f"LocalTranscriber.transcribe for {wav.name}:\n"
                f"  LocalTranscriber: {theirs!r}\n"
                f"  this script     : {mine!r}\n"
                "The two sides would differ by decode settings as well as by "
                "VAD, so nothing is scored."
            )
    return [f"  mirror check passed on {len(checked)} clip(s): "
            f"vad_filter={side} here decodes exactly as "
            f"LocalTranscriber.transcribe does (which now sets "
            f"vad_filter={side} itself)"]


def write_probes(out: Path) -> list[tuple[str, Path, str]]:
    """Write a silent clip and a low-level noise clip to transcribe.

    Neither contains speech, so anything a side returns for them is invented.
    This is the cheapest test of the failure VAD is supposed to prevent.

    Args:
        out: Output folder.

    Returns:
        (label, path, description) for each probe.
    """
    import numpy as np
    import soundfile as sf

    n = int(SILENCE_S * SAMPLE_RATE)
    silence = np.zeros(n, dtype="float32")

    rng = np.random.default_rng(20260927)
    amplitude = 10.0 ** (NOISE_DBFS / 20.0)
    noise = (rng.standard_normal(n) * amplitude).astype("float32")

    out.mkdir(parents=True, exist_ok=True)
    probes = []
    for label, data, description in (
            ("silence", silence, f"{SILENCE_S:.0f} s of digital silence"),
            ("noise", noise,
             f"{SILENCE_S:.0f} s of gaussian noise at {NOISE_DBFS:.0f} dBFS")):
        path = out / f"probe_{label}.wav"
        sf.write(str(path), data, SAMPLE_RATE)
        rms = float((data ** 2).mean() ** 0.5)
        dbfs = 20 * math.log10(rms) if rms > 0 else float("-inf")
        probes.append((label, path, f"{description} (measured {dbfs:.1f} dBFS)"))
    return probes


def changed_rows(rows: list[dict]) -> list[dict]:
    """The clips whose transcript VAD altered.

    Args:
        rows: Per-clip result rows.

    Returns:
        The rows where the two sides disagree.
    """
    return [r for r in rows if r["text_off"] != r["text_on"]]


def is_loop(row: dict) -> bool:
    """Whether this row belongs to one of the runaway-decode items.

    Args:
        row: A per-clip result row.

    Returns:
        True if the row's item is in LOOP_ITEMS.
    """
    return row["item"] in LOOP_ITEMS


def clip_cer(scorer, row: dict, side: str, spoken: dict) -> float | None:
    """Character error rate of one attempt on one side.

    Scored by score.py's own machinery on a one-attempt set, so a per-clip
    number and the totals above it cannot disagree about how a clip was
    aligned.

    Args:
        scorer: The loaded block05 score module.
        row: A per-clip result row.
        side: "off" or "on".
        spoken: {tag: what the card said to speak}, devices only.

    Returns:
        The CER, or None where the card gives no character reference (every
        strip, and any item not walked).
    """
    one = [{"item": row["item"], "raw_transcript": row[f"text_{side}"]}]
    return scorer.score_attempts(one, spoken)["cer"]


def per_clip_table(scorer, rows: list[dict], spoken: dict) -> str:
    """Render the CER of every attempt, both sides, worst first.

    The point of reading it per clip is that a total hides which clips carry
    the errors. Here the two runaway decodes are visible as the outliers they
    are, which is also what makes excluding them auditable rather than
    asserted.

    Args:
        scorer: The loaded block05 score module.
        rows: Per-clip result rows.
        spoken: {tag: what the card said to speak}, devices only.

    Returns:
        The table.
    """
    scored = []
    for r in rows:
        off = clip_cer(scorer, r, "off", spoken)
        on = clip_cer(scorer, r, "on", spoken)
        scored.append((r, off, on))
    # Worst first, by the off side; the unscorable strips sort last.
    scored.sort(key=lambda t: (t[1] is None, -(t[1] or 0.0),
                               t[0]["item"], t[0]["attempt_no"]))

    head = (f"  {'item':<7}{'att':>4}  {'kind':<7}{'CER off':>9}"
            f"{'CER on':>9}  note")
    L = [head, "  " + "-" * (len(head) - 2)]
    for r, off, on in scored:
        if off is None:
            note = "no character reference on the card (strip)"
        elif is_loop(r):
            note = "RUNAWAY DECODE -- excluded from the no-loops rows"
        else:
            note = ""
        L.append(f"  {r['item']:<7}{r['attempt_no']:>4}  {r['kind']:<7}"
                 f"{scorer.pct(off):>9}{scorer.pct(on):>9}  {note}")
    return "\n".join(L)


def table(rows: list[dict]) -> str:
    """Render the per-side totals.

    Args:
        rows: Per-clip result rows.

    Returns:
        The table.
    """
    def empties(side):
        return sum(1 for r in rows if not r[f"text_{side}"].strip())

    def seconds(side):
        return [r[f"secs_{side}"] for r in rows]

    head = ("  side            clips  empty  mean s/clip  median s/clip"
            "  total s")
    lines = [head, "  " + "-" * (len(head) - 2)]
    for side, label in (("off", "vad_filter=False"), ("on", "vad_filter=True")):
        secs = seconds(side)
        lines.append(
            f"  {label:<15}{len(rows):>6}{empties(side):>7}"
            f"{statistics.mean(secs):>13.2f}{statistics.median(secs):>15.2f}"
            f"{sum(secs):>9.1f}")
    return "\n".join(lines)


def main() -> None:
    """CLI: transcribe both ways, score both, and print what moved."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=RUN)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--model", default=MODEL_SIZE)
    parser.add_argument("--limit", type=int, default=0,
                        help="transcribe only the first N clips (a smoke test)")
    parser.add_argument("--mirror-check", type=int, default=3,
                        help="clips to re-run through LocalTranscriber; 0 skips")
    parser.add_argument("--faults", type=Path, default=DECISIONS / "faults.csv")
    parser.add_argument("--card", type=Path, default=ROOT / "walker_card.txt")
    args = parser.parse_args()

    refuse_unsafe_output(args.out, args.run)
    vad_note = require_vad()          # fail now, not after an hour of decoding
    scorer = load_scorer()

    attempts, collapsed = load_attempts(args.run)
    missing = [a for a in attempts if a["wav"] is None]
    usable = [a for a in attempts if a["wav"] is not None]
    if args.limit:
        usable = usable[:args.limit]
    if not usable:
        raise SystemExit(f"no clips found under {args.run / 'audio'}")

    transcriber = LocalTranscriber(args.model)
    notes = [vad_note] + mirror_check(transcriber, [a["wav"] for a in usable],
                                      args.mirror_check)

    # One decode per clip per side, shared by the attempts pointing at it.
    clips = sorted({a["wav"] for a in usable})
    decoded: dict[Path, dict] = {}
    for n, wav in enumerate(clips, 1):
        print(f"  [{n}/{len(clips)}] {wav.name}", file=sys.stderr)
        off_text, off_conf, off_s = transcribe(transcriber.model, wav, False)
        on_text, on_conf, on_s = transcribe(transcriber.model, wav, True)
        decoded[wav] = {"text_off": off_text, "conf_off": off_conf,
                        "secs_off": off_s, "text_on": on_text,
                        "conf_on": on_conf, "secs_on": on_s}

    rows = []
    for attempt in usable:
        d = decoded[attempt["wav"]]
        rows.append({"item": attempt["item"], "kind": attempt.get("kind", ""),
                     "attempt_no": attempt["attempt_no"],
                     "wav": attempt["wav"].name,
                     "stored": attempt.get("raw_transcript", ""), **d})

    probes = write_probes(args.out)
    probe_rows = []
    for label, path, description in probes:
        off_text, _oc, _os = transcribe(transcriber.model, path, False)
        on_text, _nc, _ns = transcribe(transcriber.model, path, True)
        probe_rows.append({"probe": label, "description": description,
                           "text_off": off_text, "text_on": on_text})

    # ---------------------------------------------------------------- report
    spoken, card_notes = scorer.reference_card(args.faults, args.card)
    def as_set(side: str, subset: list[dict]) -> list[dict]:
        """One side of one subset, in the shape score_attempts wants.

        Args:
            side: "off", "on" or "stored".
            subset: The rows to include.

        Returns:
            One {item, raw_transcript} dict per row.
        """
        key = "stored" if side == "stored" else f"text_{side}"
        return [{"item": r["item"], "raw_transcript": r[key]} for r in subset]

    kept = [r for r in rows if not is_loop(r)]
    dropped = [r for r in rows if is_loop(r)]

    print(f"\nVAD comparison - {args.run.name}, faster-whisper {args.model}, "
          f"{len(clips)} clip(s), {len(rows)} attempt(s)")
    print("\n".join(notes))
    if collapsed:
        print(f"  {collapsed} duplicate (item, attempt) record(s) collapsed, "
              "last one kept, as score.py does with the same file")
    if missing:
        print(f"  {len(missing)} attempt(s) have no clip on disk and are "
              "left out entirely")
    print()
    print(table(rows))

    print("\n  Character error rate, both sides scored by score.py against "
          "the walker card")
    print("\n".join(card_notes))
    print()
    print(scorer.overall_table([
        ("vad_filter=False", scorer.score_attempts(as_set("off", rows),
                                                   spoken)),
        ("vad_filter=True", scorer.score_attempts(as_set("on", rows), spoken)),
        ("vad_filter=False, no loops",
         scorer.score_attempts(as_set("off", kept), spoken)),
        ("vad_filter=True, no loops",
         scorer.score_attempts(as_set("on", kept), spoken)),
        ("stored (not a baseline)",
         scorer.score_attempts(as_set("stored", rows), spoken)),
    ]))
    print("  the stored row is the run's own transcripts, shown for drift "
          "only: no file records which model produced them, so it is not a "
          "baseline and the VAD effect is the first two rows.")
    print(f"  the two no-loops rows drop every attempt at "
          f"{', '.join(LOOP_ITEMS)}, where the decoder ran away and filled "
          f"the transcript with one repeated token. Those insertions dominate "
          f"the first two rows, so read the pair: the full rows say how often "
          f"the decode failed, the no-loops rows say how well a tag is heard "
          f"when it did not.")
    if dropped:
        print(f"  {len(dropped)} attempt(s) dropped from the no-loops rows:")
        for r in sorted(dropped, key=lambda r: (r["item"], r["attempt_no"])):
            off = clip_cer(scorer, r, "off", spoken)
            on = clip_cer(scorer, r, "on", spoken)
            print(f"      {r['item']:<7} a{r['attempt_no']}  "
                  f"CER off {scorer.pct(off)}, on {scorer.pct(on)}  "
                  f"({len(r['text_off'])} chars off, "
                  f"{len(r['text_on'])} on)")
        print("      the clean re-reads of those items go too, which can only "
              "raise the no-loops CER, never flatter it.")
    else:
        print(f"  no attempt at {', '.join(LOOP_ITEMS)} is in this set, so "
              f"the no-loops rows are the full rows.")

    print("\n  Character error rate per clip, worst first")
    print(per_clip_table(scorer, rows, spoken))

    changed = changed_rows(rows)
    print(f"\n  {len(changed)} of {len(rows)} attempt(s) changed transcript:")
    for r in changed:
        print(f"      {r['item']:<7} a{r['attempt_no']}  "
              f"off {r['text_off']!r}")
        print(f"      {'':<7}     on  {r['text_on']!r}")
    if not changed:
        print("      none -- on this run VAD changed no transcript at all")

    emptied = [r for r in rows
               if r["text_off"].strip() and not r["text_on"].strip()]
    strips_emptied = [r for r in emptied if r["item"].startswith("-X")]
    print(f"\n  VAD emptied {len(emptied)} attempt(s) that had text without "
          f"it, {len(strips_emptied)} of them strips:")
    for r in emptied:
        mark = "STRIP " if r["item"].startswith("-X") else ""
        print(f"      {mark}{r['item']:<7} a{r['attempt_no']}  "
              f"was {r['text_off']!r}")
    if not emptied:
        print("      none")

    strips = [r for r in rows if r["item"].startswith("-X")]
    print(f"\n  All {len(strips)} strip attempt(s), the ones that abstained "
          "live:")
    for r in sorted(strips, key=lambda r: (r["item"], r["attempt_no"])):
        print(f"      {r['item']:<5} a{r['attempt_no']}  "
              f"off {r['text_off']!r}")
        print(f"      {'':<5}     on  {r['text_on']!r}")

    print("\n  Probes -- neither clip contains speech, so any text is invented:")
    for p in probe_rows:
        print(f"      {p['probe']:<8} {p['description']}")
        print(f"      {'':<8} off {p['text_off']!r}")
        print(f"      {'':<8} on  {p['text_on']!r}")

    # ---------------------------------------------------------------- files
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "vad_compare.json").write_text(json.dumps(
        {"run": args.run.name, "model": args.model, "decode": DECODE,
         "noise_dbfs": NOISE_DBFS, "attempts": rows, "probes": probe_rows},
        indent=1, ensure_ascii=False), encoding="utf-8")
    with open(args.out / "vad_compare.csv", "w", newline="",
              encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item", "kind", "attempt_no", "wav", "text_off",
                         "text_on", "changed", "stored", "conf_off", "conf_on",
                         "secs_off", "secs_on"])
        for r in rows:
            writer.writerow([r["item"], r["kind"], r["attempt_no"], r["wav"],
                             r["text_off"], r["text_on"],
                             r["text_off"] != r["text_on"], r["stored"],
                             r["conf_off"], r["conf_on"],
                             round(r["secs_off"], 3), round(r["secs_on"], 3)])
    print(f"\n  wrote {args.out / 'vad_compare.json'}")
    print(f"  wrote {args.out / 'vad_compare.csv'}")
    print(f"  {args.run} was not written to.")


if __name__ == "__main__":
    main()
