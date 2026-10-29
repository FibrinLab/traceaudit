"""The ENABLE trace page copied as plain text (from a browser, a PDF or a chat): no `#` heading marks, tables with
tabs instead of pipes, the report JSON and the thinking without code fences. `normalise` rewrites that form into the
Markdown `enable_md.parse_markdown` reads, so a pasted page and the engine's .md file give the same ledger."""
from __future__ import annotations

import re

_PART_TITLES = ("available information", "model's own reasoning", "delivered report", "structured rationale",
                "discriminator ablation", "audit checks")
_PART = re.compile(r"^(\d)\.\s+(.+?)\s*$")
_SECTION = re.compile(r"^([A-Za-z][A-Za-z0-9 _/\-]*?)\s*\((\d+) facts?[^)]*\)\s*$")
_TABLE_HEAD = re.compile(r"^(ids|modality|diagnosis|criterion)(\t|\s{2,})")
_STATS_LINE = re.compile(r"^\d[\d,]* characters\.")
_H3_TITLES = {"key findings": "Key findings", "differential": "Differential", "who criteria, per diagnosis": "WHO criteria, per diagnosis",
              "reference criteria, per candidate": "Reference criteria, per candidate", "decision detail": "Decision detail"}


def looks_copied(text: str) -> bool:
    """True for a trace page without Markdown marks: numbered part titles present, no `## ` headings."""
    if re.search(r"^## \d+\.", text, re.M):
        return False
    hits = 0
    for m in _PART.finditer(text) if False else (m for line in text.splitlines() for m in [_PART.match(line)] if m):
        if any(m.group(2).lower().startswith(t) for t in _PART_TITLES):
            hits += 1
    return hits >= 2 and ("\t" in text or re.search(r"^ids\s{2,}field", text, re.M) is not None)


def _split_cells(line: str, sep: str) -> list[str]:
    return [c.strip() for c in (line.split("\t") if sep == "\t" else re.split(r"\s{2,}", line.strip()))]


def _table_lines(lines: list[str], i: int) -> tuple[list[str], int]:
    """Convert the tab (or wide-space) table starting at lines[i] into pipe rows; returns (rows, next index)."""
    sep = "\t" if "\t" in lines[i] else "  "
    header = _split_cells(lines[i], sep)
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    i += 1
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            break
        if sep == "\t" and "\t" not in line:
            break
        if sep != "\t" and not re.search(r"\s{2,}", line.strip()):
            break
        cells = _split_cells(line, sep)
        cells += [""] * (len(header) - len(cells))
        out.append("| " + " | ".join(cells[: len(header)]) + " |")
        i += 1
    return out, i


def _balanced_json(text: str, start: int) -> str | None:
    """The JSON object starting at text[start] == '{', tracking strings so braces inside them do not count."""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(text)):
        ch = text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:k + 1]
    return None


def _bold_after(line: str, label: str, stop: str = " ·") -> str:
    """`Decision: CLL/SLL · confidence` -> `Decision: **CLL/SLL** · confidence`."""
    i = line.find(label)
    if i < 0:
        return line
    j = i + len(label)
    rest = line[j:].lstrip()
    k = rest.find(stop)
    value = rest if k < 0 else rest[:k]
    tail = "" if k < 0 else rest[k:]
    if not value or value.startswith("**"):
        return line
    return line[:j] + " **" + value.strip() + "**" + tail


def _head(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if line.startswith("Case:"):
            line = re.sub(r"^Case:\s*(\S+)", lambda m: f"Case: `{m.group(1)}`", line)
            m = re.search(r"ground truth:\s*(.+?)(?:\s*\(|\s*·|$)", line)
            if m and not m.group(1).startswith("**"):
                line = line[: m.start(1)] + f"**{m.group(1).strip()}**" + line[m.end(1):]
        elif line.startswith("Model:"):
            line = re.sub(r"^Model:\s*([^·`]+?)(\s*·|$)", lambda m: f"Model: `{m.group(1).strip()}`{m.group(2)}", line)
        out.append(line)
    return out


def _part1(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    in_who = False
    while i < len(lines):
        line = lines[i]
        sm = _SECTION.match(line)
        if sm:
            name = sm.group(1).strip()
            in_who = name.lower().startswith(("who", "reference"))
            out.append(f"### {name} ({sm.group(2)} facts)")
            i += 1
            continue
        if _TABLE_HEAD.match(line):
            rows, i = _table_lines(lines, i)
            out += rows
            continue
        if in_who and line.strip() and not line.startswith(("|", "**")):
            # a candidate name on its own line, followed (after optional blank lines) by a table
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _TABLE_HEAD.match(lines[j]):
                out.append(f"**{line.strip()}**")
                i += 1
                continue
        out.append(line)
        i += 1
    return out


def _part2(lines: list[str]) -> list[str]:
    body = [ln for ln in lines]
    while body and not body[0].strip():
        body.pop(0)
    if body and _STATS_LINE.match(body[0]):
        body.pop(0)
    while body and not body[0].strip():
        body.pop(0)
    return ["", "```", *body, "```", ""]


def _part3(lines: list[str]) -> list[str]:
    text = "\n".join(lines)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("predicted_diagnosis raw:"):
            line = _bold_after(line, "predicted_diagnosis raw:")
            line = _bold_after(line, "delivered:")
            line = re.sub(r"failure_kind:\s*([^\s`·]+)", r"failure_kind: `\1`", line)
            out.append(line)
            i += 1
            continue
        if line.startswith("Removed by post-processing"):
            out.append(line)
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("Raw model JSON"):
                out.append("- " + lines[i].strip())
                i += 1
            continue
        if line.startswith("Raw model JSON"):
            start = text.find("{", sum(len(ln) + 1 for ln in lines[:i]))
            obj = _balanced_json(text, start) if start >= 0 else None
            if obj:
                out += ["", "```json", obj, "```", ""]
                consumed = text[:start + len(obj)].count("\n")
                i = consumed + 1
                continue
        out.append(line)
        i += 1
    return out


def _part4(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    in_who = False
    while i < len(lines):
        line = lines[i]
        low = line.strip().lower()
        if low.startswith("decision:") and "**" not in line:
            out.append(_bold_after(line, "Decision:"))
            i += 1
            continue
        if low in _H3_TITLES:
            in_who = low.startswith(("who criteria", "reference criteria"))
            out.append(f"### {_H3_TITLES[low]}")
            i += 1
            continue
        if low.startswith("arm b thinking"):
            body = lines[i + 1:]
            while body and not body[0].strip():
                body.pop(0)
            out += ["Arm B thinking (verbatim):", "```", *body, "```"]
            break
        if _TABLE_HEAD.match(line):
            rows, i = _table_lines(lines, i)
            out += rows
            continue
        if in_who and line.strip() and not line.startswith("|"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _TABLE_HEAD.match(lines[j]):
                name = re.sub(r"\s*\([^)]*\)\s*$", "", line.strip())
                out.append(f"**{name}**")
                i += 1
                continue
        for label in ("Discriminator:", "Unresolved:", "Would change the diagnosis:"):
            if line.strip().startswith(label):
                txt = line.strip()
                if label == "Discriminator:":
                    txt = re.sub(r"\s*\[([^\]]*)\]\s*$", lambda m: f" `[{m.group(1)}]`", txt)
                line = "- " + txt
                break
        out.append(line)
        i += 1
    return out


def _part5(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "delivered diagnosis without them:" in line and "**" not in line:
            line = _bold_after(line, "delivered diagnosis without them:", stop=" (was")
        if _TABLE_HEAD.match(line):
            rows, i = _table_lines(lines, i)
            out += rows
            continue
        out.append(line)
        i += 1
    return out


def normalise(text: str) -> str:
    """Rewrite a copied trace page as the engine's Markdown."""
    lines = text.replace("\r\n", "\n").split("\n")
    marks: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        m = _PART.match(line)
        if m and any(m.group(2).lower().startswith(t) for t in _PART_TITLES):
            marks.append((idx, m.group(1), m.group(2)))
    out = _head(lines[: marks[0][0]]) if marks else list(lines)
    for k, (idx, n, title) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        body = lines[idx + 1:end]
        out.append(f"## {n}. {title}")
        conv = {"1": _part1, "2": _part2, "3": _part3, "4": _part4, "5": _part5}.get(n)
        out += conv(body) if conv else body
    return "\n".join(out)
