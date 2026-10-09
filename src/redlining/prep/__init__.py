"""redlining.prep: Blocks 1-3, the files a run reads but never writes.

These five scripts turn the raw EPLAN export into the three things an
inspection needs -- the cleaned component set, the walking order, and the
checklist that joins it to the advisor's bands -- plus the one-shot draw
that picked the Block 9 fault set. They run before a session, by hand, and
nothing in a run calls them except load_checklist.

Each is re-exported at its old top-level path, so `redlining.checklist` and
`python -m redlining.loader` both still resolve. paths.py stays outside this
package: it is the one anchor every layer shares.
"""
