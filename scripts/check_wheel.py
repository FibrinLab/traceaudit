"""Build a wheel and check it ships every package directory in the source tree.

Editable installs (pip install -e) read the source tree, so a subpackage left
out of the wheel only shows up in a container. The wheel is built from a clean
copy of the tree so a stale build/ directory cannot hide the gap.
Run: python scripts/check_wheel.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "traceaudit"


def source_packages() -> set[str]:
    return {str(p.parent.relative_to(ROOT)) for p in SRC.rglob("__init__.py") if "__pycache__" not in p.parts}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", ".git", "node_modules", "runs", "serve-data"))
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "--no-cache-dir", "-w", tmp, str(src)], check=True)
        whl = next(Path(tmp).glob("*.whl"))
        shipped = {str(Path(n).parent) for n in zipfile.ZipFile(whl).namelist() if n.endswith("__init__.py")}
    missing = sorted(source_packages() - shipped)
    if missing:
        print("packages missing from the wheel:", ", ".join(missing))
        return 1
    print(f"wheel ships all {len(shipped)} packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
