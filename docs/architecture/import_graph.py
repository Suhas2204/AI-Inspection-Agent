"""Emit the package's real import graph as Mermaid, and name any cycle.

pyreverse draws the class diagram here, and its package diagram with it, but
it resolves only single-dot relative imports: `from .report import RunLog` is
drawn, `from ..core.adjudicate import Adjudicator` is not. Six edges of the
thirty-odd in this package are single-dot, so its package diagram shows the
inside of inspection/ and speech/ and nothing between the layers.

This script reads the same files with ast and draws all of them, which is
what makes the layer claim in README.md checkable. It also separates the two
kinds of edge that matter for a cycle:

    solid   imported while the module body runs; Python must resolve it
    dotted  imported inside a function body, so it resolves on first call

A cycle of solid edges is an ImportError waiting for an import order. A cycle
with one dotted edge is the deliberate kind, and this package has exactly one.

Shims are excluded: the sixteen one-line modules at the top of the package
re-export their new home and would double every node.

    uv run python docs/architecture/import_graph.py           # to stdout
    uv run python docs/architecture/import_graph.py -o out.mmd
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "src" / "redlining"
PACKAGES = ("prep", "speech", "inspection", "evaluation", "view", "core")

# Everything at the top of the package except these is a re-export shim.
NOT_A_SHIM = {"__init__.py", "paths.py"}


def modules() -> list[tuple[str, Path]]:
    """Every non-shim module, as (dotted name within redlining, path)."""
    out = [(p.stem, p) for p in sorted(PKG.glob("*.py")) if p.name in NOT_A_SHIM
           and p.name != "__init__.py"]
    for pkg in PACKAGES:
        out += [(f"{pkg}.{p.stem}", p)
                for p in sorted((PKG / pkg).glob("*.py")) if p.stem != "__init__"]
    return out


def edges(name: str, path: Path) -> dict[str, bool]:
    """Imports of this module, as {target: deferred}. Deferred = inside a def."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    own = name.rpartition(".")[0]

    # By node, not by name: session.py imports audio_input at body level for
    # the VAD constants AND defers three more from it inside run(). Keying on
    # the module name would call that one edge deferred, which it is not.
    inside_a_function = {
        id(n)
        for scope in ast.walk(tree)
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for n in ast.walk(scope)
        if isinstance(n, ast.ImportFrom)
    }

    found: dict[str, bool] = {}
    for n in ast.walk(tree):
        if not (isinstance(n, ast.ImportFrom) and n.level and n.module):
            continue
        # level 1 is a sibling of this module; level 2 climbs out of its package
        target = f"{own}.{n.module}" if (n.level == 1 and own) else n.module
        # one target can be imported twice; a single body-level import is enough
        found[target] = found.get(target, True) and id(n) in inside_a_function
    return found


def cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Every distinct cycle, as a path that returns to where it started."""
    out: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def walk(node: str, path: list[str]) -> None:
        if node in path:
            ring = path[path.index(node):] + [node]
            key = tuple(sorted(set(ring)))
            if key not in seen:
                seen.add(key)
                out.append(ring)
            return
        for nxt in graph.get(node, []):
            walk(nxt, path + [node])

    for node in sorted(graph):
        walk(node, [])
    return out


def mermaid(graph: dict[str, dict[str, bool]]) -> str:
    """The graph as a Mermaid flowchart, one subgraph per package."""
    def node_id(name: str) -> str:
        return name.replace(".", "_")

    lines = ["flowchart LR"]
    for pkg in PACKAGES:
        members = sorted(m for m in graph if m.startswith(f"{pkg}."))
        if not members:
            continue
        lines.append(f"  subgraph {pkg}[{pkg}/]")
        for m in members:
            lines.append(f"    {node_id(m)}[{m.split('.', 1)[1]}]")
        lines.append("  end")
    for m in sorted(graph):
        if "." not in m:
            lines.append(f"  {node_id(m)}[[{m}]]")
    for src in sorted(graph):
        for dst, deferred in sorted(graph[src].items()):
            arrow = "-.->" if deferred else "-->"
            lines.append(f"  {node_id(src)} {arrow} {node_id(dst)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="write here instead of stdout")
    args = ap.parse_args()

    graph = {name: edges(name, path) for name, path in modules()}
    text = mermaid(graph)

    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text, end="")

    body_only = {k: [d for d, deferred in v.items() if not deferred]
                 for k, v in graph.items()}
    every = {k: list(v) for k, v in graph.items()}
    n_edges = sum(len(v) for v in graph.values())
    print(f"\n{len(graph)} modules, {n_edges} edges", file=sys.stderr)
    for label, g in (("counting every import", every),
                     ("counting body-level imports only", body_only)):
        found = cycles(g)
        print(f"cycles, {label}:", file=sys.stderr)
        for ring in found:
            print("    " + " -> ".join(ring), file=sys.stderr)
        if not found:
            print("    none", file=sys.stderr)


if __name__ == "__main__":
    main()
