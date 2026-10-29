"""Deterministic assertion extraction (spec 03)."""
from __future__ import annotations

import re
from collections import defaultdict

from . import lexicon as lex_mod
from .lexicon import Lexicon, MarkerToken
from .schema import Assertion, Case
from .textutil import normalise, split_sentences


class PolarityConflict(ValueError):
    pass


_CLAUSE_BOUNDARY = re.compile(r";|:|\n|→|=>|->|(?<![eig])\.\s+(?=[a-z])|\bbut\b|\bwhereas\b|\bwhile\b|\bhowever\b|\balthough\b|\bexcept\b")

_SUFFIX = re.compile(
    r"""^\s?(?:
        (?P<hyph>-(?:positive|negative|pos|neg|expressing))(?![a-z])
      | (?P<sym>\+\+|\+/-|\(\+/-\)|\(\+\)|\(-\)|\+)
      | (?P<word>positive|negative|pos|neg|positivity|negativity|dim|bright|weak|weakly|partial|partially|strong|strongly|
                 moderate|absent|present|expressed|lost|retained|heterogeneous|undetectable)(?![a-z])
    )
    (?:\s?(?P<int1>dim|bright|weak|partial|strong|moderate|heterogeneous|subset))?
    (?:\s?\((?P<paren>[a-z\-\s/%\d.]+)\))?
    """,
    re.X,
)
_SUFFIX_PAREN_ONLY = re.compile(r"^\s?\((?P<paren>dim|weak|bright|strong|moderate|partial|heterogeneous|subset)\)")
_BARE_MINUS = re.compile(r"^\s?-(?=\s|[,;./)\-]|$)")  # "cyclin D1-" followed by a dash (normalised em dash) is still a bare minus
_RUN_BREAK = re.compile(r"\b(?:with|plus|together|as well as|alongside|showing|including)\b")
_LAB_KINDS = {"immunophenotype", "cytogenetic", "molecular"}
_LIST_WORDS = {"positive", "negative", "pos", "neg", "positivity", "negativity", "expressed", "absent", "present", "lost", "retained", "undetectable"}

_PRE = re.compile(
    r"""(?:^|[\s,;:(])(?:
      (?P<neg>negative\s+for|neg\s+for|negativity\s+for|no\s+evidence\s+of|no\s+expression\s+of|absence\s+of|absent|
               lack\s+of|lacks|lacking|lack|loss\s+of|without|not\s+expressed|fails?\s+to\s+express|did\s+not\s+express|
               does\s+not\s+express|do\s+not\s+express|no|not|negative|lacked)
    | (?P<pos>positive\s+for|pos\s+for|positivity\s+for|expression\s+of|co-?expression\s+of|over-?expression\s+of|
              expresses|expressing|express|expressed|shows?|showing|showed|demonstrates?|demonstrated|demonstrating|
              harbou?rs|harbou?red|carries|carrying|detected|identified|with|has|have|had|having|positive|presence\s+of|
              staining\s+for|reactivity\s+for|immunoreactive\s+for|aberrant|co-?expresses|co-?expressing|exhibits?|displays?)
    )
    (?:\s+(?:the|a|an|following|markers?|antigens?|for|of|strong|bright|dim|weak|partial|moderate|variable|heterogeneous|
            nuclear|cytoplasmic|aberrant|diffuse|focal|uniform|both|all|also|only|clearly|typical|characteristic))*
    \s*:?\s*$""",
    re.X,
)

_POST = re.compile(
    r"""^\s*\)?\s*(?:\([^()]*\)\s*)?(?:expression|staining|positivity|immunoreactivity|mutation|variant|rearrangement|deletion|
              translocation|fusion|status|protein)?\s*(?:\([^()]*\)\s*)?
    (?:is|are|was|were|being|remains?|remained)?\s*
    (?:(?:also|both|all|still|clearly|strongly|weakly|dimly|brightly)\s+)*
    (?:
      (?P<neg>not\s+(?:(?:also|clearly|strongly|weakly|dimly|brightly)\s+)?
               (?:expressed|detected|identified|seen|present|demonstrated|found|positive|mutated|rearranged|observed|noted|
                  confirmed|retained|preserved|co-?expressed|over-?expressed)|
               absent|negative|lost|excluded|wild[- ]?type|unmutated|undetectable|lacking|non-?rearranged|germline)
    | (?P<pos>expressed|detected|identified|seen|present|positive|retained|preserved|mutated|rearranged|over-?expressed|
              demonstrated|confirmed|noted|observed|found|co-?expressed)
    )(?![a-z])""",
    re.X,
)
_NOUN_POS = re.compile(r"^\s*(?:expression|positivity|co-?expression|over-?expression|staining|immunoreactivity)(?![a-z])")
_NOUN_NEG = re.compile(r"^\s*(?:negativity|loss|absence)(?![a-z])")

_GAP = re.compile(
    r"""^\s*\)?\s*(?:,|/|;|&|\+|,?\s*and|,?\s*or|,?\s*plus|,?\s*with|,?\s*as\s+well\s+as|,?\s*together\s+with)?
        \s*(?:\((?:dim|bright|weak|partial|moderate|strong|subset|variable|heterogeneous|[\d%.\s]+)\))?\s*,?\s*
        (?:(?:dim|weak|bright|strong|partial|moderate|aberrant|variable|heterogeneous|and|or)\s+)*\(?\s*$""",
    re.X,
)

_NUMBER = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)")
_INTENSITY_WINDOW = 45

_FISH_CTX = re.compile(r"\b(fish|rearrang|translocat|fusion|break-?apart|karyotyp|cytogenetic|t\(|del\(|deletion|17p|probe)")
_IHC_CTX = re.compile(r"\b(ihc|immunohisto|stain|express|nuclear|protein|immunoreactiv|positive|negative)")
_MUT_CTX = re.compile(r"\b(mutat|variant|sequenc|ngs|vaf|wild|allele|exon|codon|p\.|c\.)")


def extract_assertions(text: str, lexicon: Lexicon | None = None, report: str | None = None) -> list[Assertion]:
    lx = lexicon or lex_mod.load()
    if not text:
        return []
    norm = normalise(text)
    sentences = split_sentences(text)
    masked = bytearray(len(text))
    out: list[Assertion] = []
    # entity names take precedence over finding aliases they contain ("monoclonal B-cell lymphocytosis")
    entity_spans = [(m.start, m.end) for m in lx.find_entities(text)]

    def mask(a: int, b: int) -> None:
        for i in range(a, b):
            masked[i] = 1

    def is_masked(a: int, b: int) -> bool:
        return any(masked[a:b])

    def sentence_of(pos: int) -> tuple[int, int]:
        for s, e in sentences:
            if s <= pos < e:
                return s, e
        return 0, len(text)

    def clause_of(pos: int, end_pos: int) -> tuple[int, int]:
        s, e = sentence_of(pos)
        cs = s
        for m in _CLAUSE_BOUNDARY.finditer(norm, s, pos):
            cs = m.end()
        ce = e
        m2 = _CLAUSE_BOUNDARY.search(norm, end_pos, e)
        if m2:
            ce = m2.start()
        return cs, ce

    for es, ee in entity_spans:
        mask(es, ee)

    # 1. phrase pass
    for fid, pol, s, e, ph in lx.phrase_matches(text):
        if is_masked(s, e):
            continue
        warnings: tuple[str, ...] = ()
        if pol == "pos":
            cs, _ = clause_of(s, e)
            before = norm[cs:s].rstrip()
            if re.search(r"(?:^|\s)(?:no|without|not|absence\s+of|lack\s+of|negative\s+for|excludes?|exclude)\s*$", before):
                pol = "neg"
                warnings = ("PHRASE_NEGATED",)
        out.append(Assertion(fid, pol, s, e, text[s:e], s, e, "phrase", None, warnings, report))
        mask(s, e)

    # 2. numeric pass
    for fid, f in lx.findings.items():
        rule = f.get("numeric_rule")
        if not rule:
            continue
        anchors = [(a, False) for a in rule["anchors"]] + [(a, True) for a in rule.get("fallback_anchors", [])]
        unit_pat = rule.get("unit_pattern") or ""
        unit_re = re.compile(unit_pat, re.IGNORECASE) if unit_pat and unit_pat != "%" else None
        for anchor, fallback in anchors:
            for m in lex_mod._alias_regex(anchor).finditer(text):
                if is_masked(m.start(), m.end()):
                    continue
                window_end = min(len(text), m.end() + 80)
                window = norm[m.end():window_end]
                found = None
                for nm in _NUMBER.finditer(window):
                    after = window[nm.end():nm.end() + 16]
                    if unit_pat == "%":
                        if not after.lstrip().startswith("%"):
                            continue
                    elif unit_re is not None:
                        if not unit_re.search(after):
                            continue
                    found = nm
                    break
                if not found:
                    continue
                value = float(found.group(1))
                thr = float(rule["threshold"])
                comp = rule["comparator"]
                ok = {">=": value >= thr, ">": value > thr, "<": value < thr, "<=": value <= thr}[comp]
                pol = "pos" if ok else "neg"
                ns = m.end() + found.start(1)
                ne = m.end() + found.end(1)
                w = ("FALLBACK_ANCHOR",) if fallback else ()
                out.append(Assertion(fid, pol, m.start(), m.end(), text[m.start():ne], ns, ne, "numeric", None, w, report))
                mask(m.start(), ne)

    # 3. alias pass
    tokens = [t for t in lx.marker_tokens(text) if not is_masked(t.start, t.end)]
    tokens = [_disambiguate(t, norm, sentence_of(t.start), lx) for t in tokens]

    resolved: list[dict] = []
    for t in tokens:
        info = {"tok": t, "pol": None, "rule": "none", "cue": (t.end, t.end), "int": None, "warn": []}
        f = lx.findings[t.finding_id]
        after = norm[t.end:]
        m = _SUFFIX.match(after)
        mp = _SUFFIX_PAREN_ONLY.match(after)
        if m:
            kind = "hyph" if m.group("hyph") else "sym" if m.group("sym") else "word"
            raw = (m.group(kind) or "").lstrip("-")
            inten = m.group("int1") or _intensity_word(m.group("paren") or "", lx) or (raw if raw in lx.polarity["intensity_pos"] else None)
            pol = _polarity_of_cue(raw, lx)
            info.update(pol=pol, rule="suffix", cue=(t.end, t.end + m.end()), int=inten)
            # a polarity *word* after the last member of a list scopes over the whole list (spec 03 §1 rules 2-3)
            if kind in ("word", "hyph") and raw in _LIST_WORDS:
                info["list_word"] = True
        elif mp:
            info.update(pol="pos", rule="suffix", cue=(t.end, t.end + mp.end()), int=mp.group("paren"))
        else:
            bm = _BARE_MINUS.match(after)
            if bm:
                info.update(pol="neg", rule="suffix", cue=(t.end, t.end + bm.end()))
        resolved.append(info)

    # lists
    lists: list[list[int]] = []
    for i, info in enumerate(resolved):
        if lists:
            prev = resolved[lists[-1][-1]]
            ps, pe = sentence_of(prev["tok"].start)
            same_sentence = ps <= info["tok"].start < pe
            gap = norm[prev["cue"][1]:info["tok"].start]
            if same_sentence and _GAP.match(gap) and not _CLAUSE_BOUNDARY.search(gap):
                lists[-1].append(i)
                continue
        lists.append([i])

    for lst in lists:
        first, last = resolved[lst[0]], resolved[lst[-1]]
        cs, ce = clause_of(first["tok"].start, last["cue"][1])
        pre_text = norm[cs:first["tok"].start]
        post_text = norm[last["cue"][1]:ce]
        list_pol = None
        list_rule = None
        list_cue = None
        pm = _PRE.search(pre_text)
        if not pm:
            # a preceding phrase assertion joined by a list separator ("No splenomegaly or lymphadenopathy")
            ss, _ = sentence_of(first["tok"].start)
            for pa in out:
                if pa.rule == "phrase" and pa.polarity and ss <= pa.start and pa.end <= first["tok"].start \
                        and lx.findings[pa.finding_id]["kind"] == lx.findings[first["tok"].finding_id]["kind"] \
                        and _GAP.match(norm[pa.end:first["tok"].start]) and not _CLAUSE_BOUNDARY.search(norm[pa.end:first["tok"].start]):
                    list_pol, list_rule, list_cue = pa.polarity, "pre", (pa.start, pa.end)
        if pm:
            list_pol = "neg" if pm.group("neg") else "pos"
            list_rule = "pre"
            cue_start = cs + pm.start() + (1 if pm.group(0)[:1] in " ,;:(" else 0)
            list_cue = (cue_start, cs + pm.end())
        else:
            qm = _POST.match(post_text)
            if qm:
                list_pol = "neg" if qm.group("neg") else "pos"
                list_rule = "post"
                list_cue = (last["cue"][1], last["cue"][1] + qm.end())
            elif _NOUN_POS.match(post_text):
                nm = _NOUN_POS.match(post_text)
                list_pol, list_rule = "pos", "noun"
                list_cue = (last["cue"][1], last["cue"][1] + nm.end())
            elif _NOUN_NEG.match(post_text):
                nm = _NOUN_NEG.match(post_text)
                list_pol, list_rule = "neg", "noun"
                list_cue = (last["cue"][1], last["cue"][1] + nm.end())
        seen_or = False
        for k, i in enumerate(lst):
            info = resolved[i]
            if list_rule == "pre" and list_pol == "neg" and k:
                # a negative pre-cue stops at an "or"-closed pair followed by a comma, and at a plus/with joiner:
                # "no cyclin D1 or t(11;14), del13q" and "no t(11;14), plus del13q and smudge cells" leave del13q alone
                gap = norm[resolved[lst[k - 1]]["cue"][1]:info["tok"].start]
                if _RUN_BREAK.search(gap) or (seen_or and "," in gap):
                    break
                if re.search(r"\bor\b", gap):
                    seen_or = True
            if list_rule == "pre" and info["pol"] is not None and info["pol"] != list_pol:
                break  # a pre-cue's scope ends at a member with its own opposite suffix: "negative CD79b and FMC7, LEF1+, cyclin D1 ..."
            if info["pol"] is None and list_pol is not None:
                info.update(pol=list_pol, rule=list_rule, cue=list_cue)
                # intensity adjective immediately before the token inside the list
                pre_adj = re.search(r"(dim|weak|bright|strong|partial|moderate|aberrant)\s*$", norm[max(cs, info["tok"].start - 12):info["tok"].start])
                if pre_adj:
                    info["int"] = pre_adj.group(1)

    for lst in lists:
        if len(lst) > 1:
            # "CD11c/CD25/CD103 positivity, splenomegaly": a polarity word consumed as one member's suffix scopes over the
            # unresolved members before it (spec 03 §1 rules 2-3); members after it start a new run
            pending: list[tuple[int, bool]] = []  # (member index, joined only by tight "and"/"/" since it was added)
            for k, i in enumerate(lst):
                info = resolved[i]
                gap = norm[resolved[lst[k - 1]]["cue"][1]:info["tok"].start] if k else ""
                if k and _RUN_BREAK.search(gap):
                    pending = []  # "MYD88 L265P with CD5/CD10 negativity": the word before "with" is not part of the run
                if k and "," in gap:
                    pending = [(j, False) for j, _ in pending]
                if info["pol"] is None:
                    pending.append((i, True))
                elif info.get("list_word"):
                    kind = lx.findings[info["tok"].finding_id]["kind"]
                    for j, tight in pending:
                        jk = lx.findings[resolved[j]["tok"].finding_id]["kind"]
                        # same kind always; across lab kinds only when tightly joined ("cyclin D1 and t(11;14) negative");
                        # never into morphology/clinical ("3% prolymphocytes and CD38 positivity")
                        if jk == kind or (tight and jk in _LAB_KINDS and kind in _LAB_KINDS):
                            resolved[j].update(pol=info["pol"], rule="suffix", cue=info["cue"])
                    pending = []
                else:
                    pending = []

    for info in resolved:
        t: MarkerToken = info["tok"]
        f = lx.findings[t.finding_id]
        if f.get("intensity"):
            # intensity-coded: polarity from intensity vocabulary only
            cs, ce = clause_of(t.start, info["cue"][1])
            win_a = max(cs, t.start - _INTENSITY_WINDOW)
            win_b = min(ce, info["cue"][1] + _INTENSITY_WINDOW)
            word = None
            hit = _nearest_intensity(norm, win_a, win_b, t.start, lx)
            if hit:
                word = hit[0]
                info["cue"] = (hit[1], hit[2])
            if word in lx.polarity["intensity_dim"]:
                info.update(pol="pos", rule=info["rule"] if info["rule"] != "none" else "intensity", int=word)
            elif word in lx.polarity["intensity_bright"]:
                info.update(pol="neg", rule=info["rule"] if info["rule"] != "none" else "intensity", int=word)
            else:
                info.update(pol=None, rule="none", cue=(t.end, t.end))
        elif info["pol"] is None and f.get("default_polarity"):
            info.update(pol=f["default_polarity"], rule="default")
        cue_s, cue_e = info["cue"]
        s0, e0 = min(t.start, cue_s), max(t.end, cue_e)
        out.append(Assertion(t.finding_id, info["pol"], t.start, t.end, text[s0:e0], cue_s, cue_e,
                             info["rule"], info["int"], tuple(info["warn"]), report))

    out.sort(key=lambda a: a.start)
    return _flag_conflicts(out, sentences)


def _flag_conflicts(assertions: list[Assertion], sentences: list[tuple[int, int]]) -> list[Assertion]:
    by_sent: dict[tuple[int, str], set[str]] = defaultdict(set)

    def sid(pos: int) -> int:
        for i, (s, e) in enumerate(sentences):
            if s <= pos < e:
                return i
        return -1

    for a in assertions:
        if a.polarity:
            by_sent[(sid(a.start), a.finding_id)].add(a.polarity)
    out = []
    for a in assertions:
        if a.polarity and len(by_sent[(sid(a.start), a.finding_id)]) > 1:
            out.append(Assertion(a.finding_id, a.polarity, a.start, a.end, a.surface, a.cue_start, a.cue_end, a.rule,
                                 a.intensity, a.warnings + ("CONFLICT",), a.report))
        else:
            out.append(a)
    return out


def _polarity_of_cue(raw: str, lx: Lexicon) -> str | None:
    raw = raw.strip()
    if raw in ("+", "++", "(+)", "+/-", "(+/-)") or raw in ("positive", "pos", "positivity", "present", "expressed", "retained", "expressing"):
        return "pos"
    if raw in ("-", "(-)") or raw in ("negative", "neg", "negativity", "absent", "lost", "undetectable"):
        return "neg"
    if raw in lx.polarity["intensity_pos"]:
        return "pos"
    return None


def _intensity_word(s: str, lx: Lexicon) -> str | None:
    for w in s.replace("/", " ").split():
        w = w.strip(",")
        if w in lx.polarity["intensity_pos"] or w in lx.polarity["intensity_dim"] or w in lx.polarity["intensity_bright"]:
            return w
    return None


def _nearest_intensity(norm: str, a: int, b: int, pos: int, lx: Lexicon) -> tuple[str, int, int] | None:
    words = sorted(set(lx.polarity["intensity_dim"] + lx.polarity["intensity_bright"]), key=len, reverse=True)
    best = None
    for w in words:
        for m in re.finditer(r"(?<![a-z])" + re.escape(w) + r"(?![a-z\-])", norm[a:b]):
            d = abs(a + m.start() - pos)
            if best is None or d < best[0]:
                best = (d, w, a + m.start(), a + m.end())
    return (best[1], best[2], best[3]) if best else None


def _disambiguate(t: MarkerToken, norm: str, sent: tuple[int, int], lx: Lexicon) -> MarkerToken:
    s, e = sent
    ctx = norm[s:e]
    alias = t.alias.lower()
    fid = t.finding_id
    if fid == "t_14_18_BCL2" and alias.startswith("t(14;18)") and "malt1" in ctx and "bcl2" not in ctx and "bcl-2" not in ctx:
        fid = "t_14_18_MALT1"
    elif fid == "cyclin_D1" and alias == "ccnd1":
        if _FISH_CTX.search(ctx) and not _IHC_CTX.search(ctx):
            fid = "t_11_14"
    elif fid == "BCL2" and alias in ("bcl2", "bcl-2"):
        if _FISH_CTX.search(ctx) and not _IHC_CTX.search(ctx):
            fid = "t_14_18_BCL2"
    elif fid == "TP53_mut" and alias == "tp53":
        if _FISH_CTX.search(ctx) and not _MUT_CTX.search(ctx):
            fid = "del_17p"
    if fid != t.finding_id:
        return MarkerToken(fid, t.start, t.end, t.text, t.alias)
    return t


def findings(text: str, lexicon: Lexicon | None = None) -> dict[str, str]:
    """Reduce assertions to finding -> polarity; raise PolarityConflict on disagreement anywhere in the text."""
    result: dict[str, str] = {}
    for a in extract_assertions(text, lexicon):
        if a.polarity is None:
            continue
        if a.finding_id in result and result[a.finding_id] != a.polarity:
            raise PolarityConflict(f"{a.finding_id}: both pos and neg asserted (at {a.start}: {a.surface!r})")
        result[a.finding_id] = a.polarity
    return result


def finding_spans(case: Case, lexicon: Lexicon | None = None) -> dict[str, list[dict]]:
    """finding -> [{report, start, end, polarity, surface}] with offsets into Case.reports[report]."""
    out: dict[str, list[dict]] = defaultdict(list)
    for key, body in case.reports.items():
        if not body:
            continue
        for a in extract_assertions(body, lexicon, report=key):
            if a.polarity is None:
                continue
            out[a.finding_id].append({"report": key, "start": a.start, "end": a.end, "cue_start": a.cue_start,
                                      "cue_end": a.cue_end, "polarity": a.polarity, "surface": a.surface, "rule": a.rule})
    return dict(out)


def mentions(text: str, finding_ids: list[str], lexicon: Lexicon | None = None) -> list[tuple[str, int, int]]:
    """(finding_id, start, end) for any alias occurrence of the given findings (polarity not required)."""
    lx = lexicon or lex_mod.load()
    out = []
    for fid in finding_ids:
        for sp in lx.mentions_marker(text, fid):
            out.append((fid, sp.start, sp.end))
    return sorted(out, key=lambda x: x[1])
