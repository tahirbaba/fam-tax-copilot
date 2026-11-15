from famcheck.evaluate import run


def test_golden_set_decisions_and_guardrails():
    rep = run(mode="replay")
    bad = [r for r in rep.rows if not r["ok"]]
    assert not bad, bad
    assert rep.decisions_total == 14
    assert rep.wrong_missed == 0          # no wrong value was ever auto-approved
    assert rep.wrong_caught >= 1          # the simulated misread (inv14) was caught
    assert rep.auto_precision == 1.0
