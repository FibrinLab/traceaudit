"""Importers turn pipeline artefacts into the fact ledger (traceaudit.ledger)."""
from __future__ import annotations

from pathlib import Path

from .. import ledger
from .enable_md import parse_markdown, render_artefact


def load(path: str | Path) -> tuple[ledger.LedgerCase, ledger.LedgerTrace]:
    text = Path(path).read_text(encoding="utf-8")
    return parse_markdown(text)


__all__ = ["load", "parse_markdown", "render_artefact"]
