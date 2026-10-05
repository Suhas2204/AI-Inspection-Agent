"""Tests for the real-model front end (orchestrator.LlamaCppLLM).

Two halves, and only the first runs by default.

Offline. The wire conversion and the failure policy, with no server anywhere:
the tool schemas and the redacted transcript reach the endpoint unchanged in
content, and every way a request can go wrong comes back as the same clarify
Reply MockLLM uses -- never as a guessed tool call. The unreachable-server
case is exercised against a closed port, so it needs no network.

Opt-in integration. Dispatch accuracy and latency against a llama.cpp server,
over about twenty utterances covering every intent. Skipped unless
RUN_LLM_TESTS=1 is set AND the server answers AND it lists the model asked
for, because this is a measurement of a shared machine rather than a property
of the code. Run it with:

    export RUN_LLM_TESTS=1
    uv run pytest tests/test_orchestrator_llm.py -s -k integration

    # and again against the other model
    export LLM_MODEL=Qwen3.8-27B-UD-Q8_K_XL
    uv run pytest tests/test_orchestrator_llm.py -s -k integration

-s matters: the numbers are printed, not asserted. The assertions are a smoke
floor -- that the thing dispatches at all -- and the measurement is the point.
One request per utterance and no retries, because the server is shared.
"""

from __future__ import annotations

import csv
import json
import os
import re
import statistics
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

from redlining.adjudicate import Adjudicator
from redlining.checklist import load_checklist
from redlining.normalise import compact
from redlining.orchestrator import (
    CLARIFY,
    LLM_MODEL,
    LLM_TIMEOUT_S,
    LLM_URL,
    TOOL_NAMES,
    TOOLS,
    LlamaCppLLM,
    Orchestrator,
    Reply,
    ToolCall,
    _arguments_for,
    _wire_messages,
    _wire_tools,
    secrets_of,
)
from redlining.paths import PROCESSED, SCHEMATIC
from redlining.report import RunLog

WORDS = re.compile(r"[A-Za-z0-9]+")

# A port nothing listens on, for the unreachable case. Port 9 is discard and
# is not served here; the connection is refused immediately, so the test is
# fast and needs no network.
DEAD_URL = "http://127.0.0.1:9/v1"


@pytest.fixture(scope="module")
def adj() -> Adjudicator:
    """Adjudicator loaded once per module from the cleaned schematic."""
    return Adjudicator.from_export(SCHEMATIC)


@pytest.fixture(scope="module")
def checklist() -> list:
    """The whole checklist, in the order every path walks it."""
    return load_checklist()


# ===========================================================================
# Offline: what goes on the wire
# ===========================================================================

def test_the_tool_schemas_go_out_unchanged():
    """Same names, descriptions and parameters; only the envelope is added."""
    wired = _wire_tools(TOOLS)

    assert len(wired) == len(TOOLS)
    for sent, original in zip(wired, TOOLS):
        assert sent["type"] == "function"
        assert sent["function"]["name"] == original["name"]
        assert sent["function"]["description"] == original["description"]
        assert sent["function"]["parameters"] == original["parameters"]


def test_submit_reading_still_offers_the_model_nowhere_to_put_words():
    """The no-arguments schema survives the wrapping.

    This is the guarantee from test_orchestrator.py, re-checked on the shape
    that actually reaches a model: if a text parameter appeared here, a model
    could offer a reading and the run would measure the model.
    """
    sent = next(t for t in _wire_tools(TOOLS)
                if t["function"]["name"] == "submit_reading")
    assert sent["function"]["parameters"]["properties"] == {}
    assert sent["function"]["parameters"]["required"] == []


def _words(messages: list[dict]) -> Counter:
    """Every word in a message list's contents, counted.

    The contents are tokenised directly rather than through json.dumps,
    which would escape a newline to a literal backslash-n and glue the "n"
    onto the next word.

    Args:
        messages: Messages whose content is a string or a dict.

    Returns:
        A Counter over the words.
    """
    text = " ".join(
        content if isinstance(content := m["content"], str)
        else json.dumps(content, sort_keys=True) for m in messages)
    return Counter(WORDS.findall(text))


def test_the_transcript_goes_out_with_nothing_added(adj, checklist, tmp_path):
    """Every word the orchestrator holds is sent, and no word more.

    Content, not structure: roles are remapped to get onto the wire, so what
    is pinned here is that the set of words is the same in both directions.
    """
    orc = Orchestrator(adj, checklist[:3], RunLog(root=tmp_path, run_id="w"),
                       LlamaCppLLM(url=DEAD_URL))
    orc.call("next_location")
    orc.hear("where next")
    orc.call("progress")

    held = _words(orc.messages)
    sent = _words(_wire_messages(orc.messages))

    assert not held - sent, f"dropped on the way out: {held - sent}"
    assert sent - held == Counter(
        ["tool", "result"] * 2 + ["next", "location", "progress"]), \
        "the only additions are the labels naming the two tool results"


def test_a_tool_result_is_labelled_rather_than_dropped():
    """The API has nowhere for an unpaired tool result, so it becomes a line."""
    out = _wire_messages([{"role": "system", "content": "rules"},
                          {"role": "tool", "name": "progress",
                           "content": {"remaining": 4}}])

    assert out[0] == {"role": "system", "content": "rules"}
    assert out[1]["role"] == "user"
    assert "progress" in out[1]["content"]
    assert "remaining" in out[1]["content"] and "4" in out[1]["content"]


def test_adjacent_turns_of_one_role_are_joined():
    """Gemma's template rejects two user turns in a row; nothing is lost."""
    out = _wire_messages([{"role": "system", "content": "rules"},
                          {"role": "tool", "name": "repeat",
                           "content": {"say": "Please read it again."}},
                          {"role": "user", "content": "minus 1 F1"}])

    assert [m["role"] for m in out] == ["system", "user"]
    assert "Please read it again." in out[1]["content"]
    assert out[1]["content"].endswith("minus 1 F1")


def test_the_roles_the_api_has_are_kept():
    """system stays system and assistant stays assistant."""
    out = _wire_messages([{"role": "system", "content": "rules"},
                          {"role": "user", "content": "where next"},
                          {"role": "assistant", "content": "Go to the frame."},
                          {"role": "user", "content": "thanks"}])
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]


# --------------------------------------------------- the arguments it accepts

def test_no_arguments_is_an_empty_call():
    """Most tools take none, and a model sending nothing is correct."""
    for raw in (None, "", "  ", "{}"):
        assert _arguments_for("next_location", raw, TOOLS) == {}


def test_a_position_number_arrives_as_an_integer():
    """Sent as a number or as a string of one; both mean the position."""
    assert _arguments_for("skip", '{"item": 3}', TOOLS) == {"item": 3}
    assert _arguments_for("skip", '{"item": "3"}', TOOLS) == {"item": 3}


@pytest.mark.parametrize("raw", [
    '{"item": "the third one"}',
    '{"item": true}',
    '{"item": [3]}',
    '{"item": null}',
])
def test_a_position_that_is_not_a_number_is_malformed(raw):
    """Refused, not guessed at: skipping the wrong position loses a reading."""
    with pytest.raises(ValueError):
        _arguments_for("skip", raw, TOOLS)


@pytest.mark.parametrize("raw", ['{"item": ', 'not json at all', '[1, 2]',
                                 '"a string"'])
def test_arguments_that_are_not_an_object_are_malformed(raw):
    """A half-written call is a malformed call."""
    with pytest.raises(ValueError):
        _arguments_for("skip", raw, TOOLS)


def test_an_undeclared_argument_is_dropped():
    """The tools take no **kwargs, so forwarding one would raise mid-run."""
    assert _arguments_for("next_location", '{"hint": "go left"}', TOOLS) == {}


def test_submit_reading_keeps_what_the_model_tried_to_pass():
    """The one exception, and the reason it is one.

    submit_reading ignores the text and records in the attempt that the model
    supplied it. Dropping it here would protect nothing -- the words are
    ignored either way -- and would erase the evidence that a model tried to
    substitute its own reading for the trainee's.
    """
    out = _arguments_for("submit_reading", '{"text": "-1F1"}', TOOLS)
    assert out == {"text": "-1F1"}


# ------------------------------------------------- failures become a clarify

def test_an_unreachable_server_asks_the_trainee_again():
    """Connection refused: no guess, no exception out of decide()."""
    llm = LlamaCppLLM(url=DEAD_URL, timeout_s=2.0)
    decision = llm.decide([{"role": "user", "content": "where next"}], TOOLS)

    assert decision == Reply(CLARIFY)
    assert len(llm.failures) == 1, llm.failures
    assert len(llm.latencies_s) == 1, "the attempt is still timed"


def test_an_unreachable_server_moves_no_state(adj, checklist, tmp_path):
    """A whole turn through the orchestrator, with the server down."""
    orc = Orchestrator(adj, checklist[:2], RunLog(root=tmp_path, run_id="d"),
                       LlamaCppLLM(url=DEAD_URL, timeout_s=2.0))
    orc.call("next_location")
    before = orc.progress()

    out = orc.say("minus 1 F1")

    assert out == {"reply": CLARIFY}
    assert orc.progress() == before, "no state moved"
    assert not (orc.log.attempts_path.exists()
                and orc.log.attempts_path.read_text(encoding="utf-8").strip())


class _Canned:
    """The smallest stand-in for one chat-completions response.

    Shaped like the object the OpenAI client returns, so _read() can be
    driven over every malformed answer without a server.
    """

    def __init__(self, tool=None, arguments=None, content=None,
                 choices=True):
        """Build a response.

        Args:
            tool: Tool name the model called, or None.
            arguments: Its arguments, as a JSON string.
            content: Text content, or None.
            choices: False for a response with no choices at all.
        """
        function = type("F", (), {"name": tool, "arguments": arguments})
        call = type("C", (), {"function": function})
        message = type("M", (), {
            "tool_calls": [call] if tool else None,
            "content": content,
        })
        self.choices = ([type("Ch", (), {"message": message})]
                        if choices else [])


@pytest.mark.parametrize("response, kind", [
    (_Canned(tool="read_schematic", arguments="{}"), "unknown_tool"),
    (_Canned(tool="skip", arguments='{"item": "left"}'), "bad_arguments"),
    (_Canned(tool="skip", arguments="{broken"), "bad_arguments"),
    (_Canned(content=""), "empty_response"),
    (_Canned(content=None), "empty_response"),
    (_Canned(choices=False), "no_choices"),
])
def test_an_invalid_tool_call_asks_the_trainee_again(response, kind):
    """Every malformed answer is one clarify, recorded as its own kind."""
    llm = LlamaCppLLM(url=DEAD_URL)

    decision = llm._read(response, TOOLS)

    assert decision == Reply(CLARIFY)
    assert [f["kind"] for f in llm.failures] == [kind]


def test_a_tool_the_model_really_called_is_passed_through():
    """The valid case, so the above is not just "everything is a clarify"."""
    llm = LlamaCppLLM(url=DEAD_URL)

    assert llm._read(_Canned(tool="next_location", arguments="{}"),
                     TOOLS) == ToolCall("next_location", {})
    assert llm._read(_Canned(tool="skip", arguments='{"item": 2}'),
                     TOOLS) == ToolCall("skip", {"item": 2})
    assert not llm.failures


def test_the_models_own_words_are_passed_to_the_trainee():
    """Text instead of a tool call is a legitimate answer, not a failure.

    The system prompt asks the model to speak when a request is unclear, so
    its words go through. They cannot carry a secret: it was never told one.
    """
    llm = LlamaCppLLM(url=DEAD_URL)

    decision = llm._read(_Canned(content="Could you read it again?"), TOOLS)

    assert decision == Reply("Could you read it again?")
    assert not llm.failures


# ----------------------------------------------- the rows reach disk at all

def _fake_rows(n: int) -> list[dict]:
    """n rows shaped as the measurement writes them.

    Args:
        n: How many.

    Returns:
        Rows keyed as FIELDS.
    """
    return [{"model": "m", "request_no": i, "utterance": f"said {i}",
             "expected_intent": "skip", "chosen_tool": "skip",
             "correct": True, "latency_s": 0.5 + i, "state": "open",
             "reply_text": ""} for i in range(1, n + 1)]


def test_the_rows_are_written_as_csv_and_json(tmp_path):
    """Both files carry every row, and the CSV header is FIELDS in order."""
    llm = LlamaCppLLM(url=DEAD_URL)
    rows = _fake_rows(3)

    csv_path, json_path = _persist("m", rows, llm, out_dir=tmp_path)

    with csv_path.open(encoding="utf-8", newline="") as fh:
        read = list(csv.DictReader(fh))
    assert tuple(read[0]) == FIELDS
    assert [r["utterance"] for r in read] == ["said 1", "said 2", "said 3"]
    assert [r["latency_s"] for r in read] == ["1.5", "2.5", "3.5"]

    blob = json.loads(json_path.read_text(encoding="utf-8"))
    assert blob["rows"] == rows
    assert blob["measured"] == 3 and blob["utterances"] == len(UTTERANCES)


def test_the_settings_are_written_beside_the_rows(tmp_path):
    """A latency means nothing without the model, endpoint and temperature."""
    llm = LlamaCppLLM(url=DEAD_URL, model="m", timeout_s=60.0)

    _, json_path = _persist("m", _fake_rows(1), llm, out_dir=tmp_path)

    blob = json.loads(json_path.read_text(encoding="utf-8"))
    assert blob["model"] == "m" and blob["url"] == DEAD_URL
    assert blob["temperature"] == 0.0 and blob["timeout_s"] == 60.0
    assert blob["measured_at"].startswith(str(datetime.now().year))


def test_a_run_that_dies_halfway_keeps_what_it_measured(tmp_path):
    """Written after every request, so both files are always complete.

    The scar this is here for: the first sweep printed a summary and
    discarded the rows, and the per-utterance latencies could not be got
    back from the printed aggregates without spending the shared server's
    time again.
    """
    llm = LlamaCppLLM(url=DEAD_URL)

    for n in (1, 2, 3):
        csv_path, json_path = _persist("m", _fake_rows(n), llm,
                                       out_dir=tmp_path)
        with csv_path.open(encoding="utf-8", newline="") as fh:
            assert len(list(csv.DictReader(fh))) == n
        assert len(json.loads(json_path.read_text("utf-8"))["rows"]) == n


def test_the_failures_are_written_too(tmp_path):
    """A row that clarified because the server broke must say so in the file."""
    llm = LlamaCppLLM(url=DEAD_URL, timeout_s=2.0)
    llm.decide([{"role": "user", "content": "where next"}], TOOLS)

    _, json_path = _persist("m", _fake_rows(1), llm, out_dir=tmp_path)

    blob = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(blob["failures"]) == 1
    assert blob["failures"][0]["kind"] and blob["failures"][0]["detail"]


@pytest.mark.parametrize("model, stem", [
    ("Qwen3.8-27B-UD-Q8_K_XL", "Qwen3.8-27B-UD-Q8_K_XL"),
    ("Gemma-4-26B-A4B-it-UD-Q4_K_XL", "Gemma-4-26B-A4B-it-UD-Q4_K_XL"),
    ("vendor/model:v1", "vendor_model_v1"),
    ("../../escape", ".._.._escape"),
])
def test_a_model_name_cannot_climb_out_of_the_output_directory(model, stem):
    """Dots and hyphens are kept; a separator is not."""
    assert _file_stem(model) == stem


def test_the_output_directory_is_under_data_processed():
    """Written where the other generated files live, not next to the tests."""
    assert OUT == PROCESSED / "llm_intent"


def test_the_defaults_are_the_ones_the_study_ran():
    """Pinned because the numbers in the write-up were measured with them."""
    llm = LlamaCppLLM()
    assert llm.temperature == 0.0
    assert llm.timeout_s == LLM_TIMEOUT_S == 60.0
    assert llm.url == LLM_URL and llm.model == LLM_MODEL


def test_the_client_is_not_built_until_a_request_is_made():
    """Constructing one contacts nothing, so an import needs no server."""
    assert LlamaCppLLM(url=DEAD_URL)._client is None


# ===========================================================================
# Opt-in integration: a real model on a shared server
# ===========================================================================

# Every intent the dispatcher has, with utterances a trainee at a cabinet
# would actually produce. Phrasings are varied on purpose -- "where next" is
# in MockLLM's regex, "okay, on to the next one" is not, and a real model
# should get both. "clarify" is an intent too: the right answer to a request
# that is not one is to ask, so an utterance that is not a request belongs in
# the measurement as much as one that is.
#
# Each utterance also names the state it is judged in, because no single
# state makes all seven intents the right answer. Measured from a transcript
# that already holds a location, "where next" can be answered by reading that
# location back out, and a first run of this test watched Gemma do exactly
# that for all four next_location utterances -- scoring the harness, not the
# model. Measured from a transcript with nothing open, a bare reading has no
# position to be judged against. So:
#
#   "fresh"  nothing open yet, as at the start of a run. next_location is
#            the only thing to do, and its own description says "call this
#            to start".
#   "open"   a position has been given out and is waiting for a reading.
#            Every other intent is a live option there.
UTTERANCES = [
    # next_location
    ("where next", "next_location", "fresh"),
    ("what is next", "next_location", "fresh"),
    ("okay, on to the next one", "next_location", "fresh"),
    ("done with that, send me somewhere else", "next_location", "fresh"),
    # submit_reading
    ("minus 1 F1", "submit_reading", "open"),
    ("it says minus 2 K 3", "submit_reading", "open"),
    ("I read minus 1 Q 1", "submit_reading", "open"),
    ("L 3 N 1 PE 1 bracket 1", "submit_reading", "open"),
    # repeat
    ("say that again", "repeat", "open"),
    ("sorry, pardon", "repeat", "open"),
    ("I did not catch where you said", "repeat", "open"),
    # progress
    ("how far through are we", "progress", "open"),
    ("how many are left", "progress", "open"),
    ("what is my progress", "progress", "open"),
    # skip
    ("skip this one", "skip", "open"),
    ("I cannot reach that one, leave it", "skip", "open"),
    ("skip position 4", "skip", "open"),
    # explain_location
    ("I cannot find it, which row is it in", "explain_location", "open"),
    ("whereabouts am I meant to be standing", "explain_location", "open"),
    # clarify: not a request, so the answer is a question
    ("", "clarify", "open"),
    ("the weather is terrible in here", "clarify", "open"),
    ("hmm", "clarify", "open"),
]

# Above chance (1/7 intents, so 14%) by a wide margin, and well below what a
# usable dispatcher would need. A floor, not a result: the printed accuracy
# is the result, and a model that trips this has not dispatched at all.
ACCURACY_FLOOR = 0.5


def _server_models() -> list[str] | None:
    """Model names the endpoint lists, or None if it does not answer.

    A GET on /models, not an inference request: the gate costs the shared
    server nothing.

    Returns:
        The model ids, or None if the server is unreachable or unparseable.
    """
    try:
        with urllib.request.urlopen(f"{LLM_URL}/models", timeout=5) as fh:
            return [m["id"] for m in json.load(fh)["data"]]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def _requires_server() -> None:
    """Skip unless this was asked for and the server can serve it.

    Three separate reasons to skip, reported apart, because "you did not ask
    for this" and "the server is down" are not the same news.
    """
    if os.environ.get("RUN_LLM_TESTS") != "1":
        pytest.skip("opt-in: set RUN_LLM_TESTS=1 to spend requests on the "
                    "shared server")
    available = _server_models()
    if available is None:
        pytest.skip(f"no OpenAI-compatible server at {LLM_URL}")
    if LLM_MODEL not in available:
        pytest.skip(f"{LLM_MODEL} is not served at {LLM_URL}; it lists "
                    f"{available}")


def _contexts(adj, items, tmp_path) -> tuple[Orchestrator, dict[str, list]]:
    """The two transcripts utterances are judged from.

    Each utterance is judged from a short fixed transcript rather than from a
    growing conversation. Two reasons, both about the measurement: an
    utterance's score then depends on the utterance alone and not on what was
    asked before it, and the prompts stay short and nearly the same length,
    so the latencies are comparable to each other.

    Neither context costs a request. The orchestrator calls its own tools, so
    building "open" is free.

    Args:
        adj: Adjudicator.
        items: Checklist items.
        tmp_path: pytest temporary directory.

    Returns:
        (orchestrator, {"fresh": messages, "open": messages}).
    """
    orc = Orchestrator(adj, items, RunLog(root=tmp_path, run_id="llm-acc"),
                       LlamaCppLLM())
    fresh = list(orc.messages)
    orc.call("next_location")
    return orc, {"fresh": fresh, "open": list(orc.messages)}


def _chosen(decision) -> str:
    """The intent name a decision stands for.

    Args:
        decision: A ToolCall or a Reply.

    Returns:
        The tool name, or "clarify" for a reply.
    """
    return decision.name if isinstance(decision, ToolCall) else "clarify"


OUT = PROCESSED / "llm_intent"

# Columns, in the order they are written. The first six are the measurement
# itself; state and reply_text are what make a wrong row diagnosable months
# later, when the only thing left is the file.
FIELDS = ("model", "request_no", "utterance", "expected_intent",
          "chosen_tool", "correct", "latency_s", "state", "reply_text")


def _file_stem(model: str) -> str:
    """A filename for a model name.

    Model names carry dots and hyphens, which are fine in a filename; this
    exists for anything that is not, so a name can never climb out of the
    output directory.

    Args:
        model: Model name as the endpoint knows it.

    Returns:
        The name with every other character replaced by an underscore.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def _persist(model: str, rows: list[dict], llm: LlamaCppLLM,
             out_dir: Path = OUT) -> tuple[Path, Path]:
    """Write every row measured so far, as CSV and as JSON.

    Called after each request rather than once at the end, and both files
    are rewritten whole so neither is ever half-written. The reason is a
    scar: the first sweep of this test printed a summary and discarded the
    rows, and the per-utterance latencies could not be reconstructed from
    the printed aggregates without spending the shared server's time again.
    Rows reach disk before the next request is made, so a run that dies
    halfway still leaves everything it measured.

    The JSON carries the settings as well as the rows. A latency is only
    meaningful next to the model, the endpoint and the temperature it was
    measured at, and a file that will be cited in a write-up should not
    depend on someone remembering them.

    Args:
        model: Model name, which names the files.
        rows: Rows so far, newest last.
        llm: The client, for the settings and the recorded failures.
        out_dir: Where to write. Defaults to data/processed/llm_intent.

    Returns:
        (csv_path, json_path).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{_file_stem(model)}.csv"
    json_path = out_dir / f"{_file_stem(model)}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    json_path.write_text(json.dumps(
        {"model": model,
         "url": llm.url,
         "temperature": llm.temperature,
         "timeout_s": llm.timeout_s,
         "measured_at": datetime.now(timezone.utc).isoformat(
             timespec="seconds"),
         "utterances": len(UTTERANCES),
         "measured": len(rows),
         "failures": llm.failures,
         "rows": rows}, indent=2) + "\n", encoding="utf-8")
    return csv_path, json_path


def _report(model: str, rows: list[dict], llm: LlamaCppLLM) -> float:
    """Print the measurement and return the accuracy.

    Args:
        model: Model name, for the heading.
        rows: One dict per utterance, keyed as FIELDS.
        llm: The client, for its recorded failures.

    Returns:
        Intent accuracy over all rows.
    """
    right = [r for r in rows if r["correct"]]
    accuracy = len(right) / len(rows)
    # The first request is reported apart: on this server an unloaded model is
    # swapped in on demand, so request one can carry a model load that the
    # other twenty-one do not.
    first = rows[0]["latency_s"]
    rest = [r["latency_s"] for r in rows[1:]]

    print(f"\n=== {model} ===")
    print(f"intent accuracy  {len(right)}/{len(rows)} = {accuracy:.0%}")
    print(f"first request    {first:.2f} s  (may include a model load)")
    print(f"latency, n={len(rest)}  median {statistics.median(rest):.2f} s  "
          f"mean {statistics.fmean(rest):.2f} s  "
          f"min {min(rest):.2f} s  max {max(rest):.2f} s")

    by_intent: dict[str, list[dict]] = {}
    for row in rows:
        by_intent.setdefault(row["expected_intent"], []).append(row)
    print("per intent:")
    for intent, group in by_intent.items():
        hits = sum(1 for r in group if r["correct"])
        print(f"  {intent:<18} {hits}/{len(group)}")

    wrong = [r for r in rows if not r["correct"]]
    if wrong:
        print("wrong:")
        for row in wrong:
            print(f"  {row['utterance']!r:<42} "
                  f"want {row['expected_intent']:<17}"
                  f" got {row['chosen_tool']}")
            if row["reply_text"]:
                print(f"      said instead: {row['reply_text'][:110]!r}")
    if llm.failures:
        print("failures:")
        for failure in llm.failures:
            print(f"  {failure['kind']}: {failure['detail'][:120]}")
    return accuracy


def test_integration_intent_accuracy_and_latency(adj, checklist, tmp_path):
    """Dispatch accuracy and latency for one model, one request per utterance.

    The numbers are printed, not asserted. What is asserted is that the thing
    dispatched: every decision names a real tool or is a reply, and the
    accuracy clears a floor set well above chance.
    """
    _requires_server()
    orc, contexts = _contexts(adj, checklist[:5], tmp_path)
    llm = orc.llm

    rows = []
    for number, (said, want, state) in enumerate(UTTERANCES, start=1):
        before = len(llm.latencies_s)
        decision = llm.decide(
            contexts[state] + [{"role": "user", "content": said}], TOOLS)
        chosen = _chosen(decision)
        rows.append({"model": llm.model,
                     "request_no": number,
                     "utterance": said,
                     "expected_intent": want,
                     "chosen_tool": chosen,
                     "correct": chosen == want,
                     "latency_s": round(llm.latencies_s[before], 3),
                     "state": state,
                     "reply_text": ("" if isinstance(decision, ToolCall)
                                    else decision.text)})
        # After every request, not at the end. See _persist.
        csv_path, json_path = _persist(llm.model, rows, llm)

    accuracy = _report(llm.model, rows, llm)
    print(f"rows written     {csv_path}")
    print(f"                 {json_path}")

    for decision in llm.calls:
        assert isinstance(decision, Reply) or decision.name in TOOL_NAMES, \
            decision
    assert accuracy >= ACCURACY_FLOOR, \
        f"{llm.model} dispatched {accuracy:.0%} of {len(rows)} utterances"


def test_integration_the_real_model_is_told_no_more_than_the_mock(
        adj, checklist, tmp_path):
    """The redaction boundary holds with a model that can ask for things.

    Three turns, with the reading CORRECT so that what the trainee says and
    what the schematic expects coincide -- the run where a leak is likeliest.
    The scan is the one test_orchestrator.py runs over MockLLM, applied to
    the transcript a real model was actually sent.
    """
    _requires_server()
    item = checklist[0]
    orc = Orchestrator(adj, [item], RunLog(root=tmp_path, run_id="llm-leak"),
                       LlamaCppLLM())
    secrets = secrets_of(adj, [item])

    for utterance in ("where next", "which row is it in", item.tag):
        orc.say(utterance)

    sent = _wire_messages(orc.orchestrator_messages)
    found = [w for message in sent
             for w in WORDS.findall(message["content"])
             if compact(w) in secrets]
    assert not found, f"secrets reached the model: {found[:10]}"

    user = [m for m in orc.messages if m["role"] == "user"]
    assert any(compact(w) in secrets
               for m in user for w in WORDS.findall(m["content"])), \
        "the trainee did read the tag out, so the scan had something to catch"
