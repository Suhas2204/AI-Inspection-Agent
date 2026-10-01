# Reproducing Chapter 5

Every number and figure in Chapter 5 comes from one recorded run,
`runs/20260927-130613`, whose data files are committed to this repository. The
commands below regenerate all of them on a clean clone. None of them needs a
microphone, a GPU, a network connection or an API key, and none of them writes
anything into `runs/` or `data/raw/`.

```bash
git clone https://github.com/Suhas2204/AI-Inspection-Agent.git
cd AI-Inspection-Agent
uv sync
```

Setting D7 is the configuration the run was performed at: tag edit-distance
threshold `d ≤ 1` and two silent re-asks, which are the defaults, so no flag
has to be passed to reach it.

---

## Read this before quoting M1 and M2

**Two of the Chapter 5 numbers are not what `score.py` prints.** They are not
wrong, but they are computed under different definitions from the ones fixed in
`src/redlining/score.py`, and a reader who runs the command in this file will
see different figures on screen. This has to be settled before submission —
either the chapter adopts the scorer's definitions, or the chapter states its
own and says why.

| Chapter 5 | `score.py` prints | Why they differ |
|---|---|---|
| M1 = 85.7 % | `"precision": 0.8` | 85.7 % is **per position**: 12 of the 14 flags raised sit on a planted position. 80 % is **per fault row**: 8 rows caught, 2 false flags. A label swap is one row at two positions, and this run has four swaps, so the two counts cannot agree. |
| M2 = 8/8 | `"detection_rate": 0.8` | 8/8 counts the **device** fault rows only, all of which were caught. 8/10 counts **all** rows, including the two strip-count faults (`-X3`, `-X8`), both missed. |

The arithmetic behind both is reproduced by the snippet in
[Appendix: checking M1 and M2](#appendix-checking-m1-and-m2) below, so whichever
definition the chapter keeps can be cited and re-derived.

**M3, M5 and M6 agree with the scripts exactly** and need no reconciliation.

---

## Preconditions

```bash
uv run pytest
```

Expected: `58 passed`. The suite needs no hardware and takes under a second.

---

## M1 — Redline precision (provisional)

```bash
uv run python -m redlining.score runs/20260927-130613
uv run python -m redlining.score runs/20260927-130613 --json
uv run python -m redlining.score runs/20260927-130613 --latex
```

Prints, under the scorer's own per-row definition:

```
Metric 1 - redline precision (provisional, see module docstring)
  false flags          : 2
  precision            : 80%
```

The two false flags are `-X1` and `-X6`, both strip counts misheard by the
recogniser (`M1` for `N1`, `R1` for the bracket). **Precision is provisional**:
the scorer counts a flag at an unplanted position as false without replaying
the audio, so it cannot separate a genuine finding from a misread. CONTEXT §12
assigns that adjudication to `experiments/block09_eval/redlines.py`, which is
not written.

For the per-position figure of 85.7 %, see the appendix.

---

## M2 — Detection rate

Same command as M1; the scorer computes both.

```
Metric 2 - fault detection
  planted (detectable) : 10  (4 label swap(s), each counted once)
  caught               : 8
  missed               : 2
  not walked           : 0
  detection rate       : 80%

By band
  band 1: 3 caught, 0 missed  (100%)
  band 2: 5 caught, 0 missed  (100%)
  band 3: 0 caught, 2 missed  (0%)
```

The two missed rows are the strip-count faults. Both device bands are at 100 %,
which is the 8/8 the chapter quotes.

---

## M3 — Risk–coverage curve

```bash
uv run python experiments/block09_eval/risk_coverage.py runs/20260927-130613 \
    --csv data/processed/risk_coverage.csv
```

Writes `data/processed/risk_coverage.png` and the CSV, and prints the sweep over
`TAG_EDIT_MAX` 0–3 × `MAX_REASKS` 0–2. The D7 row is marked `*`:

```
tag_max reasks  atts   cov     abst    risk    miss  ff   caught  det     prec
   1 *    2     72  100.0%    0.0%    5.7%     2   2     8/10   80%    80%
```

Across all twelve settings coverage spans 95.7–100 % and risk 5.7–6.0 %. The
script prints three self-checks under the table, all of which must pass:

- the replay reproduces 70/70 of the run's recorded outcomes at the defaults;
- the D7 row equals `score.py` on the untouched report;
- `PART_EDIT_MAX` is inert in a tag-mode run, verified at 0/1/2/3.

**The thesis figure** (Arial 10 pt, 16 cm, decimal comma, vector PDF):

```bash
uv run python experiments/block09_eval/risk_coverage.py runs/20260927-130613 --lang de
```

Writes `data/processed/risiko_abdeckung.pdf`. Add `--out data/processed/risiko_abdeckung.png`
for a raster preview; use the PDF in the thesis, since only it carries embedded
Arial.

---

## M4 — Confusability map

A property of the schematic alone. No run needed.

```bash
uv run python experiments/block09_eval/confusability.py \
    --csv data/processed/confusability.csv
```

```
  62 spoken device tags
  246 pairs at edit distance 1
  62 tags (100%) have at least one one-character twin
  12 of those pairs also differ phonetically
  38 sit next to each other on the same rail
  1 are BOTH -- the worst case
      -6F1     vs -6F4      (1/4)
```

The phonetic grouping is engineering judgement, not a measured confusion
matrix; the script says so in its own output.

---

## M5 — ASR character error rate

```bash
uv run python experiments/block05_asr/score.py runs/20260927-130613
uv run python experiments/block05_asr/score.py runs/20260927-130613 --all-characters
```

```
  set                        atts  ref ch   sub  del  ins     CER
  standing attempt            62     266     0    0    0    0.0%
  every attempt               64     275     1    0  135   49.5%
  every well-formed           62     266     0    0    0    0.0%
```

**The chapter's 0 % is the first row**: the attempt that stood at each of the 62
device positions. Quote it with its two caveats, both of which the script
prints:

1. The 49.5 % row is the same data including two first attempts the normaliser
   rejected, both decoder repetition loops (`-7F9` heard as 113 characters,
   `-12F4` as a loop of its own tag). Both were recovered by a re-ask. They are
   a different failure mode from a misheard character, which is why they are
   reported separately rather than averaged in.
2. Both sides are normalised, so this is the error rate of the pipeline the
   adjudicator sees, not of the raw recogniser output.

The 8 terminal strips are excluded: a strip is spoken as counts, so the walker
card gives it no character-level reference.

---

## M6 — Time per inspection point

Recorded by the run, not recomputed:

```bash
uv run python -c "import json; r=json.load(open('runs/20260927-130613/report.json',encoding='utf-8')); print(f\"{r['duration_s']}s / {r['items_verdicted']} items = {r['duration_s']/r['items_verdicted']:.1f} s per point\")"
```

```
1063.5s / 70 items = 15.2 s per point
```

That is 17 min 44 s for the cabinet, wall-clock, including the re-asks and the
local transcription of every clip.

---

## What a clean clone cannot do

The run's **audio is not committed** — 72 WAV recordings, 12 MB, of a person
speaking. Every number above is reproducible without it, but two things are
not:

- the CONTEXT §4 replay gate, listening to the clip behind a flag before
  reporting it;
- resolving whether `-X1` and `-X6` are genuine findings or misreads, which is
  what would turn M1 from provisional into final.

Both need the machine the run was recorded on. The `audio_path` values in
`report.json` are absolute paths that resolve nowhere else.

---

## Appendix: checking M1 and M2

This snippet derives both the chapter's figures and the scorer's from the same
two committed files, so the difference can be inspected rather than taken on
trust. It writes nothing.

```bash
uv run python - <<'PY'
import json, csv
rep = json.load(open("runs/20260927-130613/report.json", encoding="utf-8"))
faults = list(csv.DictReader(open("data/decisions/faults.csv", encoding="utf-8")))

def positions(f):
    a, b = f["item"].strip(), (f.get("item_b") or "").strip()
    return [a, b] if b and b != a else [a]

final = {i["item"]: i for i in rep["items"]}
planted = {p for f in faults for p in positions(f)}
flagged = {k for k, v in final.items() if v["flagged"]}

tp, fp = flagged & planted, flagged - planted
print(f"M1 per position : {len(tp)}/{len(flagged)} = {len(tp)/len(flagged)*100:.1f}%  (chapter)")
print(f"M1 per row      : 8/10 = 80%                  (score.py)")
print(f"   false flags  : {sorted(fp)}")

dev = [f for f in faults if f["kind"] == "device"]
caught = [f for f in dev if any(p in flagged for p in positions(f))]
print(f"M2 device rows  : {len(caught)}/{len(dev)}                      (chapter)")
print(f"M2 all rows     : {len(caught)}/{len(faults)} = {len(caught)/len(faults)*100:.0f}%            (score.py)")
PY
```

```
M1 per position : 12/14 = 85.7%  (chapter)
M1 per row      : 8/10 = 80%                  (score.py)
   false flags  : ['-X1', '-X6']
M2 device rows  : 8/8                      (chapter)
M2 all rows     : 8/10 = 80%            (score.py)
```
