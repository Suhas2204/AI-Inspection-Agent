
# DECISIONS.md

## Block 0 — Spec — 25 Aug

Expected: ~60 parts.
Found: 220 records in the export.
Changed: replaced CONTEXT.md with v2.0 (now superseded by v3.0, 12 Sep).

## Block 1 — Loader — 26 Aug

Expected: 173 core, 37 part numbers.
Found: 173 core, 92 devices, 8 strips — but 31 part numbers.
       The other 6 belonged to filler parts.
Changed: gate count is 31.
Gate: FILL: PASSED if the 26 Aug run against the raw export was clean;
      otherwise run loader.py once and date it here.

### Block 1 — Loader — reproducible from the raw export — 20 Sep

Changed: "wire ridge" added to FILLER_TERMS as the English twin of
         "aderleiste". The German term was always in the list; this export
         names the type in English, so 20 bus bridges were being kept as
         devices and the cleaned file could not be reproduced from the raw.
Changed: merge_wrapper_locations extended to carry location AND position
         together. The export splits -1Q2 and -1Q3 into a '- Kombination'
         wrapper holding the coordinates and a real record holding the part
         number; keeping one meant losing the other. Location alone left
         them in the right frame with no rail row -- orphans, not rows.
Found:   -1Q2 and -1Q3 now place at right frame row 2 position 1 and row 3
         position 1. 14 rows shifted (the two, plus 12 pushed one along in
         right frame rows 2 and 3). No rows added or removed; still 70.
         No "no location in file" rows remain.
Gate: PASSED — 173 core, 92 devices, 31 part numbers, 100 checklist
      records. Reproducible from the raw export for the first time; the
      26 Aug FILL above is answered by this run, not by editing it.
      data/processed/dropped.csv written: 47 rows, every drop with a
      reason, including the 2 wrappers marked as merged.

## Block 2 — Position — 27 Aug

Gate: PASSED.
Found: walked the cabinet with printed walking_order.csv, item by item.
       Order matches: left to right, top to bottom, one walk, no backtracking.
Note: earlier entry wrongly said NOT PASSED; corrected 13 Sep.

## Block 3 — Bands — closed 30 Aug

Found: all 29 rows banded (bands.csv, banded_by Suhas, 30/08/2026).
       21 device types cover 62 devices; 8 strips cover 81 terminals.
Decided: bands.csv is not regenerated — it holds human decisions.
ZEW 35 DBS end brackets (10): IN strip counts. They appear as a BRACKET
       function in the expected counts (attempts.jsonl) and in strip
       composition notes (bands.csv).
       Reason: FILL: one line — why brackets are worth counting aloud.
       (§10 still lists this OPEN — this entry closes it.)
Advisor session: FILL: date it was held, or write "not yet held —
       CLAUDE.md §11 'advisor confirmed' is unsupported until then."
Gate: PASSED — all 70 checklist items carry a band via type inheritance.
Note: earlier entry said "100 items" — dead count from v2.0; v3.0 is 70.

## Block 4 — Normaliser — [date FILL]

Found: rules survive real tag reads.
Changed: punctuation bug found and fixed during live runs.
Gate: PASSED.

## Block 5 — ASR check — partial, 28 Aug, corrected 13 Sep

Ran: faster-whisper large-v3, quiet lab. 19 segments ≈ 26 reads,
     OLD per-terminal convention (predates the strip-count decision).
Found: local 26/26 correct. Expected filled by author listening to audio.
       All spoken tags verified legal against walking_order.csv.
Caveats: single speaker = author; N small; old convention.
OPEN: API comparison pass (no credit) — run or skip, decide by: FILL.
NOT measured: count-style strip speech — the type that abstained live —
     part numbers, rating lines, B16/B10.
Gate: NOT passed until count-style strips are recorded and scored.

## Block 6 — Adjudicator — 13 Sep

Found: all four outcomes reachable.
Changed: tests moved, 11 passing, gate PASSED.
Gate: PASSED.

## Block 7 — Session — [date FILL]

Found: live runs completed at the cabinet. Tag items worked.
       Strips -X3, -X6, -X7 abstained on every attempt (attempts.jsonl:
       raw transcript empty or "You"). Cause unknown: audio path,
       phrasing, or model. Diagnose before Block 9.
Gate: PASSED for tags; strip path unresolved.

## Block 8 — Flags/report — [date FILL]

Found: report generated (report.md / report.json). Flags append-only,
       audio retained per attempt. No delete path in report.py.
Gate: PASSED.

## Block 9 — Evaluation — NOT STARTED. This is the thesis chapter.

Block 9 fault set drawn, seed 20260920; regenerated for corrected wording, selection verified identical.

Drawn 20 Sep from data/decisions/fault_candidates.csv (18 candidates) into
data/decisions/faults.csv: 10 faults, 4 of them label swaps across two
positions, 14 distinct positions, bands 3/5/2.
Regenerated later the same day after what_i_do was rewritten into spoken
instructions. Not a reselection: id, item, item_b, detectable and row
order were all unchanged, so seed 20260920 returned the identical ten;
only the carried instruction text differs. The draw was never re-rolled.
The seed reproduces this set only against that 18-row candidates file --
adding or removing a candidate reselects everything, editing a value in
place does not. N_KNOWN_MISS = 0: the two known-miss candidates (C15, C16)
were deleted, C15 because it contradicted the C04 label swap at -8F7.
Drawn is not planted. The block starts when the faults are in the cabinet.

## Block 10 — Redlines — not started; cut first if time runs short.

## 3D boxes — anchor convention — 4 Oct

Question: model3d.build_boxes emits a box per cleaned part, but the export
         never says whether position is a part's corner or its centre. A
         viewer assuming the wrong one is offset by half a part everywhere.
Found:   Corner. position is the low edge on x, y and z, so a box runs
         [x, x+w], [y, y+h], [z, z+d]; y grows upward, so the y anchor is the
         part's bottom edge. Three measurements off the cleaned export:
         - 143/143 parts mounted on an ED2 rail fall inside that rail's
           495 mm x-span. As centres, 103/143, with -14K1 landing 154.5 mm
           past the end of its own rail.
         - 0 of the 173 boxes interpenetrate. As centres, 43 pairs do, 9 of
           them between non-structural parts.
         - 18 of the 34 unequal-width neighbours touch to within 0.05 mm as
           corners; 0 do as centres.
         y separately: overlap cannot decide it, because parts on one rail
         share an identical y. Settled on the envelope instead -- the four
         900 mm ED12 ducts at y=-1900 reach -1000 as a bottom edge, against
         -2800 as a top edge, 900 mm below every other part in the file.
         Bottom edge gives a 1642 mm cabinet; top edge 2512 mm.
Changed: model3d.py's UNVERIFIED anchor note replaced by this finding. No
         number changed: the pass-through anchor was already the low edge, so
         the boxes built before this check were already right.
Gate:    NOT a spec. Measured from one export, not from the CAD model. x and
         z rest on the containment and overlap counts and are firm. y rests
         on those ducts being floor-mounted -- confirm before trusting a
         vertical clearance.

## 3D viewer — outcome colours — 4 Oct

Question: the finished-run overview colours every part by what the run
         decided about it. Six categories have to stay apart for a reader
         with colour vision deficiency, not just on the author's screen.
Rejected: the obvious Okabe-Ito reading (blue #0072B2, vermillion #D55E00,
         orange #E69F00, reddish purple #CC79A7, grey #999999). Simulated
         under deuteranopia, purple and grey fall to dE 7.1 -- the same
         colour. "Colour-blind safe palette" is a property of a palette as
         a whole, not of the colours taken one at a time, and this is what
         picking named safe colours and stopping there buys.
Decided: chosen by search, maximising the worst pairwise CIELAB separation
         across normal, protanopia, deuteranopia and tritanopia vision
         (Machado 2009 simulation matrices):
           match             #1F6FB2  blue
           mismatch          #E34A33  orange-red
           abstain           #FFB400  amber
           not_in_schematic  #762A83  purple
           never visited     #A6A6A6  grey
           structural        #E3E3E3  faded
         Worst case dE 16.7, its tightest pair blue against purple, against
         7.1 for the rejected set.
Changed: the left side panel moved from green #59a14f to brown #9c755f, so
         green means the current walking step and nothing else. A green
         side panel beside a green "go here" box was the one confusion this
         palette had to avoid.
Gate:    NOT a contrast audit. The separation is between the fills; it says
         nothing about text on them, and it was measured against white. The
         legend carries the outcome name beside every swatch, so colour is
         never the only channel -- which is the part that actually makes it
         readable, and the part no dE number proves.
