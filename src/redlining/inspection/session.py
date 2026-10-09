"""Block 7: walk the checklist and run the inspection.

- Fixed sequence per item: prompt (location only) -> commit -> adjudicate
  -> reveal. The expected value is never shown before the verdict is fixed;
  any hint destroys the confirmation-bias protection of CONTEXT §7.
- Re-asks are silent ("please read it again"), at most two. Then the item is
  flagged and the run moves on. The run never stops.
- Input is pluggable: typed (default), scripted smoke test, or live
  microphone. --agent swaps the fixed walk for a conversation: the
  trainee says where they want to go and the orchestrator dispatches,
  through the same step_item, so the log is the same log.

Run:
    uv run python -m redlining.session                 # typed input
    uv run python -m redlining.session --scripted      # smoke test, no keyboard
    uv run python -m redlining.session --live --kind strip --model small --speak
    uv run python -m redlining.session --agent --speak        # voice loop
    uv run python -m redlining.session --agent --text         # typed loop
    uv run python -m redlining.session --agent --llm          # real model
"""

from __future__ import annotations

import argparse
import itertools
import re
import time
from pathlib import Path

from ..prep.checklist import Item, load_checklist
from ..core.adjudicate import (
    ABSTAIN,
    PART_EDIT_MAX,
    TAG_EDIT_MAX,
    Adjudicator,
    Verdict,
)
from ..core.normalise import (
    NOISE_WORDS,
    normalise_part,
    normalise_rating,
    normalise_tag,
    runaway,
    strip_leading_filler,
)
# Read and Heard live in core.reads so that audio_input.py and
# streamlit_input.py can build one without importing this module.
# Re-exported here: session.Read is the name every caller already uses.
from ..core.reads import Heard, Read
from ..speech.audio_input import VAD_MAX_S, VAD_SILENCE_S
from ..paths import RUNS, SCHEMATIC
from .report import Annotation, Attempt, RunLog

# Silent re-asks allowed after an abstain: 2, so 3 attempts total, per
# CONTEXT §7. The default only -- run() takes it as an argument and the CLI
# exposes it, because the re-ask budget is one axis of the risk-coverage trade
# (more re-asks, fewer items left abstaining, more verdicts committed to).
# Swept in experiments/block09_eval/risk_coverage.py.
MAX_REASKS = 2

TAG_MODE_WARNING = (
    "MODE: tag only. This checks that the right label is in the right\n"
    "place. It cannot detect a wrong part fitted under a correct label.\n")


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

# Which budget normalise.runaway applies to each raw field of a Read. The
# strip path is the reason this lives here rather than in the normalisers:
# counts go through parse_counts, which has no well_formed to carry a reason.
GUARDED_FIELDS = (("tag_raw", "tag"), ("part_raw", "part"),
                  ("rating_raw", "rating"), ("counts_raw", "counts"))


def runaway_reason(read: Read) -> str:
    """The first repetition-guard failure among a Read's raw fields, if any.

    Args:
        read: One spoken attempt, before anything has been judged.

    Returns:
        A reason to abstain, or "" if every field present looks like one read.
    """
    for field_name, kind in GUARDED_FIELDS:
        raw = getattr(read, field_name)
        if raw:
            stuck = runaway(raw, kind)
            if stuck:
                return stuck
    return ""


def count_tokens(text: str) -> list[str]:
    """Tokenise a counts transcript, uppercase, glued tokens split.

    Shared by parse_counts and unknown_labels on purpose. A token that one of
    them sees and the other does not is exactly how "M1" slipped through at
    -X1 in run 20260927-130613: the parser dropped it in silence, nothing
    else looked, and the missing N was published as a cabinet fault.

    Args:
        text: Raw counts transcript, e.g. "N 8 L 8 PE 8".

    Returns:
        Tokens, leading filler removed (see normalise.LEADING_FILLER).
    """
    raw = text.replace(",", " ").replace(":", " ").upper().split()
    toks: list[str] = []
    for t in raw:
        toks.extend(GLUED_RE.findall(t) or [t])
    return strip_leading_filler(toks)


def unknown_labels(text: str) -> list[str]:
    """Words in a counts read that name no terminal function this code knows.

    The -X1 case of run 20260927-130613: the walker counted correctly and
    Whisper wrote "L3, M1, PE1, Bracket 1". parse_counts has no "M", so it
    kept {L: 3, PE: 1, BRACKET: 1}, the adjudicator saw N missing, and an
    untouched strip was flagged "N: read 0, expected 1" -- a recogniser error
    published as a finding about the cabinet, on a verdict that is not an
    abstain and so was never re-asked.

    An unknown label means the read cannot be trusted as a whole, because
    nothing here can tell "M" misheard for "N" from a count simply not
    spoken. So it is named, not guessed at and not dropped.

    Args:
        text: Raw counts transcript.

    Returns:
        The unknown words, in the order spoken, without duplicates. Number
        words and NOISE_WORDS are not labels and never appear.
    """
    out: list[str] = []
    for t in count_tokens(text):
        if not t.isalpha():
            continue
        if t in FUNCTIONS or t in WORD_DIGITS or t.lower() in NOISE_WORDS:
            continue
        if t not in out:
            out.append(t)
    return out


def parse_counts(text: str) -> dict:
    """Turn spoken strip counts into a function -> count dict.

    - Accepts digits or number words ("N eight").
    - Splits glued tokens ("3L", "N1").
    - The count may come before or after its function ("3 L" or "L 3").
    - Only known functions (N, L, PE, BRACKET) become keys.

    A word this does not know is IGNORED here and reported by unknown_labels,
    which step_item abstains on. Ignoring it quietly is what made -X1 a false
    finding; the two functions together are the fix, so a caller that parses
    counts without also asking unknown_labels has only half of it.

    Args:
        text: Raw counts transcript, e.g. "N 8 L 8 PE 8".

    Returns:
        Dict such as {"N": 8, "L": 8, "PE": 8}. Empty if nothing parsed.
    """
    toks = count_tokens(text)

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


def step_item(item: Item, adj: Adjudicator, source, log: RunLog,
              attempt_no: int, mode: str = "tag") -> Verdict:
    """Run one attempt at one item: prompt, commit, adjudicate, log.

    Exactly one pass. It never loops, sleeps, prints or decides whether to
    re-ask -- the caller owns the attempt count and the re-ask decision.

    Args:
        item: The checklist item being read.
        adj: Adjudicator for the cabinet.
        source: Input with .device(prompt, attempt) and .strip(prompt, attempt).
        log: RunLog that receives this attempt.
        attempt_no: 1 for the first try; higher for a silent re-ask.
        mode: "part" = part number + rating line (CONTEXT §7);
            "tag" = tag only -- simpler, and blind to a wrong part.

    Returns:
        The Verdict for this attempt, already recorded in the log.
    """
    # --- prompt: location only. The expected value is not consulted.
    if hasattr(source, "_tag"):
        source._tag = item.tag        # scripted input only
    read = (source.strip(item.spoken, attempt_no) if item.kind == "strip"
            else source.device(item.spoken, attempt_no))

    # --- commit: normalise before anything is compared.
    #
    # The repetition guard comes first and SHORT-CIRCUITS the adjudicator. A
    # looped decode is not a read of this position, so there is nothing here
    # to judge against the schematic; judging it anyway is how a recogniser
    # failure is published as a finding about the cabinet. -X1 of run
    # 20260927-130613 is what that costs: "N" heard as "M" was reported as
    # "N: read 0, expected 1" against an unfaulted strip the walker had in
    # fact counted correctly. A loop is the same error with a louder tell,
    # and this is the tell. The attempt is still logged in full, and the
    # abstain spends a re-ask exactly as any other abstain does.
    stuck = runaway_reason(read)
    if stuck:
        # expected carries the tag, as every other abstain does. An empty
        # expected means "no such item in the schematic" (see Verdict), and
        # this position is in it -- it was simply never read.
        verdict = Verdict(ABSTAIN, stuck, item.tag,
                          {"raw": read.raw}, {"tag": item.tag})
        normalised, well_formed = "", False
    elif item.kind == "strip":
        counts = parse_counts(read.counts_raw)
        strays = unknown_labels(read.counts_raw)
        normalised = str(counts)
        well_formed = bool(counts) and not strays
        if counts and strays:
            # Abstained, not judged, for the reason in unknown_labels: an
            # unknown label is indistinguishable from a count that was never
            # spoken, so the counts that DID parse cannot be trusted either.
            # This is the branch -X1 needed and did not have.
            #
            # "counts and strays", not "strays" alone: a read that parsed
            # NOTHING is already handled, and better, by judge_strip's "no
            # counts were given". Whisper writes silence as "You", and
            # "the read names YOU" would be a worse account of an empty clip
            # than the one that branch already gives. The danger this guards
            # is the PARTIAL read -- counts that look complete and are not.
            verdict = Verdict(
                ABSTAIN,
                f"the read names {', '.join(strays)}, which is no terminal "
                f"function here (known: "
                f"{', '.join(sorted(FUNCTIONS))}); the counts cannot be "
                f"trusted. Ask again",
                item.tag, {"counts": counts},
                {"counts": dict(adj.expected_counts(item.tag)),
                 "tag": item.tag})
        else:
            verdict = adj.judge_strip(item.tag, counts)
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
    return verdict


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

            verdict = step_item(item, adj, source, log, attempt_no, mode=mode)

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


# ---------------------------------------------------------------------------
# The conversational loop (Block 7, experimental)
# ---------------------------------------------------------------------------

# Words that end the run. The LOOP owns stopping, not the model: there is no
# end_run tool and there is not going to be one. A model that could end a run
# could end it early, and a walk cut short at position 12 scores the 58
# positions after it as never walked.
EXIT_WORDS = frozenset({"done", "all done", "finished", "finish", "stop",
                        "quit", "exit", "that is it", "thats it"})

# A ceiling on turns, for the same reason every turn has one: a loop that
# cannot end is a loop that holds the log open.
MAX_TURNS = 400

OPENING = ("Say 'where next' to start. Say 'done' when you are finished.")

CLOSING = "That is every position. The walk is finished."

NOTHING_OPEN = "Nothing is open yet. Say 'where next' to start."


def voice_of(tool: str, result: dict, kind: str | None = None) -> str:
    """What the agent says aloud after one tool ran.

    The counterpart of orchestrator.redact(), pointing the other way.
    redact() decides what the MODEL may be told; this decides what the
    TRAINEE may be told, and the two withhold different things for
    different reasons.

    submit_reading is the whole reason this function exists rather than the
    loop reading a field out of the result. The result carries outcome,
    reason and expected -- the full verdict, because the log needs it -- and
    none of it may be spoken. A re-ask in this study is silent (session.py:
    "no echo, no hint"), because a trainee who learns the last read was
    wrong reads the next one differently. So all that is said is the re-ask
    wording, or nothing at all.

    explain_location is the other one worth stating. Its result carries a
    strip's terminal count, because the walker card prints it. It is still
    not spoken HERE: the trainee has been sent to that strip to count the
    terminals, and an agent that read the count out would be answering the
    question it just asked.

    Args:
        tool: The tool that ran.
        result: Its full, unredacted result.
        kind: "device" or "strip" for the open position, where the result
            does not carry it. Used only to choose the re-ask wording.

    Returns:
        What to say. "" says nothing, which is a real answer here.
    """
    if tool == "submit_reading":
        if not result.get("ask_again"):
            return ""                 # accepted. Nothing is revealed, ever.
        return ("Please count them again." if kind == "strip"
                else "Please read it again.")

    if tool == "next_location":
        if result.get("done"):
            return CLOSING
        asks = ("Count the terminals." if result.get("kind") == "strip"
                else "Read the tag.")
        return f"{result['location']}. {asks}"

    if tool == "repeat":
        if result.get("nothing_to_repeat"):
            return NOTHING_OPEN
        return f"{result['location']}. {result['say']}"

    if tool == "progress":
        return (f"{result['read']} read, {result['skipped']} skipped, "
                f"{result['remaining']} to go.")

    if tool == "skip":
        if result.get("error"):
            return f"There is no position {result.get('asked_for')}."
        return (f"Position {result['skipped']} skipped. "
                f"{result['remaining']} to go.")

    if tool == "explain_location":
        if result.get("nothing_open"):
            return NOTHING_OPEN
        # No terminal count: see the docstring.
        return (f"{result['frame']}, row {result['row']}, "
                f"position {result['place_in_row']}.")

    return ""


def _is_exit(utterance: str) -> bool:
    """Whether the trainee just ended the run.

    Args:
        utterance: What they said.

    Returns:
        True if the whole utterance is an exit phrase. Whole, not contained:
        "I am not done yet" is not a request to stop.
    """
    bare = re.sub(r"[^a-z0-9 ]+", "", utterance.lower()).strip()
    bare = re.sub(r"\s+", " ", bare)
    return bare in EXIT_WORDS


def dispatch_note(out: dict, failure: dict | None = None) -> str:
    """One line naming what the dispatcher chose this turn.

    Printed, never spoken. Run 20261006-184627 is why it exists: a turn came
    back as a question instead of a reading and there was no way afterwards
    to tell whether the model had chosen to speak, whether the request had
    timed out, or whether the phrase classifier had not recognised it. The
    three need different fixes and the run recorded none of them.

    Args:
        out: What Orchestrator.say returned.
        failure: The dispatcher's newest recorded failure, if this turn
            added one. LlamaCppLLM turns an error into the same clarify a
            puzzled model gives, so without this they are indistinguishable.

    Returns:
        A bracketed line for the terminal.
    """
    # Imported here, not at module scope: orchestrator imports this module
    # for step_item, so the dependency only goes one way at import time.
    from .orchestrator import CLARIFY

    if "tool" in out:
        arguments = out.get("arguments") or {}
        shown = f" {arguments}" if arguments else ""
        return f"[dispatch: {out['tool']}{shown}]"
    if failure is not None:
        return (f"[dispatch: clarify — {failure['kind']}: "
                f"{failure['detail'][:60]}]")
    if out.get("reply") == CLARIFY:
        return "[dispatch: clarify]"
    return "[dispatch: the model spoke]"


def agent_loop(orc, listen, say, max_turns: int = MAX_TURNS) -> int:
    """Hold one spoken conversation over an Orchestrator.

    The loop owns the microphone and the speaker and nothing else. It does
    not judge and does not choose a tool: it hands each utterance to the
    orchestrator and says what comes back.

    One thing it does do is walk. Once a reading has settled, the loop calls
    next_location itself and says where to go, so a trainee reads a position
    and is sent to the next one without having to ask. It advances on a
    settled reading WHATEVER the verdict was -- and that is the whole reason
    it is safe to do. Advancing only on a correct reading would tell the
    trainee the outcome by moving, which is the thing re-asks are silent to
    avoid. A reading still being re-asked does not advance and is answered
    with the re-ask line and nothing else.

    listen and say are injected rather than built here, so the loop can be
    driven from a test with no microphone, no model and no sound card. The
    voice and typed front ends differ only in which listen is passed.

    Args:
        orc: An Orchestrator.
        listen: Called for each turn. Returns the trainee's words, or None
            when there is no more input (end of file, or the mic closed).
        say: Called with each line to speak. Empty strings are passed on and
            are expected to say nothing.
        max_turns: Ceiling on turns.

    Returns:
        How many turns were taken.
    """
    turns = 0
    say(OPENING)
    failures = getattr(orc.llm, "failures", None)

    while turns < max_turns:
        value = listen()
        if value is None:
            break
        turns += 1
        heard = Heard.of(value)
        if _is_exit(heard.text):
            break

        # Captured before dispatch: submit_reading may settle the position,
        # and the re-ask wording depends on what kind it was.
        kind = orc.current.kind if orc.current else None
        before = len(failures) if failures is not None else 0

        try:
            out = orc.say(heard.text, audio_path=heard.audio_path,
                          confidence=heard.confidence)
        except RuntimeError as exc:
            # submit_reading refuses a reading with no position open rather
            # than inventing the position it would belong to, and that
            # refusal is right and stays. What must not happen is the run
            # ending over it: a trainee reading a label before being sent
            # anywhere is a thing that happens, and run 20261006-184627 is
            # the run where it did. So it becomes a prompt.
            print("    [dispatch: refused, nothing is open]")
            say(NOTHING_OPEN)
            continue
        newest = (failures[-1] if failures is not None
                  and len(failures) > before else None)
        print(f"    {dispatch_note(out, newest)}")

        if "reply" in out:
            say(out["reply"])
            continue

        say(voice_of(out["tool"], out["result"], kind))

        if (out["tool"] == "submit_reading"
                and not out["result"]["ask_again"]):
            moved = orc.call("next_location")
            say(voice_of("next_location", moved))
            if moved.get("done"):
                break
            continue

        if out["tool"] == "next_location" and out["result"].get("done"):
            break

    return turns


def run_agent(args, adj: Adjudicator, items: list[Item], log: RunLog) -> None:
    """Build the conversational front end from the CLI flags and run it.

    Args:
        args: Parsed arguments.
        adj: Adjudicator for the cabinet.
        items: Checklist items in walking order.
        log: RunLog receiving every attempt, in the usual format.
    """
    from ..speech.audio_input import init_tts, speak as speak_aloud
    from .orchestrator import LlamaCppLLM, MockLLM, Orchestrator

    llm = LlamaCppLLM() if args.llm else MockLLM()
    print(f"  dispatcher: {type(llm).__name__}"
          + (f" ({llm.model})" if args.llm else " (offline phrase mapping)"))

    orc = Orchestrator(adj, items, log, llm, max_reasks=args.max_reasks,
                       mode=args.mode)
    # The agent speaks unless told not to. --speak is an opt-in on the other
    # paths, where the prompt is also on the screen; here the voice IS the
    # front end. A run that cannot speak says so now, before anyone walks to
    # the cabinet, rather than printing its lines and looking fine.
    speaker = init_tts(not args.no_speak)
    print(f"  voice: {'on' if speaker is not None else 'off, printed only'}")

    if args.text:
        listen = _typed_listener()
    else:
        listen = _voice_listener(log.dir / "audio", args)

    started = time.monotonic()
    turns = agent_loop(orc, listen, lambda line: speak_aloud(line, speaker))
    log.duration_s = time.monotonic() - started
    print(f"\n  {turns} turn(s).")

    orc.finish()
    triage(log)
    log.write_report(expected_items=len(items), duration_s=log.duration_s)


def _typed_listener():
    """A listen() that reads lines from the keyboard.

    Returns:
        The callable. It returns None at end of file, which ends the loop.
    """
    def listen() -> str | None:
        """Read one typed turn.

        Returns:
            The line, or None at end of file.
        """
        try:
            return input("\n  you> ")
        except EOFError:
            return None
    return listen


def _voice_listener(audio_dir: Path, args):
    """A listen() that records a turn, keeps the WAV and transcribes it.

    Args:
        audio_dir: Folder for the turn WAVs, one per turn, kept.
        args: Parsed arguments, for the model size and the VAD settings.

    Returns:
        The callable.
    """
    from ..speech.audio_input import LocalTranscriber, Recorder

    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    recorder = Recorder()
    asr = LocalTranscriber(args.model)
    turn = itertools.count(1)

    def listen() -> Heard:
        """Record, keep and transcribe one turn.

        Returns:
            The turn, with the clip it was recorded to. The text is "" when
            nothing was said, and the empty string is passed on rather than
            swallowed: the dispatcher answers it by asking again, which is
            the right answer to silence, and a loop that re-recorded
            instead would hide it. The clip is returned either way, because
            "they said nothing" is a thing a reviewer may need to hear.
        """
        path = audio_dir / f"turn_{next(turn):03d}.wav"
        _path, reason = recorder.record_until_silence(
            path, silence_s=args.vad_silence, max_s=args.vad_max)
        text, conf = asr.transcribe(path)
        print(f"    heard: {text!r}  [{reason}; {path.name}]")
        return Heard(text, audio_path=str(path), confidence=conf)

    return listen


def main() -> None:
    """CLI: parse flags, build checklist and input source, run, triage, report."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default=SCHEMATIC)
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N items (smoke test only)")
    ap.add_argument("--runs-dir", default=RUNS)
    ap.add_argument("--scripted", action="store_true",
                    help="smoke test: feed the schematic back in, no keyboard")
    ap.add_argument("--live", action="store_true",
                    help="use the microphone and local Whisper")
    ap.add_argument("--model", default="small",
                    help="faster-whisper size: tiny|base|small|medium|large-v3")
    ap.add_argument("--speak", action="store_true",
                    help="read prompts aloud (needs pyttsx3)")
    ap.add_argument("--agent", action="store_true",
                    help="conversational loop: the trainee says where to go "
                         "and an LLM dispatches (Block 7 orchestrator)")
    ap.add_argument("--text", action="store_true",
                    help="--agent with typed turns instead of the microphone")
    ap.add_argument("--no-speak", action="store_true",
                    help="--agent: print the agent's lines instead of "
                         "speaking them. It speaks by default: it is a voice "
                         "loop, so silence is the thing to ask for")
    ap.add_argument("--llm", action="store_true",
                    help="--agent with a real model over LLM_URL/LLM_MODEL; "
                         "the offline phrase mapping otherwise")
    ap.add_argument("--vad-silence", type=float, default=VAD_SILENCE_S,
                    help=f"--agent: quiet that ends a spoken turn, in "
                         f"seconds (default {VAD_SILENCE_S})")
    ap.add_argument("--vad-max", type=float, default=VAD_MAX_S,
                    help=f"--agent: ceiling on one spoken turn, in seconds "
                         f"(default {VAD_MAX_S})")
    ap.add_argument("--mode", choices=["part", "tag"], default="tag",
                    help="'part': part number + rating line. "
                         "'tag': tag only -- cannot detect a wrong part")
    ap.add_argument("--kind", choices=["device", "strip", "all"], default="all",
                    help="restrict the run to one item kind")
    ap.add_argument("--max-reasks", type=int, default=MAX_REASKS,
                    help=f"silent re-asks allowed after an abstain "
                         f"(default {MAX_REASKS}, so {MAX_REASKS + 1} attempts)")
    ap.add_argument("--part-edit-max", type=int, default=PART_EDIT_MAX,
                    help="part numbers this near the expected value abstain "
                         f"instead of not-in-schematic (default {PART_EDIT_MAX})")
    ap.add_argument("--tag-edit-max", type=int, default=TAG_EDIT_MAX,
                    help=f"the same threshold for tags (default {TAG_EDIT_MAX})")
    args = ap.parse_args()

    adj = Adjudicator.from_export(args.export,
                                  part_edit_max=args.part_edit_max,
                                  tag_edit_max=args.tag_edit_max)
    items = load_checklist()
    if args.kind != "all":
        items = [i for i in items if i.kind == args.kind]
    if args.limit:
        items = items[: args.limit]

    print(f"Cabinet 20160387 · {len(items)} items · band then position")
    print("Advisory only. This run passes or fails nothing.\n")

    log = RunLog(root=Path(args.runs_dir))
    if args.agent:
        if args.mode == "tag":
            print(TAG_MODE_WARNING)
        run_agent(args, adj, items, log)
        print(f"\nReport: {log.dir / 'report.md'}")
        return

    if args.scripted:
        source = ScriptedInput(adj)
    elif args.live:
        from ..speech.audio_input import LiveInput
        source = LiveInput(log.dir / "audio", model_size=args.model,
                           speak=args.speak, mode=args.mode)
    else:
        source = KeyboardInput(args.mode)
    if args.mode == "tag":
        print(TAG_MODE_WARNING)
    run(items, adj, source, log, max_reasks=args.max_reasks, mode=args.mode)
    if not args.scripted:
        triage(log)
        # Re-emit so annotations appear. Keep the duration from the timed run.
        log.write_report(expected_items=len(items), duration_s=log.duration_s)
    print(f"\nReport: {log.dir / 'report.md'}")


if __name__ == "__main__":
    main()