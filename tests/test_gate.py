"""Gate rules with a stubbed Jev. Probabilities here are made up per case, not copied from gate.py."""
import pytest

from refill_line import gate

PATIENTS = gate.load_patients()
MARIA = {"name": "maria  lopez", "date_of_birth": "1958-03-14"}


def stub(**probs):
    """Jev stub: every question defaults to a clear 'no' unless overridden; the caller named the drug by default."""
    probs = {"named_drug": 0.91, **probs}
    def jev(state, questions):
        return {k: {"noul": probs.get(k, 0.03)} for k in questions}
    return jev


def ask(jev, **req):
    return gate.decide({**MARIA, "request": "refill please", **req}, PATIENTS, jev)


def test_unknown_caller_is_asked_to_verify_and_jev_is_not_called():
    def boom(state, questions):
        raise AssertionError("Jev must not run before identity is verified")
    r = gate.decide({"name": "Maria Lopez", "date_of_birth": "1960-01-01", "request": "x"}, PATIENTS, boom)
    assert r["decision"] == "ask" and r["reason"] == "identity"


def test_one_clear_medication_with_refills_is_filled():
    r = ask(stub(may_mean_lisinopril_10=0.93))
    assert r["decision"] == "fill" and r["prescription"] == "lisinopril_10"


def test_two_plausible_medications_ask_which_one():
    r = ask(stub(may_mean_lisinopril_10=0.81, may_mean_hydralazine_25=0.77))
    assert r["decision"] == "ask" and r["reason"] == "which_medication"
    assert set(r["candidates"]) == {"lisinopril_10", "hydralazine_25"}


def test_unsure_band_asks_even_with_a_single_candidate():
    r = ask(stub(may_mean_lisinopril_10=0.52))
    assert r["decision"] == "ask" and r["candidates"] == ["lisinopril_10"]


def test_no_matching_medication_lists_what_is_on_file():
    r = ask(stub())
    assert r["decision"] == "ask" and r["reason"] == "not_on_file"
    assert "Atorvastatin" in r["say"]


def test_dose_change_is_declined_even_when_medication_is_clear():
    r = ask(stub(may_mean_hydroxyzine_25=0.97, dose_change=0.88))
    assert r["decision"] == "decline" and r["reason"] == "dose_change"


def test_unsure_dose_change_is_confirmed():
    r = ask(stub(may_mean_hydroxyzine_25=0.97, dose_change=0.45))
    assert r["decision"] == "ask" and r["reason"] == "confirm_same_dose"


def test_no_refills_left_is_declined_with_prescriber_request():
    r = ask(stub(may_mean_hydralazine_25=0.95))
    assert r["decision"] == "decline" and r["reason"] == "no_refills"
    assert "Dr. Chen" in r["say"]


def test_too_early_is_declined_with_the_eligible_day():
    # atorvastatin: 90-day supply filled 9 days ago
    r = ask(stub(may_mean_atorvastatin_20=0.9))
    assert r["decision"] == "decline" and r["reason"] == "too_early"
    assert r["eligible_in_days"] == 90 - 7 - 9


def test_advice_question_still_fills_but_flags_pharmacist_callback():
    r = ask(stub(may_mean_hydroxyzine_25=0.9, advice=0.95))
    assert r["decision"] == "fill" and r["pharmacist_callback"] is True


def test_advice_question_is_routed_even_when_refill_is_declined():
    r = ask(stub(may_mean_atorvastatin_20=0.9, advice=0.9))
    assert r["decision"] == "decline" and r["pharmacist_callback"] is True
    assert "pharmacist will call" in r["say"]


def test_description_only_is_confirmed_before_filling():
    r = ask(stub(may_mean_lisinopril_10=0.88, named_drug=0.12))
    assert r["decision"] == "ask" and r["reason"] == "confirm_medication"


def test_description_only_still_gets_a_decline_without_confirmation():
    r = ask(stub(may_mean_hydralazine_25=0.9, named_drug=0.2))
    assert r["decision"] == "decline" and r["reason"] == "no_refills"


def test_jev_failure_never_auto_fills():
    def down(state, questions):
        raise TimeoutError("jev timed out")
    r = ask(down)
    assert r["decision"] == "decline" and r["reason"] == "judge_unavailable"


@pytest.mark.parametrize("p,band", [(0.39, "no"), (0.4, "unsure"), (0.6, "unsure"), (0.61, "yes")])
def test_band_edges(p, band):
    assert gate.band(p) == band
