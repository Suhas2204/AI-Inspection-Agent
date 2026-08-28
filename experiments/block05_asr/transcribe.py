"""Block 5: transcribe recorded labels with two engines and dump the raw text.

This script does exactly one thing: it turns audio into text, twice, and writes
both results down verbatim. It does NOT normalise, score, correct, or compare
against the schematic. Those are Blocks 4 and 6. Keeping them out of here is the
whole point -- see CONTEXT.md §7 on laundering.

Run:
    export OPENAI_API_KEY=...
    uv run python experiments/block05_asr/transcribe.py experiments/block05_asr/audio/

Outputs, next to the audio:
    transcripts.json   full result, segments with timestamps, both engines
    transcripts.csv    one row per segment, for marking right/wrong by hand

Install:
    uv add openai faster-whisper
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mpga", ".webm"}


def find_audio(target: Path):
    if target.is_file():
        return [target]
    files = sorted(p for p in target.rglob("*") if p.suffix.lower() in AUDIO_SUFFIXES)
    if not files:
        sys.exit(f"No audio found under {target}")
    return files


def transcribe_api(path: Path, language: str):
    """Whisper API. Returns (full_text, segments) or raises."""
    from openai import OpenAI

    client = OpenAI()
    with open(path, "rb") as fh:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=fh,
            language=language,
            # temperature=0 for determinism. Run it twice; the text should not move.
            temperature=0.0,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            # NO prompt. Passing part numbers here biases the decoder toward them
            # and hides exactly the misread this block exists to measure.
        )
    data = result.model_dump()
    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
        for s in data.get("segments") or []
    ]
    return data.get("text", "").strip(), segments


def transcribe_local(path: Path, language: str, model_size: str):
    """Local faster-whisper. Returns (full_text, segments) or raises."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segs, _info = model.transcribe(
        str(path),
        language=language,
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,  # stops one read contaminating the next
    )
    segments = [
        {"start": s.start, "end": s.end, "text": s.text.strip()} for s in segs
    ]
    return " ".join(s["text"] for s in segments).strip(), segments


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path, help="audio file or directory")
    ap.add_argument("--language", default="en")
    ap.add_argument("--local-model", default="large-v3")
    ap.add_argument("--skip-api", action="store_true")
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    files = find_audio(args.target)
    outdir = args.out or (args.target if args.target.is_dir() else args.target.parent)
    outdir.mkdir(parents=True, exist_ok=True)

    if not args.skip_api and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set. Set it, or pass --skip-api.")

    results = []
    for path in files:
        print(f"\n=== {path.name}")
        entry = {"file": str(path), "api": None, "local": None}

        if not args.skip_api:
            try:
                text, segs = transcribe_api(path, args.language)
                entry["api"] = {"text": text, "segments": segs}
                print(f"  api   ({len(segs)} segments): {text[:120]}")
            except Exception as exc:  # a failure is data too -- record it, do not crash
                entry["api"] = {"error": repr(exc)}
                print(f"  api   FAILED: {exc}")

        if not args.skip_local:
            try:
                text, segs = transcribe_local(path, args.language, args.local_model)
                entry["local"] = {"text": text, "segments": segs, "model": args.local_model}
                print(f"  local ({len(segs)} segments): {text[:120]}")
            except Exception as exc:
                entry["local"] = {"error": repr(exc)}
                print(f"  local FAILED: {exc}")

        results.append(entry)

    json_path = outdir / "transcripts.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    # Scoring sheet. One row per segment, longest engine wins the row count.
    csv_path = outdir / "transcripts.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["file", "seg", "start_s", "api_raw", "local_raw",
             "expected", "api_ok", "local_ok", "note"]
        )
        for entry in results:
            api_segs = (entry.get("api") or {}).get("segments") or []
            loc_segs = (entry.get("local") or {}).get("segments") or []
            for i in range(max(len(api_segs), len(loc_segs))):
                a = api_segs[i] if i < len(api_segs) else {}
                l = loc_segs[i] if i < len(loc_segs) else {}
                w.writerow([
                    Path(entry["file"]).name,
                    i,
                    round(a.get("start", l.get("start", 0.0)), 2),
                    a.get("text", ""),
                    l.get("text", ""),
                    "", "", "", "",
                ])

    print(f"\nwrote {json_path}")
    print(f"wrote {csv_path}")
    print("\nNow, by hand: fill `expected` from the label you actually read,")
    print("then mark api_ok / local_ok. Two error rates. Put them in DECISIONS.md.")


if __name__ == "__main__":
    main()
