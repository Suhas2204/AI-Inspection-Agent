# The data directory

Three kinds of file, kept apart on purpose:

| Directory | What it holds | Regenerated? |
|---|---|---|
| `raw/` | Inputs exactly as received. Never edited, never regenerated. | No — if these change, nothing downstream is comparable |
| `processed/` | Everything the pipeline and the experiments produce | Yes, by the commands in [REPRODUCE.md](../REPRODUCE.md) |
| `decisions/` | Human judgements that no script can derive | No — authored by hand, with the author and date in the file |

The split is the point. A number in `processed/` can always be traced to a
file in `raw/` through a command; a number in `decisions/` cannot, and has to
be argued for in the thesis instead.

---

## ⚠ Personal data (GDPR)

**`raw/Schaltschrankbau.m4a` is a voice recording and is committed to this
repository.** It is a recording of the author reading component labels aloud at
the cabinet — the source material for the Block 5 transcription comparison. A
recording of an identifiable person speaking is personal data under Art. 4(1)
GDPR, and publishing this repository publishes it.

Before the repository is handed over or made public, decide deliberately
whether that file should be in it. Removing it from the current commit is not
enough: it has been tracked since the first commits, so it lives in the git
history and would need the history rewritten to be removed properly. This is a
note for the author and supervisor, not legal advice.

**Run audio is deliberately not committed.** Each inspection run writes one WAV
per attempt into `runs/<timestamp>/audio/`; for the evaluated run that is 72
files and 12 MB of speech. `.gitignore` keeps all of it out, and only the three
data files of `runs/20260927-130613` are tracked. The cost of that choice is
written down in REPRODUCE.md: the CONTEXT §4 replay gate needs the machine the
run was recorded on.

**One further trace.** `runs/20260927-130613/report.json` stores `audio_path`
as an absolute path, so it contains the recording machine's Windows user name.
It identifies nobody beyond the author, but it is there.

---

## `raw/` — inputs as received

| File | Origin | Notes |
|---|---|---|
| `schematic.json` | EPLAN export of project 20160387, 265 KB | The ground truth for every comparison. `ASSUMPTION`, stated in CONTEXT §12: the schematic is correct where it and the cabinet disagree — which is exactly what a redline denies |
| `Schaltschrankbau.m4a` | Voice recording made at the cabinet, 2.4 MB | **Personal data, see above.** Input to `experiments/block05_asr/transcribe.py` |

---

## `processed/` — generated, reproducible

| File | Written by | Contents |
|---|---|---|
| `schematic.cleaned.json` | `python -m redlining.loader` | The cleaned export. Gate: 173 core components, 92 devices, 31 part numbers, 100 checklist records |
| `dropped.csv` | `python -m redlining.loader` | 47 rows — every component the loader dropped, each with a reason, and the two merged wrappers marked as merged rather than vanishing |
| `walking_order.csv` | `python -m redlining.position` | 70 rows — the order the cabinet is walked in, band first, then physical position |
| `transcripts.json`, `transcripts.csv` | `experiments/block05_asr/transcribe.py` | Raw output of both engines on the `raw/` recording, verbatim and uncorrected. The `expected` column of the CSV is filled by hand and is only partly complete; metric 5 is computed from the run instead, not from this file |
| `confusability.csv` | `experiments/block09_eval/confusability.py` | 246 tag pairs at edit distance 1 (metric 4) |
| `risk_coverage.csv` | `experiments/block09_eval/risk_coverage.py` | 12 rows — the metric 3 sweep, one row per setting |
| `risk_coverage.png` | `experiments/block09_eval/risk_coverage.py` | The working figure, with its own title and caveat |
| `risiko_abdeckung.pdf` | `… --lang de` | **The thesis plate.** Vector, Arial embedded, 16 × 9.5 cm, decimal comma |
| `risiko_abdeckung.png` | `… --lang de --out …png` | Raster preview of the same plate. Do not use it in the thesis — only the PDF carries embedded Arial |

---

## `decisions/` — human judgements

These are inputs, not outputs. Regenerating them is not possible, and editing
one invalidates every result computed from it.

| File | Rows | What it decides |
|---|---|---|
| `bands.csv` | 28 | Priority band per device type and per strip, 1 (protective) to 4 (cosmetic). Ranked over types, not per item, and inherited by component. Each row carries who banded it and when. *Observed: nothing landed in band 4* |
| `fault_candidates.csv` | 18 | The pool the planted fault set is drawn from, with a confusability note per candidate |
| `faults.csv` | 10 | **The planted fault set**, drawn from the candidates with the seed recorded in `docs/DECISIONS.md`. 8 device rows and 2 strip rows; 4 of them are label swaps, one fault across two positions. The denominator of metric 2, and the file `walker_card.txt` is overwritten from |

`faults.csv` is reproducible from its seed — `python -m redlining.select_faults`
re-draws the same ten rows byte-identical — but it is kept here rather than in
`processed/` because the *candidates* and the seed are human choices, and the
draw is only as defensible as they are.

---

## What is not in this directory

`runs/` sits at the repository root, not under `data/`, because a run is
evidence of a session rather than an input to one. It is ignored except for the
three data files of the evaluated run. See [REPRODUCE.md](../REPRODUCE.md).
