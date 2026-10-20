"""Domain packs. A domain is a lexicon (plus optional case generator and sample data).

The engine never imports a domain; it loads whichever lexicon it is given. `haematology` is the
reference domain the tool was built on. Add your own as a lexicon file (see docs/bring-your-own-domain.md).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent


def available() -> dict[str, Path]:
    """name -> lexicon path for every packaged domain."""
    out = {}
    for d in sorted(ROOT.iterdir()):
        if d.is_dir() and (d / "lexicon.json").exists():
            out[d.name] = d / "lexicon.json"
    return out


def lexicon_path(name: str = "haematology") -> Path:
    try:
        return available()[name]
    except KeyError as e:
        raise ValueError(f"unknown domain {name!r}; packaged: {sorted(available())}") from e


def sample_paths(name: str = "haematology") -> tuple[Path | None, Path | None]:
    d = ROOT / name
    c, p = d / "sample_cases.jsonl", d / "sample_perturbations.jsonl"
    return (c if c.exists() else None, p if p.exists() else None)
