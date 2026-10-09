"""What a turn and a read are, shared by every input source.

These two dataclasses used to live in session.py, next to the loop that
consumes them. Every input adapter has to build one, so audio_input.py and
streamlit_input.py imported session.py to reach them -- while session.py
imports audio_input.py for the endpointing constants. Both halves of that
cycle were only survivable because the adapters deferred their import into
the method body. The types carry no logic and belong to no block, so they
sit here instead and the cycle is gone.

The orchestrator's import of session.py is a different matter: it needs
MAX_REASKS and step_item, not just a type, so that edge stays.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Read:
    """One spoken attempt, before anything has been judged.

    Attributes:
        tag_raw: Raw transcript of a spoken tag.
        part_raw: Raw transcript of a spoken part number.
        rating_raw: Raw transcript of a spoken rating line.
        counts_raw: Raw transcript of spoken strip counts.
        confidence: ASR confidence (0-1), if known.
        audio_path: Where the recording is stored, if any.
    """
    tag_raw: str = ""
    part_raw: str = ""
    rating_raw: str = ""
    counts_raw: str = ""
    confidence: float | None = None
    audio_path: str | None = None

    @property
    def raw(self) -> str:
        """All non-empty raw fields joined with " | "."""
        return " | ".join(x for x in (self.tag_raw, self.part_raw,
                                      self.rating_raw, self.counts_raw) if x)


@dataclass(frozen=True)
class Heard:
    """One turn as it arrived from the trainee.

    The clip is part of the turn, not an afterthought. Block 8's gate is
    that the audio behind any flag can be replayed, and flags are not known
    while recording, so a turn that was recorded has to carry where.

    Attributes:
        text: What was heard, exactly as it arrived.
        audio_path: The clip it came from, or None for a typed turn. None is
            the honest answer there, not a path to a file nobody wrote.
        confidence: ASR confidence (0-1), if known.
    """
    text: str
    audio_path: str | None = None
    confidence: float | None = None

    @classmethod
    def of(cls, value) -> "Heard":
        """Accept either a Heard or a bare string.

        A typed listener and a test script return strings, and there is no
        clip behind either. Wrapping them here keeps listen() simple for the
        callers that have nothing to carry.

        Args:
            value: A Heard, or the words on their own.

        Returns:
            A Heard.
        """
        return value if isinstance(value, cls) else cls(str(value))
