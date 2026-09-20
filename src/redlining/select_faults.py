"""Pick the Block 9 fault set from the candidates, reproducibly.

Run once. Record the seed in DECISIONS.md. Do not run it again and
keep the result you prefer -- that is selection bias, and it is the
one thing an examiner can check.

    uv run python -m redlining.select_faults 20260920 > data/faults.csv

A candidate may carry an optional item_b: a label swap planted across
two positions. It is still one row and one place in the denominator,
so N_DETECTABLE counts faults, not positions. No two picked faults may
occupy the same position -- see the collision check below.
"""
import csv, random, sys
from collections import Counter

from .paths import DECISIONS
from .score import positions      # one definition of "where a fault sits"

CANDIDATES = DECISIONS / "fault_candidates.csv"

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20260920
N_DETECTABLE = 10          # counted in the detection-rate denominator
N_KNOWN_MISS = 0           # carried, reported, excluded from denominator

rows = list(csv.DictReader(open(CANDIDATES, encoding="utf-8")))
missing = {"item", "detectable"} - set(rows[0])
if missing:
    sys.exit(f"{CANDIDATES} lacks column(s): {', '.join(sorted(missing))}")

detectable = [r for r in rows if r["detectable"] == "yes"]
known_miss = [r for r in rows if r["detectable"] == "no"]

for name, pool, want in (("detectable", detectable, N_DETECTABLE),
                         ("known-miss", known_miss, N_KNOWN_MISS)):
    if want > len(pool):
        sys.exit(f"{CANDIDATES} offers {len(pool)} {name} candidate(s), "
                 f"but {want} are wanted.")

# Both draws come from the seeded rng: the selection reproduces from the
# seed alone, not from the row order of the candidates file. The known-miss
# draw is skipped outright when none are wanted, so an empty pool is a
# legitimate study design and not an error.
rng = random.Random(SEED)
picked = rng.sample(detectable, N_DETECTABLE)
if N_KNOWN_MISS:
    picked += rng.sample(known_miss, N_KNOWN_MISS)

# A position carries at most one fault. Two faults at one terminal make the
# flag ambiguous and the denominator wrong, and a swap occupies two
# positions, so the chance of a clash is real. Make the candidates disjoint
# and run again on this same seed; do not hunt for a seed that happens to fit.
clash = sorted(p for p, n in Counter(
    p for f in picked for p in positions(f)).items() if n > 1)
if clash:
    sys.exit(f"seed {SEED} picked faults sharing position(s): {', '.join(clash)}. "
             "Separate them in the candidates file and re-run with this seed.")

w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()) + ["seed", "planted_on", "found"])
w.writeheader()
for r in picked:
    r.update(seed=SEED, planted_on="", found="")
    w.writerow(r)
