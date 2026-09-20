
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
