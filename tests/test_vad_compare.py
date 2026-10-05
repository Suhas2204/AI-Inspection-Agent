"""Tests for the VAD side experiment's attempt loader.

One thing is tested here: that vad_compare and score.py agree about how many
attempts a run has. They did not. score.py keys attempts by
(item, attempt_no) and keeps the last record; vad_compare appended every
line, so run 20260927-130613 -- whose -7F9 attempt 1 is written twice after
a page reload -- was 73 attempts to one script and 72 to the other, and the
duplicate was a runaway decode counted twice in the headline CER.

The module is loaded by path, the way vad_compare loads score.py, because
experiments/ is not an importable package.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[1]
          / "experiments" / "block05_asr" / "vad_compare.py")


@pytest.fixture(scope="module")
def vc():
    """The vad_compare module, imported by path."""
    spec = importlib.util.spec_from_file_location("vad_compare_under_test",
                                                  SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_run(root: Path, records: list[dict]) -> Path:
    """Build a minimal run folder with the given attempts and their clips.

    Args:
        root: Folder to build in.
        records: Attempt dicts; each one's audio_path basename is created.

    Returns:
        The run folder.
    """
    audio = root / "audio"
    audio.mkdir(parents=True)
    lines = []
    for rec in records:
        name = Path(rec["audio_path"]).name
        (audio / name).write_bytes(b"")
        lines.append(json.dumps(rec))
    (root / "attempts.jsonl").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")
    return root


def attempt(item: str, attempt_no: int, transcript: str) -> dict:
    """One attempt record, as attempts.jsonl carries it.

    Args:
        item: Tag.
        attempt_no: Attempt number.
        transcript: raw_transcript, used to tell two records apart.

    Returns:
        The record.
    """
    return {"item": item, "kind": "device", "attempt_no": attempt_no,
            "raw_transcript": transcript,
            "audio_path": f"C:/elsewhere/{item.lstrip('-')}_tag_a{attempt_no}.wav"}


def test_a_repeated_item_and_attempt_is_collapsed(vc, tmp_path):
    """Two records for one (item, attempt) become one, and it is reported."""
    run = write_run(tmp_path / "run", [
        attempt("-7F9", 1, "first write"),
        attempt("-7F9", 1, "second write"),
        attempt("-7F9", 2, "Minus 7F9"),
    ])

    attempts, collapsed = vc.load_attempts(run)

    assert collapsed == 1
    assert len(attempts) == 2
    assert [(a["item"], a["attempt_no"]) for a in attempts] == [("-7F9", 1),
                                                                ("-7F9", 2)]


def test_the_last_record_wins(vc, tmp_path):
    """A re-recorded attempt keeps the later text, as score.py does."""
    run = write_run(tmp_path / "run", [
        attempt("-7F9", 1, "first write"),
        attempt("-7F9", 1, "second write"),
    ])

    attempts, _collapsed = vc.load_attempts(run)

    assert [a["raw_transcript"] for a in attempts] == ["second write"]


def test_nothing_is_collapsed_when_nothing_repeats(vc, tmp_path):
    """A clean run is untouched and reports no duplicates."""
    run = write_run(tmp_path / "run", [
        attempt("-1F1", 1, "Minus 1 F1"),
        attempt("-1F1", 2, "Minus 1 F1"),
        attempt("-5F2", 1, "Minus 5 F2"),
    ])

    attempts, collapsed = vc.load_attempts(run)

    assert collapsed == 0
    assert len(attempts) == 3


def test_the_real_run_has_exactly_one_duplicate(vc):
    """The run this was found in: 73 records, 72 attempts, 1 collapsed.

    Skipped where the run folder is not present, so the suite still passes on
    a checkout without runs/.
    """
    if not (vc.RUN / "attempts.jsonl").exists():
        pytest.skip(f"{vc.RUN} is not on this machine")

    attempts, collapsed = vc.load_attempts(vc.RUN)

    assert collapsed == 1
    assert len(attempts) == 72
    keys = [(a["item"], a["attempt_no"]) for a in attempts]
    assert len(keys) == len(set(keys))


def test_a_run_without_attempts_stops(vc, tmp_path):
    """No attempts.jsonl is a hard failure, not an empty comparison."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit):
        vc.load_attempts(empty)
