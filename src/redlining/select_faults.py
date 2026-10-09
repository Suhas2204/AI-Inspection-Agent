"""Compatibility shim: the fault draw moved to redlining.prep.select_faults.

This one gets no re-export, and that is deliberate. prep/select_faults.py is
a script, not a module: it has no __main__ guard, so everything it does --
read the candidates, draw on the seed, check for collisions, write the CSV to
stdout -- happens at import. A shim that imported it to re-export its names
would perform the draw on `import redlining.select_faults`, and a shim that
imported it AND delegated would perform it twice, printing two CSVs into one
file. So the shim only delegates.

    uv run python -m redlining.select_faults 20260920 > data/faults.csv

sys.argv is untouched by the hand-off, so the seed argument still arrives.
Nothing imports this module; it is run once and its seed is recorded in
docs/DECISIONS.md.
"""

from __future__ import annotations

if __name__ == "__main__":
    import runpy

    runpy.run_module("redlining.prep.select_faults", run_name="__main__")
