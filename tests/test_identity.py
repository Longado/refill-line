"""Identity as a phone line actually hears it.

Speech recognition hands over honorifics, accents, filler and the occasional wrong letter, and
callers say their birth date in words. The date carries the entropy here, so a name is allowed to
be off by one letter only when the date of birth matches exactly.
"""
import pytest

from refill_line import gate

P = gate.load_patients()
DOB = "March 14th, 1958"


@pytest.mark.parametrize("heard", [
    "Maria Lopez", "maria lopez", "Maria  Lopez",
    "Mrs. Maria Lopez", "Ms Maria Lopez", "Maria Lopez Jr",
    "María López",                      # accents from a name-aware transcript
    "this is Maria Lopez", "my name is Maria Lopez", "it's Maria Lopez",
    "Maria Lopes",                      # one letter wrong, date still exact
])
def test_the_caller_is_recognised(heard):
    assert gate.find_patient(P, heard, DOB)["id"] == "p1"


@pytest.mark.parametrize("heard", [
    "Maria", "Lopez",                   # half a name is not an identification
    "Marco Lopez", "Maria Carter",      # a different person on the same date
    "", "the pharmacy",
])
def test_a_stranger_is_not(heard):
    assert gate.find_patient(P, heard, DOB) is None


def test_one_wrong_letter_still_needs_the_right_date():
    assert gate.find_patient(P, "Maria Lopes", "March 15th, 1958") is None


@pytest.mark.parametrize("said,iso", [
    ("March fourteenth nineteen fifty eight", "1958-03-14"),
    ("march fourteen, nineteen fifty-eight", "1958-03-14"),
    ("the fourteenth of March nineteen fifty eight", "1958-03-14"),
    ("14th of March 1958", "1958-03-14"),
    ("November second, nineteen seventy one", "1971-11-02"),
    ("nineteen seventy one, november second", "1971-11-02"),
])
def test_dates_said_in_words(said, iso):
    assert gate.parse_dob(said) == iso


@pytest.mark.parametrize("said", ["March nineteen fifty eight", "the fourteenth of March", "nineteen fifty eight"])
def test_a_date_missing_a_part_is_not_a_date(said):
    assert gate.parse_dob(said) is None
