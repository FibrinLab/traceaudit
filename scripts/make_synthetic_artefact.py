"""Write tests/fixtures/synthetic_trace_SYN-003.md from tests/synthetic_artefact.py (run after changing the builder)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from synthetic_artefact import artefact_text  # noqa: E402

out = ROOT / "tests" / "fixtures" / "synthetic_trace_SYN-003.md"
out.write_text(artefact_text(), encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size} bytes)")
