"""Tests for Block 9 (score.py): label swaps and what counts against a run.

A swap is one fault planted at two positions (item and item_b). It is
caught from either end, takes one place in the denominator, and neither
end can be charged as a false flag. Known-miss positions are carried by
the study and enter neither metric.

Every case below is built from a synthetic report, not a recorded run:
these fix the definitions, not the cabinet.
"""

import pytest

from redlining.score import score


def attempt(item: str, flagged: bool, band: int = 1, attempt_no: int = 1) -> dict:
    """One final attempt at one position, as report.json carries it."""
    return {
        "item": item,
        "attempt_no": attempt_no,
        "flagged": flagged,
        "band": band,
        "outcome": "FLAG" if flagged else "OK",
        "audio_path": f"audio/{item}.wav",
    }


def run(*attempts: dict) -> dict:
    return {"run_id": "test", "items_expected": len(attempts), "complete": True,
            "items": list(attempts)}


def fault(item: str, item_b: str = "", detectable: str = "yes") -> dict:
    return {"item": item, "item_b": item_b, "detectable": detectable,
            "fault_class": "test fault"}


def test_swap_caught_at_item_b_with_item_unwalked():
    """A flag at the B end catches the swap even if the A end is never walked."""
    s = score(run(attempt("-X2", True)), [fault("-X1", "-X2")])
    assert (s["caught"], s["missed"], s["not_walked"]) == (1, 0, 0)


def test_swap_counts_once_in_the_denominator():
    """Two positions, one fault: the denominator sees one, not two."""
    s = score(run(attempt("-X2", True)), [fault("-X1", "-X2")])
    assert s["planted"] == 1 and s["detection_rate"] == 1.0


def test_swap_missed_when_both_ends_walked_and_neither_flagged():
    """Both ends reached and silent is a miss, not an unscorable row."""
    s = score(run(attempt("-X3", False), attempt("-X4", False)),
              [fault("-X3", "-X4")])
    assert (s["caught"], s["missed"], s["not_walked"]) == (0, 1, 0)


def test_swap_with_one_end_unwalked_is_not_scorable():
    """One end unreached and the other unflagged: not walked, not missed.

    The unreached end might have carried the flag, so the run cannot be
    charged with a miss it was never given the chance to make.
    """
    s = score(run(attempt("-X5", False)), [fault("-X5", "-X6")])
    assert (s["caught"], s["missed"], s["not_walked"]) == (0, 0, 1)
    assert s["detection_rate"] is None          # nothing scorable in the set


def test_neither_end_of_a_swap_is_a_false_flag():
    """The flag that caught the swap is not also charged as a false one."""
    s = score(run(attempt("-X1", True), attempt("-X2", True)),
              [fault("-X1", "-X2")])
    assert s["false_flags"] == 0 and s["precision"] == 1.0


def test_false_flag_at_an_unplanted_item():
    """A flag where nothing was planted is the only kind that counts false."""
    s = score(run(attempt("-X7", True), attempt("-Q1", True)),
              [fault("-X7")])
    assert s["false_flags"] == 1
    assert s["false_flag_rows"][0]["item"] == "-Q1"
    assert s["precision"] == 0.5


def test_flag_at_a_known_miss_position_enters_neither_metric():
    """Known misses are carried, not scored: no denominator, no false flag."""
    s = score(run(attempt("-X9", True)), [fault("-X9", detectable="no")])
    assert s["planted"] == 0 and s["detection_rate"] is None
    assert s["false_flags"] == 0 and s["precision"] is None
    assert s["known_miss_flagged"] == 1


def test_flag_at_the_b_end_of_a_known_miss_swap_is_not_false():
    """The exclusion reaches both ends of a known-miss swap too."""
    s = score(run(attempt("-X10", True)), [fault("-X9", "-X10", detectable="no")])
    assert s["false_flags"] == 0
    assert s["known_miss_flagged"] == 1


def test_swap_is_banded_at_the_end_that_caught_it():
    """Band credit follows the flagged position, not the A end by default."""
    s = score(run(attempt("-X1", False, band=1), attempt("-X2", True, band=3)),
              [fault("-X1", "-X2")])
    assert s["per_band"][3]["caught"] == 1
    assert s["per_band"][1]["caught"] == 0


def test_blank_item_b_is_a_single_position_fault():
    """An empty item_b must not invent a second position."""
    s = score(run(attempt("-X8", False)), [fault("-X8", "")])
    assert (s["missed"], s["not_walked"], s["swaps"]) == (1, 0, 0)
