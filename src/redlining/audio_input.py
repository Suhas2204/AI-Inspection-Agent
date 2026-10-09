"""Block 7: live microphone input (record -> keep WAV -> transcribe locally).

- Same interface as KeyboardInput: .device(prompt, attempt) and
  .strip(prompt, attempt), each returning a session.Read.
- Audio is kept for EVERY attempt: Block 8's gate is that the audio behind
  any flag can be replayed, and flags are not known while recording.
- Captures and transcribes only. Judgement happens later, in Block 6.
- Recording per attempt is Enter-to-start, Enter-to-stop, so it needs a real
  interactive terminal. The conversational loop uses record_until_silence
  instead, which ends a turn on an energy gate with Enter as a fallback: a
  trainee with both hands on a cabinet cannot press Enter twice a turn.

Install:
    uv add sounddevice soundfile faster-whisper
"""

from __future__ import annotations

import math
import queue
import sys
import threading
from pathlib import Path

from .core.types import Read

SAMPLE_RATE = 16_000          # what Whisper wants; resampling is one more thing
CHANNELS = 1

# --- endpointing, for the conversational loop ------------------------------
#
# The agent loop cannot ask the trainee to press Enter twice per turn: their
# hands are on a cabinet. So a turn ends when they stop talking.
#
# This is an ENERGY GATE, not Silero. It compares the RMS of each frame to a
# threshold and ends the turn after a stretch of quiet. Silero runs in
# LocalTranscriber already (vad_filter=True), but it scores a whole file after
# the fact, which is no use for deciding when to stop recording. An energy
# gate is the cheap thing that works in a quiet lab and is honest about what
# it is: in a noisy workshop it will cut late, or not at all, which is why
# Enter still stops a turn and why every turn has a hard ceiling.
#
# None of these numbers are measured. They are starting points, exposed as
# --vad-silence and --vad-max so a run can move them without an edit.
VAD_FRAME_S = 0.03      # the usual VAD frame: stable RMS, no clipped word tail
VAD_THRESHOLD = 0.015   # RMS of float samples, full scale 1.0
VAD_ONSET_S = 0.15      # loud for this long before a turn counts as started
VAD_SILENCE_S = 1.2     # quiet for this long after speech ends the turn
VAD_MAX_S = 20.0        # ceiling, so a stuck turn cannot hold the run open


def rms(block) -> float:
    """Root-mean-square level of one block of samples.

    Args:
        block: Samples, any shape numpy accepts. Empty is allowed.

    Returns:
        The RMS as a float, 0.0 for an empty block.
    """
    import numpy as np

    arr = np.asarray(block, dtype="float64")
    return float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0


class Endpointer:
    """Decides when a spoken turn has ended, from frame energy alone.

    Separated from the recorder so it can be tested without a microphone:
    feed it levels and it says when to stop. Every reason it stops is named,
    because "nothing was recorded" and "they talked past the ceiling" are
    different events and a loop that could not tell them apart would report
    both as an empty reading.

    Attributes:
        started: Whether speech has been detected yet.
        elapsed_s: Audio fed so far, in seconds.
    """

    def __init__(self, threshold: float = VAD_THRESHOLD,
                 silence_s: float = VAD_SILENCE_S, max_s: float = VAD_MAX_S,
                 onset_s: float = VAD_ONSET_S, frame_s: float = VAD_FRAME_S):
        """Set the gate up.

        Args:
            threshold: RMS at or above which a frame counts as speech.
            silence_s: Quiet needed after speech to end the turn.
            max_s: Hard ceiling on one turn.
            onset_s: Speech needed before the turn counts as started. A
                single loud frame is a door or a dropped tool, not a word.
            frame_s: Seconds of audio per fed frame.
        """
        self.threshold = threshold
        self.silence_s = silence_s
        self.max_s = max_s
        self.onset_s = onset_s
        self.frame_s = frame_s
        self.started = False
        self.elapsed_s = 0.0
        self._loud_s = 0.0
        self._quiet_s = 0.0

    def feed(self, level: float) -> str:
        """Add one frame and say whether the turn is over.

        Args:
            level: RMS of the frame, as rms() returns it.

        Returns:
            "" to keep recording, or why it stopped: "silence" (they finished
            speaking), "max" (they were still going at the ceiling), or
            "no-speech" (the ceiling arrived and nothing was ever said).
        """
        self.elapsed_s += self.frame_s
        loud = level >= self.threshold

        if not self.started:
            self._loud_s = self._loud_s + self.frame_s if loud else 0.0
            if self._loud_s >= self.onset_s:
                self.started = True
                self._quiet_s = 0.0
        else:
            self._quiet_s = 0.0 if loud else self._quiet_s + self.frame_s
            if self._quiet_s >= self.silence_s:
                return "silence"

        if self.elapsed_s >= self.max_s:
            return "max" if self.started else "no-speech"
        return ""


# --- speaking --------------------------------------------------------------
#
# One speaker, used by LiveInput's prompts and by the agent loop's replies.
# Two copies would drift, and the one that drifted would be the one nobody
# listened to in a test.
#
# A NEW pyttsx3 engine per utterance, which is not a style choice. Measured
# on this machine (Windows, SAPI5), one engine reused across three lines:
#
#     utterance 1   3.453 s   audible
#     utterance 2   0.172 s   silent
#     utterance 3   0.094 s   silent
#
# All three fired started-utterance and all three returned normally, so
# nothing in the API says anything went wrong -- the engine simply stops
# producing audio after its first runAndWait() and keeps reporting success.
# That is why the agent printed its lines and said nothing from the second
# turn on.
#
# pyttsx3.init() cannot fix it: it memoises per driver name in
# _activeEngines and hands back the SAME dead engine. Constructing
# pyttsx3.Engine() directly bypasses that cache, and the same three lines
# then take 4.687 s, 1.813 s and 2.218 s and are all audible. A dedicated
# thread per utterance measured the same; the thread was never the cure, the
# cache was, so the simpler of the two is what is here.

class Speaker:
    """Says one line at a time, on a new engine each time.

    Failures are reported and counted, never swallowed. A run is a person
    standing at a cabinet: losing the voice is a degradation they must be
    told about, and an exception out of the speaker would end the walk over
    something that is not the walk.

    Attributes:
        spoken: Lines successfully spoken.
        failures: One message per line that could not be spoken.
    """

    def __init__(self, factory=None):
        """Set the speaker up without building an engine.

        Args:
            factory: Called with no arguments to build one engine. Defaults
                to pyttsx3.Engine. Injected so a test can drive the failure
                path, and count engines, with no sound card in the machine.
        """
        self._factory = factory
        self.spoken = 0
        self.failures: list[str] = []

    def _engine(self):
        """Build one engine.

        Returns:
            A new pyttsx3 engine, NOT pyttsx3.init()'s cached one.
        """
        if self._factory is not None:
            return self._factory()
        import pyttsx3
        return pyttsx3.Engine()

    def say(self, text: str) -> bool:
        """Speak one line on an engine of its own.

        Args:
            text: What to say.

        Returns:
            True if it was spoken, False if it failed. A failure is printed
            to stderr as it happens and kept in `failures`.
        """
        try:
            engine = self._engine()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            note = f"{type(exc).__name__}: {exc}"
            self.failures.append(note)
            print(f"  [tts failed: {note}]", file=sys.stderr)
            return False
        try:
            engine.stop()
        except Exception:
            pass          # the line was already spoken; tearing down is not
        self.spoken += 1
        return True


def init_tts(enabled: bool = True):
    """Build the speaker and prove it can speak before the walk starts.

    The probe is the point. A trainee who gets to the cabinet before anyone
    notices the voice is dead has walked to the cabinet for nothing, and the
    failure this fixes was silent in exactly that way.

    Args:
        enabled: False returns None without trying, for a run that should
            print only.

    Returns:
        A Speaker, or None if speech is off or could not be made to work.
        None means every line is printed and not spoken, which the caller
        announces rather than hides.
    """
    if not enabled:
        return None
    try:
        import pyttsx3  # noqa: F401
    except Exception as exc:
        print(f"  (no text-to-speech: {type(exc).__name__}: {exc})")
        return None

    speaker = Speaker()
    if not speaker.say("Ready."):
        print("  (text-to-speech did not speak; lines will be printed only)")
        return None
    return speaker


def speak(text: str, speaker=None, indent: str = "  ") -> None:
    """Print one line and, if there is a speaker, say it aloud.

    The "[speaking]" marker is a diagnostic kept on purpose: it is how a run
    shows that it reached the speaker at all. Without it, a line printed
    with no sound looks the same whether speech was switched off, the engine
    was never built, or the engine was built and went quiet.

    Empty text says nothing at all. The agent loop relies on that: after a
    reading is accepted there is deliberately nothing to say, and a helper
    that printed a blank line would make silence look like a bug.

    Args:
        text: What to say. Empty or None is a no-op.
        speaker: A Speaker from init_tts(), or None to print only.
        indent: Leading spaces, matching the rest of the terminal output.
    """
    if not text:
        return
    marker = "[speaking] " if speaker is not None else ""
    print(f"\n{indent}{marker}{text}")
    if speaker is not None:
        speaker.say(text)


class _EnterWatcher:
    """One stdin reader for the whole process, so turns cannot pile up.

    A thread blocked on input() cannot be cancelled. A watcher started per
    turn therefore outlives its turn and goes on waiting, and every extra
    one competes for the same stdin: the Enter meant to end turn 9 can be
    taken by the thread still waiting from turn 3, and the turn it was meant
    for runs to the ceiling instead. One reader, started once, with a queue
    the recorder drains at the start of each turn so a stale press cannot
    end the next turn before it begins.

    Attributes:
        started: Whether the reader thread is running.
    """

    def __init__(self):
        """Set up the queue without starting the reader."""
        self._presses: queue.Queue = queue.Queue()
        self.started = False

    def _read_forever(self) -> None:
        """Push one item per line read from stdin, until stdin ends."""
        while True:
            try:
                input()
            except (EOFError, OSError):
                return
            self._presses.put(True)

    def start(self) -> None:
        """Start the reader, once."""
        if not self.started:
            threading.Thread(target=self._read_forever, daemon=True).start()
            self.started = True

    def drain(self) -> None:
        """Discard presses that arrived before this turn."""
        while not self._presses.empty():
            self._presses.get()

    def pressed(self) -> bool:
        """Whether Enter has been pressed since the last drain.

        Returns:
            True if at least one press is waiting.
        """
        return not self._presses.empty()


ENTER = _EnterWatcher()


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
            """Queue each incoming audio block (sounddevice stream callback).

            Args:
                indata: The block of samples just captured. It is copied
                    before queuing, because sounddevice reuses the buffer.
                _frames: Sample count, which the queue does not need.
                _time: Stream timestamps, unused.
                status: Underrun or overrun flags, reported to stderr so a
                    dropped block is visible rather than silent.
            """
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


    def record_until_silence(self, path: Path,
                             silence_s: float = VAD_SILENCE_S,
                             max_s: float = VAD_MAX_S,
                             threshold: float = VAD_THRESHOLD
                             ) -> tuple[Path, str]:
        """Record one spoken turn, ending when the speaker stops.

        For the conversational loop, where a trainee has both hands on a
        cabinet and cannot press Enter twice a turn. Enter still works and
        still stops the turn, because the gate is an energy threshold and
        will not survive a noisy workshop on its own.

        The WAV is written whichever way the turn ended, including when
        nothing was said: Block 8's gate is that the audio behind any flag
        can be replayed, and an empty file is itself the record that the
        trainee said nothing. Never reuse the previous turn's clip to stand
        in for a failed one.

        Args:
            path: WAV file to write.
            silence_s: Quiet after speech that ends the turn.
            max_s: Hard ceiling on one turn.
            threshold: RMS at or above which a frame counts as speech.

        Returns:
            (path, reason), reason being "silence", "max", "no-speech" or
            "enter". The caller prints it, so a turn that ended because
            nobody spoke does not look like a turn that was understood.
        """
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        frames: queue.Queue = queue.Queue()
        blocksize = max(1, int(self.sample_rate * VAD_FRAME_S))

        def callback(indata, _frames, _time, status):
            """Queue each incoming block (sounddevice stream callback).

            Args:
                indata: Samples just captured, copied because sounddevice
                    reuses the buffer.
                _frames: Sample count, unused.
                _time: Stream timestamps, unused.
                status: Underrun or overrun flags, reported to stderr.
            """
            if status:
                print(f"    [audio: {status}]", file=sys.stderr)
            frames.put(indata.copy())

        print("    [speak — it stops when you do, or press Enter]")
        ENTER.start()
        ENTER.drain()          # a press from an earlier turn is not this one

        gate = Endpointer(threshold=threshold, silence_s=silence_s,
                          max_s=max_s, frame_s=blocksize / self.sample_rate)
        chunks: list = []
        reason = ""
        with sd.InputStream(samplerate=self.sample_rate, channels=CHANNELS,
                            blocksize=blocksize, callback=callback):
            while not reason and not ENTER.pressed():
                try:
                    block = frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                chunks.append(block)
                reason = gate.feed(rms(block))

        while not frames.empty():            # whatever arrived on the way out
            chunks.append(frames.get())
        if not reason:
            reason = "enter"

        path.parent.mkdir(parents=True, exist_ok=True)
        if not chunks:
            path.write_bytes(b"")
            return path, "no-speech"
        sf.write(str(path), np.concatenate(chunks, axis=0), self.sample_rate)
        return path, reason


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

        vad_filter=True since 5 Oct 2026. Silero VAD drops the non-speech
        stretches before decoding, which is what stops the runaway decodes of
        run 20260927-130613 shorter: measured on that run's own clips by
        experiments/block05_asr/vad_compare.py, it cut -12F4 attempt 1 from 22
        tokens to 3 and -7F9 attempt 1 from 112 tokens to 28 -- shorter, but
        -7F9 is still 28 repetitions of "9" and still not a read. It is not
        free either: on the same run it turned -X1's "L3" into "N3", trading
        one misread for another, and it needs onnxruntime present. So the
        repetition guard in normalise.runaway is not redundant with this;
        it is what actually catches the loop VAD only shortened.

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
            vad_filter=True,                    # see VAD note in the docstring
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
        """Start text-to-speech. Kept as a method so callers are unchanged.

        Returns:
            The TTS engine, or None if unavailable.
        """
        return init_tts(True)

    def _say(self, text: str) -> None:
        """Print a prompt and, if TTS is on, speak it.

        Args:
            text: Prompt to show and say.
        """
        speak(text, self._tts)

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
        if attempt == 1:
            self._say(prompt)
        else:
            self._say("Please count them again.")

        print("    counts, e.g. 'N 8 L 8 PE 8':")
        txt, path, conf = self._capture("counts", attempt)
        return Read(counts_raw=txt, confidence=conf, audio_path=path)