"""redlining: voice-guided inspection assistant for one control cabinet.

Pipeline, one module per block:
    loader       Block 1  raw export -> cleaned component set
    position     Block 2  coordinates -> spoken locations (walking order)
    make_bands   Block 3  emit the rows the advisor bands
    checklist    Block 3  walking order + bands -> ordered checklist
    session      Block 7  run the inspection loop
    audio_input  Block 7  microphone + local Whisper input
    report       Block 8  append-only run log and report

core/ sits outside that list: no block of its own, importable from anywhere.
Every name below is re-exported at its old top-level path as well, so
redlining.normalise and `python -m redlining.adjudicate` both still resolve.
    core.types            Read and Heard, shared by every input source
    core.normalise        Block 4  raw transcript -> canonical string
    core.adjudicate       Block 6  read vs schematic -> one of four verdicts
    core.stats            Block 9  Wilson intervals and exact McNemar
"""
