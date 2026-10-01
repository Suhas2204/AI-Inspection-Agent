"""Streamlit front end for the inspection session (Block 7).

No session logic lives here. The page owns only what a caller owns: which
item is current, which attempt this is, and whether to re-ask. Every read is
prompt -> commit -> adjudicate -> log inside session.step_item, exactly as
the terminal runner does it, so the two front ends cannot drift.

- Synchronous throughout: one click, one transcription, one rerun. No
  threads, no async, no background workers.
- The recorder is keyed on (item, attempt), so a clip cannot be submitted
  twice; StreamlitInput then consumes the path and raises if it is missing.
  A failed read must be loud -- a silently reused clip would turn "said
  nothing on attempt 2" into a copy of attempt 1 and hide the flag.
- The four tabs read the run folder this session is writing. Only the flag
  annotations write anything, and they are additive: a flag cannot be closed
  here, because closing one would be sign-off (CONTEXT §4).

State is read as st.session_state["key"], never st.session_state.key. The
proxy is a Mapping, so "items" resolves to its .items() method and shadows
the checklist. Subscript access is used for every key so the next key to
collide cannot reintroduce that bug.

Run:
    uv run streamlit run app.py
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import streamlit as st

from redlining.adjudicate import ABSTAIN, Adjudicator
from redlining.audio_input import LocalTranscriber
from redlining.checklist import load_checklist
from redlining.paths import DECISIONS, PROCESSED, ROOT, RUNS, SCHEMATIC
from redlining.report import FLAGGED, Annotation, RunLog
from redlining.session import MAX_REASKS, TAG_MODE_WARNING, step_item
from redlining.streamlit_input import MODEL_SIZE, StreamlitInput

MODE = "tag"                      # what the runs use (CONTEXT §7)
ABSTAIN_CEILING = 0.10            # CONTEXT §8 working ceiling
ANNOTATION_KINDS = ["i_misspoke", "part_looks_wrong", "note"]
SCORE_SCRIPT = ROOT / "src" / "redlining" / "score.py"
FAULTS_CANDIDATES = [
    DECISIONS / "faults.csv",
    ROOT / "experiments" / "block09_eval" / "faults.csv",
    PROCESSED / "faults.csv",
]


@st.cache_resource(show_spinner=f"Loading faster-whisper {MODEL_SIZE} ...")
def load_transcriber(model_size: str = MODEL_SIZE) -> LocalTranscriber:
    """Load the Whisper model once and share it across reruns.

    This cache is load-bearing: without it every rerun reloads large-v3 and
    the page is unusable.

    Args:
        model_size: faster-whisper size to load.

    Returns:
        The shared transcriber.
    """
    return LocalTranscriber(model_size)


def init_state() -> None:
    """Populate st.session_state once per browser session."""
    if "adj" in st.session_state:
        return
    st.session_state["adj"] = Adjudicator.from_export(SCHEMATIC)
    st.session_state["items"] = load_checklist()
    st.session_state["log"] = RunLog(root=RUNS)
    st.session_state["item_index"] = 0
    st.session_state["attempt_no"] = 1
    st.session_state["source"] = StreamlitInput(mode=MODE, asr=load_transcriber())
    st.session_state["last_verdict"] = None
    st.session_state["started"] = time.monotonic()


def elapsed_s() -> float:
    """Seconds since the run began, or the final duration once it has ended.

    Returns:
        The elapsed seconds. After the run is written the stored duration is
        returned instead of a live clock, so the figure on screen matches the
        one in the report rather than drifting past it.
    """
    log = st.session_state["log"]
    if log.duration_s is not None:
        return log.duration_s
    return time.monotonic() - st.session_state["started"]


def finish_run() -> None:
    """Stamp the duration and emit report.json and report.md."""
    log, items = st.session_state["log"], st.session_state["items"]
    log.duration_s = time.monotonic() - st.session_state["started"]
    log.write_report(expected_items=len(items), duration_s=log.duration_s)


def submit(clip, item) -> None:
    """Judge one recorded clip, then advance or re-ask.

    The page decides only what a caller decides. Everything between the clip
    and the log entry is step_item's.

    Args:
        clip: The recorded audio from st.audio_input.
        item: The checklist item being read.
    """
    log = st.session_state["log"]
    attempt_no = st.session_state["attempt_no"]
    label = "counts" if item.kind == "strip" else MODE
    wav = Path(log.dir) / "audio" / f"{item.tag.lstrip('-')}_{label}_a{attempt_no}.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(clip.getvalue())

    source = st.session_state["source"]
    source.pending_audio_path = wav
    verdict = step_item(item, st.session_state["adj"], source, log, attempt_no)

    recorded = {a.item: a for a in log.final_attempts}[item.tag]
    re_ask = verdict.outcome == ABSTAIN and attempt_no <= MAX_REASKS
    st.session_state["last_verdict"] = {
        "item": item.tag,
        "attempt_no": attempt_no,
        "raw": recorded.raw_transcript,
        "normalised": recorded.normalised,
        "outcome": verdict.outcome,
        "reason": verdict.reason,
        "re_ask": re_ask,
    }

    if re_ask:
        st.session_state["attempt_no"] = attempt_no + 1   # silent re-ask
        return
    st.session_state["item_index"] += 1
    st.session_state["attempt_no"] = 1
    if st.session_state["item_index"] >= len(st.session_state["items"]):
        finish_run()


# --------------------------------------------------------------------- page
st.set_page_config(page_title="Cabinet 20160387", layout="centered")
init_state()
items = st.session_state["items"]
log = st.session_state["log"]
item_index = st.session_state["item_index"]
attempt_no = st.session_state["attempt_no"]

st.title("Cabinet 20160387")
st.caption("Advisory only. This run passes or fails nothing. "
           "A qualified person reviews every flag and signs off.")
if MODE == "tag":
    st.warning(TAG_MODE_WARNING)

if item_index >= len(items):
    st.success(f"Run complete — {len(items)} items walked in {round(elapsed_s())}s.")
    st.caption(f"Report: {log.dir / 'report.md'}")
else:
    item = items[item_index]
    st.markdown(f"**Item {item_index + 1} of {len(items)}** · band {item.band}")
    st.markdown(
        f"<p style='font-size:2.4rem;line-height:1.25;font-weight:600;"
        f"margin:0.4em 0'>{item.spoken}</p>",
        unsafe_allow_html=True,
    )
    if attempt_no > 1:
        st.info("Please read it again.")

    clip = st.audio_input(
        "Record the read",
        key=f"rec_{item_index}_{attempt_no}",   # a new widget per attempt
    )
    if st.button("Submit read", type="primary", disabled=clip is None):
        try:
            submit(clip, item)
        except RuntimeError as exc:             # no clip: fail loudly
            st.error(str(exc))
        else:
            st.rerun()

last_verdict = st.session_state["last_verdict"]
if last_verdict:
    st.divider()
    st.subheader(f"{last_verdict['item']} · attempt "
                 f"{last_verdict['attempt_no']} · {last_verdict['outcome']}")
    st.text(f"heard:      {last_verdict['raw']}")
    st.text(f"normalised: {last_verdict['normalised']}")
    st.write(last_verdict["reason"])
    if last_verdict["re_ask"]:
        st.warning("Please read it again.")

# --------------------------------------------------------------------- tabs
st.divider()
tab_run, tab_flags, tab_faults, tab_metrics = st.tabs(
    ["Run", "Flags", "Faults", "Metrics"])

with tab_run:
    finals = log.final_attempts
    abstains = sum(1 for a in finals if a.outcome == ABSTAIN)
    rate = abstains / max(len(finals), 1)
    c1, c2, c3 = st.columns(3)
    c1.metric("Items walked", f"{len(finals)} of {len(items)}")
    c2.metric("Duration", f"{round(elapsed_s())}s")
    c3.metric("Abstain", f"{rate:.0%}")
    if rate > ABSTAIN_CEILING:
        st.warning(f"Abstain rate {rate:.1%} is above the "
                   f"{ABSTAIN_CEILING:.0%} working ceiling (CONTEXT §8).")
    repeats = sorted({a.item for a in finals if a.attempt_no >= 3})
    if repeats:
        st.caption("Items that consumed three attempts — illegible label, or "
                   "noise: " + ", ".join(repeats))
    st.caption(f"Run folder: {log.dir}")
    st.dataframe(
        [{"item": a.item, "band": a.band, "outcome": a.outcome,
          "attempts": a.attempt_no, "heard": a.raw_transcript,
          "normalised": a.normalised} for a in finals],
        hide_index=True,
    )

with tab_flags:
    flags = log.flags
    st.write(f"**{len(flags)} flag(s).** You may add an account of each. You "
             "cannot close one; every flag reaches the reviewer.")
    for a in flags:
        with st.expander(f"{a.item} · band {a.band} · {a.outcome}"):
            st.write(a.reason)
            st.text(f"location: {a.spoken_prompt}")
            st.text(f"heard:    {a.raw_transcript}")
            if a.audio_path and Path(a.audio_path).exists():
                st.audio(a.audio_path)
            else:
                st.caption("Audio not retained.")
            kind = st.selectbox("Account", ANNOTATION_KINDS, key=f"kind_{a.item}")
            text = st.text_area("Detail", key=f"text_{a.item}")
            if st.button("Add annotation", key=f"add_{a.item}"):
                log.annotate(Annotation(a.item, kind, text))
                st.rerun()
            for n in log.annotations_for(a.item):
                st.caption(f"{n.kind}: {n.text}")

with tab_faults:
    faults_path = next((p for p in FAULTS_CANDIDATES if p.exists()), None)
    if faults_path is None:
        st.info("No faults.csv yet — Block 9 plants the faults (CONTEXT "
                "§Metrics, metric 2). This tab joins it to the run by tag and "
                "counts caught against missed once it exists.")
        st.caption("Looked in: " + ", ".join(
            str(p.relative_to(ROOT)) for p in FAULTS_CANDIDATES))
    else:
        rows = list(csv.DictReader(
            faults_path.read_text(encoding="utf-8").splitlines()))
        tag_col = next((c for c in ("tag", "item", "designation")
                        if rows and c in rows[0]), None)
        if tag_col is None:
            st.error(f"{faults_path} has no tag, item or designation column "
                     "to join on.")
        else:
            walked = {a.item: a for a in log.final_attempts}
            joined = []
            for r in rows:
                a = walked.get(r[tag_col])
                joined.append({
                    **r,
                    "outcome": a.outcome if a else "not walked",
                    "status": ("caught" if a and a.outcome in FLAGGED
                               else "missed" if a else "not walked"),
                })
            caught = sum(1 for j in joined if j["status"] == "caught")
            st.metric("Caught", f"{caught} of {len(joined)}")
            st.caption(f"Joined {faults_path.relative_to(ROOT)} on '{tag_col}'. "
                       "Caught = the run flagged it; missed = the run walked "
                       "it and did not.")
            st.dataframe(joined, hide_index=True)

with tab_metrics:
    if SCORE_SCRIPT.exists():
        st.info(f"{SCORE_SCRIPT.relative_to(ROOT)} exists but is not wired into "
                "this page yet.")
    else:
        st.info("Placeholder. Detection rate @ 10% abstain and the "
                "risk–coverage curve appear here once "
                f"{SCORE_SCRIPT.relative_to(ROOT)} exists (CONTEXT §Metrics, "
                "metrics 2 and 3).")
    st.caption("Time per cabinet (metric 6) is on the Run tab. Nothing is "
               "reported here that is not on the CONTEXT metrics list.")
