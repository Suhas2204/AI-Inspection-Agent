"""redlining: voice-guided inspection assistant for one control cabinet.

Pipeline, one module per block:
    loader       Block 1  raw export -> cleaned component set
    position     Block 2  coordinates -> spoken locations (walking order)
    make_bands   Block 3  emit the rows the advisor bands
    checklist    Block 3  walking order + bands -> ordered checklist
    normalise    Block 4  raw transcript -> canonical string
    adjudicate   Block 6  read vs schematic -> one of four verdicts
    session      Block 7  run the inspection loop
    audio_input  Block 7  microphone + local Whisper input
    report       Block 8  append-only run log and report
"""
