# Project Context — AI Inspection Agent for Control Cabinets

**Version:** 3.0 · **Date:** 2026-08-31 · **Type:** Master's thesis, ~1 month
**Supersedes:** v2.0. Changes in v3.0 are corrections against the code that was
actually written and the first live runs at the cabinet. Several v2.0 `FACT`
lines were wrong. See §12.
**Purpose of this file:** paste at the start of an LLM session so it understands
the project without re-explanation. Sections are labelled by epistemic status.
Treat `FACT` as given, `DECISION` as changeable with reason, `ASSUMPTION` as
unverified, `OPEN` as genuinely undecided.

---

## 1. What we are building

A voice-guided inspection assistant for **one** electrical control cabinet.

The schematic export (`schematic.json`, converted from EPLAN) is parsed into an
ordered checklist. The system prompts the trainee by **mounting location only**
— "left frame, row 3, position 1" — and does **not** name the expected device.
The trainee reads the label aloud. The system compares what was said against the
schematic and flags disagreements with a stated reason. If audio is unclear it
asks for a repeat rather than guessing.

Confirmed mismatches become **redlines** sent upstream to correct the schematic.

## 2. Why

`FACT` Inspection happens after cabinet build, before shipping to the customer.
`FACT` It is done manually today by a trainee.
`ASSUMPTION` Manual inspection is slow and lets some defects escape.
`ASSUMPTION` Directing attention to high-impact components first reduces both
time and misses.

Neither assumption is measured. No baseline will be produced (§8), so both
remain assumptions in the thesis.

## 3. Who it is for

A **trainee** performing final inspection, holding a phone or laptop (audio;
camera unused in v1), standing at the cabinet. No printed schematic, no paper
checklist in hand — the system is their only guide.

`ASSUMPTION` The trainee speaks English. The cabinet is German-market, so assume
**accented, non-native English** rather than native.

## 4. Regulatory stance — do not weaken this

The system is **advisory only**. It flags and explains; it never passes or fails
a cabinet. A qualified human reviews every flag and signs off. This keeps the
system outside EU AI Act high-risk classification. Any proposal that moves it
toward autonomous sign-off is out of scope.

**Corollary:** flags are **append-only**. The trainee may annotate a flag with
evidence; the trainee may **not** close, dismiss, or delete one. Every flag
reaches the reviewer. A trainee closing flags is a trainee performing sign-off.
This is structural in `report.py`: there is no delete path in the code.

## 5. Scope

**In:** one physical cabinet in the lab · one JSON export (in hand) · **220
records in the export, 70 checklist items** (§6) · component conformance only ·
English speech · voice input only.

**Out (v1):** wiring/netlist correctness · torque, crimp, insulation, routing ·
camera and vision (Phase 2, gated on evidence) · multiple cabinets or variants ·
generalization · any automated pass/fail · **any web or phone UI** (see below).

### Do not suggest these — already considered and deferred
- **Camera / Grounding DINO / SAM 2 / detector fine-tuning.** Phase 2 only, and
  only if voice-only is shown to miss real defects.
- **Data Matrix codes.** Every Schneider device carries one. Fastest and most
  reliable read available, and **still out of scope in v1**, because it needs
  the camera. Noted for Phase 2.
- **Generalizing to many cabinets.** One cabinet first.
- **Regenerating the export.** A usable export exists. Use it as-is.
- **A web or phone UI.** *(new in v3.0.)* Technically about two days of work —
  FastAPI, one page, browser microphone, a tunnel for the link. It adds no
  evidence to the thesis. Build it only if Block 9 finishes early.
- **An LLM in the adjudication path.** *(new in v3.0.)* The judgement is string
  equality against a closed set of 28–31 part numbers. A language model cannot
  do that better than `==`, and would do it non-reproducibly. Whisper is the AI
  in this system; the judge is deliberately deterministic so that a defect
  cannot be laundered by a plausible-sounding correction. This is a thesis
  position, not a limitation to apologise for.

## 6. The cabinet, as measured

`FACT` `schematic.json`, project 20160387, **220 component records**.

```
220  all records
 -42  mechanical filler   (blanking covers, wire ridges, spacers, insulators)
  -5  "- Kombination"     (assembly wrappers duplicating a real child record)
─────
173  core
      ├─  92  uniquely-tagged records
      │       ├─ 62  electrical devices        → 62 checklist items
      │       └─ 30  structural (rails, ducts) → excluded, see below
      └─  81  terminals across 8 strips        →  8 checklist items
─────
 70  checklist items
```

`FACT` **The device tag is not a unique key across the raw export.** In the
cleaned set there are **100 distinct designations across 173 records** — 92
unique device tags plus 8 strip tags shared by 81 terminals. `-X5` names 20
records, `-X7` 12, `-X3` and `-X2` 11 each. The real key is
`(designation, location)` or `component_id`.
*(v2.0 said 133 across 220. That counted the filler and wrappers.)*

`FACT` **31 distinct part numbers exist** in the cleaned set, and `type` maps
one-to-one onto `order_reference` across all 21 types. Excluding structural
parts: **28 part numbers across 18 device types**.
*(v2.0 said 37 across 39 types. The 37 was computed before filler removal.)*

`FACT` **The DIN rails are records in the export.** *(This reverses a v2.0
`FACT` that said no rail field exists.)* Type `ED2`, 495 mm wide, tagged
`-D1`–`-D5` in the left frame and `-D11`–`-D15` in the right, at identical
heights in both frames: −450, −650, −775, −900, −1025 mm. Every device sits at
exactly its rail's `y`. A row is therefore **read from the rail records**, not
clustered by a tolerance. `ED138` and `ED12` are wire ducts, sitting *between*
rails at −287.5, −512.5, −587.5, −1112.5 and −1900.

Consequences:
- Five rows per frame, top to bottom. Row 1 is the terminal-strip rail.
- The v2.0 approach (`ROW_TOLERANCE_MM = 50`) produced ten rows per frame and
  was wrong. It was caught by the first live run, not by inspection.
- The two "side panel" location prefixes contain **only ducts**, so they
  disappear from the checklist entirely. `OPEN` question closed.

`FACT` **Terminal pitch.** v2.0 asserted a constant 5.2 mm. Unverified against
the export and not relied on by any code. Claim withdrawn.

`FACT` **Legibility, resolved from photographs and confirmed at the cabinet:**
- **Devices:** most carry a part number on the front label (`A9F03116`,
  `A9F03310`, `A9P44610`) alongside a family/rating line (`Acti9 iC60N B16`).
  Tags are on a separate label strip.
- **Four devices carry no part number at all.** `-5F1`, `-5F2`, `-6F1`
  (`A9D56616`) and `-5F3` (`A9D56613`) print only `iDPN N Vigi B 16A` / `B 13A`.
  These are RCBOs, and therefore band 1. Any check that depends on a printed
  part number is blind to them. *(New in v3.0.)*
- **Terminals:** no type string on the part; `order_reference` is a Weidmüller
  warehouse number that appears only on packaging. Readable are colour and
  position markers — and **the markers are absent from the export**. The counts
  also disagree: `-X5` has 20 records but 17 printed markers, because the
  records include end brackets and cross-connectors that carry no number.

## 7. Decisions made, with reasons

**`DECISION` Devices: the trainee speaks the tag.** *(Reverses v2.0.)*
v2.0 had the trainee speak part number plus rating line, on the grounds that the
tag cannot detect a wrong part fitted under a correct label. That reasoning still
holds and is **not** withdrawn — it is recorded in §9 as a stated limitation.
The decision was taken for tractability in a one-month thesis: one short spoken
token per item instead of two long alphanumeric strings, with a correspondingly
lower ASR burden. The consequence must be stated plainly in the thesis: **this
system verifies that the right label is in the right place. It does not verify
that the right part is under the label.**

**`DECISION` Terminals: strip-level function counts.**
Terminals carry no readable identity. Each of the 8 strips is one checklist item,
checked as counts by function (N / L / PE), derived from the type string
(`NDT`→N, `N-L-PE`, `L-L`, `WNT`→N, `WPE`→PE, `WDU`→L).
*Known weaknesses, both stated in the thesis:* a terminal swapped for another of
the same function is invisible; and nobody has yet asked a working inspector
whether counting by colour is how this is done in practice.

**`DECISION` Prompt by location only; never name the expected device.**
Sequence is **prompt → commit → adjudicate → reveal**. Re-asks are silent:
"please read it again", with no echo of what was heard.

**`DECISION` No fuzzy matching into the legal set.**
A read that matches no schematic entry returns *not-in-schematic*, never a
nearest neighbour. Edit distance is used only to *explain* an abstain, never to
*repair* a read. Snapping a bad read to a legal value launders the defect before
the comparison layer sees it.

**`DECISION` Four adjudication outcomes.**
`match` · `mismatch` · `not-in-schematic` · `abstain`. Abstain triggers a silent
re-ask, **maximum two**, then the item is flagged. Three attempts on one item is
itself a signal (illegible label, or noise).

**`DECISION` The run never stops.**
Flags queue and are triaged at the end. Raw audio is retained for **every
attempt**, not only flagged ones — you cannot know while recording which will be
flagged.

**`DECISION` Priority is human-authored, and ranked by type.**
Four bands: (1) protective and safety-relevant, (2) main power path, (3) control
and signal, (4) cosmetic/labelling. Ranked over device types plus strips and
inherited by component, not judged per item. Within a band, items are ordered by
physical position so the cabinet is walked once.
*Observed:* nothing landed in band 4. The scheme is effectively three bands for
this cabinet.

**`DECISION` ASR is local.** `faster-whisper`, CPU. Lab-only recording keeps
§10's works-council question closed. The Whisper API remains the accuracy
comparison, not the deployment path.

**`DECISION` Environment is pinned, and the pins are load-bearing.**
`ctranslate2` 4.8.1 crashes silently on Windows — a native abort with no Python
traceback. Pinned to 3.24.0, which requires `setuptools<81`. `faster-whisper`
≥1.2.1 demands `ctranslate2` ≥4.0, so the two cannot both be resolved by `uv
sync`; the working venv is maintained with `uv pip install` and run with
`--no-sync`. Ugly, and recorded here so the next machine does not rediscover it.

## 8. Evaluation — what this thesis can and cannot claim

**No manual baseline will be run.** `DECISION`, deliberate: at one cabinet and
3–5 runs a non-inferiority claim cannot be powered.

**Consequence, stated plainly in the thesis:** the baseline's second job —
establishing *what share of real escaped defects are component-conformance
defects at all* — is **not answered**. §9 names this as the biggest risk to the
premise and it stays open.

**Faults are planted, run, and scored by the author alone.** No blinding is
available. Every accuracy number is bounded by this.

**Reported metrics:** per-item detection rate on the planted fault set ·
false-flag rate · abstain rate (working ceiling ~10% of items) · time per
cabinet, as a constraint not a goal.

**Report contents:** all 70 items, not only flags. Matches are what make a
false-flag rate computable, and the full run log is the evaluation dataset.

## 9. Untested assumptions — flag these, don't build on them

- That the defects reaching customers are component-conformance defects at all.
  **Unquantified, the biggest risk to the premise, and unaddressed by design.**
- **That the label above a device tells you what is under it.** *(New in v3.0,
  and now the central limitation.)* §7 chose tag-only reading. A B16 fitted where
  a B10 belongs, under a correct label, is invisible to this system. The cabinet
  contains four such confusable pairs — `A9F03116`/`A9F03110` and
  `A9F03316`/`A9F03310`. **This class of defect cannot appear in the Block 9
  fault list, and the detection rate must be reported as conditional on it.**
- That a trainee reading a label aloud reports what is there rather than what
  they expect. Location-only prompting removes the system's own contribution but
  not the bias. **Solo evaluation cannot measure it.**
- That voice-only inspection is faster or more accurate than manual. **No
  baseline exists and none will be produced.**
- That strip-level function counts catch a meaningful share of terminal defects.
  **Untested, weak by construction, and the calling convention is unvalidated
  against practice.**

## 10. Open questions

- `OPEN` **Do the 30 structural records belong in the checklist?** v3.0 excludes
  them, giving 70 items. Including them gives 100. They are the metalwork the
  components clip onto; blanking covers and spacers were already dropped as
  filler in Block 1 on the same reasoning. **Decide and record it — the item
  count, the bands, and the time budget all move with it.**
- `OPEN` Whether the 10 `ZEW 35 DBS` end brackets count toward strip totals.
  They currently appear as a `BRACKET` function the trainee would have to count
  aloud.
- `OPEN` Which IEC standards govern this inspection. 61439, 81346 and 60204-1
  are candidates. **Clause content is unverified and must be read in the actual
  standards, not recalled from a model.** No IEC-driven claim may be made until
  this is done. The current bands are engineering judgement, not standards-based.
- `OPEN` Whether redlines write back to ECAD/PLM, or v1 emits a report a human
  carries upstream. The latter is the realistic deliverable.
- `OPEN` What "human audit, 95%" meant. Source unrecovered; appears nowhere else.
- `OPEN` Works-council / data-protection clearance if recording moves to the
  shop floor. Lab-only defers this.

## 11. Build order and state

Blocks 0–10, gated. `DECISIONS.md` holds outcomes per block.

| Block | State |
|---|---|
| 0 Spec | done — this file is v3.0 |
| 1 Loader | `loader.py` written; gate needs one clean run against the raw export |
| 2 Position | **passed** — rails read from `ED2` records, walked at the cabinet |
| 3 Bands | rows banded, advisor confirmed |
| 4 Normaliser | rules survive real tag reads; punctuation bug found and fixed |
| 5 ASR check | 100 labels recorded. **Gate not passed: no error rate on paper, per engine.** Run `transcribe.py` over the recordings — it is one pass and it is a thesis table |
| 6 Adjudicator | all four outcomes reachable; tests still in `__main__`, not `tests/` |
| 7 Session | live runs completed at the cabinet |
| 8 Flags/report | append-only, audio retained per attempt |
| 9 Evaluation | **not started. This is the thesis chapter.** |
| 10 Redlines | not started; cut first if time runs short |

## 12. Change log — v2.0 → v3.0

| § | v2.0 said | v3.0 says | Why |
|---|---|---|---|
| 6 | 37 part numbers, 39 types | 31 across 21 types; 28 across 18 excluding structural | 37 was counted before filler removal |
| 6 | 133 designations across 220 | 100 across 173 | 133 counted filler and wrappers |
| 6 | no rail/position field exists | rails are `ED2` records, `-D1`–`-D5` / `-D11`–`-D15` | found while debugging the first live run |
| 6 | positions derived from tolerance banding | rows read from rail records | tolerance gave 10 rows where the cabinet has 5 |
| 6 | terminal pitch is a constant 5.2 mm | withdrawn, unverified | asserted in v2.0 with no source |
| 6 | devices carry a part number | four RCBOs do not | confirmed at the cabinet |
| 5, 6 | 100 checklist items | 70 (62 devices + 8 strips) | 30 records are rails and ducts, not components |
| 7 | speak part number + rating line | speak the tag | tractability; limitation moved to §9 |
| 7 | legal set of 37 | 28–31 depending on §10 | corrected count |
| 5 | — | no UI, no LLM in the judge | both proposed and declined, with reasons |
| 7 | — | environment pins are load-bearing | `ctranslate2` 4.8.1 aborts on Windows |
| 10 | side panels unclear | closed — ducts only | they vanish once structural parts are excluded |
| 9 | — | tag-only reading cannot see a wrong part | direct consequence of the §7 reversal |

## 13. How to use this file

Challenge §9 rather than inheriting it. If a suggestion conflicts with §4 or §5,
say so instead of working around it. If you believe a §7 decision is wrong, argue
against the stated reason. Do not inherit the numbers in §6 — every one of them
came from running code against the export, and three of them were wrong in v2.0.




### Metrics — defined before measurement, in priority order

`DECISION` These six are the whole evaluation. Nothing is reported that is not
on this list, and nothing on this list is skipped because it came out badly.

| # | Metric | Question it answers | Input | Computed in | State |
|---|---|---|---|---|---|
| 1 | **Redline precision** | Of flags raised, how many are genuine schematic errors worth sending upstream? | `runs/*/report.md` + adjudication by the author against the cabinet | `experiments/block09_eval/redlines.py` | not started |
| 2 | **Detection rate @ 10% abstain** | Of planted faults, how many are flagged when the system may skip 10% of items? | `runs/*/attempts.csv` + `faults.csv` | `block09_eval/score.py` | not started |
| 3 | **Risk–coverage curve** | How much does detection improve as the system is allowed to abstain more? | same as 2 | `block09_eval/score.py` | not started |
| 4 | **Confusability map** | Which device tags are close enough that a one-character misread yields a different *legal* tag? | `data/schematic.cleaned.json` only | `block09_eval/confusability.py` | not started |
| 5 | **ASR character accuracy** | Does Whisper hear the tag, and which character does it lose? | `data/transcripts.csv`, `expected` column filled by hand | `experiments/block05_asr/score.py` | blocked: `expected` empty |
| 6 | **Time per cabinet** | Does a run fit inside the working shift? | `RunLog.duration_s` | already recorded | measured, not reported |

**Priority is deliberate.** 1 is the thesis claim: this project is about
redlining, and a flag that never becomes a correction is not a redline. 2 and 3
are the standard selective-prediction pair and give the claim its shape. 4 is
free — it needs no run, and it bounds what voice can ever achieve on *this*
cabinet, which is how the Phase 2 camera decision gets derived from data rather
than asserted. 5 and 6 are plumbing: they explain results, they do not
constitute them.

**What none of these can claim.** All six are computed by the author, on one
cabinet, against faults the author planted, using the schematic as ground truth.
`ASSUMPTION` the schematic is correct where the cabinet and it disagree — which
is precisely what a redline denies. Every redline in metric 1 must therefore be
resolved by eye at the cabinet, and that resolution is unblinded.

`OPEN` Whether any of the four device-tag pairs found by metric 4 are physically
adjacent in the walking order. Adjacent twins are worse than distant ones: a
misheard tag lands on a real neighbour and the mismatch never surfaces.