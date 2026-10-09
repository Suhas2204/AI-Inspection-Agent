"""Block 7: Streamlit input (transcribe a clip the page already recorded).

- Same interface as KeyboardInput: .device(prompt, attempt) and
  .strip(prompt, attempt), each returning a session.Read.
- It neither records nor prompts. A Streamlit page captures the audio with
  its own widget, writes it to disk, sets .pending_audio_path, and only then
  calls .device() or .strip(). The prompt and attempt arguments exist to
  match the interface; the page has already shown the prompt itself.
- Transcription is not reimplemented here: it is LocalTranscriber from
  audio_input, the same local faster-whisper path the microphone uses.
  large-v3 by default -- a browser page is not a trainee standing in a
  switchroom waiting for the model.
- The pending path is CONSUMED by the call. Calling again without setting a
  fresh file raises instead of re-transcribing the previous clip: one
  attempt, one recording, or the audio behind a flag is not that attempt's
  audio (CONTEXT §4, Block 8's replay gate).

Usage:
    src = StreamlitInput(mode="tag")          # cache this; it holds the model
    src.pending_audio_path = wav_path         # written by the page
    read = src.device(item.spoken, attempt_no)
"""

from __future__ import annotations

from pathlib import Path

from .audio_input import LocalTranscriber
from .core.types import Read

MODEL_SIZE = "small"


class StreamlitInput:
    """Transcribes an already-recorded clip. Drop-in replacement for KeyboardInput.

    Attributes:
        mode: "tag" for the tag only, "part" for part number + rating line.
        model_size: faster-whisper size used when the model is loaded.
        pending_audio_path: Clip the next call transcribes. Set by the caller,
            cleared by the call.
        pending_rating_audio_path: Second clip, part mode only, for the rating
            line. Optional: without it no rating line is read.
    """

    def __init__(self, mode: str = "tag", model_size: str = MODEL_SIZE,
                 asr: LocalTranscriber | None = None):
        """Set up the source without loading the model.

        The model is loaded on first transcription, so building this object is
        cheap enough for a Streamlit script that reruns top to bottom. Pass an
        existing transcriber (e.g. from @st.cache_resource) to share one model
        across reruns.

        Args:
            mode: "tag" to read the tag only, "part" for part number + rating.
            model_size: faster-whisper size, e.g. "large-v3" or "small".
            asr: Already-loaded transcriber to reuse; None loads one on demand.
        """
        self.mode = mode
        self.model_size = model_size
        self._asr = asr
        self.pending_audio_path: str | Path | None = None
        self.pending_rating_audio_path: str | Path | None = None

    @property
    def asr(self) -> LocalTranscriber:
        """The transcriber, loaded on first use and kept for later calls."""
        if self._asr is None:
            self._asr = LocalTranscriber(self.model_size)
        return self._asr

    def _take(self, attr: str,
              required: bool = True) -> tuple[str, str | None, float | None]:
        """Transcribe one pending clip and clear it.

        Clearing is the point: an attempt that was never given a new recording
        must fail loudly, not inherit the previous attempt's transcript.

        Args:
            attr: Name of the pending-path attribute to consume.
            required: Raise if it is unset, rather than returning nothing.

        Returns:
            (text, audio_path, confidence). ("", None, None) if the path was
            unset and not required.

        Raises:
            RuntimeError: The path is required but was not set.
        """
        raw = getattr(self, attr)
        if raw is None:
            if required:
                raise RuntimeError(
                    f"{attr} is not set. Record the clip, write it to disk and "
                    f"set {attr} before each call; it is cleared after every "
                    "read, so one attempt cannot reuse another's audio."
                )
            return "", None, None

        setattr(self, attr, None)
        path = Path(raw)
        text, conf = self.asr.transcribe(path)
        return text, str(path), conf

    # ------------------------------------------------------------------------
    def device(self, prompt: str, attempt: int):
        """Transcribe the pending clip as one device read.

        Args:
            prompt: Ignored; the page has already shown it.
            attempt: Ignored; the caller owns the attempt count.

        Returns:
            Read with tag_raw (tag mode) or part_raw + rating_raw (part mode),
            plus confidence and audio_path.
        """
        text, path, conf = self._take("pending_audio_path")

        if self.mode == "tag":
            return Read(tag_raw=text, confidence=conf, audio_path=path)

        rate_txt, _rate_path, rate_conf = self._take(
            "pending_rating_audio_path", required=False)
        confs = [c for c in (conf, rate_conf) if c is not None]
        return Read(
            part_raw=text,
            rating_raw=rate_txt,
            confidence=round(sum(confs) / len(confs), 3) if confs else None,
            audio_path=path,
        )

    def strip(self, prompt: str, attempt: int):
        """Transcribe the pending clip as one strip's terminal counts.

        Args:
            prompt: Ignored; the page has already shown it.
            attempt: Ignored; the caller owns the attempt count.

        Returns:
            Read with counts_raw, confidence and audio_path.
        """
        text, path, conf = self._take("pending_audio_path")
        return Read(counts_raw=text, confidence=conf, audio_path=path)
