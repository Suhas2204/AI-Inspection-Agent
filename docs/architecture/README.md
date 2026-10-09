# Architecture

Three files, all generated, none hand-drawn. Regenerate them after any move
and commit the result; a diagram that disagrees with the code is worse than
no diagram.

| File | Shows | Made by |
|---|---|---|
| `packages.mmd` | every import between the 18 modules, grouped by package | `import_graph.py` |
| `classes.mmd` | the 25 classes, their attributes and methods | `pyreverse` |
| `packages_pyreverse.mmd` | what pyreverse sees of the same imports: 6 of 31 | `pyreverse` |

Mermaid renders on GitHub, in VS Code with the Markdown Preview Mermaid
extension, and at <https://mermaid.live> if you paste a file in.

## The six layers

`paths.py` is the only module left at the top of the package. It holds every
file location, anchored at `ROOT = Path(__file__).resolve().parents[2]`, which
is why it did not move: one level deeper and `ROOT` would silently become
`src/`, every data path would resolve to a file that is not there, and nothing
would raise. Everything else sits in one of six packages.

| Package | When it runs | Depends on |
|---|---|---|
| `prep/` | before a walk, by hand | `paths` (and `evaluation.score`, once) |
| `speech/` | during a walk | `core.reads` |
| `inspection/` | during a walk | `core`, `prep.checklist`, `speech`, `paths` |
| `evaluation/` | after a walk | `core.stats`, `prep.checklist`, `paths` |
| `view/` | whenever someone looks | `prep.position`, `paths` |
| `core/` | anywhere | `paths`, and nothing else |

The direction is the point. `core/` is importable from everywhere because it
imports almost nothing: `reads`, `normalise` and `stats` have no project
imports at all, and `adjudicate` reads the schematic. `prep/` modules import
`paths` and nothing else. Nothing in `core/`, `prep/`, `speech/` or `view/`
imports `inspection/`, so a run can be scored, a card printed or the cabinet
drawn without loading the loop, the microphone or an LLM client.

One edge runs against the grain: `prep.select_faults -> evaluation.score`, for
`positions()`. The fault draw and the scorer have to agree on where a fault
sits or the collision check is meaningless, so they share one function rather
than two copies of a definition. It runs once, before everything else, and it
is the reason `prep/` is not strictly a leaf.

## The one cycle

```
inspection.orchestrator -> inspection.session -> inspection.orchestrator
```

`orchestrator` needs `MAX_REASKS` and `step_item`, so its import of `session`
runs when the module body does. `session` needs `CLARIFY` and the three LLM
classes only inside `agent_loop` and `run_agent`, so those two imports sit in
the function bodies -- dotted in `packages.mmd`. That is what makes the cycle
survivable: counting body-level imports alone, there is no cycle at all, so no
import order can fail.

It is deliberate, not residual. Both modules drive the same `step_item`, which
is the whole point of the orchestrator -- the log an LLM-driven run writes is
byte-for-byte the log a walked run writes, because it is the same function.
Breaking the cycle means moving `step_item` to a third module that both import,
which changes the loop rather than the layout. Until someone wants that, the
two live in one package and the deferred imports carry a comment saying why.

Two earlier cycles are gone: `session <-> audio_input` and
`session <-> streamlit_input`, both caused by `Read` living in `session.py`
while every input source had to build one. `Read` and `Heard` are in
`core.reads` now and the input sources import them directly.

## Regenerating

`pyreverse` ships with pylint, a dev dependency:

```bash
uv run python docs/architecture/import_graph.py -o docs/architecture/packages.mmd
```

It prints the module count, the edge count and any cycle to stderr, which is
the quickest check that a move did what it looked like it did.

For the two pyreverse files, point it at a copy of the package with the
sixteen top-level shims removed -- they re-export their new home, so including
them doubles every node:

```bash
cp -r src/redlining /tmp/uml/redlining
cd /tmp/uml/redlining && rm adjudicate.py audio_input.py checklist.py \
  loader.py make_bands.py model3d.py normalise.py orchestrator.py \
  position.py report.py score.py select_faults.py session.py stats.py \
  streamlit_input.py walker_card.py
cd /tmp/uml && PYTHONPATH=/tmp/uml uv run pyreverse -o mmd -p redlining \
  -d out --colorized redlining
```

`-o svg` instead of `-o mmd` writes SVG, but needs a Graphviz `dot` on PATH;
without one pyreverse says so and writes nothing. No SVG is committed here for
that reason. Mermaid needs no toolchain, which is why it is the source of
truth.

## Why two package diagrams

`pyreverse` resolves single-dot relative imports and not double-dot ones.
`from .report import RunLog` is drawn; `from ..core.adjudicate import
Adjudicator` is not. Six of this package's thirty-one edges are single-dot, so
`packages_pyreverse.mmd` shows the inside of `inspection/` and `speech/` and
nothing between the layers. It is committed as what the standard tool produces;
`packages.mmd` is committed as what the imports actually are. Its generator is
40 lines of `ast` and sits next to it, so the claim is checkable rather than
asserted.

The class diagram has no such gap -- `classes.mmd` is pyreverse's own output,
unedited.

It has 25 classes and no arrows, which is correct and not a failure: no class
in this package inherits from another. `LLM` is a `typing.Protocol`, and
`MockLLM` and `LlamaCppLLM` satisfy it structurally without subclassing it, so
there is no inheritance edge to draw. The composition pyreverse would
otherwise show is in `packages.mmd` instead, at the level the modules sit at.
