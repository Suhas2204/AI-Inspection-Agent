"""Tests for the conversational front end (session --agent).

Offline throughout. No microphone, no sound card, no Whisper, no server: the
loop takes its listen() and say() as arguments, so a test supplies a script
and collects what was spoken. What is pinned here:

1. What the agent says to the TRAINEE. This is a second boundary, pointing
   the other way from orchestrator.redact(): that one decides what the model
   may be told, voice_of decides what the trainee may be told, and the thing
   that must never be said aloud is the verdict. A re-ask in this study is
   silent, so an accepted reading says nothing at all and a rejected one says
   only "read it again".
2. The endpointer, fed levels rather than audio: it waits for speech, ends a
   turn on quiet, and names why it stopped -- "nothing was said" and "they
   talked past the ceiling" are different events.
3. The loop ends when it should and only when it should. Stopping belongs to
   the loop, not the model: there is no end_run tool.
"""

from __future__ import annotations

import itertools
import json
import re

import pytest

from redlining.adjudicate import ABSTAIN, MATCH, Adjudicator
from redlining.audio_input import (
    VAD_FRAME_S,
    Endpointer,
    Speaker,
    _EnterWatcher,
    init_tts,
    rms,
    speak,
)
from redlining.checklist import load_checklist
from redlining.normalise import compact, normalise_tag
from redlining.orchestrator import (
    CLARIFY,
    MockLLM,
    Orchestrator,
    _is_reading,
    secrets_of,
)
from redlining.paths import SCHEMATIC
from redlining.report import RunLog
from redlining.session import (
    CLOSING,
    EXIT_WORDS,
    MAX_REASKS,
    MAX_TURNS,
    NOTHING_OPEN,
    OPENING,
    Heard,
    _is_exit,
    agent_loop,
    dispatch_note,
    voice_of,
)

WORDS = re.compile(r"[A-Za-z0-9]+")


@pytest.fixture(scope="module")
def adj() -> Adjudicator:
    """Adjudicator loaded once per module from the cleaned schematic."""
    return Adjudicator.from_export(SCHEMATIC)


@pytest.fixture(scope="module")
def checklist() -> list:
    """The whole checklist, in the order every path walks it."""
    return load_checklist()


def correct_reading(adj: Adjudicator, item) -> str:
    """What the schematic says is at this position, as a trainee would say it.

    Args:
        adj: The adjudicator holding the cabinet.
        item: A checklist item.

    Returns:
        The reading text.
    """
    if item.kind == "strip":
        counts = adj.expected_counts(item.tag)
        return " ".join(f"{k} {v}" for k, v in counts.items())
    return item.tag


def drive(adj, items, log, said: list[str]):
    """Run the loop over a script, collecting everything spoken.

    Args:
        adj: Adjudicator.
        items: Checklist items.
        log: RunLog.
        said: Trainee turns. Exhausting them ends the loop, as end of file
            would.

    Returns:
        (orchestrator, spoken lines, turns taken).
    """
    orc = Orchestrator(adj, items, log, MockLLM())
    turns_in = iter(said)
    spoken: list[str] = []

    def listen():
        """One scripted turn, or None when the script runs out."""
        return next(turns_in, None)

    taken = agent_loop(orc, listen, spoken.append)
    return orc, spoken, taken


def recorded(log: RunLog) -> list[dict]:
    """Attempts as written, minus the volatile timestamp.

    Args:
        log: RunLog whose attempts file is read.

    Returns:
        One dict per attempt, in order.
    """
    if not log.attempts_path.exists():
        return []
    return [{k: v for k, v in json.loads(line).items() if k != "at"}
            for line in log.attempts_path.read_text("utf-8").splitlines()]


# =========================================================== 1. what is said

def test_an_accepted_reading_says_nothing_at_all():
    """The silent re-ask rule, at the speaker. Nothing is revealed, ever."""
    assert voice_of("submit_reading", {"ask_again": False, "outcome": MATCH,
                                       "reason": "tag matches", "attempt_no": 1,
                                       "expected": {"tag": "-1F1"}}) == ""


@pytest.mark.parametrize("kind, expected", [
    ("device", "Please read it again."),
    ("strip", "Please count them again."),
    (None, "Please read it again."),
])
def test_a_reask_says_only_that_and_in_the_usual_wording(kind, expected):
    """The same two lines session.py already uses for a silent re-ask."""
    said = voice_of("submit_reading", {"ask_again": True, "outcome": ABSTAIN,
                                       "reason": "nothing was read"}, kind)
    assert said == expected


def test_the_verdict_is_never_spoken_however_it_came_out(adj, checklist):
    """Outcome, reason and expected are in the result and never in the voice.

    The result carries the whole verdict because the log needs it. A trainee
    who learns the last read was wrong reads the next one differently, so
    none of it is said out loud.
    """
    secrets = secrets_of(adj, checklist)
    item = checklist[0]
    for ask_again in (True, False):
        result = {"recorded": True, "item": item.tag, "reading": "minus 9 F 9",
                  "position": 1, "attempt_no": 1, "ask_again": ask_again,
                  "attempts_left": 2, "outcome": "mismatch",
                  "reason": f"expected {item.tag}, read -9F9",
                  "expected": {"tag": item.tag}}
        said = voice_of("submit_reading", result, item.kind)

        assert "mismatch" not in said and "expected" not in said
        assert not [w for w in WORDS.findall(said) if compact(w) in secrets]


def test_the_terminal_count_is_not_read_out_to_someone_counting_terminals():
    """explain_location carries it, because the walker card prints it.

    Saying it here would answer the question the agent just asked.
    """
    said = voice_of("explain_location",
                    {"position": 7, "frame": "left frame", "row": 3,
                     "place_in_row": 2, "kind": "strip",
                     "location": "left frame, row 3, position 2",
                     "band": 2, "terminals": "12 terminals"})

    assert "12" not in said and "terminal" not in said
    assert "left frame" in said and "row 3" in said


@pytest.mark.parametrize("result, wanted", [
    ({"done": False, "position": 1, "location": "left frame, row 2, "
      "position 1", "kind": "device", "asks_for": "the tag", "attempt_no": 1,
      "remaining": 5}, "Read the tag."),
    ({"done": False, "position": 2, "location": "left frame, row 3, "
      "position 4", "kind": "strip", "asks_for": "terminal counts",
      "attempt_no": 1, "remaining": 4}, "Count the terminals."),
])
def test_next_location_sends_them_somewhere_and_says_what_to_do(result,
                                                                wanted):
    """The location, then the ask. Never what is mounted there."""
    said = voice_of("next_location", result)
    assert said.startswith(result["location"])
    assert said.endswith(wanted)


def test_the_end_of_the_walk_is_announced():
    """done is the one next_location result that is not a place."""
    assert voice_of("next_location", {"done": True, "remaining": 0}) == CLOSING


def test_progress_is_counts_and_nothing_else():
    """No outcome is spoken, for the same reason none is given to the model."""
    said = voice_of("progress", {"positions_total": 70, "read": 12,
                                 "skipped": 2, "remaining": 56,
                                 "position": 13, "attempt_no": 1})
    assert said == "12 read, 2 skipped, 56 to go."


@pytest.mark.parametrize("result, wanted", [
    ({"skipped": 4, "remaining": 9}, "Position 4 skipped. 9 to go."),
    ({"error": "no such position", "asked_for": 99, "positions_total": 70},
     "There is no position 99."),
])
def test_skip_says_what_happened_including_when_nothing_did(result, wanted):
    """An out-of-range number is reported, not silently ignored."""
    assert voice_of("skip", result) == wanted


@pytest.mark.parametrize("tool, result", [
    ("repeat", {"nothing_to_repeat": True}),
    ("explain_location", {"nothing_open": True}),
])
def test_nothing_open_says_so_and_offers_the_way_out(tool, result):
    """A trainee who asks before starting is told how to start."""
    said = voice_of(tool, result)
    assert "Nothing is open" in said and "where next" in said


def test_repeat_gives_the_place_again_with_the_reask_wording():
    """The same wording the keyboard path uses, from the tool's own result."""
    said = voice_of("repeat", {"position": 1, "location": "left frame, row 2,"
                               " position 1", "kind": "device",
                               "attempt_no": 2, "say": "Please read it again."})
    assert said == "left frame, row 2, position 1. Please read it again."


def test_an_unknown_tool_says_nothing_rather_than_guessing():
    """A tool added later is silent here until someone gives it a voice."""
    assert voice_of("some_new_tool", {"anything": 1}) == ""


# ================================================== 2. the endpointer

def frames(gate: Endpointer, level: float, seconds: float) -> str:
    """Feed a stretch of one level, stopping early if the gate does.

    Args:
        gate: The endpointer.
        level: RMS to feed.
        seconds: How much audio to feed.

    Returns:
        The stop reason, or "" if it never stopped.
    """
    for _ in range(max(1, round(seconds / gate.frame_s))):
        reason = gate.feed(level)
        if reason:
            return reason
    return ""


def test_quiet_alone_never_ends_a_turn_that_never_started():
    """Silence before anyone speaks is waiting, not the end of a turn."""
    gate = Endpointer(silence_s=0.5, max_s=10.0)
    assert frames(gate, 0.0, 3.0) == ""
    assert not gate.started


def test_a_turn_ends_after_the_speaker_stops():
    """Speech, then quiet for silence_s, and the turn is over."""
    gate = Endpointer(threshold=0.01, silence_s=0.5, max_s=30.0, onset_s=0.09)
    assert frames(gate, 0.2, 1.0) == "", "still talking"
    assert gate.started
    assert frames(gate, 0.0, 2.0) == "silence"


def test_a_pause_in_the_middle_does_not_end_the_turn():
    """Shorter than silence_s is a breath between words, not an ending."""
    gate = Endpointer(threshold=0.01, silence_s=1.0, max_s=30.0, onset_s=0.09)
    frames(gate, 0.2, 0.5)
    assert frames(gate, 0.0, 0.6) == "", "a pause, not the end"
    assert frames(gate, 0.2, 0.3) == "", "they carried on"
    assert frames(gate, 0.0, 1.2) == "silence"


def test_one_loud_frame_is_a_dropped_tool_not_a_word():
    """Onset needs speech to persist, or a cabinet door starts a turn."""
    gate = Endpointer(threshold=0.01, silence_s=0.5, max_s=10.0, onset_s=0.3)
    frames(gate, 0.5, 0.03)
    assert not gate.started
    assert frames(gate, 0.0, 2.0) == "", "and the blip did not end one either"


def test_nothing_said_is_reported_as_nothing_said():
    """Distinct from a turn that ran long: the loop prints which it was."""
    gate = Endpointer(threshold=0.01, silence_s=0.5, max_s=1.0)
    assert frames(gate, 0.0, 2.0) == "no-speech"


def test_talking_past_the_ceiling_stops_the_turn():
    """A turn cannot hold the run open, however much is being said."""
    gate = Endpointer(threshold=0.01, silence_s=5.0, max_s=1.0, onset_s=0.09)
    assert frames(gate, 0.3, 3.0) == "max"


def test_the_frame_length_is_what_the_recorder_feeds():
    """The default gate is calibrated in the units the recorder hands it."""
    assert Endpointer().frame_s == VAD_FRAME_S


def test_rms_is_zero_for_silence_and_rises_with_level():
    """Fed straight from the recorder's blocks, so shape must not matter."""
    assert rms([]) == 0.0
    assert rms([0.0] * 100) == 0.0
    assert rms([[0.5], [-0.5]]) == pytest.approx(0.5)
    assert rms([0.1] * 10) < rms([0.4] * 10)


# ======================================================== the shared speaker

class _Engine:
    """A pyttsx3 stand-in that records what it was asked to say.

    Attributes:
        built: Every engine ever built by this class, newest last. A class
            attribute on purpose: the bug being guarded against is one
            engine serving several utterances, so the test has to count
            engines across calls, not within one.
    """

    built: list = []

    def __init__(self):
        """Register this engine and start with nothing said."""
        self.said: list[str] = []
        self.waited = 0
        self.stopped = 0
        _Engine.built.append(self)

    @classmethod
    def fresh(cls):
        """Forget every engine built so far.

        Resets _Engine.built explicitly, not cls.built: assigning on a
        subclass would shadow the shared list, and every engine registers
        itself on the base class.

        Returns:
            The class, so it can be passed straight in as a factory.
        """
        _Engine.built = []
        return cls

    def say(self, text):
        """Queue one line.

        Args:
            text: What to speak.
        """
        self.said.append(text)

    def runAndWait(self):  # noqa: N802 -- pyttsx3's own spelling
        """Block until the queue is spoken."""
        self.waited += 1

    def stop(self):
        """Tear the engine down."""
        self.stopped += 1


class _DeadEngine(_Engine):
    """An engine that reports success and makes no sound.

    What pyttsx3 actually does on Windows after its first runAndWait():
    started-utterance fires, runAndWait returns, and nothing is audible.
    Nothing in the API says anything is wrong, which is why this is caught
    by building a new engine every time rather than by checking a result.
    """


def test_each_utterance_gets_an_engine_of_its_own():
    """The fix, stated as the thing that must stay true.

    Measured on this machine: one reused pyttsx3 engine spoke utterance 1 in
    3.45 s and then returned in 0.17 s and 0.09 s, silently, having fired
    started-utterance all three times. pyttsx3.init() cannot help, because
    it memoises per driver and hands the same dead engine back.
    """
    speaker = Speaker(factory=_Engine.fresh())

    for line in ("one", "two", "three"):
        assert speaker.say(line) is True

    assert len(_Engine.built) == 3, "one engine per utterance, not one reused"
    assert [e.said for e in _Engine.built] == [["one"], ["two"], ["three"]]
    assert all(e.waited == 1 for e in _Engine.built)
    assert speaker.spoken == 3 and not speaker.failures


def test_the_engine_is_torn_down_after_it_has_spoken():
    """Built per utterance, so each one is also released per utterance."""
    speaker = Speaker(factory=_Engine.fresh())
    speaker.say("one")

    assert _Engine.built[0].stopped == 1


def test_a_teardown_that_fails_does_not_lose_the_line():
    """stop() raising after the line was spoken is not a failure to speak."""
    class _BadStop(_Engine):
        def stop(self):
            raise RuntimeError("COM already released")

    speaker = Speaker(factory=_BadStop)
    assert speaker.say("one") is True
    assert speaker.spoken == 1 and not speaker.failures


def test_a_speaker_that_cannot_speak_says_so_and_keeps_the_run_going(capsys):
    """Errors are reported and counted, never swallowed and never raised.

    Raising would end a walk over something that is not the walk; swallowing
    is the bug this whole change exists to fix.
    """
    def explode():
        raise OSError("no audio device")

    speaker = Speaker(factory=explode)

    assert speaker.say("one") is False
    assert speaker.say("two") is False
    assert speaker.spoken == 0
    assert len(speaker.failures) == 2
    assert "no audio device" in speaker.failures[0]
    assert "tts failed" in capsys.readouterr().err, "and loudly"


def test_a_failure_part_way_through_is_counted_not_hidden():
    """The second line failing must not look like the second line speaking."""
    attempts = itertools.count(1)

    class _FailsOnce(_Engine):
        def runAndWait(self):
            """Speak, except on the second utterance."""
            if next(attempts) == 2:
                raise RuntimeError("driver went away")
            super().runAndWait()

    speaker = Speaker(factory=_FailsOnce.fresh())
    results = [speaker.say(line) for line in ("one", "two", "three")]

    assert results == [True, False, True]
    assert speaker.spoken == 2 and len(speaker.failures) == 1


def test_speak_prints_and_speaks(capsys):
    """One helper, so the prompts and the replies cannot drift apart."""
    speaker = Speaker(factory=_Engine.fresh())
    speak("left frame, row 2", speaker)

    assert "left frame, row 2" in capsys.readouterr().out
    assert _Engine.built[0].said == ["left frame, row 2"]
    assert speaker.spoken == 1


def test_speak_marks_the_line_it_is_speaking(capsys):
    """The diagnostic the silent failure needed.

    A printed line with no sound looked identical whether speech was off,
    the engine was never built, or the engine had gone quiet. The marker
    separates the first two from the third.
    """
    speak("left frame, row 2", Speaker(factory=_Engine.fresh()))
    assert "[speaking] left frame, row 2" in capsys.readouterr().out


def test_speak_without_a_speaker_prints_without_the_marker(capsys):
    """No TTS is a degradation, not a failure: the run goes on in text."""
    speak("left frame, row 2", None)

    out = capsys.readouterr().out
    assert "left frame, row 2" in out
    assert "[speaking]" not in out, "nothing was spoken, so nothing claims to be"


def test_speak_says_nothing_for_an_empty_line(capsys):
    """An accepted reading speaks nothing, and must not print a blank line."""
    speaker = Speaker(factory=_Engine.fresh())
    speak("", speaker)

    assert capsys.readouterr().out == ""
    assert _Engine.built == [] and speaker.spoken == 0


def test_tts_off_builds_no_engine():
    """--no-speak must not import or start pyttsx3."""
    assert init_tts(False) is None


def test_the_agent_loop_really_reaches_the_speaker(adj, checklist, tmp_path):
    """"Is speak() called at all?" -- answered for a whole walk, not asserted.

    Every line the loop speaks goes through one Speaker, so the engine count
    is the number of lines actually spoken aloud.
    """
    from redlining.audio_input import speak as speak_aloud

    item = checklist[0]
    speaker = Speaker(factory=_Engine.fresh())
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="sp"),
                       MockLLM())
    said = iter(["where next", correct_reading(adj, item), "where next"])
    agent_loop(orc, lambda: next(said, None),
               lambda line: speak_aloud(line, speaker))

    # Opening, the location, then the closing. The accepted reading speaks
    # nothing, which is the one line that must NOT reach the engine.
    assert speaker.spoken == 3, [e.said for e in _Engine.built]
    assert len(_Engine.built) == 3, "a new engine for each of them"
    assert CLOSING in [e.said[0] for e in _Engine.built]



# ----------------------------------------------- the Enter fallback, shared

def test_a_press_from_an_earlier_turn_cannot_end_this_one():
    """One reader for the process, drained at the start of every turn.

    A thread blocked on input() cannot be cancelled, so the old watcher --
    one per turn -- outlived its turn and went on competing for stdin. The
    Enter meant to end turn 9 could be taken by the thread still waiting
    from turn 3, and the turn it was meant for ran to the ceiling instead.
    """
    watcher = _EnterWatcher()
    watcher._presses.put(True)          # a press left over from last turn
    assert watcher.pressed()

    watcher.drain()
    assert not watcher.pressed(), "last turn's press does not end this one"

    watcher._presses.put(True)
    assert watcher.pressed(), "but this turn's press does"


def test_the_reader_is_started_once_however_many_turns():
    """One thread for the run, not one per spoken turn."""
    watcher = _EnterWatcher()
    assert not watcher.started

    started = []
    watcher._read_forever = lambda: started.append(1)
    for _ in range(5):
        watcher.start()

    assert watcher.started


def test_the_recorder_closes_the_microphone_before_anything_is_spoken():
    """Speaking into an open capture stream is how a loop records itself.

    Checked on the source rather than with a sound card: the stream is a
    context manager, and the loop only speaks after listen() has returned.
    """
    import inspect

    from redlining.audio_input import Recorder

    src = inspect.getsource(Recorder.record_until_silence)
    assert src.index("with sd.InputStream") < src.index("return path, reason")
    assert "threading.Thread" not in src, "no per-turn watcher thread"


# ============================================== 3. the loop starts and stops

def test_a_walk_through_the_loop_logs_what_the_other_paths_log(adj, checklist,
                                                               tmp_path):
    """Three positions, read correctly, one turn each way."""
    items = checklist[:3]
    said = []
    for item in items:
        said += ["where next", correct_reading(adj, item)]

    orc, spoken, turns = drive(adj, items, RunLog(root=tmp_path, run_id="w"),
                               said)

    assert turns == len(said)
    attempts = recorded(orc.log)
    assert len(attempts) == 3
    assert {a["outcome"] for a in attempts} == {MATCH}
    assert [a["item"] for a in attempts] == [i.tag for i in items]


def test_the_loop_opens_by_saying_how_to_start(adj, checklist, tmp_path):
    """Spoken before anything is listened for: an empty run still says it."""
    _orc, spoken, turns = drive(adj, checklist[:1],
                                RunLog(root=tmp_path, run_id="o"), [])
    assert turns == 0
    assert len(spoken) == 1 and "where next" in spoken[0]


@pytest.mark.parametrize("word", sorted(EXIT_WORDS))
def test_every_exit_word_ends_the_run(adj, checklist, tmp_path, word):
    """Stopping is the loop's, not the model's: there is no end_run tool."""
    orc, _spoken, turns = drive(adj, checklist[:3],
                                RunLog(root=tmp_path, run_id=f"x{len(word)}"),
                                ["where next", word, "where next"])
    assert turns == 2, "the turn after the exit word was never taken"
    assert not recorded(orc.log)


@pytest.mark.parametrize("utterance", [
    "Done.", "  DONE  ", "that's it", "All done!",
])
def test_an_exit_word_is_recognised_however_it_was_said(utterance):
    """Punctuation, case and spacing are not part of the decision."""
    assert _is_exit(utterance)


@pytest.mark.parametrize("utterance", [
    "I am not done yet", "done with that one, where next", "minus 1 F1",
    "", "stopwatch",
])
def test_an_exit_word_inside_a_sentence_does_not_end_the_run(utterance):
    """Whole utterance only, or a reading could end the walk."""
    assert not _is_exit(utterance)


def test_an_exit_word_is_never_handed_to_the_dispatcher(adj, checklist,
                                                        tmp_path):
    """The model is not consulted about whether the run is over."""
    orc = Orchestrator(adj, checklist[:2], RunLog(root=tmp_path, run_id="nd"),
                       MockLLM())
    agent_loop(orc, iter(["done", "where next"]).__next__, lambda _: None)

    assert orc.llm.calls == [], "nothing reached the dispatcher"


def test_running_out_of_input_ends_the_run(adj, checklist, tmp_path):
    """End of file, or a microphone that closed. Not an error."""
    _orc, _spoken, turns = drive(adj, checklist[:2],
                                 RunLog(root=tmp_path, run_id="eof"),
                                 ["where next"])
    assert turns == 1


def test_the_last_position_ends_the_walk(adj, checklist, tmp_path):
    """next_location reporting done is a terminus, and it is announced."""
    item = checklist[0]
    orc, spoken, _turns = drive(adj, [item],
                                RunLog(root=tmp_path, run_id="end"),
                                ["where next", correct_reading(adj, item),
                                 "where next", "where next"])
    assert CLOSING in spoken
    assert spoken[-1] == CLOSING, "and nothing was said after it"


def test_the_loop_cannot_run_for_ever(adj, checklist, tmp_path):
    """A ceiling, for the same reason a spoken turn has one."""
    orc = Orchestrator(adj, checklist, RunLog(root=tmp_path, run_id="cap"),
                       MockLLM())
    turns = agent_loop(orc, lambda: "how far through are we",
                       lambda _: None, max_turns=5)
    assert turns == 5


def test_an_unclear_turn_is_passed_on_as_a_question(adj, checklist, tmp_path):
    """The dispatcher's reply is spoken; no tool ran and nothing was logged."""
    orc, spoken, _turns = drive(adj, checklist[:2],
                                RunLog(root=tmp_path, run_id="q"),
                                ["where next", "the weather is terrible"])
    assert CLARIFY in spoken
    assert not recorded(orc.log)


def test_silence_is_passed_on_rather_than_swallowed(adj, checklist, tmp_path):
    """An empty turn is what the mic returns when nothing was said.

    It goes to the dispatcher, which asks again. A loop that re-recorded
    instead would hide the one thing a run needs to notice.
    """
    orc, spoken, turns = drive(adj, checklist[:1],
                               RunLog(root=tmp_path, run_id="sil"),
                               ["where next", ""])
    assert turns == 2
    assert spoken[-1] == CLARIFY


def test_a_misread_through_the_loop_is_still_a_misread(adj, checklist,
                                                       tmp_path):
    """The loop carries words; it does not tidy them."""
    orc, _spoken, _turns = drive(adj, checklist[:1],
                                 RunLog(root=tmp_path, run_id="mis"),
                                 ["where next", "minus 9 F 9"])
    attempt, = recorded(orc.log)
    assert attempt["raw_transcript"] == "minus 9 F 9"
    assert attempt["outcome"] != MATCH


def walked_aloud(adj, checklist, tmp_path, run_id):
    """Walk every position correctly and collect what was said aloud.

    Correct readings on purpose: the read and the answer then coincide,
    which is where a leak would show.

    Args:
        adj: Adjudicator.
        checklist: Every item.
        tmp_path: pytest temporary directory.
        run_id: Run folder name.

    Returns:
        (orchestrator, spoken lines).
    """
    said = []
    for item in checklist:
        said += ["where next", correct_reading(adj, item)]
    orc, spoken, _turns = drive(adj, checklist,
                                RunLog(root=tmp_path, run_id=run_id), said)
    assert len(recorded(orc.log)) == len(checklist), "the walk really ran"
    return orc, spoken


def test_no_device_tag_part_or_rating_is_ever_spoken(adj, checklist,
                                                     tmp_path):
    """The answer at a device is its tag, and it is never said aloud.

    The companion to test_orchestrator's scan of the model's messages: that
    one covers what the MODEL is told, this one covers what reaches the
    trainee's ears. Part numbers and rating lines are in here too -- they
    are the answer in part mode, and nothing speaks them in either.
    """
    orc, spoken = walked_aloud(adj, checklist, tmp_path, "ears")
    strips = {compact(i.tag) for i in checklist if i.kind == "strip"}
    answers = orc.secrets - strips

    leaked = [(line, w) for line in spoken
              for w in WORDS.findall(line) if compact(w) in answers]
    assert not leaked, f"spoken aloud: {leaked[:5]}"


def test_the_only_secret_spoken_is_the_strip_name_in_its_own_prompt(
        adj, checklist, tmp_path):
    """A decision, pinned here so it cannot happen by accident later.

    A strip's location IS its name -- "left frame, row 1, strip X1" is
    item.spoken, which step_item records as the spoken_prompt and which the
    keyboard and microphone paths have always read out. The agent says the
    same words, and it is not a disclosure: what is adjudicated at a strip
    is the terminal counts, and the name is how the trainee finds the strip
    rather than the answer to anything. No device's tag appears in its own
    prompt (0 of them do), so this exception cannot quietly widen to cover
    the case that would matter.
    """
    orc, spoken = walked_aloud(adj, checklist, tmp_path, "ears2")
    strips = {compact(i.tag) for i in checklist if i.kind == "strip"}

    spoken_secrets = {compact(w) for line in spoken
                      for w in WORDS.findall(line) if compact(w) in orc.secrets}
    assert spoken_secrets <= strips, "something other than a strip name"
    assert spoken_secrets, "and the strip names really were spoken"

    for item in checklist:
        if item.kind == "device":
            assert compact(item.tag) not in compact(item.spoken)



# ------------------------------------------- walking on after a reading

# Settles at position 1 as not_in_schematic, so the walk moves on, and it is
# wrong -- which is the pair the no-disclosure test below needs.
WRONG_BUT_SETTLED = "minus 9 F 9"

# Abstains, so the position is re-asked rather than settled.
ABSTAINS = "minus 9 F 9 9 9"


def test_an_accepted_reading_is_followed_by_the_next_location(adj, checklist,
                                                              tmp_path):
    """The trainee reads, and is sent on without having to ask."""
    items = checklist[:2]
    orc, spoken, _turns = drive(adj, items,
                                RunLog(root=tmp_path, run_id="adv"),
                                ["where next", correct_reading(adj, items[0])])

    assert spoken == [OPENING,
                      f"{items[0].spoken}. Read the tag.",
                      "",                       # the verdict, which is silent
                      f"{items[1].spoken}. Read the tag."]


def test_a_wrong_reading_moves_on_exactly_like_a_right_one(adj, checklist,
                                                           tmp_path):
    """Why advancing automatically is safe, stated as a test.

    The walk advances on a SETTLED reading, whatever the verdict was. If it
    advanced only on a correct one, the trainee would learn the outcome from
    whether they were moved on -- which is the thing silent re-asks exist to
    prevent. So the two must be indistinguishable, and here they are
    compared line for line.
    """
    items = checklist[:2]
    right = drive(adj, items, RunLog(root=tmp_path, run_id="r"),
                  ["where next", correct_reading(adj, items[0])])[1]
    wrong = drive(adj, items, RunLog(root=tmp_path, run_id="w"),
                  ["where next", WRONG_BUT_SETTLED])[1]

    assert right == wrong, "the verdict showed in what was said"

    # And the two really did reach different verdicts, or this proves nothing.
    outcomes = set()
    for run_id, said in (("ro", correct_reading(adj, items[0])),
                         ("wo", WRONG_BUT_SETTLED)):
        orc, _s, _t = drive(adj, items, RunLog(root=tmp_path, run_id=run_id),
                            ["where next", said])
        outcomes.add(recorded(orc.log)[0]["outcome"])
    assert outcomes == {MATCH, "not_in_schematic"}


def test_a_reading_still_being_reasked_does_not_move_on(adj, checklist,
                                                        tmp_path):
    """A re-ask says the re-ask line and nothing else."""
    items = checklist[:2]
    orc, spoken, _turns = drive(adj, items,
                                RunLog(root=tmp_path, run_id="reask"),
                                ["where next", ABSTAINS])

    assert spoken == [OPENING,
                      f"{items[0].spoken}. Read the tag.",
                      "Please read it again."]
    assert orc.current is items[0], "still the same position"


def test_a_strip_being_reasked_is_asked_to_count_again(adj, checklist,
                                                       tmp_path):
    """The other re-ask line, and still nothing else."""
    strip = next(i for i in checklist if i.kind == "strip")
    _orc, spoken, _turns = drive(adj, [strip],
                                 RunLog(root=tmp_path, run_id="rs"),
                                 ["where next", "9 9 9 9 9 9"])

    assert spoken[-1] == "Please count them again."


def test_the_reask_budget_is_spent_then_the_walk_moves_on(adj, checklist,
                                                          tmp_path):
    """Silent while re-asks remain, then settled and moved on, as session.run."""
    items = checklist[:2]
    said = ["where next"] + [ABSTAINS] * (MAX_REASKS + 1)
    _orc, spoken, _turns = drive(adj, items,
                                 RunLog(root=tmp_path, run_id="budget"), said)

    assert spoken[2:2 + MAX_REASKS] == ["Please read it again."] * MAX_REASKS
    assert spoken[-1] == f"{items[1].spoken}. Read the tag.", \
        "the budget ran out, the position settled, and the walk moved on"


def test_one_where_next_is_enough_for_a_whole_walk(adj, checklist, tmp_path):
    """What the change is for: read a position, get sent to the next."""
    items = checklist[:4]
    said = ["where next"] + [correct_reading(adj, i) for i in items]

    orc, spoken, turns = drive(adj, items,
                               RunLog(root=tmp_path, run_id="walk"), said)

    assert turns == len(said)
    assert len(recorded(orc.log)) == len(items)
    assert spoken[-1] == CLOSING, "and the end announced itself"


def test_the_last_reading_ends_the_walk(adj, checklist, tmp_path):
    """Advancing off the final position is the terminus, not an error."""
    item = checklist[0]
    _orc, spoken, turns = drive(adj, [item],
                                RunLog(root=tmp_path, run_id="fin"),
                                ["where next", correct_reading(adj, item),
                                 "where next"])

    assert spoken[-1] == CLOSING
    assert turns == 2, "the turn after the walk ended was never taken"


def test_the_automatic_advance_tells_the_model_no_more_than_a_asked_one(
        adj, checklist, tmp_path):
    """The loop calls the tool, so the transcript is redacted as always."""
    items = checklist[:3]
    said = ["where next"] + [correct_reading(adj, i) for i in items]
    orc, _spoken, _turns = drive(adj, items,
                                 RunLog(root=tmp_path, run_id="adv-leak"),
                                 said)

    found = [w for m in orc.orchestrator_messages
             for w in WORDS.findall(json.dumps(m))
             if compact(w) in orc.secrets]
    assert not found, f"secrets reached the model: {found[:5]}"


# ------------------------------------------------ what the dispatcher chose

def test_a_tool_choice_is_named(adj):
    """The line run 20261006-184627 had no way to produce."""
    assert dispatch_note({"tool": "submit_reading", "arguments": {},
                          "result": {}}) == "[dispatch: submit_reading]"


def test_a_tool_choice_shows_its_arguments():
    """A skip of the wrong position is only visible with the number."""
    note = dispatch_note({"tool": "skip", "arguments": {"item": 4},
                          "result": {}})
    assert note == "[dispatch: skip {'item': 4}]"


def test_the_stock_clarify_is_named_as_one():
    """The classifier did not recognise the utterance."""
    assert dispatch_note({"reply": CLARIFY}) == "[dispatch: clarify]"


def test_a_model_speaking_its_own_words_is_not_called_a_clarify():
    """Choosing to speak and failing to understand are different events."""
    note = dispatch_note({"reply": "Could you read just the tag?"})
    assert note == "[dispatch: the model spoke]"


def test_a_clarify_caused_by_a_failure_names_the_failure():
    """A timeout and a puzzled model produce the same reply and are not the same.

    LlamaCppLLM turns every error into the clarify a puzzled model gives, so
    without this the terminal cannot tell a dead server from a bad routing.
    """
    note = dispatch_note({"reply": CLARIFY},
                         {"kind": "APITimeoutError", "detail": "timed out"})
    assert "APITimeoutError" in note and "timed out" in note


def test_every_turn_prints_what_the_dispatcher_chose(adj, checklist, tmp_path,
                                                     capsys):
    """Over a few turns of mixed kinds, one line each."""
    items = checklist[:2]
    drive(adj, items, RunLog(root=tmp_path, run_id="notes"),
          ["where next", correct_reading(adj, items[0]), "how far",
           "the weather is terrible"])

    printed = [ln.strip() for ln in capsys.readouterr().out.splitlines()
               if "[dispatch:" in ln]
    assert printed == ["[dispatch: next_location]",
                       "[dispatch: submit_reading]",
                       "[dispatch: progress]",
                       "[dispatch: clarify]"]


def test_the_automatic_advance_is_not_reported_as_a_turn(adj, checklist,
                                                         tmp_path, capsys):
    """It was the loop's call, not the dispatcher's choice.

    Printing it as a dispatch would credit the model with a decision it did
    not make, and the point of the line is to show what the model chose.
    """
    items = checklist[:2]
    drive(adj, items, RunLog(root=tmp_path, run_id="adv-note"),
          ["where next", correct_reading(adj, items[0])])

    printed = [ln for ln in capsys.readouterr().out.splitlines()
               if "[dispatch:" in ln]
    assert len(printed) == 2, printed


# ------------------------------------- what run 20261006-184627 actually did

def test_the_run_that_prompted_this_is_pinned(adj, checklist, tmp_path):
    """Why "Minus one q1" was not submitted, kept as a regression.

    Nothing in the text path was at fault. The phrase classifier reads
    "Minus one q1" as a reading and the normaliser maps it to -1Q1, as the
    first two assertions show. What went wrong was the turn BEFORE it: ASR
    heard "where next" as "We're next.", which matches no intent, so no
    position was ever opened -- and a reading with nothing open cannot be
    judged without inventing the position it belongs to.

    Pinned so the two halves cannot be confused again: the classifier is
    right about the reading, and the mishearing is what has to be survived.
    """
    assert _is_reading("Minus one q1"), "the reading itself is recognised"
    assert normalise_tag("Minus one q1").value == "-1Q1"

    assert not _is_reading("We're next."), "and the mishearing is not one"
    orc, spoken, _turns = drive(adj, checklist[:2],
                                RunLog(root=tmp_path, run_id="184627"),
                                ["We're next.", "Minus one q1"])

    # No position open, so the reading is refused rather than guessed at --
    # and the run survives the refusal instead of ending on it.
    assert spoken[1] == CLARIFY, "the mishearing opened nothing"
    assert spoken[2] == NOTHING_OPEN, "and the reading was refused, not judged"
    assert not recorded(orc.log)



# ---------------------------------------- the clip behind every attempt

def test_a_recorded_turn_puts_its_clip_in_the_log(adj, checklist, tmp_path):
    """Block 8's gate: the audio behind any flag must be replayable.

    Flags are not known while recording, so the clip has to be recorded with
    the attempt whatever the verdict was.
    """
    item = checklist[0]
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="clip"),
                       MockLLM())
    clip = str(tmp_path / "audio" / "turn_002.wav")
    said = iter([Heard("where next"),
                 Heard(correct_reading(adj, item), audio_path=clip,
                       confidence=0.83)])
    agent_loop(orc, lambda: next(said, None), lambda _: None)

    attempt, = recorded(orc.log)
    assert attempt["audio_path"] == clip
    assert attempt["confidence"] == 0.83


def test_a_flagged_reading_keeps_its_clip_too(adj, checklist, tmp_path):
    """The attempt a reviewer will actually want to hear."""
    item = checklist[0]
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="clipf"),
                       MockLLM())
    clip = str(tmp_path / "audio" / "turn_002.wav")
    said = iter([Heard("where next"),
                 Heard(WRONG_BUT_SETTLED, audio_path=clip, confidence=0.4)])
    agent_loop(orc, lambda: next(said, None), lambda _: None)

    attempt, = recorded(orc.log)
    assert attempt["outcome"] != MATCH
    assert attempt["audio_path"] == clip


def test_every_attempt_of_a_reasked_position_keeps_its_own_clip(adj, checklist,
                                                                tmp_path):
    """One clip per attempt, not one per position.

    A position re-asked three times was recorded three times, and the
    reviewer needs the attempt that was flagged, not the first one.
    """
    item = checklist[0]
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="clipr"),
                       MockLLM())
    turns = [Heard("where next")]
    turns += [Heard(ABSTAINS, audio_path=f"turn_{n:03d}.wav")
              for n in range(2, 2 + MAX_REASKS + 1)]
    said = iter(turns)
    agent_loop(orc, lambda: next(said, None), lambda _: None)

    paths = [a["audio_path"] for a in recorded(orc.log)]
    assert paths == [f"turn_{n:03d}.wav"
                     for n in range(2, 2 + MAX_REASKS + 1)]


def test_a_typed_turn_records_no_clip_rather_than_a_wrong_one(adj, checklist,
                                                              tmp_path):
    """--text has no audio, and None says so. A path to nothing would lie."""
    item = checklist[0]
    orc, _spoken, _turns = drive(adj, [item],
                                 RunLog(root=tmp_path, run_id="typed"),
                                 ["where next", correct_reading(adj, item)])

    attempt, = recorded(orc.log)
    assert attempt["audio_path"] is None
    assert attempt["confidence"] is None


def test_a_bare_string_is_still_a_turn():
    """Typed and scripted listeners carry nothing, and need not say so."""
    assert Heard.of("where next") == Heard("where next", None, None)
    assert Heard.of(Heard("x", "a.wav", 0.5)) == Heard("x", "a.wav", 0.5)


def test_the_clip_is_never_shown_to_the_model(adj, checklist, tmp_path):
    """It travels with the words to the log, and not into the transcript.

    A file name is not a secret here, but it is not the model's business
    either, and the path is the one place a tag could re-enter by the back
    door -- LiveInput names its clips after the item.
    """
    item = checklist[0]
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="clipm"),
                       MockLLM())
    clip = f"{item.tag.lstrip('-')}_tag_a1.wav"      # the naming LiveInput uses
    said = iter([Heard("where next"),
                 Heard(correct_reading(adj, item), audio_path=clip)])
    agent_loop(orc, lambda: next(said, None), lambda _: None)

    assert recorded(orc.log)[0]["audio_path"] == clip, "the log has it"
    blob = json.dumps(orc.orchestrator_messages)
    assert clip not in blob and ".wav" not in blob, "and the model does not"


# -------------------------------- why "Minus one q1" was not submitted

# Measured against Gemma-4-26B-A4B-it-UD-Q4_K_XL on 6 Oct, with position 1
# open, which is the state run 20261006-184627 was actually in:
#
#     "Minus one q1"      -> reply, "Please read the tag."
#     "minus one q one"   -> reply, "Please read the tag."
#     "minus 1q1."        -> submit_reading
#     "minus 1 q 1"       -> submit_reading
#
# The model routes a tag whose digits arrived as NUMERALS and declines one
# whose digits arrived as WORDS, re-prompting instead. Nothing in this
# project's own text path shares that problem, which is what the test below
# pins: the phrase classifier reads all four as a reading and the normaliser
# maps all four to the same tag.
WORD_FORM_READINGS = ["Minus one q1", "minus one q one"]
NUMERAL_FORM_READINGS = ["minus 1q1.", "minus 1 q 1"]


@pytest.mark.parametrize("said", WORD_FORM_READINGS + NUMERAL_FORM_READINGS)
def test_the_offline_path_reads_digits_as_words_or_numerals_alike(said):
    """Whatever the model does, nothing here depends on how digits arrived.

    So a run on MockLLM would have submitted every one of these, and the
    re-prompt in run 20261006-184627 was the model's decision, not this
    project's classifier or normaliser.
    """
    assert _is_reading(said)
    assert normalise_tag(said).value == "-1Q1"


def test_a_word_form_reading_is_submitted_and_matches(adj, checklist,
                                                      tmp_path):
    """End to end on the offline dispatcher, since that is what we control."""
    item = checklist[0]
    orc, _spoken, _turns = drive(adj, [item],
                                 RunLog(root=tmp_path, run_id="words"),
                                 ["where next", "minus one q one"])

    attempt, = recorded(orc.log)
    assert attempt["raw_transcript"] == "minus one q one"
    assert attempt["normalised"] == "-1Q1"
    assert attempt["outcome"] == MATCH


def test_the_turn_ceiling_is_a_number_not_a_guess():
    """Pinned so it cannot drift into being effectively infinite."""
    assert MAX_TURNS == 400
