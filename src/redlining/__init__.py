"""redlining: voice-guided inspection assistant for one control cabinet.

What a run produces, one module per block:
    score           Block 9  score one run against the planted faults
    walker_card     Block 9  the card the walker reads while planting
    model3d                  axis-aligned boxes for the 3D view

inspection/ is one run, from the first prompt to the written report:
    inspection.session       Block 7  walk the checklist, run the inspection
    inspection.orchestrator  Block 7  an LLM front end over step_item
    inspection.report        Block 8  append-only run log and report

core/ sits outside that list: no block of its own, importable from anywhere.
Every name below is re-exported at its old top-level path as well, so
redlining.normalise and `python -m redlining.adjudicate` both still resolve.
    core.reads            Read and Heard, shared by every input source
    core.normalise        Block 4  raw transcript -> canonical string
    core.adjudicate       Block 6  read vs schematic -> one of four verdicts
    core.stats            Block 9  Wilson intervals and exact McNemar

speech/ is the input sources, one interface, one output -- a Read:
    speech.audio_input      Block 7  microphone + local Whisper
    speech.streamlit_input  Block 7  a clip the page already recorded

prep/ is what runs before a session, by hand, and never during one:
    prep.loader           Block 1  raw export -> cleaned component set
    prep.position         Block 2  coordinates -> spoken locations
    prep.make_bands       Block 3  emit the rows the advisor bands
    prep.checklist        Block 3  walking order + bands -> ordered checklist
    prep.select_faults    Block 9  the one-shot, seeded fault draw

paths.py stays at the top: one anchor, shared by every layer.
"""
