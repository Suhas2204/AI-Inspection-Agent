"""Block 7: live microphone input (record -> keep WAV -> transcribe locally).

- Same interface as KeyboardInput: .device(prompt, attempt) and
  .strip(prompt, attempt), each returning a session.Read.
- Audio is kept for EVERY attempt: Block 8's gate is that the audio behind
  any flag can be replayed, and flags are not known while recording.
- Captures and transcribes only. Judgement happens later, in Block 6.
- Recording is Enter-to-start, Enter-to-stop (no voice-activity detection),
  so it needs a real interactive terminal.

Install:
    uv add sounddevice soundfile faster-whisper
"""

from __future__ import annotations

import math
import queue
import sys
import threading
from pathlib import Path

SAMPLE_RATE = 16_000          # what Whisper wants; resampling is one more thing
CHANNELS = 1


class Recorder:
    """Records microphone audio to a WAV file between two Enter presses."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        """Check the audio packages are installed (exits if not).

        Args:
            sample_rate: Recording rate in Hz; 16 kHz is what Whisper expects.
        """
        try:
            import sounddevice  # noqa: F401
            import soundfile    # noqa: F401
        except ImportError:
            sys.exit("Missing audio deps. Run: uv add sounddevice soundfile")
        self.sample_rate = sample_rate

    def record_to(self, path: Path) -> Path:
        """Record from the default microphone between two Enter presses.

        Args:
            path: WAV file to write.

        Returns:
            The same path. The file is written empty if nothing was captured.
        """
        import sounddevice as sd
        import soundfile as sf

        frames: queue.Queue = queue.Queue()
        stop = threading.Event()

        def callback(indata, _frames, _time, status):
            """Queue each incoming audio block (sounddevice stream callback)."""
            if status:
                print(f"    [audio: {status}]", file=sys.stderr)
            frames.put(indata.copy())

        input("    [Enter to start recording]")
        with sd.InputStream(samplerate=self.sample_rate, channels=CHANNELS,
                            callback=callback):
            t = threading.Thread(target=lambda: (input("    [recording — Enter to stop]"),
                                                 stop.set()), daemon=True)
            t.start()
            while not stop.is_set():
                sd.sleep(50)

        chunks = []
        while not frames.empty():
            chunks.append(frames.get())
        if not chunks:
            path.write_bytes(b"")
            return path

        import numpy as np
        audio = np.concatenate(chunks, axis=0)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio, self.sample_rate)
        return path


class LocalTranscriber:
    """Local faster-whisper transcriber, loaded once and reused. No network, no API key."""

    def __init__(self, model_size: str = "small", language: str = "en"):
        """Load the Whisper model on CPU (int8). Exits if faster-whisper is missing.

        Args:
            model_size: tiny | base | small | medium | large-v3.
            language: Spoken language code passed to Whisper.
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            sys.exit("Missing ASR dep. Run: uv add faster-whisper")
        print(f"  loading {model_size} (first run downloads weights) ...")
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.language = language
        print("  ready.\n")

    def transcribe(self, path: Path) -> tuple[str, float | None]:
        """Transcribe one WAV file (no initial prompt, so misreads stay visible).

        Args:
            path: Recorded WAV file.

        Returns:
            (text, confidence): joined transcript and mean segment probability
            (0-1). ("", None) if the file is missing or empty.
        """
        if not path.exists() or path.stat().st_size == 0:
            return "", None
        segments, _info = self.model.transcribe(
            str(path),
            language=self.language,
            beam_size=5,
            temperature=0.0,
            condition_on_previous_text=False,   # one read must not prime the next
            # NO initial_prompt. Seeding the decoder with part numbers would bias
            # it toward them and hide the misread this whole project measures.
        )
        segs = list(segments)
        text = " ".join(s.text.strip() for s in segs).strip()
        logprobs = [s.avg_logprob for s in segs if s.avg_logprob is not None]
        conf = round(math.exp(sum(logprobs) / len(logprobs)), 3) if logprobs else None
        return text, conf


class LiveInput:
    """Microphone input. Drop-in replacement for KeyboardInput."""

    _tag = ""

    def __init__(self, audio_dir: Path, model_size: str = "small",
                 speak: bool = False, mode: str = "part"):
        """Set up the recorder, the Whisper model and optional text-to-speech.

        Args:
            audio_dir: Folder where each attempt's WAV is kept (created if missing).
            model_size: faster-whisper size, e.g. "small" or "large-v3".
            speak: Read prompts aloud with pyttsx3, if available.
            mode: "tag" for the tag only, "part" for part number + rating line.
        """
        self.mode = mode
        self.audio_dir = Path(audio_dir)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.recorder = Recorder()
        self.asr = LocalTranscriber(model_size)
        self.speak = speak
        self._tts = self._init_tts() if speak else None

    def _init_tts(self):
        """Start pyttsx3 text-to-speech.

        Returns:
            The TTS engine, or None if unavailable (prompts are then printed only).
        """
        try:
            import pyttsx3
            return pyttsx3.init()
        except Exception:
            print("  (no TTS available — prompts will be printed only)")
            return None

    def _say(self, text: str) -> None:
        """Print a prompt and, if TTS is on, speak it.

        Args:
            text: Prompt to show and say.
        """
        print(f"\n  {text}")
        if self._tts:
            self._tts.say(text)
            self._tts.runAndWait()

    def _capture(self, label: str, attempt: int) -> tuple[str, str, float | None]:
        """Record one clip, keep it under audio_dir, and transcribe it.

        Args:
            label: Part of the file name, e.g. "tag", "part", "counts".
            attempt: Attempt number, also used in the file name.

        Returns:
            (text, audio_path, confidence).
        """
        name =f"{self._tag.lstrip('-')}_{label}_a{attempt}.wav"
        path = self.audio_dir / name
        self.recorder.record_to(path)
        text, conf = self.asr.transcribe(path)
        print(f"    heard: {text!r}")
        return text, str(path), conf

    # ------------------------------------------------------------------------
    def device(self, prompt: str, attempt: int):
        """Ask for and capture one device read by voice.

        Args:
            prompt: Location-only prompt, spoken on the first attempt.
            attempt: 1 for the first try; later tries get a silent re-ask.

        Returns:
            Read with tag_raw (tag mode) or part_raw + rating_raw (part mode),
            plus confidence and audio_path.
        """
        from .session import Read

        if attempt == 1:
            self._say(prompt)                     # location only
        else:
            self._say("Please read it again.")    # silent re-ask: no echo, no hint

        if self.mode == "tag":
            print("    tag:")
            tag_txt, tag_path, tag_conf = self._capture("tag", attempt)
            return Read(tag_raw=tag_txt, confidence=tag_conf, audio_path=tag_path)

        print("    part number:")
        part_txt, part_path, part_conf = self._capture("part", attempt)
        print("    rating line:")
        rate_txt, _rate_path, rate_conf = self._capture("rating", attempt)

        confs = [c for c in (part_conf, rate_conf) if c is not None]
        return Read(
            part_raw=part_txt,
            rating_raw=rate_txt,
            confidence=round(sum(confs) / len(confs), 3) if confs else None,
            audio_path=part_path,
        )

    def strip(self, prompt: str, attempt: int):
        """Ask for and capture one strip's terminal counts by voice.

        Args:
            prompt: Location-only prompt, spoken on the first attempt.
            attempt: 1 for the first try; later tries get a silent re-ask.

        Returns:
            Read with counts_raw, confidence and audio_path.
        """
        from .session import Read

        if attempt == 1:
            self._say(prompt)
        else:
            self._say("Please count them again.")

        print("    counts, e.g. 'N 8 L 8 PE 8':")
        txt, path, conf = self._capture("counts", attempt)
        return Read(counts_raw=txt, confidence=conf, audio_path=path)