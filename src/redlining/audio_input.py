"""Compatibility shim: Block 7's microphone input moved to speech.audio_input.

Re-exports the implementation, which is now in speech/, including the two
private names: tests/test_agent_loop.py imports _EnterWatcher, and ENTER is
a module-level singleton that has to stay one object -- a second instance
would start a second thread on the same stdin.

No __main__ here: this module never had one. `python -m redlining.session
--live` is how the microphone path is driven.
"""

from __future__ import annotations

from .speech.audio_input import (  # noqa: F401
    CHANNELS,
    ENTER,
    SAMPLE_RATE,
    VAD_FRAME_S,
    VAD_MAX_S,
    VAD_ONSET_S,
    VAD_SILENCE_S,
    VAD_THRESHOLD,
    Endpointer,
    LiveInput,
    LocalTranscriber,
    Recorder,
    Speaker,
    _EnterWatcher,
    init_tts,
    rms,
    speak,
)

__all__ = [
    "CHANNELS", "ENTER", "SAMPLE_RATE", "VAD_FRAME_S", "VAD_MAX_S",
    "VAD_ONSET_S", "VAD_SILENCE_S", "VAD_THRESHOLD", "Endpointer", "LiveInput",
    "LocalTranscriber", "Recorder", "Speaker", "init_tts", "rms", "speak",
]
