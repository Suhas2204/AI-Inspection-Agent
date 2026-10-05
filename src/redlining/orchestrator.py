"""Block 7 (experimental): an LLM front end that drives one inspection run.

Text only. No microphone, no model weights, no network: the trainee's words
arrive as strings and an LLM decides which tool to call. MockLLM in this
module is the only implementation here, so the whole thing runs offline and
in tests.

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
    from redlining.adjudicate import Adjudicator
    from redlining.checklist import load_checklist
    from redlining.orchestrator import MockLLM, Orchestrator
    from redlining.report import RunLog

    orc = Orchestrator(Adjudicator.from_export(SCHEMATIC), load_checklist(),
                       RunLog(), MockLLM())
    orc.say("where next")
    orc.say("it says minus 1 F1")
    orc.finish()
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .adjudicate import ABSTAIN, STRIP_TAGS, Adjudicator
from .checklist import Item
from .normalise import DIGIT_WORDS, TEEN_TENS_WORDS, compact
from .report import RunLog
from .session import MAX_REASKS, Read, step_item

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
            "other words, ask them for the reading on its own."),
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
           "where you want to go, or the reading on its own, with no other "
           "words around it.")


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

    Args:
        utterance: The trainee's words.

    Returns:
        True if it looks like a reading and nothing else. False for an empty
        utterance, and for anything wrapped in other words ("it says minus 1
        F1"), which is asked for again rather than trimmed -- trimming is
        editing, and nothing here edits a trainee's words.
    """
    words = [w for w in re.split(r"[^A-Za-z0-9]+", utterance) if w]
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
    That includes a reading wrapped in other words: "it says minus 1 F1" is
    asked for again rather than trimmed down to the tag, because trimming is
    editing and the orchestrator judges the words as they arrived.

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
    """

    def __init__(self):
        """Start with nothing to hand over."""
        self.text = ""

    def device(self, prompt: str, attempt: int) -> Read:
        """Return the pending text as a device reading.

        Args:
            prompt: Ignored; the LLM has already prompted.
            attempt: Ignored, for the same reason.

        Returns:
            Read with tag_raw set.
        """
        return Read(tag_raw=self.text)

    def strip(self, prompt: str, attempt: int) -> Read:
        """Return the pending text as a strip's counts.

        Args:
            prompt: Ignored; the LLM has already prompted.
            attempt: Ignored, for the same reason.

        Returns:
            Read with counts_raw set.
        """
        return Read(counts_raw=self.text)


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

    def hear(self, utterance: str) -> None:
        """Record what the trainee said, without dispatching anything.

        The only way words enter this module. submit_reading judges whatever
        was last heard, so this is the single place a reading can come from
        and the model is not one of them.

        Args:
            utterance: The trainee's words, exactly as they arrived.
        """
        self._utterance = utterance
        self.messages.append({"role": "user", "content": utterance})

    def say(self, utterance: str) -> dict:
        """One turn: give the LLM what the trainee said and act on its decision.

        Args:
            utterance: The trainee's words.

        Returns:
            {"tool": name, "arguments": {...}, "result": {...}} when a tool
            ran, or {"reply": text} when the model asked for the request
            again. A reply means no tool ran and no state moved.
        """
        self.hear(utterance)
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
