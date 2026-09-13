
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

## Block 6 — Adjudicator — [date FILL]

Found: all four outcomes reachable.
Open: tests still in __main__, not tests/. Move before Block 9 relies
      on them.
Gate: NOT passed until tests moved and run green.

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

## Block 10 — Redlines — not started; cut first if time runs short.
