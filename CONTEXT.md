# Project Context — AI Inspection Agent for Control Cabinets

**Version:** 2.0 · **Date:** 2026-08-24 · **Type:** Master's thesis, ~1 month
**Supersedes:** v1.0. Changes in v2.0 are corrections against the actual export and cabinet photos, not changes of mind. See §12 for the change log.
**Purpose of this file:** paste at the start of an LLM session so it understands the project without re-explanation. Sections are labelled by epistemic status. Treat `FACT` as given, `DECISION` as changeable with reason, `ASSUMPTION` as unverified, `OPEN` as genuinely undecided.

---

## 1. What we are building

A voice-guided inspection assistant for **one** electrical control cabinet.

The cabinet's schematic export (`schematic.json`, converted from EPLAN) is parsed into an ordered checklist. The system prompts the trainee by **mounting location only** — "Rail AB, position 4" — and does **not** name the expected device. The trainee reads the label aloud. The system compares what was said against the schematic, and flags mismatches with a stated reason. If audio is unclear, it asks for a repeat rather than guessing.

Confirmed mismatches become **redlines** sent upstream to correct the schematic.

## 2. Why

`FACT` Inspection happens after cabinet build, before shipping to the customer.
`FACT` It is done manually today by a trainee.
`ASSUMPTION` Manual inspection is slow and lets some defects escape to the customer.
`ASSUMPTION` Directing attention to high-impact components first reduces both time and misses.

Neither assumption is measured. No baseline will be produced (§8), so both remain assumptions in the thesis.

## 3. Who it is for

A **trainee** performing final inspection, holding a phone (audio; camera unused in v1), standing at the cabinet. No printed schematic, no paper checklist in hand — the system is their only guide.

`ASSUMPTION` The trainee speaks English. The cabinet is German-market, so assume **accented, non-native English** rather than native.

## 4. Regulatory stance — do not weaken this

The system is **advisory only**. It flags and explains; it never passes or fails a cabinet. A qualified human reviews every flag and signs off. This is deliberate: it keeps the system outside EU AI Act high-risk classification. Any proposal that moves the system toward autonomous sign-off is out of scope.

**Corollary (v2.0):** flags are **append-only**. The trainee may annotate a flag with evidence; the trainee may **not** close, dismiss, or delete one. Every flag reaches the reviewer. A trainee closing flags is a trainee performing sign-off.

## 5. Scope

**In:** one physical cabinet in the lab · one JSON schematic export (already in hand) · **220 components in the export, 100 checklist items** (§6) · component conformance only · English speech · voice input only.

**Out (v1):** wiring/netlist correctness · torque, crimp, insulation, routing · camera and vision (Phase 2, gated on evidence) · multiple cabinets or variants · generalization · any automated pass/fail.

### Do not suggest these — already considered and deferred
- **Camera / Grounding DINO / SAM 2 / detector fine-tuning.** Phase 2 only, and only if voice-only is shown to miss real defects. Annotation cost is not justified before that evidence exists.
- **Data Matrix codes.** Every Schneider device carries one. It is the fastest and most reliable read available and it is **still out of scope in v1**, because it requires the camera. Noted for Phase 2.
- **Generalizing to many cabinets.** One cabinet first. Scaling is a separate question.
- **Regenerating the export.** A usable export exists. Use it as-is.

## 6. The cabinet, as measured

`FACT` `schematic.json`, project 20160387, **220 component records**.

```
220  all records
 -42  mechanical filler   (blanking covers, wire ridges, spacers, insulators)
  -5  "- Kombination"     (assembly wrappers duplicating a real child record)
─────
173  core
      ├─  92  devices with a unique tag   → 92 checklist items
      └─  81  terminals across 8 strips   →  8 checklist items
─────
100  checklist items
```

`FACT` **The device tag is not a unique key.** 133 distinct designations across 220 records. `-X5` names 20 components, `-X7` 14, `-X2` and `-X3` 13 each. The real key is `(designation, location)` or `component_id`.

`FACT` **Only 37 distinct part numbers exist** in the whole cabinet, and `type` maps one-to-one onto `order_reference` across all 39 types. Reading the type is equivalent to reading the part number.

`FACT` **There is no rail/position field.** Location is an IEC 81346-style coded string (`+NSHV+AA00001VLXX.DA00015VXXX.AB00009VXXX`). Speakable positions must be derived from `relative_position` (mm) plus `layer`. Terminal pitch is a constant 5.2 mm and y-banding is clean, so ordering is reliable.

`FACT` **Legibility, resolved from photographs** (was `OPEN` in v1.0):
- **Devices:** part number is printed on the front label (`A9F03116`, `A9F03310`, `A9P44610`), alongside a family/rating line (`Acti9 iC60N B16`). Tags are on the label strip above (`-7F8`, `-5F1`). Both readable.
- **Terminals:** the type string is **not** on the part, and `order_reference` is a Weidmüller warehouse number that appears only on packaging. Readable instead: strip tag, colour, and position markers — and **the markers are absent from the export**, so they cannot be compared against anything.

## 7. Decisions made, with reasons

**`DECISION` Devices: the trainee speaks two things — part number and family/rating line.**
Not the tag. The tag is printed on a strip the trainee can see, and speaking it adds ASR load without adding a check. Part number (`A9F03116`) and rating line (`iC60N B16`) sit on the same label and are cross-checked against **each other** as well as against the schematic; disagreement means a misread or a swapped part with a stale label. The discrimination that matters is one character — `A9F03116` vs `A9F03310`, B16 vs B10, adjacent on the same rail.

**`DECISION` Terminals: strip-level colour and function counts.**
Per §6, terminals carry no readable identity. Each of the 8 strips is one checklist item, checked as counts by function (N / L / PE), derivable from the type string (`N-L-PE`, `L-L`, `L-L-PE`, `WNT`=N, `WPE`=PE).
*Known weakness, state it in the thesis:* a terminal swapped for another of the same colour is invisible to this check.

**`DECISION` Prompt by location only; never name the expected device.**
Naming the device primes the answer and manufactures the very confirmation bias §9 warns about. Sequence is **prompt → commit → adjudicate → reveal**. Re-asks are silent: "please read it again," with no echo of what was heard.

**`DECISION` Closed vocabulary applies to device tags only.**
*This reverses v1.0.* Constraining part-number recognition makes a wrong part unrepresentable — the recogniser snaps it to the nearest legal token and the defect is laundered before the comparison layer ever sees it. Part numbers are **free-transcribed**, then adjudicated against the legal set of 37 as a separate step that can return *not in schematic*. Constrained decoding is kept for tags, where the schematic genuinely enumerates every legal value.

**`DECISION` Four adjudication outcomes.**
`match` · `mismatch` · `not-in-schematic` · `abstain`. Two clean reads that disagree are a **mismatch**, not a tiebreak — the human reviewer settles it. Abstain triggers a silent re-ask, **maximum two**, then the item is flagged. Attempt count is logged; three attempts on one item is itself a signal (illegible label, or noise).

**`DECISION` The run never stops.**
Flags queue and are triaged at the end. Raw audio is retained per flag so review does not require a second trip to the cabinet.

**`DECISION` Priority is human-authored, and ranked by type.**
Four bands: (1) protective and safety-relevant, (2) main power path, (3) control and signal, (4) cosmetic/labelling. Ranked over **21 device types + 8 strips = 29 decisions**, inherited by component — not 100 individual judgements. Within a band, items are ordered by physical position so the trainee walks the cabinet once. Auto-deriving priority is a research project of its own and is not affordable in one month.

**`DECISION` Method is not fixed to any particular model or vendor.**
Requirement is: reason over the schematic plus spoken input, judge match or mismatch, explain why, and abstain when unsure. Simplest thing that achieves this wins. ASR: Whisper API for accuracy, benchmarked against local `faster-whisper` — lab-only recording keeps §10's works-council question closed.

## 8. Evaluation — what this thesis can and cannot claim

**No manual baseline will be run.** `DECISION`, taken deliberately: at one cabinet and 3–5 runs, a non-inferiority claim against manual inspection cannot be powered, so the stopwatch comparison would be a number with an interval wide enough to contain anything.

**Consequence, and it must be stated plainly in the thesis:** the second job of the baseline — establishing *what share of real escaped defects are component-conformance defects at all* — is therefore **not answered**. §9 names this as the biggest risk to the premise and it stays open.

**Faults are planted, run, and scored by the author alone.** No blinding is available. Every accuracy number in the thesis is bounded by this. The confirmation-bias question cannot be measured by someone measuring themselves.

**Reported metrics:** per-item detection rate on the planted fault set · false-flag rate (system says wrong, cabinet was right — this destroys trust fastest) · abstain/defer rate (working ceiling ~10% of items; above that, trainees rubber-stamp to move on) · time per cabinet, as a constraint not a goal · cost and tokens per run.

**Report contents:** all 100 items, not only flags. Matches are what make a false-flag rate computable, and the full run log is the evaluation dataset.

## 9. Untested assumptions — flag these, don't build on them

- That the defects reaching customers are component-conformance defects at all — rather than wiring, torque, or assembly faults this method cannot see. **Unquantified, the biggest risk to the whole premise, and now unaddressed by design (§8).**
- That a trainee reading a label aloud reports what is actually there, rather than what they expect. Location-only prompting removes the system's own contribution to this, but does not remove the bias. **Voice-only cannot detect it; solo evaluation cannot measure it.**
- That ASR handles alphanumeric strings reliably in shop-floor noise. **Never measured. This is the first thing to test, because it can invalidate the method.** Expect Whisper to emit prose (`"a nine f zero three one one six"`); that is a normalisation problem, not a failure.
- That voice-only inspection is faster or more accurate than manual. **No baseline exists and none will be produced.**
- That strip-level colour counts catch a meaningful share of terminal defects. **Untested, and weak by construction.**

## 10. Open questions

- `OPEN` Which IEC standards actually govern this inspection, and what do they require? IEC 61439 (low-voltage assemblies, routine verification), IEC 81346 (reference designations) and IEC 60204-1 (electrical equipment of machines) are the likely candidates — **clause-level content is unverified and must be read in the actual standards, not recalled from a model.**
- `OPEN` Whether redlines write back to ECAD/PLM programmatically, or v1 simply emits a structured report a human carries upstream. The latter is the realistic thesis deliverable.
- `OPEN` What "human audit, 95%" means concretely — 95% of what, measured how. **Source of this figure is unrecovered; it appears in no other section.**
- `OPEN` Whether the 10 end brackets (`ZEW 35 DBS`) count toward strip totals or are filtered as mechanical.
- `OPEN` Voice recording on the shop floor may need works-council / data-protection clearance. Lab-only recording defers this; a shop-floor trial does not.

## 11. Build order

Blocks 0–10, gated. See `BLOCK_MAP.svg` for the full map and `DECISIONS.md` for outcomes per block.
**Block 5 (ASR reality check) is the gate that can invalidate everything downstream. Do it first.**

## 12. Change log — v1.0 → v2.0

| § | v1.0 said | v2.0 says | Why |
|---|---|---|---|
| 1, 5 | XML schematic | JSON export | The artifact in hand is JSON; a conversion already happened |
| 5 | ~50–60 components | 220 records → 100 items | Counted from the export |
| 6 | tag is the unique key | tag is not unique | 133 tags across 220 records |
| 7 | speak tag + part number | speak part number + rating line | Tag adds ASR load without adding a check |
| 7 | closed vocabulary everywhere | tags only | Constrained decoding launders the wrong-part defect |
| 7 | location supplied as guidance | location is the *only* prompt | Naming the device primes the answer |
| 8 | run 3–5 manual baselines | no baseline | Cannot be powered at n=1 cabinet |
| 10 | legibility open | resolved from photos | Devices yes, terminals no |
| 4 | — | flags append-only | Trainee triage must not become sign-off |

## 13. How to use this file

Challenge §9 rather than inheriting it. If a suggestion conflicts with §4 or §5, say so instead of working around it. If you believe a §7 decision is wrong, argue against the stated reason.