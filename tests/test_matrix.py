import pytest

from qrt.matrix import AUDIT_NAMES, build_auc, build_matrix


def case(row, lab, reject, score=0.0, audit="delay"):
    audits = {a: {"reject": False, "score": 0.0, "value": 0.0} for a in AUDIT_NAMES}
    audits[audit] = {"reject": reject, "score": score, "value": score}
    return {"row": row, "label": lab, "audits": audits}


def cell(matrix, row, audit):
    return next(m for m in matrix if m["row"] == row and m["audit"] == audit)


def test_catch_and_false_alarm_rates():
    cases = ([case("a", "FAKE", True)] * 3 + [case("a", "FAKE", False)] +
             [case("a", "REAL", True)] + [case("a", "REAL", False)] * 3 +
             [case("a", "MARGINAL", True)] * 5 + [case("a", "FAKE", None)] * 2)
    m = cell(build_matrix(cases), "a", "delay")
    assert (m["n_fake"], m["caught"], m["catch_rate"]) == (4, 3, 0.75)
    assert (m["n_real"], m["false_alarms"], m["false_alarm_rate"]) == (4, 1, 0.25)
    assert m["n_marginal"] == 5 and m["n_not_applicable"] == 2
    assert m["catch_lo"] < 0.75 < m["catch_hi"]
    assert m["tier"] == 3


def test_auc_pools_real_claims_across_rows():
    cases = ([case("fake_row", "FAKE", True, score=-1.0)] * 4 +
             [case("real_row", "REAL", False, score=+1.0)] * 4)
    auc = {(r["row"], r["audit"]): r["auc"] for r in build_auc(cases)}
    assert auc[("fake_row", "delay")] == pytest.approx(1.0)
