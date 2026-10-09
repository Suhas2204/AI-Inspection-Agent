
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

## Block 9 — interval estimates and the paired VAD test — 5 Oct

Question: every metric in this study is a proportion over a small
         denominator — 70 positions, 10 planted fault rows, 64 scorable
         attempts. A bare percentage hides that, and invites comparisons
         the run cannot support.
Decided: every reported rate (correct, abstention, fault detection, false
         flag/precision, coverage, risk, per band, per character) now
         prints its k/n and a 95% Wilson score interval beside the
         percentage. The percentages are unchanged; nothing was restated.
Rejected: the normal-approximation (Wald) interval,
         p ± z·sqrt(p(1−p)/n). It has zero width at k = 0 and k = n, and
         this run reports 0/70 abstains and 70/70 coverage — Wald would
         print "0.0% to 0.0%" for both and claim a certainty nobody
         measured. Wilson gives 0/70 = [0.0, 5.2]. Recommended for small n
         by Brown, Cai & DasGupta (2001).
Rejected: an interval on the character error rate, anywhere. A CER is
         errors per reference character, not a binomial proportion: the
         characters inside one attempt are not independent trials, and
         insertions let the numerator exceed the denominator — one runaway
         decode in this corpus scores 2750%. CER is reported as itself,
         with the per-clip table beside it.
Found:   what the intervals say that the percentages did not —

           detection rate   8/10    80.0%  [49.0, 94.3]
           precision        8/10    80.0%  [49.0, 94.3]
           abstention       0/70     0.0%  [ 0.0,  5.2]
           correct          56/70   80.0%  [69.2, 87.7]
           band 3           0/2      0.0%  [ 0.0, 65.8]

         Band 3 is the clearest case. "0%" reads as a finding; "0/2,
         [0.0, 65.8]" reads as two observations. The same in the
         per-character table, where 100.0% on three characters is
         [44, 100]: score.py already warned about thin evidence, and the
         interval now quantifies it rather than naming it.
Decided: the VAD on/off comparison is scored as a PAIRED test, not two
         independent rates. Both sides decoded the same 64 clips, so
         comparing the marginals as if they were two samples would
         overstate what the run can tell us. Per-attempt correct is exact
         match against the card — the same test the correct column uses,
         called one attempt at a time, so the two cannot drift.
Found:   vad_filter=False 62/64 = 96.9% [89.3, 99.1]
         vad_filter=True  63/64 = 98.4% [91.7, 99.7]
         both right 62, both wrong 1, b (only OFF right) 0, c (only ON
         right) 1. Exact McNemar: p = 1.0000. The single discordant
         attempt is -12F4 attempt 1, which only the VAD side got right;
         the one both got wrong is -7F9 attempt 1, the loop VAD shortened
         but did not fix.
Rejected: the chi-square form of McNemar, (b−c)²/(b+c). It is an
         approximation that should not be trusted much below b + c = 25,
         and here b + c = 1. The p-value is the exact binomial test it
         approximates: under the null b ~ Binomial(b+c, ½), computed in
         exact integer arithmetic.
Gate:    p = 1.0 is NOT a finding of equivalence, and must not be written
         up as one. With b + c = 1 the test has essentially no power: it
         could not have detected a difference of any size, so a large
         p-value here is a statement about the run and not about VAD. The
         63 attempts the two sides agreed on carry no information about
         which is better; only the discordant ones do, and there is one.
         The same caution applies to every interval above — intervals that
         overlap across the 12 swept settings in risk_coverage are not
         evidence that the settings differ, and most of them overlap.
Gate:    the decision to enable VAD does NOT rest on this test, and never
         did. It rests on the probes: without VAD the model invents "You"
         from digital silence, which is what cost -X3, -X6 and -X7 every
         attempt they had. On per-attempt correctness the two sides are
         indistinguishable here (both 60/60, [94.0, 100.0], once the two
         loop clips are excluded), and this run was never going to settle
         that question either way.
Changed: src/redlining/stats.py holds wilson_ci and mcnemar_exact;
         experiments/stats.py re-exports it. The split exists because
         src/redlining/score.py reports three of these rates and an
         installed package cannot import from an unpackaged experiments
         folder — and two copies of a Wilson interval could drift apart
         while both kept passing their own tests. A test asserts object
         identity, not equal behaviour. No scipy: statistics.NormalDist
         for the quantile, math.comb for the binomial tail.
Note:    fixing the LaTeX table to carry the new interval column exposed
         that its percent signs had never been escaped. A bare % starts a
         LaTeX comment, so every percentage row had been commenting out
         the rest of itself, trailing row separator included. Any thesis
         table built from --latex before 5 Oct should be regenerated.

## Block 7 — LLM orchestrator — what the model may not know — 5 Oct

Question: a trainee at a cabinet wants to say "where next", "say that
         again", "skip this one, I can't reach it". That is a dispatch
         problem and the only thing an LLM is needed for here. Everything
         else a model could reach for is the risk.
Decided: src/redlining/orchestrator.py. Text only — no microphone, no
         weights, no network — and MockLLM is the only implementation, so
         it runs offline and in the test suite. It is a DRIVER around
         session.step_item, not a second pipeline: normalising, the
         Adjudicator and the log are the same calls the keyboard and
         Streamlit paths make. There is no second adjudicator and no place
         for one. The only policy the module owns is whether a re-ask is
         still allowed, and that rule is borrowed from session.run rather
         than invented.
Decided: three guarantees, in the order they matter.

         1. It cannot rewrite the reading. submit_reading takes NO
            arguments: it signals that the trainee has just read the
            position out, and the orchestrator normalises the utterance it
            already holds (hear() is the only way words enter the module).
            A model that sends a text argument anyway has it ignored, and
            the attempt records that it tried. First because it is worst:
            a model that could supply the words could turn a misread into
            a match, and the run would be measuring the model.
         2. It cannot learn what the schematic expects. Tools return their
            results unchanged — full verdict, reason, expected — and
            exactly one function, redact(), stands between those results
            and the model. Two passes: keys carrying the answer are
            dropped outright, because a reason like "N: read 0, expected
            1" cannot be substring-scrubbed without deleting every digit;
            then every surviving string is scanned word by word against
            the cabinet's 162 tags, part numbers and rating lines. The
            second pass is the backstop for a field nobody remembers to
            add to the first list.
         3. It cannot decide a verdict. The verdict is step_item's. The
            orchestrator reads verdict.outcome once, to apply session.run's
            re-ask rule, and never to form a judgement of its own.
Found:   audited over a full 70-position walk with CORRECT readings — the
         case where the read and the answer coincide and a leak is most
         likely — 141 orchestrator messages and 3424 words scanned against
         162 secrets, nothing through.
Decided: the OUTCOME is withheld from the model as well as the answer.
         "mismatch" names no tag, so the scanning pass would never catch
         it, and it is withheld anyway: it says the trainee got it wrong,
         and a model that knows will sooner or later let them know. Re-asks
         in this study are silent (session.py: "no echo, no hint") because
         a trainee who learns the last read was wrong reads the next one
         differently. ask_again is all a dispatcher needs and all it gets.
Decided: skip takes a POSITION NUMBER, not a tag. Not a style choice: the
         tag expected at a location is the answer the trainee is being
         tested on, so a tool signature taking one would hand the model the
         thing this module exists to withhold. The number is the
         walking-order index the walker card also prints, and it names a
         place without saying what is mounted there.
Decided: a skipped position writes no attempt, so it is simply absent from
         the log. score.py already reads an absent planted position as
         "not walked" and scores it neither way, which is exactly what a
         skip means — no new status, no new column, no change to the
         scorer.
Gate:    the trainee's own utterance IS passed to the model verbatim, and
         this is the one thing the no-disclosure guarantee does not cover.
         It has to be: a router cannot tell a reading from a request
         otherwise. When a trainee reads a position correctly their words
         match what the schematic expects, and that is the INPUT, not a
         disclosure by this module. The guarantee is about what the
         orchestrator tells the model, and orchestrator_messages is the
         list it covers. A test asserts the tag is present in the utterance
         and absent from every message the orchestrator originates, so the
         exception is visible rather than discovered later. Closing it
         entirely would mean the model never seeing the reading, which
         removes the tool-calling design; that trade has not been made.
Changed: normalise.CARRIER_PHRASES — "it says", "it reads", "I see",
         "I read", "the tag is", "that's" — stripped at the FRONT of a
         transcript only, with every match recorded in
         Normalised.stripped. Before it, "it says minus 1 F1" normalised
         to "-ITSAYS1F1" and a good read abstained.
Gate:    these phrases are NOT measured from the corpus, and they are the
         only list in normalise.py that is not. Run 20260927-130613 was
         recorded one reading at a time with nobody to address, so it
         contains no carrier phrase; LEADING_FILLER's single member "so"
         was measured, these six were not. They come from the
         conversational front end, where there is someone to address.
         Extend them from utterances people actually said. "that is" reads
         like "that's" and is deliberately absent, so that growing the list
         stays a decision rather than a drift.
Gate:    the removal is logged, and that is what makes it legitimate. raw
         keeps every word the trainee said, value is what was judged, and
         stripped is the difference. A fixed rule that reports itself can
         be audited, repeated and argued with. An earlier objection to
         trimming at all was about a MODEL doing it on judgement, and that
         objection stands: the model still carries no words. Nothing is
         stripped from the middle of a reading either — "minus 1 it says
         F1" still fails, as "minus 12 so f3" always has — and stripping
         never repairs what follows: "it says minus 9 F 9" reaches the same
         verdict as "minus 9 F 9", which at position 1 is a flag, because
         a fault is planted there.
Gate:    every carrier phrase is more than one token, enforced by a test.
         That is the invariant making this safe where single words would
         not be: "i", "s" and "is" each normalise to content on their own,
         since a single letter is a letter, so they can only ever be
         removed as part of a phrase.
Gate:    MockLLM is a stand-in, not an evaluation. It is a fixed phrase
         mapping, so nothing here says whether a real model would route
         these utterances correctly, resist asking for the answer, or stay
         silent about an outcome it was not given. What the tests establish
         is that it CANNOT get the answer, rewrite a reading or reach a
         verdict however it behaves — which is the part that should not
         depend on the model.

### Block 7 — LLM orchestrator — a real model, measured — 5 Oct

Ran:     LlamaCppLLM against the shared llama.cpp server over
         OpenAI-compatible chat completions, temperature 0, 60 s ceiling,
         no retries. 22 utterances covering all six tools plus clarify,
         one request each, each judged from the state in which its intent
         is the right call.
Found:   Gemma-4-26B-A4B-it-UD-Q4_K_XL 21/22 = 95%, Wilson 95% [78, 99].
         Qwen3.8-27B-UD-Q8_K_XL 20/22 = 91%, Wilson 95% [72, 97].
         Latency over the 21 requests after the first: Gemma median
         0.47 s, mean 0.70 s, range 0.36-2.95. Qwen median 1.33 s, mean
         1.72 s, range 1.00-4.00. First request: Gemma 2.95 s, already
         loaded; Qwen 7.19 s, swapped in on demand. No transport failure
         and no invalid tool call from either model.
Decided: Gemma. The accuracy intervals overlap almost entirely, so this
         measurement does NOT separate the two on routing, and saying
         95% beats 91% on 22 utterances would be reading noise. The
         decision rests on latency, where 0.47 s against 1.33 s is a
         clean 3x on the same hardware and the same prompts, and on cold
         start, which a trainee pays whenever the server has swapped the
         model out. A dispatcher someone stands at a cabinet waiting for
         is chosen on the axis that is actually separated.
Found:   the misses are the same shape in both models: the model answered
         from the transcript instead of calling the tool that answers
         properly. Gemma took "skip position 4" as a request for the
         location and read the location back. Qwen answered "how many are
         left" from the remaining count already in the transcript rather
         than calling progress, and routed "whereabouts am I meant to be
         standing" to repeat rather than explain_location. Neither model
         reached for the answer, and no miss was a fault of the client.
Changed: the harness, and it moved the number. The first sweep judged
         every utterance from ONE transcript that already held a
         next_location result, and Gemma scored 0/4 on next_location
         there -- not a routing failure: it read the location back out of
         the context it had been handed. That scored the harness, not the
         model. Each intent is now judged in a state where it is
         unambiguously the right call -- "fresh", nothing open as at the
         start of a run, for next_location; "open", a position given out
         and waiting for a reading, for the rest -- and Gemma went
         77% -> 95% on the same utterances with the same model and the
         same client.
Decided: the state is part of the measurement and is recorded per row.
         No single state makes all seven intents correct: from a
         transcript holding a location, "where next" can be answered by
         reading it back; from a transcript with nothing open, a bare
         reading has no position to be judged against. A measurement that
         hid which state it used would be unreproducible and, as above,
         wrong by up to 18 points.
Note:    SUPERSEDED by the 6 Oct entry below, do not cite: the
         accuracies here were measured against dispatch prompt v1 and
         the 22-item set, both of which have since changed. The
         latency comparison and the choice of Gemma stand, because a
         one-sentence prompt change does not move latency and the
         choice rested on latency and cold start.
Note:    per-utterance rows not retained; re-measurement pending. The
         sweep printed a summary and discarded the rows, so the
         aggregates above are what survived. Which utterance went where
         is recoverable from the printed per-intent tallies and the named
         misses; the per-utterance latencies are not, and rebuilding them
         would mean spending the shared server's time again. The test now
         writes every row to data/processed/llm_intent/<model>.csv and
         .json after each request, so the next sweep is the one to cite.
         Treat every number here as provisional until it lands.
Gate:    22 utterances is a first measurement, not proof. One author
         wrote them, which makes them a guess at how a trainee speaks and
         not a sample of it; three or four per intent cannot separate 95%
         from 91%, which is what the overlapping intervals say outright;
         and none of this is a walk -- every utterance was judged from a
         short fixed transcript, so multi-turn dispatch, recovery after a
         clarify, and behaviour under the re-ask budget are all
         unmeasured. Extend the utterances from things people actually
         said, as the carrier phrases are to be extended, before any of
         this is quoted as a model comparison.
Note:    the entry above says "no network" and "MockLLM is the only
         implementation here". Both were true when written; LlamaCppLLM
         makes neither true, and the module docstring was corrected with
         it. Every offline test still runs with no server, and the
         integration test is skipped unless it is asked for and the
         server answers.

### Block 7 — LLM orchestrator — dispatch prompt v2 — 6 Oct

Found:   run 20261006-184627. A trainee at position 1 said "minus one Q
         one" -- the correct label, digits spoken as words -- and the agent
         replied "Please read the tag." instead of submitting it. Probed
         afterwards against Gemma with position 1 open, which is the state
         that run was in:

             "Minus one q1"      reply, "Please read the tag."
             "minus one q one"   reply, "Please read the tag."
             "minus 1q1."        submit_reading
             "minus 1 q 1"       submit_reading

         The model submits a label whose digits arrived as NUMERALS and
         declines one whose digits arrived as WORDS. Systematic, not a
         one-off, and it is the model alone: _is_reading accepts all four
         and normalise maps all four to the same tag, so a run on MockLLM
         would have submitted every one of them.
Decided: one sentence added to submit_reading's description -- digits
         spoken as words are still the reading, and a label is never
         re-asked merely because its numbers arrived as words. The likely
         cause is the sentence already there: "call this only when what
         they said IS the reading and nothing else", which the model
         appears to read as excluding "one" as other words.
Gate:    the example in that sentence is a tag that is NOT in the cabinet.
         "minus one Q one" was the obvious example to write and it
         normalises to the tag at position 1, which carries a planted
         fault -- the prompt would have spelled out the answer to the first
         position a trainee walks to. The existing leak scan would not have
         caught it: it reads word by word, and a spoken tag is several
         words, none of which is a secret on its own. A second scan now
         normalises every run of two to six consecutive words in the prompt
         and the schemas and checks THAT against the secrets, with a test
         that it would have caught the example that was proposed.
Changed: the prompt is now versioned, PROMPT_VERSION in orchestrator.py.
         v1 is what the 5 Oct comparison measured; v2 is v1 plus that
         sentence. Nothing may report dispatch accuracy without saying
         which version produced it.
Changed: the measurement set is 24 utterances, up from 22. The two added
         are verbatim from run 20261006-184627 rather than invented:
         "Minus one q1", the word-form reading v1 declined, and "We're
         next.", which is what Whisper made of "where next". The second is
         a mishearing and belongs in the set for that reason -- the
         trainee did ask to be moved on, and a dispatcher has to survive
         ASR as it actually is. This is the Gate on the 5 Oct entry being
         acted on: the set grows from utterances people actually said.
Gate:    SUPERSEDED, do not cite: the v1 accuracies. Gemma 21/22 = 95%,
         Wilson [78, 99], and Qwen 20/22 = 91%, Wilson [72, 97], were
         measured against prompt v1 and the 22-item set. Both have since
         changed, so neither figure is current and neither may be quoted as
         if it were. The LATENCY comparison -- Gemma median 0.47 s against
         Qwen 1.33 s, and cold start 2.95 s against 7.19 s -- is not touched
         by a one-sentence prompt change, and the choice of Gemma rested on
         it, so that decision stands; the accuracy figures do not.
OPEN:    re-measure both models at v2 over the 24, and report whether the
         sentence fixed the word-form readings without costing anything
         elsewhere. Not run yet: the server is shared and this entry is
         being written before spending on it. Until it is run, the only
         claim supported here is that v1 declined word-form readings.

### Layout — src/redlining split into six packages — 9 Oct

Found:  19 modules flat in src/redlining/, and three import cycles between
        them. Read lived in session.py, so audio_input.py and
        streamlit_input.py both reached into session.py to build one while
        session.py imported audio_input.py for the endpointing constants.
        Both halves survived only because the two input sources deferred
        their import into the method body, four times between them. A flat
        list also says nothing about what may import what, which is the
        question that matters when adding a module.
Changed: paths.py stays at the top. Everything else moved into six
        packages, in the order the work happens: prep/ (Blocks 1-3 and the
        fault draw, run by hand before a walk), speech/ (the two input
        sources), inspection/ (session, orchestrator, report), evaluation/
        (score, walker_card), view/ (model3d), and core/ (reads,
        normalise, adjudicate, stats -- no block of its own, importable
        from anywhere).
Changed: Read and Heard moved to core.reads, which removed two of the three
        cycles outright. The input sources import them directly now and
        their four deferred imports became one plain import each.
Kept:    the third cycle, orchestrator <-> session, inside inspection/.
        orchestrator needs MAX_REASKS and step_item at module level;
        session needs CLARIFY and the LLM classes only inside agent_loop
        and run_agent, so those stay deferred. Counting body-level imports
        alone there is no cycle, so no import order can fail. Breaking it
        properly means moving step_item to a third module, which changes
        the loop rather than the layout -- not done here, and both modules
        drive the same step_item on purpose: an LLM-driven run writes
        byte-for-byte the log a walked run writes because it is the same
        function.
Kept:    every old import path. Each moved module left a shim at its old
        path that re-exports the implementation -- private names included,
        because tests import _pre, _is_exit, _EnterWatcher, _wire_tools,
        _wire_messages, _arguments_for, _is_reading and _emit_row -- and
        delegates `python -m redlining.<name>` to the new module with
        runpy. 16 shims, 382 names, every one checked for object identity
        rather than equality: old.X is new.X. No test, no experiment script
        and nothing in app.py had to change its imports, which is the
        evidence that the shims work, so they were left on the old paths
        deliberately.
Gate:    paths. Every path constant was captured before the move and
        diffed after -- data/raw, data/processed, data/decisions, runs/,
        and the copies in loader.RAW/OUT, position.DATA and
        make_bands.SRC/OUT. Identical, byte for byte. paths.py was not
        moved for exactly this reason: ROOT is parents[2], and one level
        deeper makes ROOT src/, every data path resolve to a file that is
        not there, and nothing raise.
Found:  core/types.py, the first name for core/reads.py, shadowed the
        standard library's `types`. enum and weakref import from it during
        start-up, so any sys.path entry pointing at core/ -- which a direct
        `python src/redlining/core/adjudicate.py` creates -- made the
        interpreter import ours and fail inside `import json`, before a line
        of project code ran. Renamed to core/reads.py, and speech/ is named
        speech/ and not io/ for the same reason.
Changed: select_faults.py had no __main__ guard, so reading the candidates,
        the seeded draw, the collision check and the CSV to stdout all
        happened at import. Its body is in main() now. The command is
        byte-for-byte what it was -- 2010 bytes, same md5, with the seed
        argument, without it, and run at either path -- and importing the
        module writes nothing.
Gate:    all fourteen `python -m` entry points run, at both the old path
        and the new one, score --latex included. The agent loop was driven
        on piped input ("where next", "minus 1 Q1", "done") with --agent
        --text and no --llm, which exercises the deferred orchestrator
        import: MockLLM dispatched next_location and submit_reading over 3
        turns and wrote a report. make_bands still exits 1 on its own
        guard. No tracked file under data/ or runs/ changed. 460 passed, 2
        skipped, unchanged at every one of the eight commits.
Note:    docs/architecture/ holds the diagrams, generated and not drawn:
        packages.mmd from docs/architecture/import_graph.py, classes.mmd
        from pyreverse (pylint is a dev dependency now). pyreverse resolves
        single-dot relative imports and not double-dot ones, so its own
        package diagram finds 6 of the 31 edges; both are committed, and
        docs/architecture/README.md says which is which and why.
OPEN:    the shims are a migration aid, not a design. Nothing is forced to
        use them, and the right time to delete them is after the thesis is
        submitted and the quoted paths are frozen -- not before, because
        README, REPRODUCE and CONTEXT quote module paths a reader may type.
