"""redlining.core: types and helpers with no I/O and no block of their own.

Nothing here reads a file, opens a device or talks to a server, and nothing
here imports from a block module. That is the whole rule, and it is what
makes the package safe to import from anywhere -- including from the input
adapters, which is why `types.py` exists.
"""
