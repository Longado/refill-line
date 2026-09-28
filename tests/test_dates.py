"""Spoken dates arrive as the caller said them; code turns them into a date, never the model.

(Asking the agent's model to format the date in the tool argument makes it stop replying
altogether — bisected against the live API on 2026-09-24, see runs/live_call.log.)
"""
import pytest

from refill_line import gate


@pytest.mark.parametrize("said", [
    "1958-03-14",
    "March 14th, 1958",
    "March 14 1958",
    "14 March 1958",
    "3/14/1958",
    "03-14-1958",
    "  march 14th, 1958  ",
])
def test_spoken_dates_land_on_the_same_day(said):
    assert gate.parse_dob(said) == "1958-03-14"


@pytest.mark.parametrize("said", ["", "sometime in the fifties", "March 1958", "14/03/1958x", "2026-13-40"])
def test_unparseable_dates_return_none(said):
    assert gate.parse_dob(said) is None


def test_identity_matches_on_a_spoken_date():
    patients = gate.load_patients()
    assert gate.find_patient(patients, "Maria Lopez", "March 14th, 1958")["id"] == "p1"


def test_identity_still_rejects_the_wrong_day():
    patients = gate.load_patients()
    assert gate.find_patient(patients, "Maria Lopez", "March 15th, 1958") is None
