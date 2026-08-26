```text
redlining/
├─ pyproject.toml
├─ README.md
├─ DECISIONS.md
├─ BLOCK_MAP.svg
├─ CONTEXT.md            ← fix this first (Block 0)
│
├─ data/
│  ├─ schematic.json
│  └─ bands.csv          ← Block 3, advisor session
│
├─ src/redlining/
│  ├─ loader.py          ← Block 1
│  ├─ position.py        ← Block 2
│  ├─ checklist.py       ← Block 3
│  ├─ normalise.py       ← Block 4
│  ├─ adjudicate.py      ← Block 6
│  ├─ session.py         ← Block 7
│  └─ report.py          ← Block 8
│
├─ tests/                ← one file per module
│
├─ experiments/
│  └─ block05_asr/       ← recordings + error rate
│
└─ runs/                 ← output, gitignored
```
