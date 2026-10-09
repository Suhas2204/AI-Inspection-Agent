"""redlining: voice-guided inspection assistant for one control cabinet.

One module stays at the top: paths.py, the anchor every layer shares.
Everything else sits in one of six packages, in the order the work happens.
Every name below is also re-exported at its old top-level path, so
`redlining.score` and `python -m redlining.session` both still resolve.

prep/ runs before a session, by hand, and never during one:
    prep.loader              Block 1  raw export -> cleaned component set
    prep.position            Block 2  coordinates -> spoken locations
    prep.make_bands          Block 3  emit the rows the advisor bands
    prep.checklist           Block 3  walking order + bands -> checklist
    prep.select_faults       Block 9  the one-shot, seeded fault draw

speech/ is the input sources: one interface, one output -- a Read:
    speech.audio_input       Block 7  microphone + local Whisper
    speech.streamlit_input   Block 7  a clip the page already recorded

inspection/ is one run, from the first prompt to the written report:
    inspection.session       Block 7  walk the checklist, run the inspection
    inspection.orchestrator  Block 7  an LLM front end over step_item
    inspection.report        Block 8  append-only run log and report

evaluation/ is what a finished run is worth:
    evaluation.score         Block 9  one run against the planted faults
    evaluation.walker_card   Block 9  the card the walker reads

view/ is the picture:
    view.model3d                      axis-aligned boxes for the 3D view

core/ sits outside the order: no block of its own, no I/O but reading the
schematic, and importable from anywhere:
    core.reads                        Read and Heard, for every input source
    core.normalise           Block 4  raw transcript -> canonical string
    core.adjudicate          Block 6  read vs schematic -> one of four
    core.stats               Block 9  Wilson intervals and exact McNemar
"""
