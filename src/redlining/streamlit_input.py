"""Compatibility shim: the Streamlit input moved to speech.streamlit_input.

Re-exports the implementation, which is now in speech/. app.py takes both
names from here-or-there; MODEL_SIZE in particular is the app's default
Whisper size, and experiments/block05_asr/vad_compare.py quotes it in a
comment as the value it matches.

No __main__ here: this module never had one. The page drives it.
"""

from __future__ import annotations

from .speech.streamlit_input import (  # noqa: F401
    MODEL_SIZE,
    StreamlitInput,
)

__all__ = ["MODEL_SIZE", "StreamlitInput"]
