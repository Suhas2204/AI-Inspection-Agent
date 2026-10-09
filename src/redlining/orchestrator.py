"""Block 7 (experimental): an LLM front end that drives one inspection run.

Text only. No microphone and no model weights: the trainee's words arrive as
strings and an LLM decides which tool to call. Two implementations of that
LLM live here. MockLLM is a fixed phrase-to-tool mapping and needs no server,
so every ordinary test runs offline against it. LlamaCppLLM talks to a
llama.cpp server over the OpenAI-compatible chat-completions API; it is used
by one opt-in integration test and by nothing that runs by default.

What this is for. The scripted and keyboard paths walk the checklist in a
fixed order and ask for one reading per position. A trainee at a cabinet
wants to say "where next", "say that again", "skip this one, I can't reach
it". That is a dispatch problem, and it is the only thing the LLM does here.

What the LLM does NOT do, and cannot:

  - It does not decide a verdict. submit_reading hands the text to
    session.step_item, which normalises it, asks the Adjudicator, and writes
    the attempt to the log. That is the same function the keyboard and
    Streamlit paths call, so a verdict reached through this module is the
    verdict those paths would have reached. There is no second adjudicator
    here and no place for one.
  - It never learns what the schematic expects. Every tool returns its
    result unchanged -- the caller and the log get the whole verdict -- and
    exactly one function, redact(), stands between those results and the
    LLM. Nothing reaches the model except through it.

The redaction boundary, stated once because it is the only thing in this
module that must not be got wrong:

  Tool results are produced in full, recorded in full, and redacted on the
  way to the LLM. redact() works two ways at once: it drops the keys that
  carry answers outright (expected, reason, normalised, ...) and then scans
  whatever is left for any identifier-shaped secret -- every tag in the
  cabinet, every part number, every rating line. The second pass is the
  backstop: a field added later that happens to carry a tag is caught
  without anyone remembering to add it to the first list.

  Bare counts are handled by the first pass only. "N: read 0, expected 1"
  cannot be scrubbed by substring search without redacting every digit, so
  the verdict's reason is dropped whole rather than filtered.

  The trainee's own utterance IS passed to the LLM verbatim -- it has to
  be, or the model could not tell a reading from a request. When a trainee
  reads a position correctly their words match what the schematic expects,
  and that is the input, not a disclosure by this module. The guarantee
  here is about what the ORCHESTRATOR tells the LLM, and
  orchestrator_messages is the list it covers.

  What the model cannot do is change those words. submit_reading takes no
  arguments: it signals that the trainee has just read the position out,
  and the orchestrator takes the utterance it already holds. A model that
  sends a text argument anyway has it ignored, and a test drives exactly
  that case -- an LLM substituting the correct tag for a trainee's misread,
  and the misread being what gets scored. This matters more than the
  reading reaching the model at all: a model that could rewrite a reading
  could turn a misread into a match, and the run would be measuring the
  model.

The log is session.step_item's, so it is byte-for-byte the format the other
paths write and score.py reads unchanged. A skipped position is simply
absent from it, which is already how score.py reads "not walked" -- no new
status and no new column.

Usage:
    from redlining.core.adjudicate import Adjudicator
    from redlining.checklist import load_checklist
    from redlining.orchestrator import LlamaCppLLM, MockLLM, Orchestrator
    from redlining.report import RunLog

    orc = Orchestrator(Adjudicator.from_export(SCHEMATIC), load_checklist(),
                       RunLog(), MockLLM())
    orc.say("where next")
    orc.say("it says minus 1 F1")
    orc.finish()

Swap MockLLM() for LlamaCppLLM() to drive the same run with a real model; it
reads LLM_URL and LLM_MODEL from the environment and nothing else changes,
because the orchestrator hands either one the same redacted transcript.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .checklist import Item
from .core.adjudicate import ABSTAIN, STRIP_TAGS, Adjudicator
from .core.normalise import (
    DIGIT_WORDS,
    TEEN_TENS_WORDS,
    compact,
    strip_lead_in,
)
from .core.reads import Read
from .report import RunLog
from .session import MAX_REASKS, step_item

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# Keys withheld from the model, in two groups for two different reasons.
#
# ANSWER_KEYS carry the schematic's answer, or carry it in prose. Dropped
# outright rather than filtered, because a substring scan cannot safely clean
# them: "N: read 0, expected 1" would need every digit removed to be safe.
ANSWER_KEYS = frozenset({"expected", "reason", "normalised", "item", "tag",
                         "detail", "type", "order_reference", "rating",
                         "part", "counts", "reading"})

# VERDICT_KEYS do not contain the answer, and are withheld anyway. "mismatch"
# never says what the right tag was -- but it does say the trainee got it
# wrong, and a model that knows will sooner or later let them know too.
# Re-asks in this study are silent (session.py: "no echo, no hint"), because
# a trainee who learns the last read was wrong reads the next one
# differently. ask_again is all the dispatcher needs and all it gets.
VERDICT_KEYS = frozenset({"outcome"})

SECRET_KEYS = ANSWER_KEYS | VERDICT_KEYS

REDACTED = "[redacted]"

# What counts as identifier-shaped for the scanning pass: runs of letters and
# digits, so "-1F1" is found inside "reads -1F1 here" and inside "X1_a1".
_WORDS = re.compile(r"[A-Za-z0-9]+")


def secrets_of(adj: Adjudicator, items: list[Item]) -> frozenset[str]:
    """Every string this run must never show the LLM, compacted for matching.

    Three sources, because a position's answer can be spelled three ways:
    the tag the schematic expects there, the part number fitted, and the
    rating line printed on it.

    Args:
        adj: The adjudicator, for the cabinet's parts and ratings.
        items: Checklist items, for the tags.

    Returns:
        Compacted secrets, e.g. {"1F1", "A9F03116", "IC60NB16", ...}. Short
        strings are kept: "X1" is a real tag and has to be caught.
    """
    out = {compact(i.tag) for i in items}
    out |= {compact(t) for t in STRIP_TAGS}
    out |= {compact(t) for t in adj.devices}
    out |= set(adj.legal_parts)
    for record in list(adj.devices.values()) + list(adj.terminals):
        out |= {compact(record.get("order_reference")),
                compact(record.get("type"))}
    return frozenset(s for s in out if s)


def redact(payload: Any, secrets: frozenset[str]) -> Any:
    """Remove every expected value and schematic answer from one payload.

    THE boundary. Nothing reaches the LLM except through this function, and
    nothing else in this module is allowed to decide what is safe.

    Two passes, and both are needed:

    1. Any key in SECRET_KEYS is dropped, whatever it holds -- the answer
       itself (ANSWER_KEYS) and how a reading was judged (VERDICT_KEYS).
       Dropping beats filtering here: the verdict's reason carries the
       answer in prose that no scan could clean.
    2. Every surviving string is scanned word by word against `secrets`. A
       word that compacts to a known tag, part number or rating line is
       replaced. This is the pass that catches a field nobody thought about.

    Args:
        payload: Anything bound for the LLM -- a dict, list, string or
            scalar. Not mutated.
        secrets: From secrets_of().

    Returns:
        A new structure, safe to show the model.
    """
    if isinstance(payload, dict):
        return {k: redact(v, secrets) for k, v in payload.items()
                if k not in SECRET_KEYS}
    if isinstance(payload, (list, tuple)):
        return [redact(v, secrets) for v in payload]
    if isinstance(payload, str):
        return _scrub(payload, secrets)
    return payload


def _scrub(text: str, secrets: frozenset[str]) -> str:
    """Replace any word of `text` that is a secret.

    Word by word rather than by substring, so that redacting the tag "-X1"
    cannot also mangle an unrelated word that merely contains "x1".

    Args:
        text: A string bound for the LLM.
        secrets: Compacted secrets.

    Returns:
        The string with secret words replaced by REDACTED.
    """
    def one(match: re.Match) -> str:
        """Replace this word if it is a secret."""
        return REDACTED if compact(match.group()) in secrets else match.group()

    return _WORDS.sub(one, text)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

# The tools, as JSON Schema, in the shape a tool-calling API wants. Static
# text: no cabinet value appears here, and a test asserts that against the
# same secret set redact() uses.
#
# skip takes a POSITION NUMBER, not a tag. This is not a style choice. The
# tag expected at a location is the answer the trainee is being tested on,
# so a tool that took one would hand the model the thing this module exists
# to withhold. The number is the walking-order index the walker card also
# prints, and it names a place without saying what is mounted there.
TOOLS = [
    {
        "name": "next_location",
        "description": (
            "Move to the next position that still needs a reading and return "
            "where to send the trainee. Call this to start, and again after a "
            "reading has been accepted. Returns the location only -- it never "
            "says what is mounted there."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_reading",
        "description": (
            "Signal that the trainee has just read the position out, so their "
            "words are judged. Takes NO arguments and you do not supply the "
            "reading: the words are taken from the transcript exactly as they "
            "arrived. You cannot correct, complete or tidy them, and you "
            "should not try -- a misread has to stay a misread or the run "
            "measures you instead of the trainee. Call this only when what "
            "they said IS the reading and nothing else; if they wrapped it in "
            "other words, ask them for the reading on its own. Digits spoken "
            "as words are still the reading -- \"minus nine Q nine\" is a "
            "reading exactly as \"minus 9 Q 9\" is -- so never ask for a "
            "label again merely because its numbers arrived as words."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "repeat",
        "description": (
            "Say the current location again, without spending an attempt. Use "
            "this when the trainee did not catch where to go. It does not "
            "re-ask for a reading and it reveals nothing new."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "progress",
        "description": (
            "How far through the walk this run is: positions finished, "
            "skipped and remaining, and which attempt the current position is "
            "on. Counts only -- it does not say how any reading was judged."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "skip",
        "description": (
            "Leave a position unread and move on, for when the trainee cannot "
            "reach or see it. A skipped position is recorded as never walked, "
            "which is not the same as a failed reading."),
        "parameters": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "integer",
                    "description": (
                        "Position number, as next_location and progress "
                        "report it. Omit to skip the current position."),
                },
            },
            "required": [],
        },
    },
    {
        "name": "explain_location",
        "description": (
            "Describe the current position in more detail -- frame, rail row "
            "and place along the row -- for a trainee who cannot find it. It "
            "adds detail about WHERE to stand and nothing about what is "
            "there."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOLS)

# The dispatch prompt is versioned because changing it invalidates every
# accuracy number measured against the one before. v1 is what the 5 Oct
# comparison in DECISIONS.md measured; v2 added the sentence in
# submit_reading about digits spoken as words, after run 20261006-184627
# showed Gemma declining "Minus one q1" and re-prompting instead. Anything
# that reports accuracy must report this alongside it.
PROMPT_VERSION = "v2"

SYSTEM_PROMPT = """\
You guide one trainee through a control-cabinet inspection, one position at a
time. You are a dispatcher, not an inspector.

Call next_location to send them somewhere. When they read something out, pass
their exact words to submit_reading. If it answers ask_again, ask them to read
it again and say nothing else -- do not tell them anything about the previous
reading, do not hint, and do not guess at what they should have said. If a
request is unclear, ask them to say it again rather than choosing a tool.

You are never told what is mounted at a position and you cannot find out. That
is deliberate: the run measures whether the trainee reads the cabinet
correctly, and anything you revealed would be measured instead.\
"""


# ---------------------------------------------------------------------------
# The LLM interface
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    """The model's decision to call one tool.

    Attributes:
        name: Tool name, which must be in TOOL_NAMES.
        arguments: Keyword arguments for it.
    """
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Reply:
    """The model's decision to say something instead of calling a tool.

    Attributes:
        text: What to say to the trainee.
    """
    text: str


class LLM(Protocol):
    """What the orchestrator needs from a model. One method.

    An implementation receives the redacted transcript and the tool schemas
    and returns either a ToolCall or a Reply. It is handed no other state,
    so it cannot reach past redact() for anything.
    """

    def decide(self, messages: list[dict], tools: list[dict]
               ) -> ToolCall | Reply:
        """Choose a tool call or a reply.

        Args:
            messages: The conversation so far, already redacted.
            tools: TOOLS, as JSON Schema.

        Returns:
            A ToolCall to run, or a Reply to pass to the trainee.
        """
        ...


# Phrase -> intent, for MockLLM. Commands are matched first, so "skip 3" is
# a skip and not a reading that happens to contain a number.
_INTENTS = (
    ("next_location", re.compile(r"\b(where\s+next|next\s+(?:one|position|"
                                 r"item)?|what\s+next|move\s+on)\b", re.I)),
    ("repeat", re.compile(r"\b(say\s+(?:that\s+)?again|again|repeat|pardon|"
                          r"come\s+again)\b", re.I)),
    ("skip", re.compile(r"\b(skip|can'?t\s+reach|cannot\s+reach|leave\s+it|"
                        r"pass\s+on\s+this)\b", re.I)),
    ("progress", re.compile(r"\b(progress|how\s+(?:far|many|much)|how'?s\s+it"
                            r"\s+going)\b", re.I)),
    ("explain_location", re.compile(r"\b(where\s+(?:am\s+i|is\s+(?:it|that))|"
                                    r"explain|describe|can'?t\s+find|"
                                    r"which\s+row)\b", re.I)),
)

# Words that can be part of a spoken reading. A tag is "minus 1 F1", counts
# are "L 3 N 1 PE 1 bracket 1"; neither contains an ordinary English word.
_SIGN_WORDS = frozenset({"minus", "dash", "negative", "hyphen"})
_COUNT_LABELS = frozenset({"l", "n", "pe", "bracket", "brackets"})

CLARIFY = ("Sorry, I did not follow that. Could you say it again -- either "
           "where you want to go, or what the label reads.")


def _is_reading(utterance: str) -> bool:
    """Whether every word of an utterance could belong to a spoken reading.

    Classification only. It decides WHETHER to submit, never WHAT: the
    orchestrator judges the utterance as it arrived either way, so a
    misclassification here cannot change a single character of what is
    scored.

    Deliberately not a validity check. "minus 9 F 9 9 9" is a reading and a
    misread, and it has to reach the adjudicator to be scored -- a classifier
    that only submitted well-formed readings would quietly swallow exactly
    the defects this study measures.

    A carrier phrase in front of the reading is allowed -- "it says minus 1
    F1" is one reading, not a sentence about one -- and it is recognised with
    normalise.strip_lead_in, the same fixed list the normaliser strips with.
    Sharing that list is the point: a phrase this accepts is a phrase the
    normaliser will take off, so the classifier cannot wave through an
    utterance that then fails to normalise for a reason only it knew about.

    Args:
        utterance: The trainee's words.

    Returns:
        True if it looks like a reading, with or without a carrier phrase in
        front. False for an empty utterance and for anything else.
    """
    words = [w for w in re.split(r"[^A-Za-z0-9]+", utterance) if w]
    words, _lead_in = strip_lead_in(words)
    if not words:
        return False
    for word in words:
        low = word.lower()
        if low in _SIGN_WORDS or low in _COUNT_LABELS:
            continue
        if any(c.isdigit() for c in word):      # "1", "1q1", "12"
            continue
        if len(word) == 1 and word.isalpha():   # "f", "q", "k"
            continue
        if low in DIGIT_WORDS or low in TEEN_TENS_WORDS:
            continue
        return False
    return any(any(c.isdigit() for c in w) or w.lower() in DIGIT_WORDS
               or w.lower() in TEEN_TENS_WORDS for w in words)


class MockLLM:
    """A fixed phrase-to-tool mapping, so the orchestrator runs with no model.

    It is a stand-in for a tool-calling model, not a pretend one: it reads
    the last trainee utterance and nothing else. It cannot put words in the
    trainee's mouth even if it tries, because submit_reading carries no
    words -- the worst a misclassification can do is submit the wrong
    utterance, which abstains loudly instead of scoring something nobody
    said.

    An utterance it does not recognise returns a Reply asking for it again.
    A carrier phrase in front of a reading IS recognised -- "it says minus 1
    F1" is one reading -- because normalise.CARRIER_PHRASES strips it on a
    fixed list and records what it took off. The model still carries no
    words: it says only that a reading happened.

    Attributes:
        calls: Every decision it has made, for tests to inspect.
    """

    def __init__(self):
        """Start with no decisions recorded."""
        self.calls: list[ToolCall | Reply] = []

    def decide(self, messages: list[dict], tools: list[dict]
               ) -> ToolCall | Reply:
        """Map the last trainee utterance to a tool call or a reply.

        Args:
            messages: The redacted transcript. Only the last "user" message
                is read.
            tools: TOOLS. Used to check the chosen name really exists.

        Returns:
            A ToolCall, or a Reply asking for the request again.
        """
        names = {t["name"] for t in tools}
        said = next((m["content"] for m in reversed(messages)
                     if m["role"] == "user"), "")

        decision: ToolCall | Reply = Reply(CLARIFY)
        for name, pattern in _INTENTS:
            if pattern.search(said) and name in names:
                decision = ToolCall(name)
                break
        else:
            if _is_reading(said) and "submit_reading" in names:
                # No arguments. The words are the orchestrator's to use.
                decision = ToolCall("submit_reading")

        self.calls.append(decision)
        return decision


# ---------------------------------------------------------------------------
# A real model, over an OpenAI-compatible endpoint
# ---------------------------------------------------------------------------

# Defaults for a llama.cpp server on the machine next to the cabinet. Both are
# overridable by environment variable, so a run can be pointed at another host
# or another model without editing code -- which is how the two models in the
# comparison are swapped.
LLM_URL = os.environ.get("LLM_URL", "http://localhost:8080/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Gemma-4-26B-A4B-it-UD-Q4_K_XL")

# Temperature 0: the dispatcher must choose the same tool for the same words
# every time, or two runs over the same utterances are not comparable and a
# wrong dispatch cannot be reproduced to be looked at.
LLM_TEMPERATURE = 0.0

# A trainee standing at a cabinet is waiting for an answer. Sixty seconds is
# already far past useful; it is a ceiling that stops a wedged request hanging
# the run, not a latency target. Reaching it is a failure, and is counted
# as one.
LLM_TIMEOUT_S = 60.0

# llama.cpp wants no credential. The OpenAI client insists on one being
# present, so a placeholder is passed. No key is read from the environment on
# purpose: this endpoint is local, and a real key has no business being sent
# to it.
LLM_API_KEY = "no-key-needed"

# submit_reading is the one tool allowed to receive arguments it does not
# declare. Its contract (see the method) is to ignore them AND to record that
# the model tried -- "llm_text_ignored" in the attempt. Rejecting the call
# here as malformed would protect nothing, since the words are ignored either
# way, and would destroy the evidence that a model attempted to substitute its
# own reading. For every other tool an undeclared argument is dropped before
# the call: those tools take no **kwargs, so forwarding one would raise out of
# the middle of a run.
ABSORBS_EXTRA_ARGS = frozenset({"submit_reading"})


def _wire_tools(tools: list[dict]) -> list[dict]:
    """Wrap TOOLS in the envelope the chat-completions API expects.

    Names, descriptions and parameter schemas are passed through untouched,
    so the model is offered the same tools MockLLM is checked against; only
    the envelope differs.

    Args:
        tools: TOOLS, or the same shape.

    Returns:
        The same list, each entry wrapped as {"type": "function", ...}.
    """
    return [{"type": "function",
             "function": {"name": t["name"],
                          "description": t["description"],
                          "parameters": t["parameters"]}}
            for t in tools]


def _wire_messages(messages: list[dict]) -> list[dict]:
    """Render the redacted transcript as chat-completions messages.

    Content-preserving, which is the whole requirement: the model is shown
    what MockLLM is shown and nothing else. Redaction has already happened
    upstream -- this function is handed the orchestrator's message list as it
    stands and adds nothing to it.

    Two mappings are needed to get that list onto the wire:

      - A role-"tool" message in this module carries a tool name and a dict.
        The API's own tool role requires a tool_call_id pairing with an
        assistant tool_call, which this transcript does not record, because
        the orchestrator calls its tools itself. The result is therefore
        presented as a labelled transcript line rather than dropped.
      - Adjacent messages of the same role are joined. Several chat templates
        -- Gemma's among them -- require turns to alternate and reject two
        user turns in a row, which the mapping above can produce.

    Args:
        messages: Orchestrator.messages, already redacted.

    Returns:
        A list of {"role", "content"} dicts, content always a string.
    """
    flat: list[dict] = []
    for message in messages:
        content = message["content"]
        if not isinstance(content, str):
            content = json.dumps(content, sort_keys=True)
        if message["role"] == "tool":
            flat.append({"role": "user",
                         "content": f"[tool result: {message['name']}] "
                                    f"{content}"})
        else:
            flat.append({"role": message["role"], "content": content})

    merged: list[dict] = []
    for message in flat:
        if merged and merged[-1]["role"] == message["role"]:
            merged[-1]["content"] += "\n\n" + message["content"]
        else:
            merged.append(dict(message))
    return merged


def _arguments_for(name: str, raw: str | None, tools: list[dict]) -> dict:
    """Parse and check one tool call's arguments.

    Args:
        name: The tool the model named; already known to exist.
        raw: The arguments as the API returns them -- a JSON string, or None.
        tools: TOOLS, for the declared properties and their types.

    Returns:
        Keyword arguments for the tool, undeclared ones dropped unless the
        tool absorbs them.

    Raises:
        ValueError: If the arguments are not a JSON object, or a declared
            argument is the wrong type. Both are a malformed call, and the
            caller turns them into a clarify rather than a guess.
    """
    try:
        parsed = json.loads(raw) if raw and raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"arguments are not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"arguments are {type(parsed).__name__}, not an object")

    schema = next(t for t in tools if t["name"] == name)
    declared = schema["parameters"].get("properties", {})
    out = {}
    for key, value in parsed.items():
        if key not in declared:
            if name in ABSORBS_EXTRA_ARGS:
                out[key] = value
            continue
        if declared[key].get("type") == "integer":
            # A model that sends "3" for a position number means 3. A model
            # that sends "the third one" does not have a position number, and
            # must not be guessed at.
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError(f"{key}={value!r} is not a position number")
            try:
                value = int(value)
            except ValueError as exc:
                raise ValueError(
                    f"{key}={value!r} is not a position number") from exc
        out[key] = value
    return out


class LlamaCppLLM:
    """A tool-calling model behind an OpenAI-compatible endpoint.

    A drop-in for MockLLM: one method, the same two return types, and it is
    handed the same tool schemas and the same already-redacted transcript.
    Nothing about the redaction boundary changes because the model is now
    real -- decide() receives the messages the orchestrator built, and has no
    other way to reach the cabinet.

    Every failure becomes the clarify Reply MockLLM uses for an utterance it
    does not understand, and that is the only safe answer. A connection
    refused, a timeout, a tool that does not exist, arguments that are not
    JSON: none of them say what the trainee wanted, so the trainee is asked
    again. The alternative -- picking the likeliest tool -- would submit a
    reading nobody asked to have judged, or move the walk on from a position
    that was never read.

    Failures are recorded rather than swallowed, in `failures`, so that a run
    which clarified twenty times because the server was down cannot be
    mistaken for one that clarified twenty times because the model was
    confused.

    Attributes:
        url: Base URL, e.g. "http://localhost:8080/v1".
        model: Model name the endpoint knows it by.
        timeout_s: Per-request ceiling.
        temperature: Sampling temperature.
        calls: Every decision made, as MockLLM records them.
        latencies_s: Wall-clock seconds per request, failures included.
        failures: One dict per clarify-by-failure: {"kind", "detail"}.
    """

    def __init__(self, url: str = LLM_URL, model: str = LLM_MODEL,
                 timeout_s: float = LLM_TIMEOUT_S,
                 temperature: float = LLM_TEMPERATURE):
        """Record where the model is, without contacting it.

        The client is built on the first request, so constructing this costs
        nothing and an unreachable server shows up at decide() -- where it
        can be recorded -- rather than at import.

        Args:
            url: Base URL of the OpenAI-compatible endpoint.
            model: Model name to request.
            timeout_s: Per-request timeout in seconds.
            temperature: Sampling temperature; 0 for a reproducible dispatch.
        """
        self.url = url
        self.model = model
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.calls: list[ToolCall | Reply] = []
        self.latencies_s: list[float] = []
        self.failures: list[dict] = []
        self._client = None

    def _ensure_client(self):
        """Build the OpenAI client on first use.

        Returns:
            The client.
        """
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.url, api_key=LLM_API_KEY,
                                  timeout=self.timeout_s, max_retries=0)
        return self._client

    def _clarify(self, kind: str, detail: str) -> Reply:
        """Record a failure and return the clarify reply.

        Args:
            kind: Short category, e.g. "APITimeoutError", "unknown_tool".
            detail: What happened, for the run's notes.

        Returns:
            Reply(CLARIFY).
        """
        self.failures.append({"kind": kind, "detail": detail})
        return Reply(CLARIFY)

    def decide(self, messages: list[dict], tools: list[dict]
               ) -> ToolCall | Reply:
        """Ask the model which tool to call, or what to say.

        Args:
            messages: The redacted transcript, as the orchestrator holds it.
            tools: TOOLS, as JSON Schema.

        Returns:
            A ToolCall the orchestrator can run, the model's own words as a
            Reply, or Reply(CLARIFY) if anything at all went wrong. It never
            raises: a front end that died on a dropped connection would end
            the run, and the run is a person walking a cabinet.
        """
        start = time.monotonic()
        try:
            response = self._ensure_client().chat.completions.create(
                model=self.model,
                messages=_wire_messages(messages),
                tools=_wire_tools(tools),
                tool_choice="auto",
                temperature=self.temperature,
                timeout=self.timeout_s,
            )
        except Exception as exc:
            # Deliberately every exception. A timeout, a refused connection,
            # a 500 from the server, a model name it does not know: the
            # answer to all of them is to ask the trainee again, so there is
            # nothing to gain by telling them apart beyond naming the class
            # in the record.
            self.latencies_s.append(time.monotonic() - start)
            decision = self._clarify(type(exc).__name__, str(exc)[:300])
            self.calls.append(decision)
            return decision
        self.latencies_s.append(time.monotonic() - start)

        decision = self._read(response, tools)
        self.calls.append(decision)
        return decision

    def _read(self, response: Any, tools: list[dict]) -> ToolCall | Reply:
        """Turn one response into a decision, or into a clarify.

        Args:
            response: What the endpoint returned.
            tools: TOOLS, for validating the arguments.

        Returns:
            A ToolCall, a Reply carrying the model's own words, or
            Reply(CLARIFY).
        """
        choices = getattr(response, "choices", None)
        if not choices:
            return self._clarify("no_choices", repr(response)[:300])
        message = choices[0].message

        for call in (getattr(message, "tool_calls", None) or [])[:1]:
            name = call.function.name
            if name not in TOOL_NAMES:
                # Not a tool. There is nothing to do with it and nothing to
                # infer from it -- a model inventing "read_schematic" is not
                # telling us what the trainee said.
                return self._clarify("unknown_tool", str(name)[:300])
            try:
                arguments = _arguments_for(name, call.function.arguments,
                                           tools)
            except ValueError as exc:
                return self._clarify("bad_arguments", f"{name}: {exc}"[:300])
            return ToolCall(name, arguments)

        text = (getattr(message, "content", None) or "").strip()
        if text:
            # The model chose to speak rather than dispatch, which is what
            # the system prompt asks for when a request is unclear. Its own
            # words go to the trainee.
            return Reply(text)
        return self._clarify("empty_response", "no tool call and no content")


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------

class _OneReading:
    """Input source that hands step_item a reading already collected as text.

    The same interface session.py's other sources present, so step_item
    cannot tell the difference and does exactly what it does for the
    keyboard. It deliberately has no _tag attribute: step_item sets that on
    sources that have one, and this object has no business holding the tag
    expected at the current position.

    Attributes:
        text: The reading the next call will return.
        audio_path: Where that reading was recorded, if it was. Block 8's
            gate is that the audio behind any flag can be replayed, and
            flags are not known while recording, so every attempt carries
            its clip.
        confidence: ASR confidence for it, if known.
    """

    def __init__(self):
        """Start with nothing to hand over."""
        self.text = ""
        self.audio_path: str | None = None
        self.confidence: float | None = None

    def device(self, prompt: str, attempt: int) -> Read:
        """Return the pending text as a device reading.

        Args:
            prompt: Ignored; the LLM has already prompted.
            attempt: Ignored, for the same reason.

        Returns:
            Read with tag_raw set, and the clip it came from.
        """
        return Read(tag_raw=self.text, audio_path=self.audio_path,
                    confidence=self.confidence)

    def strip(self, prompt: str, attempt: int) -> Read:
        """Return the pending text as a strip's counts.

        Args:
            prompt: Ignored; the LLM has already prompted.
            attempt: Ignored, for the same reason.

        Returns:
            Read with counts_raw set, and the clip it came from.
        """
        return Read(counts_raw=self.text, audio_path=self.audio_path,
                    confidence=self.confidence)


class Orchestrator:
    """Drives one run from text, dispatching through an LLM.

    Attributes:
        adj: Adjudicator for the cabinet. Consulted only by step_item.
        items: Checklist items, in the order the other paths walk them.
        log: RunLog receiving every attempt, in the usual format.
        llm: Anything satisfying LLM.
        max_reasks: Silent re-asks allowed after an abstain, as session.run.
        mode: "tag" or "part", passed straight to step_item.
        messages: The whole transcript, including the trainee's own words.
        secrets: What redact() must never let through.
    """

    def __init__(self, adj: Adjudicator, items: list[Item], log: RunLog,
                 llm: LLM, max_reasks: int = MAX_REASKS,
                 mode: str = "tag"):
        """Set up a run without starting it.

        Args:
            adj: Adjudicator for the cabinet.
            items: Checklist items in walking order.
            log: RunLog to record into.
            llm: The model, or MockLLM.
            max_reasks: Silent re-asks after an abstain (session.MAX_REASKS).
            mode: "tag" or "part", as session.step_item means it.
        """
        self.adj = adj
        self.items = list(items)
        self.log = log
        self.llm = llm
        self.max_reasks = max_reasks
        self.mode = mode
        self.secrets = secrets_of(adj, self.items)

        self._source = _OneReading()
        self._utterance: str | None = None    # the trainee's last words
        self._audio_path: str | None = None   # and the clip they are from
        self._confidence: float | None = None
        self._cursor: int | None = None       # index into items, or None
        self._attempt_no = 0
        self._settled: set[int] = set()       # a reading was accepted
        self._skipped: set[int] = set()
        self.messages: list[dict] = []
        self._say_system(SYSTEM_PROMPT)

    # ------------------------------------------------------------- messages
    def _say_system(self, text: str) -> None:
        """Append a system message, redacted.

        Args:
            text: The prompt.
        """
        self.messages.append({"role": "system",
                              "content": redact(text, self.secrets)})

    def _say_tool(self, name: str, result: dict) -> None:
        """Append a tool result, redacted.

        Args:
            name: Tool that produced it.
            result: Its full, unchanged return value.
        """
        self.messages.append({"role": "tool", "name": name,
                              "content": redact(result, self.secrets)})

    @property
    def orchestrator_messages(self) -> list[dict]:
        """Every message this module originated, i.e. everything but the trainee.

        The list the no-disclosure guarantee covers. A trainee's utterance is
        their own words and is passed to the model verbatim -- see the module
        docstring for why that is the one exception and why it is not a leak.
        """
        return [m for m in self.messages if m["role"] != "user"]

    # ---------------------------------------------------------------- state
    @property
    def current(self) -> Item | None:
        """The position being read, or None if there is none."""
        return None if self._cursor is None else self.items[self._cursor]

    def _position_of(self, index: int) -> int:
        """Walking-order number of an index, as the walker card prints it.

        Args:
            index: Index into items.

        Returns:
            The 1-based position number.
        """
        return index + 1

    def _index_of(self, position: int) -> int | None:
        """Index for a position number, or None if it is not one.

        Args:
            position: A 1-based position number.

        Returns:
            The index, or None.
        """
        index = position - 1
        return index if 0 <= index < len(self.items) else None

    def _pending(self) -> list[int]:
        """Indices with no accepted reading and no skip, in walking order."""
        return [i for i in range(len(self.items))
                if i not in self._settled and i not in self._skipped]

    # ---------------------------------------------------------------- tools
    def next_location(self) -> dict:
        """Move to the next position needing a reading and describe where.

        Wraps the checklist order the other paths walk; nothing is reordered
        here.

        Returns:
            Where to go: position number, the spoken location, the kind, and
            how many positions remain. {"done": True} when none are left.
        """
        if self._cursor is not None and self._cursor in self._pending():
            pass                      # the current position is still open
        else:
            pending = self._pending()
            if not pending:
                return {"done": True, "remaining": 0}
            self._cursor = pending[0]
            self._attempt_no = 0

        item = self.items[self._cursor]
        return {"done": False,
                "position": self._position_of(self._cursor),
                "location": item.spoken,
                "kind": item.kind,
                "asks_for": ("terminal counts" if item.kind == "strip"
                             else "the tag"),
                "attempt_no": self._attempt_no + 1,
                "remaining": len(self._pending())}

    def submit_reading(self, text: str | None = None, **ignored) -> dict:
        """Judge the words the trainee last said. The LLM supplies none of them.

        An INTENT signal, not a channel. The reading is whatever hear() last
        recorded, which is the utterance exactly as it arrived; nothing the
        model passes is read.

        `text` exists in the signature only so that a model which sends one
        -- out of habit, or because it wants a different answer scored -- is
        ignored rather than erroring, and so that the full result can say it
        was ignored. It is never used. If the model could supply the words it
        could turn a misread into a match, and the run would be measuring the
        model rather than the trainee.

        The verdict is session.step_item's, reached by the same call the
        keyboard and Streamlit paths make. Nothing here inspects or second-
        guesses it: this method decides only whether a re-ask is still
        allowed, by the same rule session.run uses.

        Args:
            text: Ignored. See above.
            **ignored: Also ignored, for the same reason.

        Returns:
            The result unchanged, verdict and all: the reading used, outcome,
            reason, expected, the attempt number, and whether to ask again.
            redact() is what trims this for the model; callers and the log
            see all of it.

        Raises:
            RuntimeError: If no position is open, or nothing has been heard.
                Either would mean inventing part of the attempt.
        """
        if self._cursor is None:
            raise RuntimeError(
                "no position is open: call next_location before submitting a "
                "reading, or the reading would be judged against whichever "
                "position happened to be first.")
        if self._utterance is None:
            raise RuntimeError(
                "nothing has been heard: the reading comes from the "
                "trainee's own words, so there is nothing to judge until "
                "hear() or say() has recorded some.")

        item = self.items[self._cursor]
        reading = self._utterance
        self._attempt_no += 1
        self._source.text = reading
        self._source.audio_path = self._audio_path
        self._source.confidence = self._confidence
        verdict = step_item(item, self.adj, self._source, self.log,
                            self._attempt_no, mode=self.mode)

        # session.run's rule, not a new one: an abstain is re-asked until the
        # budget runs out, and anything else settles the position.
        ask_again = (verdict.outcome == ABSTAIN
                     and self._attempt_no <= self.max_reasks)
        if not ask_again:
            self._settled.add(self._cursor)

        return {"recorded": True,
                "item": item.tag,
                "reading": reading,
                "llm_text_ignored": text if text is not None else None,
                "position": self._position_of(self._cursor),
                "attempt_no": self._attempt_no,
                "ask_again": ask_again,
                "attempts_left": max(0, self.max_reasks + 1
                                     - self._attempt_no),
                "outcome": verdict.outcome,
                "reason": verdict.reason,
                "expected": dict(verdict.expected)}

    def repeat(self) -> dict:
        """Say the current location again without spending an attempt.

        Returns:
            The same location next_location gave, plus the wording the other
            paths use for a silent re-ask. {"nothing_to_repeat": True} if no
            position is open.
        """
        if self._cursor is None:
            return {"nothing_to_repeat": True}
        item = self.items[self._cursor]
        return {"position": self._position_of(self._cursor),
                "location": item.spoken,
                "kind": item.kind,
                "attempt_no": self._attempt_no + 1,
                "say": ("Please count them again." if item.kind == "strip"
                        else "Please read it again.")}

    def progress(self) -> dict:
        """How far the walk has got. Counts only.

        No outcome is counted here. A tally of flags would tell the model how
        the run is going, and from there which positions went wrong.

        Returns:
            Totals, and the current position's attempt number.
        """
        return {"positions_total": len(self.items),
                "read": len(self._settled),
                "skipped": len(self._skipped),
                "remaining": len(self._pending()),
                "position": (None if self._cursor is None
                             else self._position_of(self._cursor)),
                "attempt_no": self._attempt_no + 1 if self._cursor is not None
                else None}

    def skip(self, item: int | None = None) -> dict:
        """Leave a position unread and move on.

        No attempt is written, so the position is simply absent from the log.
        score.py already reads an absent planted position as "not walked" and
        scores it neither way, which is what a skip means.

        Args:
            item: Position number, as next_location reports it. None skips
                the position that is open.

        Returns:
            What was skipped and what remains, or {"error": ...} for a
            position number that does not exist.
        """
        index = self._cursor if item is None else self._index_of(int(item))
        if index is None:
            return {"error": "no such position", "asked_for": item,
                    "positions_total": len(self.items)}

        self._skipped.add(index)
        self._settled.discard(index)
        if index == self._cursor:
            self._cursor = None
            self._attempt_no = 0
        return {"skipped": self._position_of(index),
                "remaining": len(self._pending())}

    def explain_location(self) -> dict:
        """Describe where the current position is, in more detail.

        Frame, rail row and place along the row -- the fields Block 2 built.
        A device's `detail` is its type, which is the rating line the trainee
        is there to read, so it is not returned. A strip's terminal count is,
        because the walker card prints it and the walker already has it.

        Returns:
            The location broken out. {"nothing_open": True} if no position is
            open.
        """
        if self._cursor is None:
            return {"nothing_open": True}
        item = self.items[self._cursor]
        out = {"position": self._position_of(self._cursor),
               "frame": item.frame,
               "row": item.row,
               "place_in_row": item.position,
               "kind": item.kind,
               "location": item.spoken,
               "band": item.band}
        if item.kind == "strip":
            out["terminals"] = item.detail
        return out

    # --------------------------------------------------------------- driving
    def call(self, name: str, arguments: dict | None = None) -> dict:
        """Run one tool by name and record its result for the model.

        Args:
            name: A name from TOOL_NAMES.
            arguments: Keyword arguments.

        Returns:
            The tool's result, unchanged.

        Raises:
            KeyError: If the name is not a tool. An unknown tool is a bug in
                the caller, not something to paper over with a reply.
        """
        if name not in TOOL_NAMES:
            raise KeyError(f"no tool {name!r}; have {sorted(TOOL_NAMES)}")
        result = getattr(self, name)(**(arguments or {}))
        self._say_tool(name, result)
        return result

    def hear(self, utterance: str, audio_path: str | None = None,
             confidence: float | None = None) -> None:
        """Record what the trainee said, without dispatching anything.

        The only way words enter this module. submit_reading judges whatever
        was last heard, so this is the single place a reading can come from
        and the model is not one of them.

        The clip and the confidence travel with the words and are recorded
        with the attempt. They are NOT passed to the model: redact() covers
        the messages, and nothing puts them there.

        Args:
            utterance: The trainee's words, exactly as they arrived.
            audio_path: Where the utterance was recorded, if it was. A typed
                turn has none, and None is the honest answer rather than a
                path to a file that does not exist.
            confidence: ASR confidence, if known.
        """
        self._utterance = utterance
        self._audio_path = audio_path
        self._confidence = confidence
        self.messages.append({"role": "user", "content": utterance})

    def say(self, utterance: str, audio_path: str | None = None,
            confidence: float | None = None) -> dict:
        """One turn: give the LLM what the trainee said and act on its decision.

        Args:
            utterance: The trainee's words.
            audio_path: Where they were recorded, if they were. Passed to
                hear(), recorded with the attempt, never shown to the model.
            confidence: ASR confidence, if known.

        Returns:
            {"tool": name, "arguments": {...}, "result": {...}} when a tool
            ran, or {"reply": text} when the model asked for the request
            again. A reply means no tool ran and no state moved.
        """
        self.hear(utterance, audio_path=audio_path, confidence=confidence)
        decision = self.llm.decide(self.messages, TOOLS)

        if isinstance(decision, Reply):
            self.messages.append({"role": "assistant",
                                  "content": redact(decision.text,
                                                    self.secrets)})
            return {"reply": decision.text}

        result = self.call(decision.name, decision.arguments)
        return {"tool": decision.name, "arguments": dict(decision.arguments),
                "result": result}

    def finish(self) -> dict:
        """Write the report, in the format the other paths write.

        Returns:
            The parsed report, as RunLog wrote it.
        """
        return self.log.write_report(expected_items=len(self.items),
                                     duration_s=self.log.duration_s)
