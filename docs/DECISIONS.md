
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

## Environment — onnxruntime pinned below 1.20 — 5 Oct

Question: faster-whisper ships Silero VAD as an ONNX model, so turning
         vad_filter on makes onnxruntime a hard runtime dependency rather
         than an optional extra. Which version.
Found:   on this Windows 11 machine onnxruntime 1.29.0 fails on import with
         "DLL load failed ... DLL initialization routine failed". 1.19.2
         imports and runs Silero VAD.
Decided: pinned onnxruntime<1.20 in pyproject.toml. 1.19.2 is what the lock
         resolves and what every number below was measured with.
Gate:    NOT a diagnosis. The root cause was not established. A missing or
         outdated Microsoft Visual C++ runtime is suspected and UNCONFIRMED.
         Windows only — Linux was not tested, so the pin may be unnecessary
         there. This is NOT a VAD-behaviour pin: nothing suggests a newer
         onnxruntime would segment or transcribe differently, only that it
         would not load here. Revisit with the cause established, not by
         bumping the number and seeing what happens.

## Block 5 — ASR — Silero VAD on by default — 5 Oct

Question: three strips (-X3, -X6, -X7) abstained on every attempt of run
         20260927-130613 with an empty or "You" transcript, and two devices
         sent the decoder into a loop. VAD was one candidate cause and one
         candidate fix, and it could have been either.
Found:   measured rather than argued, by re-transcribing all 72 clips of
         that run both ways with one loaded model
         (experiments/block05_asr/vad_compare.py):
         - on the probes, which contain no speech at all, vad_filter=False
           invents "You" for both digital silence and -50 dBFS noise;
           vad_filter=True returns nothing. That is the "You" the strips
           abstained on, and VAD removes it.
         - on the two runaway decodes it helps without fixing: -12F4
           attempt 1 went from 22 tokens to 3 and is now correct, -7F9
           attempt 1 from 112 tokens to 28 — still 28 repetitions of "9",
           still not a read.
         - on the 60 clips that decode normally it changes nothing
           measurable: both sides score 0.0% CER.
         - it is not free. It turned -X1's "L3" into "N3", trading one
           misread for another, and wrote -12F3 as the sentence
           "So, minus 12 F3." (see the leading-filler entry below).
Decided: vad_filter=True in LocalTranscriber.transcribe, so the microphone
         and the Streamlit page share it. The decision rests on the probes:
         inventing words out of silence is the failure that cost three
         strips every attempt they had.
Changed: vad_compare.py's --mirror-check now compares against the VAD-ON
         side (MIRROR_VAD), because LocalTranscriber is what it mirrors.
         Left pointing at the off side it would have failed on every clip
         VAD changes and reported it as decode-settings drift — the one
         thing that check exists to tell the truth about.
Gate:    NOT a general result about VAD. One run, one cabinet, one speaker,
         72 clips, faster-whisper small on CPU, Silero at its default
         VadOptions. The thresholds were never swept.

## Block 5 — ASR — the 73-attempt CER is superseded — 5 Oct

Question: the headline CER of run 20260927-130613 was 88.2% without VAD and
         20.1% with it. Both numbers are wrong, in the same two ways.
Found:   -7F9 attempt 1 is written TWICE in attempts.jsonl — a page reload
         re-recording one attempt. score.py keys attempts by
         (item, attempt_no) and keeps the last; vad_compare appended every
         line. So one run was 73 attempts to one script and 72 to the
         other, and the duplicate was a runaway decode counted twice,
         roughly half of every insertion in the headline number.
Changed: vad_compare.load_attempts now dedupes on (item, attempt_no),
         keeping the last record, and reports how many it collapsed. The
         two scripts agree: 72 attempts, 64 of them scorable against the
         card.
Decided: the numbers of record — run 20260927-130613, faster-whisper small,
         scored against walker card v1:

           set                         atts  ref ch  sub  ins     CER
           vad_filter=False              64     275    1  135   49.5%
           vad_filter=True               64     275    2   25    9.8%
           vad_filter=False, no loops    60     257    0    0    0.0%
           vad_filter=True, no loops     60     257    0    0    0.0%

         SUPERSEDED, do not cite: 88.2% / 20.1% on 65 attempts, and the
         earlier 0.0% / 0.8% no-loops pair. The 0.8% was the -12F3 filler
         and went with it.
Found:   with the two loop clips excluded the two sides are identical at
         0.0%, and they are the ONLY clips in the run carrying any
         character error at all. So VAD's entire measured benefit here is
         containing runaway decodes; it buys nothing on a clip that
         decodes normally.
Gate:    the no-loops rows drop every attempt at -7F9 and -12F4, including
         the clean re-reads, which can only raise that CER and never
         flatter it. Read the pair: the full rows say how often the decode
         failed, the no-loops rows say how well a tag is heard when it did
         not. Neither number alone is the answer. Strips are in none of it
         — the card gives a strip no character reference.

## Block 4 — Normaliser — repetition guard — 5 Oct

Question: a decoder that repeats one token until the window fills is not a
         misheard character, but the pipeline treated it as one. -7F9
         attempt 1 reached the adjudicator as a 113-character "tag".
Found:   two shapes, and one test does not reach both. -7F9 repeated a
         TOKEN ("9", 110 times). -12F4 repeated a PHRASE ("F4 minus 12",
         eight times), in which no token occurs twice in a row, so a
         repeat test alone passes it.
Found:   the old shape check caught both by accident, not reliably. Six
         repeated "nine"s normalise to "999999", which passes PART_RE as a
         well-formed part number, and a looped counts read of "L 3" parses
         to {L: 3} and adjudicates as a MISMATCH against the cabinet.
Decided: normalise.runaway(raw, kind), two tests: more than
         MAX_TOKEN_RUN = 5 of one token back to back, or more tokens than
         the kind's budget (MAX_TOKENS: 12 for tag and counts, 24 for part
         and rating). session.step_item asks it FIRST and short-circuits
         the adjudicator — a looped decode is not a read of that position,
         so there is nothing to judge against the schematic. The attempt is
         logged in full and the abstain spends a re-ask like any other.
Decided: the budgets are measured, not chosen. Across the 68 healthy
         attempts of run 20260927-130613 the longest device read is 4
         tokens and the longest strip read 5, so 12 sits over 2x above the
         corpus and far below both loops (22 and 112). part and rating are
         NOT measured — no run has used part mode — and are set from the
         longest fully spelled-out example in normalise.py with the same
         headroom.
Gate:    VAD does not make this redundant, and the reverse holds too. VAD
         cut -7F9 from 112 tokens to 28; this guard is what catches the 28.
         It classifies and never repairs: the raw text is kept, the
         normalised value is still returned, and only well_formed and the
         reason move — so the CER above is unchanged by it.

## Block 4 — Normaliser — leading filler only — 5 Oct

Question: switching VAD on made Whisper write one clip as a sentence,
         "So, minus 12 F3." for a clip that says nothing but the tag. It
         normalised to "-SO12F3", failed the tag shape, and a clean read
         became an abstain.
Decided: LEADING_FILLER = {"so"}, stripped from the FRONT of a transcript
         only, in all three normalisers and in the strip-counts tokeniser.
Rejected: adding "so" to NOISE_WORDS, which drops its members wherever they
         appear. A stray word in the MIDDLE of a read is evidence that the
         read went wrong, and dropping it there would launder the defect
         this project measures (CONTEXT §7). "minus 12 so f3" still fails,
         loudly, as -12SOF3.
Decided: the set has one member because that is what the corpus has. Every
         transcript on hand was checked for a leading token that is not a
         digit, a number word or a letter — the 73 attempts of run
         20260927-130613, both sides of all 72 VAD clips, and the 19 rows
         of transcripts.csv — and "so" is the only one.
Gate:    nothing may enter LEADING_FILLER that any vocabulary in
         normalise.py could read as content, and a test enforces it. "oh"
         is why: it is an English sentence opener AND a zero in
         DIGIT_WORDS, so stripping it would delete a spoken digit.

## Block 6 — Strip reads abstain on an unknown label — 5 Oct

Question: -X1 of run 20260927-130613 was published as
         "mismatch — N: read 0, expected 1". -X1 carries no planted fault,
         the card's own line says 6 terminals, the schematic expects
         L 3 / N 1 / PE 1 / BRACKET 1, and the walker counted it correctly.
Found:   Whisper wrote "M1" for "N1". parse_counts has no "M", so it
         dropped the word in silence and kept {L: 3, PE: 1, BRACKET: 1};
         the adjudicator saw N missing and reported a fault in a cabinet
         nobody had touched. Worse, a mismatch is not an abstain, so it was
         never re-asked: one attempt, straight to a flag.
Decided: session.unknown_labels names the words in a counts read that are
         no terminal function, and step_item abstains instead of
         adjudicating when there is one. An unknown label cannot be told
         apart from a count that was never spoken, so the counts that DID
         parse are not trustworthy either — it is named, never guessed at.
Changed: parse_counts and unknown_labels now share one tokeniser,
         count_tokens. A token one of them sees and the other does not is
         exactly how "M1" got through.
Decided: it fires only when counts also parsed. A read that parsed nothing
         keeps judge_strip's own "no counts were given", a better account
         of a silent clip — Whisper writes silence as "You".
Gate:    this does NOT catch a known label heard for another known one.
         With VAD on the same clip reads "N3" for "L3"; N is a real
         function, so there is nothing unknown to notice and it still
         adjudicates, as a mismatch the other way round. Nothing in a
         counts transcript distinguishes that from a strip genuinely
         missing its L terminals. Fixed in a test so it is not mistaken
         for solved.

## Block 9 — Walker card v2 — uniform strip wording — 5 Oct

Question: the card is not allowed to say which lines the fault set
         overwrote; a card that marks its own faults measures nothing.
Found:   v1 broke that at the strips. An unfaulted strip printed its TAG in
         the speak column and a faulted one printed a sentence, so 6 of 8
         strips read "-X1", "-X2", ... and exactly the 2 faulted ones read
         an instruction. The tell is visible at a glance, without reading a
         word of it, and it names the strip half of the fault set. v1 also
         told the walker to speak "-X1" at a strip, which is not what the
         app asks for there: at a strip it asks for terminal counts.
Decided: card v2. Every strip line now opens "count the terminals", faulted
         or not, so there is no form to read off, and the unfaulted strips
         finally say what the walker is meant to do. The faulted clause
         keeps faults.csv's own wording after the shared stem rather than
         being reworded here.
Changed: walker_card.py takes --version (CURRENT_VERSION = 2);
         walker_card_v2.txt written. v1 is kept and verified reproducible
         line for line, because run 20260927-130613 was walked with it.
         score.py's reference check now tries every known version and names
         which one matched, so both cards validate and the match is still
         required to be exact. Printing v2 over walker_card.txt would have
         silently invalidated that check.
Gate:    v2 removes only the GLANCEABLE tell. A faulted strip's clause still
         says something unusual, because that clause IS the planted fault —
         a walker who reads and thinks about "as if one L terminal were
         absent" knows that strip is special, and no wording hides it.
         Devices never had this problem: a faulted device shows another tag,
         indistinguishable in form from a correct one. Nothing already
         measured moves — v1 and v2 differ only at the strip lines and the
         header, and strips carry no character reference anyway.
