"""Tests for Block 7's LLM front end (orchestrator.py).

Four things are pinned here, and the first two are the ones that matter:

1. A verdict reached through the orchestrator is the verdict the scripted
   path reaches for the same reading. Not "close to" -- the same field for
   the same attempt. If this ever fails, the orchestrator has started
   deciding something.
2. No expected tag and no schematic answer reaches the model, scanned word
   by word over every message the orchestrator originates, with the reads
   deliberately CORRECT so that the read and the answer coincide and the
   scan has every chance to catch a leak.
3. An utterance the model does not understand produces a question, not a
   guessed tool call. Guessing submit_reading would put words in the
   trainee's mouth and get them scored.
4. skip and repeat do what they say: skip leaves the position out of the
   log entirely (which score.py already reads as "not walked"), and repeat
   costs nothing.
"""

import json
import re

import pytest

from redlining.adjudicate import ABSTAIN, MATCH, Adjudicator
from redlining.checklist import load_checklist
from redlining.normalise import compact
from redlining.orchestrator import (
    SECRET_KEYS,
    SYSTEM_PROMPT,
    TOOL_NAMES,
    TOOLS,
    MockLLM,
    Orchestrator,
    Reply,
    ToolCall,
    redact,
    secrets_of,
)
from redlining.paths import DECISIONS, SCHEMATIC
from redlining.report import RunLog
from redlining.score import load_faults, score
from redlining.session import MAX_REASKS, ScriptedInput, run

WORDS = re.compile(r"[A-Za-z0-9]+")


@pytest.fixture(scope="module")
def adj() -> Adjudicator:
    """Adjudicator loaded once per module from the cleaned schematic."""
    return Adjudicator.from_export(SCHEMATIC)


@pytest.fixture(scope="module")
def checklist() -> list:
    """The whole checklist, in the order every path walks it."""
    return load_checklist()


@pytest.fixture(scope="module")
def mixed(checklist) -> list:
    """Six devices and three strips: both kinds of reading in one list."""
    devices = [i for i in checklist if i.kind == "device"][:6]
    strips = [i for i in checklist if i.kind == "strip"][:3]
    return devices + strips


def correct_reading(adj: Adjudicator, item) -> str:
    """What the schematic says is at this position, as a trainee would say it.

    The same values ScriptedInput feeds back in, which is what makes the two
    paths comparable. The test is allowed to know these; the orchestrator and
    the model are not.

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


def recorded(log: RunLog) -> list[dict]:
    """Attempts as written to attempts.jsonl, minus the volatile timestamp.

    Args:
        log: RunLog whose attempts file is read.

    Returns:
        One dict per attempt, in the order recorded.
    """
    lines = log.attempts_path.read_text(encoding="utf-8").splitlines()
    return [{k: v for k, v in json.loads(line).items() if k != "at"}
            for line in lines]


def drive(adj, items, log, utterances) -> Orchestrator:
    """Build an orchestrator over `items` and say each utterance to it.

    Args:
        adj: Adjudicator.
        items: Checklist items.
        log: RunLog.
        utterances: Trainee lines, in order.

    Returns:
        The orchestrator, after the last utterance.
    """
    orc = Orchestrator(adj, items, log, MockLLM())
    for line in utterances:
        orc.say(line)
    return orc


# ------------------------------------------- 1. the same verdicts as scripted

# Compared field by field. raw_transcript is left out on purpose and checked
# separately below: ScriptedInput fills part_raw and rating_raw as well as
# tag_raw, and Read.raw joins every non-empty field, so the scripted path's
# raw text carries three values where a tag-mode reading carries one. The
# VERDICT reads only tag_raw in tag mode, which is why the two agree on
# everything that was actually judged.
VERDICT_FIELDS = ("item", "kind", "band", "attempt_no", "spoken_prompt",
                  "normalised", "well_formed", "outcome", "reason",
                  "expected")


def test_verdicts_are_identical_to_the_scripted_path(adj, mixed, tmp_path):
    """Same readings in, same verdicts out, attempt by attempt."""
    scripted_log = RunLog(root=tmp_path, run_id="scripted")
    run(mixed, adj, ScriptedInput(adj), scripted_log)

    said = []
    for item in mixed:
        said.append("where next")
        said.append(correct_reading(adj, item))
    orc_log = RunLog(root=tmp_path, run_id="orchestrated")
    drive(adj, mixed, orc_log, said)

    scripted, orchestrated = recorded(scripted_log), recorded(orc_log)
    assert len(scripted) == len(orchestrated) == len(mixed)
    for a, b in zip(scripted, orchestrated):
        for key in VERDICT_FIELDS:
            assert a[key] == b[key], f"{key} differs at {a['item']}"


def test_every_scripted_reading_matches_through_the_orchestrator(adj, mixed,
                                                                 tmp_path):
    """The correct reading is a MATCH here too, so the comparison is not vacuous.

    Two paths that both abstained on everything would also be "identical".
    """
    said = []
    for item in mixed:
        said += ["where next", correct_reading(adj, item)]
    orc = drive(adj, mixed, RunLog(root=tmp_path, run_id="all-match"), said)

    assert {a["outcome"] for a in recorded(orc.log)} == {MATCH}


def test_the_raw_transcript_is_the_trainee_text_unedited(adj, mixed, tmp_path):
    """Whatever was said is what gets logged -- a misread stays a misread."""
    orc = drive(adj, mixed[:1], RunLog(root=tmp_path, run_id="raw"),
                ["where next", "minus 9 F 9"])
    attempt, = recorded(orc.log)
    assert attempt["raw_transcript"] == "minus 9 F 9"


# --------------------------------------------- 2. nothing leaks to the model

def leaks(blob: str, secrets) -> list[str]:
    """Words of `blob` that are secrets.

    Args:
        blob: Any text bound for the model.
        secrets: From secrets_of().

    Returns:
        The offending words.
    """
    return [w for w in WORDS.findall(blob) if compact(w) in secrets]


def test_no_secret_reaches_the_model_over_a_whole_walk(adj, checklist,
                                                       tmp_path):
    """Scan every orchestrator message of a full 70-position walk.

    The readings are CORRECT on purpose. A correct read equals the answer, so
    this is the run where a leak is most likely and where a redaction that
    only dropped the "expected" key would still be caught.
    """
    said = []
    for item in checklist:
        said += ["where next", correct_reading(adj, item)]
    orc = drive(adj, checklist, RunLog(root=tmp_path, run_id="full"), said)

    assert len(recorded(orc.log)) == len(checklist), "the walk really ran"
    found = []
    for message in orc.orchestrator_messages:
        found += [(message.get("name") or message["role"], w)
                  for w in leaks(json.dumps(message), orc.secrets)]
    assert not found, f"secrets reached the model: {found[:10]}"


def test_every_tool_result_is_clean_on_its_own(adj, checklist, tmp_path):
    """Each tool, called directly, produces a message with no secret in it."""
    orc = Orchestrator(adj, checklist, RunLog(root=tmp_path, run_id="tools"),
                       MockLLM())
    orc.call("next_location")
    orc.call("explain_location")
    orc.call("repeat")
    orc.call("progress")
    orc.hear(correct_reading(adj, checklist[0]))
    orc.call("submit_reading")
    orc.call("skip")
    for message in orc.orchestrator_messages:
        assert not leaks(json.dumps(message), orc.secrets), message


def test_the_prompt_and_the_schemas_name_nothing_in_the_cabinet(adj,
                                                                checklist):
    """The static text is static: no tag, part number or rating in it."""
    secrets = secrets_of(adj, checklist)
    assert not leaks(SYSTEM_PROMPT, secrets)
    assert not leaks(json.dumps(TOOLS), secrets)


def test_the_verdict_is_withheld_as_well_as_the_answer(adj, checklist,
                                                       tmp_path):
    """The model learns whether to ask again, not whether the trainee was right.

    "mismatch" names no tag, so the scan above would never catch it. It is
    withheld anyway: a model that knows the last read was wrong will sooner
    or later tell the trainee, and re-asks in this study are silent.
    """
    orc = Orchestrator(adj, checklist[:1], RunLog(root=tmp_path, run_id="v"),
                       MockLLM())
    orc.call("next_location")
    orc.hear("minus 9 F 9")
    full = orc.call("submit_reading")

    assert full["outcome"] and full["reason"] and full["expected"], \
        "the tool itself returns the whole verdict, unchanged"

    seen = orc.orchestrator_messages[-1]["content"]
    assert "ask_again" in seen
    for withheld in ("outcome", "reason", "expected", "item", "reading"):
        assert withheld not in seen, withheld


def test_the_trainee_utterance_is_the_one_thing_passed_through(adj, checklist,
                                                               tmp_path):
    """Documents the single exception, so it cannot be mistaken for a bug.

    A trainee reading a position correctly says the very thing the schematic
    expects. The model has to see those words -- pulling "minus 1 F1" out of
    "it says minus 1 F1" is the whole dispatch job -- and that is the input,
    not a disclosure. The guarantee covers what the ORCHESTRATOR says, which
    is orchestrator_messages.
    """
    tag = checklist[0].tag
    orc = drive(adj, checklist[:1], RunLog(root=tmp_path, run_id="exc"),
                ["where next", tag])

    user = [m for m in orc.messages if m["role"] == "user"]
    assert any(leaks(m["content"], orc.secrets) for m in user), \
        "the utterance does carry the tag, which is the point of this test"
    assert not any(leaks(json.dumps(m), orc.secrets)
                   for m in orc.orchestrator_messages)


# ------------------------------------------------------- redact() on its own

def test_redact_drops_every_withheld_key():
    """A key in SECRET_KEYS goes, whatever is under it."""
    out = redact({k: "anything" for k in SECRET_KEYS} | {"keep": "me"},
                 frozenset())
    assert out == {"keep": "me"}


def test_redact_scrubs_secret_words_from_surviving_strings():
    """The backstop pass: a secret in a field nobody thought about."""
    out = redact({"note": "go to -1F1 and look"}, frozenset({"1F1"}))
    assert "1F1" not in out["note"]
    assert "look" in out["note"]


def test_redact_scrubs_whole_words_only():
    """Redacting "X1" must not mangle an unrelated word containing it."""
    out = redact({"note": "matrix1 and -X1"}, frozenset({"X1"}))
    assert "matrix1" in out["note"]
    assert out["note"].count("[redacted]") == 1


def test_redact_reaches_into_nested_structures():
    """Dicts in lists in dicts, since tool results are not always flat."""
    out = redact({"rows": [{"expected": "-1F1"}, {"note": "-1F1"}]},
                 frozenset({"1F1"}))
    assert out["rows"][0] == {}
    assert "1F1" not in out["rows"][1]["note"]


def test_redact_does_not_mutate_its_input():
    """A tool result is recorded in full after being redacted for the model."""
    payload = {"expected": {"tag": "-1F1"}, "note": "-1F1"}
    redact(payload, frozenset({"1F1"}))
    assert payload == {"expected": {"tag": "-1F1"}, "note": "-1F1"}


def test_secrets_cover_tags_parts_and_ratings(adj, checklist):
    """All three spellings of an answer are secret, not just the tag."""
    secrets = secrets_of(adj, checklist)
    assert compact("-1F1") in secrets
    assert any(p in secrets for p in adj.legal_parts)
    rating = compact(next(iter(adj.devices.values()))["type"])
    assert rating in secrets


# ------------------------------------- 3. an unclear request asks, not guesses

@pytest.mark.parametrize("utterance", [
    "blah blah blah",
    "",
    "hmm",
    "the weather is terrible in here",
])
def test_an_unknown_request_asks_again_instead_of_guessing(adj, checklist,
                                                           tmp_path,
                                                           utterance):
    """No tool runs, nothing is logged, and the trainee is asked again."""
    orc = Orchestrator(adj, checklist[:2],
                       RunLog(root=tmp_path, run_id=f"q{len(utterance)}"),
                       MockLLM())
    orc.call("next_location")
    before = orc.progress()

    out = orc.say(utterance)

    assert "reply" in out and "tool" not in out
    assert "again" in out["reply"].lower()
    assert orc.progress() == before, "no state moved"
    assert not orc.log.attempts_path.exists() or not recorded(orc.log)


class _ScriptedLLM:
    """An LLM that returns decisions from a fixed list, whatever is said.

    For driving the orchestrator past what MockLLM would choose -- including
    a model that tries to supply the reading itself.

    Attributes:
        decisions: Popped in order; the last one repeats once exhausted.
    """

    def __init__(self, decisions):
        """Keep the decisions to hand out.

        Args:
            decisions: ToolCall or Reply objects, in order.
        """
        self.decisions = list(decisions)

    def decide(self, messages, tools):
        """Return the next scripted decision.

        Args:
            messages: Ignored.
            tools: Ignored.

        Returns:
            The next ToolCall or Reply.
        """
        return self.decisions.pop(0) if len(self.decisions) > 1             else self.decisions[0]


def test_the_llm_cannot_substitute_its_own_words_for_the_trainees(
        adj, checklist, tmp_path):
    """A model that submits altered text is ignored; the raw words are judged.

    The strongest form of the guarantee: the trainee misreads, and the model
    tries to submit the CORRECT tag instead -- which would turn a flag into a
    match and make the run measure the model. submit_reading carries no
    words, so what gets normalised, logged and scored is what was said.
    """
    item = checklist[0]
    llm = _ScriptedLLM([ToolCall("next_location"),
                        ToolCall("submit_reading", {"text": item.tag})])
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="alter"),
                       llm)
    orc.say("where next")
    out = orc.say("minus 9 F 9")

    assert out["result"]["reading"] == "minus 9 F 9"
    assert out["result"]["llm_text_ignored"] == item.tag,         "the attempt records that the model tried"

    attempt, = recorded(orc.log)
    assert attempt["raw_transcript"] == "minus 9 F 9"
    assert attempt["normalised"] == "-9F9"
    assert attempt["outcome"] != MATCH,         "the substituted tag would have matched; the spoken one must not"


def test_submit_reading_takes_no_reading_in_its_schema(adj, checklist,
                                                       tmp_path):
    """Intent only: there is no parameter for the model to put words in."""
    schema = next(t for t in TOOLS if t["name"] == "submit_reading")
    assert schema["parameters"]["properties"] == {}
    assert schema["parameters"]["required"] == []


def test_a_carrier_phrase_reaches_the_same_verdict_as_the_bare_reading(
        adj, checklist, tmp_path):
    """"It says minus 1 F1" and "minus 1 F1" are judged identically.

    The carrier phrase is taken off by normalise.CARRIER_PHRASES -- a fixed
    list, applied at the front only, recording what it removed -- so the two
    utterances differ in what the trainee said and in nothing that was
    judged.
    """
    item = checklist[0]
    bare = drive(adj, [item], RunLog(root=tmp_path, run_id="bare"),
                 ["where next", "minus 1 F1"])
    carried = drive(adj, [item], RunLog(root=tmp_path, run_id="carried"),
                    ["where next", "it says minus 1 F1"])

    one, = recorded(bare.log)
    two, = recorded(carried.log)
    for field in VERDICT_FIELDS:
        assert one[field] == two[field], field

    # What the trainee said is still what is kept, and the two differ there.
    assert one["raw_transcript"] == "minus 1 F1"
    assert two["raw_transcript"] == "it says minus 1 F1"


@pytest.mark.parametrize("carrier", [
    "it says", "it reads", "I see", "I read", "the tag is", "that's",
])
def test_every_carrier_phrase_is_routed_as_a_reading(adj, checklist, tmp_path,
                                                     carrier):
    """MockLLM classifies all six as a reading, not as an unclear request."""
    orc = Orchestrator(adj, checklist[:1],
                       RunLog(root=tmp_path, run_id=f"c{len(carrier)}"),
                       MockLLM())
    orc.call("next_location")
    out = orc.say(f"{carrier} minus 1 F1")

    assert out.get("tool") == "submit_reading", out
    attempt, = recorded(orc.log)
    assert attempt["normalised"] == "-1F1"


def test_a_misread_behind_a_carrier_phrase_still_fails(adj, checklist,
                                                       tmp_path):
    """Stripping the lead-in must not repair what follows it.

    -1Q1 is expected at position 1 and carries a planted fault. Saying
    "it says minus 9 F 9" politely does not make it right: the verdict is
    the same one the bare misread gets, and it is not a match.
    """
    item = checklist[0]
    bare = drive(adj, [item], RunLog(root=tmp_path, run_id="mis-bare"),
                 ["where next", "minus 9 F 9"])
    carried = drive(adj, [item], RunLog(root=tmp_path, run_id="mis-carried"),
                    ["where next", "it says minus 9 F 9"])

    one, = recorded(bare.log)
    two, = recorded(carried.log)
    assert one["outcome"] == two["outcome"] != MATCH
    for field in VERDICT_FIELDS:
        assert one[field] == two[field], field


def test_a_carrier_phrase_with_nothing_behind_it_is_asked_for_again(
        adj, checklist, tmp_path):
    """"It says" on its own is not a reading and is not guessed at."""
    orc = Orchestrator(adj, checklist[:1], RunLog(root=tmp_path, run_id="bare-c"),
                       MockLLM())
    orc.call("next_location")
    out = orc.say("it says")

    assert "reply" in out and "tool" not in out
    assert not (orc.log.attempts_path.exists() and recorded(orc.log))


def test_a_misread_still_reaches_the_adjudicator(adj, checklist, tmp_path):
    """The classifier must not swallow a malformed reading.

    A classifier that only submitted well-formed readings would quietly drop
    exactly the defects this study measures.
    """
    orc = drive(adj, checklist[:1], RunLog(root=tmp_path, run_id="mis"),
                ["where next", "minus 9 F 9 9 9"])
    attempt, = recorded(orc.log)
    assert attempt["raw_transcript"] == "minus 9 F 9 9 9"
    assert attempt["outcome"] != MATCH


def test_the_mock_only_ever_names_a_real_tool(adj, checklist, tmp_path):
    """Whatever it decides is either a Reply or a tool that exists."""
    llm = MockLLM()
    orc = Orchestrator(adj, checklist[:3], RunLog(root=tmp_path, run_id="m"),
                       llm)
    # "where next" after the skip on purpose: a skip closes the position, so
    # a reading submitted straight after it has nothing to be judged against
    # and submit_reading refuses it. That refusal has its own test below.
    for utterance in ("where next", "say again", "how far", "where am i",
                      "skip", "where next", "minus 1 F1", "nonsense"):
        orc.say(utterance)
    for call in llm.calls:
        assert isinstance(call, Reply) or call.name in TOOL_NAMES, call


def test_an_unknown_tool_name_is_a_bug_not_a_reply(adj, checklist, tmp_path):
    """call() refuses a name that is not a tool rather than papering over it."""
    orc = Orchestrator(adj, checklist[:1], RunLog(root=tmp_path, run_id="bad"),
                       MockLLM())
    with pytest.raises(KeyError):
        orc.call("delete_everything")


# ------------------------------------------------------ 4. skip and repeat

def test_skip_leaves_the_position_out_of_the_log(adj, checklist, tmp_path):
    """Nothing is written for a skipped position: there was no reading."""
    orc = drive(adj, checklist[:3], RunLog(root=tmp_path, run_id="skip"),
                ["where next", "skip"])

    assert not (orc.log.attempts_path.exists() and recorded(orc.log))
    assert orc.progress()["skipped"] == 1


def test_skip_moves_on_to_the_next_position(adj, checklist, tmp_path):
    """The skipped position is not offered again."""
    orc = Orchestrator(adj, checklist[:3],
                       RunLog(root=tmp_path, run_id="skip2"), MockLLM())
    first = orc.call("next_location")["position"]
    orc.call("skip")
    second = orc.call("next_location")["position"]

    assert second != first
    assert orc.call("next_location")["position"] == second, \
        "asking twice does not skip ahead on its own"


def test_skip_takes_a_position_number_not_a_tag(adj, checklist, tmp_path):
    """A tag argument would hand the model the answer; a number names a place."""
    schema = next(t for t in TOOLS if t["name"] == "skip")
    assert schema["parameters"]["properties"]["item"]["type"] == "integer"

    orc = Orchestrator(adj, checklist[:4],
                       RunLog(root=tmp_path, run_id="skip3"), MockLLM())
    out = orc.call("skip", {"item": 3})
    assert out["skipped"] == 3
    assert 3 not in [orc.call("next_location")["position"] for _ in range(3)]


def test_skipping_a_position_that_does_not_exist_is_reported(adj, checklist,
                                                             tmp_path):
    """An out-of-range number comes back as an error, not a silent no-op."""
    orc = Orchestrator(adj, checklist[:2],
                       RunLog(root=tmp_path, run_id="skip4"), MockLLM())
    out = orc.call("skip", {"item": 99})
    assert "error" in out
    assert orc.progress()["skipped"] == 0


def test_a_skipped_planted_fault_scores_as_not_walked(adj, checklist,
                                                      tmp_path):
    """score.py reads the absence correctly, with no new status to teach it.

    -1Q1 is position 1 and carries a planted fault, so skipping it must land
    in not_walked -- neither caught nor missed.
    """
    orc = Orchestrator(adj, checklist, RunLog(root=tmp_path, run_id="nw"),
                       MockLLM())
    orc.call("next_location")
    orc.call("skip")
    orc.finish()

    report = json.loads((orc.log.dir / "report.json").read_text("utf-8"))
    s = score(report, load_faults(DECISIONS / "faults.csv"))
    assert "-1Q1" in [f["item"] for f in s["not_walked_rows"]]


def test_repeat_gives_the_same_location_and_costs_nothing(adj, checklist,
                                                          tmp_path):
    """Same place, same attempt number, nothing logged."""
    orc = Orchestrator(adj, checklist[:2],
                       RunLog(root=tmp_path, run_id="rep"), MockLLM())
    first = orc.call("next_location")

    again = orc.call("repeat")
    assert again["location"] == first["location"]
    assert again["position"] == first["position"]
    assert again["attempt_no"] == first["attempt_no"]
    assert not (orc.log.attempts_path.exists() and recorded(orc.log))

    assert orc.call("next_location")["position"] == first["position"]


def test_repeat_uses_the_wording_the_other_paths_use(adj, checklist, tmp_path):
    """Counts for a strip, a reading for a device -- the silent re-ask lines."""
    device = next(i for i in checklist if i.kind == "device")
    strip = next(i for i in checklist if i.kind == "strip")
    for item, expected in ((device, "Please read it again."),
                           (strip, "Please count them again.")):
        orc = Orchestrator(adj, [item],
                           RunLog(root=tmp_path, run_id=f"w{item.kind}"),
                           MockLLM())
        orc.call("next_location")
        assert orc.call("repeat")["say"] == expected


def test_repeat_before_anything_is_open_says_so(adj, checklist, tmp_path):
    """Nothing to repeat is reported, not invented."""
    orc = Orchestrator(adj, checklist[:1],
                       RunLog(root=tmp_path, run_id="rep0"), MockLLM())
    assert orc.call("repeat") == {"nothing_to_repeat": True}


# --------------------------------------------------- the re-ask budget, reused

def test_the_reask_budget_is_session_runs(adj, checklist, tmp_path):
    """Three attempts on an abstaining position, then it settles. No new policy."""
    orc = Orchestrator(adj, checklist[:2],
                       RunLog(root=tmp_path, run_id="reask"), MockLLM())
    orc.call("next_location")

    asked = []
    for _ in range(MAX_REASKS + 1):
        orc.hear("")
        asked.append(orc.call("submit_reading")["ask_again"])

    assert asked == [True] * MAX_REASKS + [False]
    attempts = recorded(orc.log)
    assert [a["attempt_no"] for a in attempts] == list(
        range(1, MAX_REASKS + 2))
    assert {a["outcome"] for a in attempts} == {ABSTAIN}
    assert orc.call("next_location")["position"] == 2


def test_a_reading_with_no_position_open_raises(adj, checklist, tmp_path):
    """Judging a reading against no position would invent the position."""
    orc = Orchestrator(adj, checklist[:1],
                       RunLog(root=tmp_path, run_id="nopos"), MockLLM())
    with pytest.raises(RuntimeError):
        orc.hear("minus 1 F1")
        orc.call("submit_reading")


# ----------------------------------------------------------------- the report

def test_the_report_is_the_format_score_py_already_reads(adj, mixed, tmp_path):
    """Written by RunLog, so it is the other paths' format by construction."""
    said = []
    for item in mixed:
        said += ["where next", correct_reading(adj, item)]
    orc = drive(adj, mixed, RunLog(root=tmp_path, run_id="rep-fmt"), said)
    orc.finish()

    report = json.loads((orc.log.dir / "report.json").read_text("utf-8"))
    assert report["items_expected"] == len(mixed)
    assert len(report["items"]) == len(mixed)
    assert {"item", "band", "outcome", "flagged", "expected"} <= set(
        report["items"][0])
    assert score(report, load_faults(DECISIONS / "faults.csv"))["run_id"]


def test_the_log_keeps_the_answer_even_though_the_model_never_sees_it(
        adj, checklist, tmp_path):
    """The log is for the reviewer, not the model: expected stays in it.

    Redaction is a boundary, not a filter on the record. score.py needs the
    expected value, and a log that dropped it to protect the model would
    break the scorer to solve a problem the scorer does not have.
    """
    orc = drive(adj, checklist[:1], RunLog(root=tmp_path, run_id="keep"),
                ["where next", "minus 9 F 9"])
    attempt, = recorded(orc.log)
    assert attempt["expected"], "the record keeps what the schematic expected"
    assert not any(leaks(json.dumps(m), orc.secrets)
                   for m in orc.orchestrator_messages)
