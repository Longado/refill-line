"""Refill gate: Jev answers the fuzzy questions, code owns identity, counting and dates.

Every Jev answer is a probability. Between UNSURE_LOW and UNSURE_HIGH the agent does not
guess: it asks the caller. Jev cannot count or compare dates, so refills and timing stay in code.
"""
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

UNSURE_LOW, UNSURE_HIGH = 0.4, 0.6  # design choice borrowed from renhua/jev_lint; evals/golden.jsonl checks it
REFILL_WINDOW_DAYS = 7  # demo policy: a refill is allowed once 7 or fewer days of supply remain
DATA = Path(__file__).with_name("patients.json")


def load_patients(path: Path = DATA) -> list[dict]:
    return json.loads(path.read_text())["patients"]


def band(p: float) -> str:
    if p < UNSURE_LOW:
        return "no"
    return "yes" if p > UNSURE_HIGH else "unsure"


HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "doctor", "mister"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
LEAD_INS = ("this is", "my name is", "it is", "its", "i am", "im", "speaking")


def _norm(s: str) -> str:
    """What a transcript hands over, reduced to the name itself: accents folded, honorifics,
    suffixes and spoken lead-ins dropped."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))   # López -> lopez, not lo pez
    s = re.sub(r"['’]", "", s)                             # it's -> its, so the lead-in is one word
    s = re.sub(r"[^a-z]+", " ", s).strip()
    for lead in LEAD_INS:
        if s.startswith(lead + " "):
            s = s[len(lead) + 1:]
    words = [w for w in s.split() if w not in HONORIFICS and w not in SUFFIXES]
    return " ".join(words)


def _one_letter_apart(a: str, b: str) -> bool:
    """True when b is a with at most one letter substituted, inserted or dropped."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long = sorted((a, b), key=len)
    i = next((n for n, (x, y) in enumerate(zip(short, long)) if x != y), len(short))
    return short[i:] == long[i + 1:]


MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
MONTHS |= {m[:3]: i for m, i in MONTHS.items()}
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
       "seventeen eighteen nineteen".split()
ORDINALS = "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth " \
           "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth".split()
TENS = {"twenty": 20, "thirty": 30}
TENS_ORD = {"twentieth": 20, "thirtieth": 30}


def _digits(s: str) -> str:
    """Spoken numbers to digits: 'march fourteenth nineteen fifty eight' -> 'march 14 1958'."""
    if re.search(r"\d[-/]\d", s):   # 1958-03-14 and 3/14/1958 are already digits; leave them whole
        return s
    words, out = s.replace("-", " ").split(), []
    i = 0
    while i < len(words):
        w = words[i]
        if w in ("nineteen", "twenty") and i + 1 < len(words):  # a year said as two halves
            rest = words[i + 1]
            tens = TENS.get(rest) or ({"forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                                       "eighty": 80, "ninety": 90}).get(rest)
            if tens is not None:
                ones = ONES.index(words[i + 2]) if i + 2 < len(words) and words[i + 2] in ONES[:10] else 0
                century = 1900 if w == "nineteen" else 2000
                out.append(str(century + tens + ones))
                i += 3 if ones else 2
                continue
        if w in TENS or w in TENS_ORD:  # 'twenty second'
            base = TENS.get(w) or TENS_ORD[w]
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if nxt in ORDINALS[:10] or nxt in ONES[:10]:
                out.append(str(base + (ORDINALS.index(nxt) if nxt in ORDINALS else ONES.index(nxt))))
                i += 2
                continue
            out.append(str(base))
        elif w in ORDINALS:
            out.append(str(ORDINALS.index(w)))
        elif w in ONES:
            out.append(str(ONES.index(w)))
        else:
            out.append(w)
        i += 1
    return " ".join(out)


def parse_dob(said: str) -> str | None:
    """A spoken or written date -> YYYY-MM-DD, or None when it isn't one whole day.

    The agent passes the caller's words through untouched: a model asked to format the date
    in a tool argument stops replying at all (bisected against the live API, 2026-09-24)."""
    s = re.sub(r"[.,]", " ", (said or "").strip().lower())
    s = re.sub(r"\b(the|of|on)\b", " ", s)
    s = _digits(re.sub(r"\s+", " ", s).strip())
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    patterns = [
        (r"^(\d{4})-(\d{1,2})-(\d{1,2})$", ("y", "m", "d")),
        (r"^([a-z]+)\s+(\d{1,2})\s+(\d{4})$", ("mon", "d", "y")),
        (r"^(\d{1,2})\s+([a-z]+)\s+(\d{4})$", ("d", "mon", "y")),
        (r"^(\d{4})\s+([a-z]+)\s+(\d{1,2})$", ("y", "mon", "d")),  # 'nineteen fifty eight, march fourteen'
        (r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", ("m", "d", "y")),  # US order, the demo's locale
    ]
    for pattern, fields in patterns:
        hit = re.match(pattern, s)
        if not hit:
            continue
        parts = dict(zip(fields, hit.groups()))
        month = MONTHS.get(parts["mon"][:3]) if "mon" in parts else int(parts["m"])
        if month is None:
            return None
        try:
            return date(int(parts["y"]), month, int(parts["d"])).isoformat()
        except ValueError:  # 13th month, 40th day
            return None
    return None


def find_patient(patients: list[dict], name: str, dob: str) -> dict | None:
    """Both parts must be given. The date carries the entropy, so when it matches exactly a
    surname may be one letter off — speech recognition mishears names, and a caller who has
    already given the right birth date should not be turned away over a letter."""
    iso = parse_dob(dob)
    heard = _norm(name).split()
    if not iso or len(heard) < 2:
        return None
    for p in patients:
        on_file = _norm(p["name"]).split()
        if p["date_of_birth"] != iso or heard[0] != on_file[0]:
            continue
        if heard[1:] == on_file[1:] or _one_letter_apart(" ".join(heard[1:]), " ".join(on_file[1:])):
            return p
    return None


def label(rx: dict) -> str:
    return f"{rx['drug']} {rx['strength']}"


def questions(patient: dict) -> dict:
    """One noul per prescription (not one choice): a choice spreads mass onto 'none' when two drugs fit
    the same description, independent yes/no keeps both candidates visible (probe 9-19)."""
    qs = {
        f"may_mean_{rx['id']}": {
            "type": "noul",
            "instructions": {"what": f"Could the medicine the caller is talking about be {rx['drug']} ({rx['strength']}, for {rx['for']})? "
                                     "Their words came from speech recognition and may be misheard or misspelled. "
                                     "Answer yes if their words could reasonably refer to this medicine, even if another one fits too.",
                             "not_for": "What they want done with the medicine (refill, questions, dose changes) does not matter here, only which medicine it is."},
            "criteria": {"true": "could be this medicine", "false": "is not this medicine"},
        }
        for rx in patient["prescriptions"]
    }
    qs["named_drug"] = {
        "type": "noul",
        "instructions": {"what": "Did the caller say the name of a medicine (possibly misheard, like 'hydro zine'), "
                                 "rather than only describing it by purpose, color, shape or time of day?",
                         "not_for": "Descriptions such as 'my blood pressure pill' or 'the one I take at night' are not names."},
        "criteria": {"true": "said a medicine name", "false": "only described the medicine"},
    }
    qs["dose_change"] = {
        "type": "noul",
        "instructions": {"what": "Is the caller asking for a different strength, a larger quantity per fill, or more frequent dosing "
                                 "than the prescription on file?",
                         "not_for": "Ordinary refill wording such as 'more of my pills', 'running low' or 'a refill' is not a change."},
        "criteria": {"true": "asks to change the prescription", "false": "wants the same prescription refilled"},
    }
    qs["advice"] = {
        "type": "noul",
        "instructions": "Besides the refill, is the caller asking for medical advice, such as whether to take, stop, combine, or adjust a medicine?",
        "criteria": {"true": "asks for medical advice", "false": "only asks for a refill"},
    }
    return qs


def _state(patient: dict, req: dict) -> dict:
    return {
        "caller_said": req.get("request", ""),
        "medication_as_heard": req.get("medication", ""),
        "prescriptions_on_file": [f"{label(rx)}, {rx['directions']}, for {rx['for']}" for rx in patient["prescriptions"]],
    }


def _or(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def decide(req: dict, patients: list[dict], jev) -> dict:
    """req: name, date_of_birth (YYYY-MM-DD), medication (as heard), request (caller's words).
    jev(state, questions) -> {question: {"noul": p}}; any exception means Jev is unavailable."""
    patient = find_patient(patients, req.get("name", ""), req.get("date_of_birth", ""))
    if not patient:
        return {"decision": "ask", "reason": "identity",
                "say": "I couldn't match that name and date of birth. Could you spell your last name and give your date of birth again?"}

    try:
        answers = jev(_state(patient, req), questions(patient))
        probs = {k: float(answers[k]["noul"]) for k in questions(patient)}
    except Exception as e:  # any failure: never auto-fill without the judge
        return {"decision": "decline", "reason": "judge_unavailable", "error": str(e),
                "say": "I can't process this refill automatically right now. A pharmacist will call you back today."}

    rxs = {rx["id"]: rx for rx in patient["prescriptions"]}
    bands = {rid: band(probs[f"may_mean_{rid}"]) for rid in rxs}
    yes = [rid for rid, b in bands.items() if b == "yes"]
    unsure = [rid for rid, b in bands.items() if b == "unsure"]
    base = {"patient": patient["id"], "probabilities": probs}

    if not yes and not unsure:
        on_file = _or([label(rx) for rx in rxs.values()])
        return {**base, "decision": "ask", "reason": "not_on_file",
                "say": f"I don't see that on your profile. The prescriptions I have are {on_file}. Which one would you like?"}
    if len(yes) != 1 or unsure:
        cands = yes + unsure
        return {**base, "decision": "ask", "reason": "which_medication", "candidates": cands,
                "say": f"Just to be sure: did you mean {_or([label(rxs[c]) for c in cands])}?"}

    rx = rxs[yes[0]]
    base["prescription"] = rx["id"]
    r = _matched(base, patient, rx, probs)
    if band(probs["advice"]) != "no":  # any outcome: the question goes to a human, never answered here
        r = {**r, "pharmacist_callback": True,
             "say": r["say"] + " I can't give medical advice, so a pharmacist will call you about your question."}
    return r


def _matched(base: dict, patient: dict, rx: dict, probs: dict) -> dict:
    dose = band(probs["dose_change"])
    if dose == "yes":
        return {**base, "decision": "decline", "reason": "dose_change",
                "say": f"I can't change the dose over the phone. I'll ask {patient['prescriber']} to review it. "
                       f"Would you like your current {label(rx)} refilled in the meantime?"}
    if dose == "unsure":
        return {**base, "decision": "ask", "reason": "confirm_same_dose",
                "say": f"Is that the same {label(rx)}, {rx['directions']}, as before?"}

    if rx["refills_left"] <= 0:
        return {**base, "decision": "decline", "reason": "no_refills",
                "say": f"There are no refills left on {label(rx)}. I'll send a renewal request to {patient['prescriber']}."}
    wait = rx["days_supply"] - REFILL_WINDOW_DAYS - rx["last_fill_days_ago"]
    if wait > 0:
        return {**base, "decision": "decline", "reason": "too_early", "eligible_in_days": wait,
                "say": f"{label(rx)} was filled {rx['last_fill_days_ago']} days ago, so it's too early. You can refill it in {wait} days."}

    if band(probs["named_drug"]) != "yes":  # nothing is dispensed on a description alone
        return {**base, "decision": "ask", "reason": "confirm_medication",
                "say": f"Just to confirm, that's your {label(rx)}, {rx['directions']}?"}
    return {**base, "decision": "fill", "reason": "ok", "pharmacist_callback": False,
            "say": f"Done. Your {label(rx)} will be ready for pickup after 4 pm today."}
