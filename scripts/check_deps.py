"""Fail if traceaudit imports anything outside the standard library at runtime (TRE constraint)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "traceaudit"
STDLIB = set(sys.stdlib_module_names)  # Python 3.10+
ALLOWED_LOCAL = {"traceaudit"}


def main() -> int:
    bad = []
    for path in ROOT.rglob("*.py"):
        if "tools" in path.parts or "build_lexicon" in path.name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for n in names:
                if n not in STDLIB and n not in ALLOWED_LOCAL:
                    bad.append(f"{path.relative_to(ROOT.parent)}:{node.lineno}: {n}")
    for b in bad:
        print(b)
    print("ok: standard library only" if not bad else f"{len(bad)} non-stdlib import(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
