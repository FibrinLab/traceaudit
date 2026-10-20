import pytest

from traceaudit.grounding import parse_answer

CASES = [
    ("Integrated diagnosis: Mantle cell lymphoma\nConfidence: high", "MCL", False),
    ("Integrated diagnosis: indeterminate between CLL and MCL", "CLL_SLL", True),
    ("This is most consistent with CLL/SLL. The differential includes MCL.", "CLL_SLL", True),
    ("Integrated diagnosis: ?MCL", "MCL", True),
    ("Overall I think this is splenic marginal zone lymphoma, though LPL cannot be excluded.", "MZL", True),
    ("Integrated diagnosis: Hairy cell leukaemia\nDifferential: SBLPN was considered and excluded.", "HCL", False),
    ("Integrated diagnosis: Follicular lymphoma, probable", "FL", True),
    ("No diagnosis can be made.", "UNRESOLVED", False),
    ("**Integrated diagnosis:** Waldenström macroglobulinaemia", "LPL", False),
]


@pytest.mark.parametrize("text,entity,hedged", CASES)
def test_parse(lx, text, entity, hedged):
    p = parse_answer(text, lx)
    assert p.entity == entity
    assert p.hedged is hedged


def test_subtype(lx):
    assert parse_answer("Integrated diagnosis: Waldenström macroglobulinaemia", lx).subtype == "WM"
