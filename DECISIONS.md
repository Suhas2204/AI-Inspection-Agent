## Block 0 — 25 Aug
Expected: ~60 parts.
Found: 220 in the export.
Changed: replaced CONTEXT.md with v2.0.


## Block 1 — 26 Aug
Expected: 173 core, 37 part numbers.
Got: 173 core, 92 devices, 8 strips — but 31 part numbers. The other 6 belonged to filler parts.
Changed: gate is 31.


## Block 2 — GATE did not passed, 27 Aug 
Expected: derived walking order (frame → row → position) to match the physical cabinet. 
Found: walked the cabinet with the printed walking_order.csv and checked it item by item. 
Order matches: left to right, top to bottom, one walk, no backtracking. 
Gate: NOT PASSED.


## Block 3 — opened 28 Aug, IN PROGRESS
Expected: 21 device types + 8 strips = 29 rows.
Found: 29 rows, confirmed against schematic.cleaned.json. 21 types cover 92 devices;
       one type (C60N,1P,16A,B / A9F03116) accounts for 23 of them.
       Also confirmed: 31 distinct part numbers, not 37.
Changed: make_bands.py added. bands.csv generated, band column empty by design.
Decided: bands.csv is not regenerated — it holds human decisions. Positions may change; bands do not.

Open, must close before the gate:
  - ZEW 35 DBS end brackets (10, across all 8 strips): count toward strip totals? ___ in / ___ out
    Reason: ______
  - Advisor session booked for: ______
  - Banded by: ______   on: ______

Gate: NOT passed. Passes when all 100 items carry a band.


Block 5 — partial, 28 Aug
Ran: faster-whisper large-v3, 19 tag reads, quiet lab, no API (no credit).
Found: tags transcribe cleanly. Pipeline works.
NOT measured: part numbers, rating lines, B16/B10.
Gate: NOT passed.