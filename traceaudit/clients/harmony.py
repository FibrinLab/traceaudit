"""Harmony channel parsing for gpt-oss raw output (spec 07 §3)."""
from __future__ import annotations

import re

_CHANNEL = re.compile(
    r"<\|channel\|>(?P<ch>analysis|commentary|final)(?P<meta>(?: to=[^<\s]*)?(?:<\|constrain\|>[^<]*)?)<\|message\|>"
    r"(?P<body>.*?)(?=<\|end\|>|<\|return\|>|<\|call\|>|<\|start\|>|$)",
    re.DOTALL,
)
_CONTROL = re.compile(r"<\|[a-z_]+\|>")


def parse_harmony(text: str) -> tuple[str, str, list[str]]:
    """Return (reasoning, answer, warnings). Reasoning = analysis (+commentary) channels verbatim; answer = last final."""
    warnings: list[str] = []
    if not text:
        return "", "", ["EMPTY"]
    analysis: list[str] = []
    commentary: list[str] = []
    finals: list[str] = []
    last_end = 0
    stray = False
    for m in _CHANNEL.finditer(text):
        start_tok = text.rfind("<|start|>", last_end, m.start())
        seg_start = start_tok if start_tok != -1 else m.start()
        between = _CONTROL.sub("", text[last_end:seg_start]).replace("assistant", "").strip()
        if between:
            stray = True
        body = m.group("body")
        ch = m.group("ch")
        if ch == "analysis":
            analysis.append(body)
        elif ch == "commentary":
            commentary.append(body)
        else:
            finals.append(body)
        last_end = m.end()
    if not analysis and not finals and not commentary:
        return "", _CONTROL.sub("", text), ["NO_CHANNELS"]
    tail = _CONTROL.sub("", text[last_end:]).strip()
    if tail:
        stray = True
    if len(analysis) > 1:
        warnings.append("MULTI_ANALYSIS")
    reasoning = "\n\n".join(analysis)
    if commentary:
        warnings.append("COMMENTARY_PRESENT")
        reasoning = reasoning + ("\n\n" if reasoning else "") + "\n\n".join("[commentary]\n" + c for c in commentary)
    if not finals:
        warnings.append("NO_FINAL")
    answer = finals[-1] if finals else ""
    if stray:
        warnings.append("STRAY_TEXT")
    return reasoning, answer, warnings
