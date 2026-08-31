"""Live microphone input for Block 7.

Same interface as KeyboardInput, so session.py does not care which one it gets:

    .device(prompt, attempt) -> Read
    .strip(prompt, attempt)  -> Read

Per read it records a WAV, keeps it, transcribes it locally, and returns the
raw text plus the audio path. The audio is retained for every attempt, not only
flagged ones -- Block 8's gate is that the audio behind any flag can be
replayed, and you cannot know which attempts will be flagged while recording.

Nothing here compares anything against the schematic. It captures and
transcribes. Judgement happens later, in Block 6.

Install:
    uv add sounddevice soundfile faster-whisper

Recording control is Enter-to-start, Enter-to-stop. Deliberately dumb: no
voice-activity detection to tune, no clipped endings, and the trainee controls
exactly what is captured.
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
    """Records to a WAV file between two Enter presses."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        try:
            import sounddevice  # noqa: F401
            import soundfile    # noqa: F401
        except ImportError:
            sys.exit("Missing audio deps. Run: uv add sounddevice soundfile")
        self.sample_rate = sample_rate

    def record_to(self, path: Path) -> Path:
        import sounddevice as sd
        import soundfile as sf

        frames: queue.Queue = queue.Queue()
        stop = threading.Event()

        def callback(indata, _frames, _time, status):
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
    """faster-whisper, loaded once and reused. No network, no API key."""

    def __init__(self, model_size: str = "small", language: str = "en"):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            sys.exit("Missing ASR dep. Run: uv add faster-whisper")
        print(f"  loading {model_size} (first run downloads weights) ...")
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.language = language
        print("  ready.\n")

    def transcribe(self, path: Path) -> tuple[str, float | None]:
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
        self.mode = mode
        self.audio_dir = Path(audio_dir)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.recorder = Recorder()
        self.asr = LocalTranscriber(model_size)
        self.speak = speak
        self._tts = self._init_tts() if speak else None

    def _init_tts(self):
        try:
            import pyttsx3
            return pyttsx3.init()
        except Exception:
            print("  (no TTS available — prompts will be printed only)")
            return None

    def _say(self, text: str) -> None:
        print(f"\n  {text}")
        if self._tts:
            self._tts.say(text)
            self._tts.runAndWait()

    def _capture(self, label: str, attempt: int) -> tuple[str, str, float | None]:
        name = f"{self._tag.lstrip('-')}_{label}_a{attempt}.wav"
        path = self.audio_dir / name
        self.recorder.record_to(path)
        text, conf = self.asr.transcribe(path)
        print(f"    heard: {text!r}")
        return text, str(path), conf

    # ------------------------------------------------------------------------
    def device(self, prompt: str, attempt: int):
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
        from .session import Read

        if attempt == 1:
            self._say(prompt)
        else:
            self._say("Please count them again.")

        print("    counts, e.g. 'N 8 L 8 PE 8':")
        txt, path, conf = self._capture("counts", attempt)
        return Read(counts_raw=txt, confidence=conf, audio_path=path)