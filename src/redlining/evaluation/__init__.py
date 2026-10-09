"""redlining.evaluation: Block 9, what a finished run is worth.

    score         one run against the planted faults: the four rates
    walker_card   the card the walker reads while planting the fault set

Both read; neither writes into runs/. A recorded run is evidence, and the
one thing an examiner can check is that scoring it does not change it.

The rest of Block 9 lives in experiments/, which is not packaged: the
statistics are in core.stats so that both halves share one Wilson interval,
and the fault draw is in prep.select_faults because it runs before a walk.

Both modules are re-exported at their old top-level paths.
"""
