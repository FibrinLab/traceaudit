"""Domain-free synthetic ledger cases for validating the ledger probes (spec 19 §validation).

Five candidates K1..K5 over five table fields f1..f5: candidate i expects f_i positive (essential), f_{i+1} positive
(desirable) and f_{i+2} negative (essential), indices mod 5. A case whose truth is K_i carries facts consistent with
that row, plus untabled fields, untested facts and numeric context, so decisive edits (one flip to the neighbour),
anchor loss (untest the desirable field), neutral edits and authority cues all exist for every case.
"""
from __future__ import annotations

import random

from .ledger import Fact, LedgerCase

CANDIDATES = ["K1", "K2", "K3", "K4", "K5"]
TABLE_FIELDS = ["f1", "f2", "f3", "f4", "f5"]
EXTRA_FIELDS = ["g1", "g2", "g3", "g4"]


def expectation_rows(candidates: list[str] = CANDIDATES, fields: list[str] = TABLE_FIELDS) -> list[dict]:
    rows = []
    n = len(fields)
    for i, cand in enumerate(candidates):
        rows.append({"candidate": cand, "criterion": f"{fields[i]} positive", "strength": "essential", "reference_ids": [f"w_{i + 1}"],
                     "expect": [{"field": fields[i], "value": "pos"}]})
        rows.append({"candidate": cand, "criterion": f"{fields[(i + 1) % n]} positive", "strength": "desirable", "reference_ids": [f"w_{i + 1}"],
                     "expect": [{"field": fields[(i + 1) % n], "value": "pos"}]})
        rows.append({"candidate": cand, "criterion": f"{fields[(i + 2) % n]} negative", "strength": "essential", "reference_ids": [f"w_{i + 1}"],
                     "expect": [{"field": fields[(i + 2) % n], "value": "neg"}]})
    return rows


def make_case(case_id: str, truth_index: int, rng: random.Random, candidates: list[str] = CANDIDATES, fields: list[str] = TABLE_FIELDS) -> LedgerCase:
    n = len(fields)
    truth = candidates[truth_index]
    pos = {fields[truth_index], fields[(truth_index + 1) % n]}
    facts: list[Fact] = []
    pid = 0
    for sec, flds in (("panel", fields), ("extras", EXTRA_FIELDS)):
        for fld in flds:
            pid += 1
            if fld in fields:
                val = "Positive" if fld in pos else "Negative"
            else:
                val = rng.choice(["Positive", "Negative", "Not performed"])
            ev = "" if val == "Not performed" else f"{fld} {val.lower()}"
            facts.append(Fact(f"p_{pid}", "patient", sec, fld, val, ev))
    pid += 1
    facts.append(Fact(f"p_{pid}", "patient", "extras", "h1", "Not performed", ""))
    facts.append(Fact("c_1", "context", "measurements", "count", str(rng.randint(10, 200)), ""))
    facts.append(Fact("c_2", "context", "measurements", "flag", rng.choice(["Present", "Absent"]), ""))
    for i, cand in enumerate(candidates):
        facts.append(Fact(f"w_{i + 1}", "who", cand, "definition",
                          f"{cand} is defined by {fields[i]} positive with {fields[(i + 2) % n]} negative; {fields[(i + 1) % n]} positive is desirable.", "", cand))
    case = LedgerCase(case_id, truth, list(candidates), facts, {f.id for f in facts},
                      {"criteria": expectation_rows(candidates, fields), "source_format": "synthetic", "review": {"status": "approved"}})
    return case


def generate_set(per_candidate: int = 2, seed: int = 0) -> list[LedgerCase]:
    rng = random.Random(seed)
    out = []
    k = 0
    for i, _ in enumerate(CANDIDATES):
        for _ in range(per_candidate):
            k += 1
            out.append(make_case(f"SYN-{k:03d}", i, rng))
    return out
