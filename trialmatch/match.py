"""Matching one patient to one trial, criterion by criterion.

1. Code checks the structured limits (age, sex) and drops administrative items.
2. A first model judges every remaining criterion against the patient's
   numbered facts and must name the facts it relied on.
3. Code rejects any verdict that cites no fact, or a fact that does not exist.
4. A second model, from a different provider, re-judges every decisive verdict
   without seeing the first one. Disagreement turns the verdict into a question.
5. Code decides the outcome from the verdicts that both agree on.
"""

from __future__ import annotations

import json

from .criteria import Criterion, is_administrative, parse
from .ctgov import Trial, nearest_site
from .llm import Model
from .patient import Patient

JUDGE_SYSTEM = """You screen patients for clinical trials. You receive a patient's facts, numbered F1, F2 ...,
and a trial's eligibility criteria, numbered I1 ... (inclusion) and E1 ... (exclusion).

For each criterion answer:
  inclusion criteria: "met", "not_met" or "unknown"
  exclusion criteria: "applies" (the patient is excluded by it), "does_not_apply" or "unknown"
Answer "unknown" whenever the facts do not settle it. Never assume a fact that is not listed.
For every answer other than "unknown", list the fact numbers you relied on, e.g. ["F3", "F5"].
If one criterion bundles several requirements, it is "met" only if every part is met.
Add a short reason in plain words (under 20 words).

Reply with JSON only:
{"verdicts": [{"id": "I1", "answer": "...", "facts": ["F.."], "reason": "..."}]}"""

DECISIVE = {"met", "not_met", "applies", "does_not_apply"}


def structured_checks(trial: Trial, patient: Patient) -> list[dict]:
    """Age and sex limits from the registry's own fields. No model involved."""
    out = []
    if trial.min_age is not None:
        ok = patient.age >= trial.min_age
        out.append({"id": "AGE-MIN", "kind": "inclusion", "text": f"Age at least {trial.min_age:g} years",
                    "answer": "met" if ok else "not_met", "by": "code", "facts": ["F1"]})
    if trial.max_age is not None:
        ok = patient.age <= trial.max_age
        out.append({"id": "AGE-MAX", "kind": "inclusion", "text": f"Age at most {trial.max_age:g} years",
                    "answer": "met" if ok else "not_met", "by": "code", "facts": ["F1"]})
    if trial.sex in ("FEMALE", "MALE"):
        ok = patient.sex == trial.sex
        out.append({"id": "SEX", "kind": "inclusion", "text": f"Sex: {trial.sex.lower()}",
                    "answer": "met" if ok else "not_met", "by": "code", "facts": ["F1"]})
    return out


def _ask(model: Model, patient: Patient, crits: list[Criterion]) -> dict[str, dict]:
    listing = "\n".join(f"{c.id} ({c.kind}). {c.text}" for c in crits)
    raw = model.complete_json(JUDGE_SYSTEM, f"Patient facts:\n{patient.numbered_facts()}\n\nCriteria:\n{listing}")
    return {str(v.get("id", "")).strip().upper(): v for v in raw.get("verdicts", []) if isinstance(v, dict)}


def _grounded(v: dict | None, c: Criterion, patient: Patient) -> dict:
    """A verdict counts only if it is a valid answer for its kind and cites real facts."""
    allowed = {"inclusion": {"met", "not_met", "unknown"}, "exclusion": {"applies", "does_not_apply", "unknown"}}[c.kind]
    if not v:
        return {"answer": "unknown", "facts": [], "reason": "No answer for this criterion.", "grounded": False}
    answer = str(v.get("answer", "unknown")).strip().lower().replace(" ", "_")
    facts = [str(f).strip().upper() for f in (v.get("facts") or []) if patient.fact(f)]
    reason = str(v.get("reason", "")).strip()
    if answer not in allowed:
        return {"answer": "unknown", "facts": [], "reason": f"Invalid answer '{answer}'.", "grounded": False}
    if answer != "unknown" and not facts:
        # A decisive answer must point at the patient's facts, or it is a guess.
        return {"answer": "unknown", "facts": [], "reason": "Answer cited no patient fact.", "grounded": False}
    return {"answer": answer, "facts": facts, "reason": reason, "grounded": True}


def match(trial: Trial, patient: Patient, writer: Model, checker: Model) -> dict:
    crits = parse(trial.criteria_text)
    judged = [c for c in crits if not is_administrative(c)]
    rows = structured_checks(trial, patient)

    first = _ask(writer, patient, judged) if judged else {}
    decisive = [c for c in judged if _grounded(first.get(c.id), c, patient)["answer"] in DECISIVE]
    second = _ask(checker, patient, decisive) if decisive else {}

    for c in crits:
        if is_administrative(c):
            rows.append({"id": c.id, "kind": c.kind, "text": c.text, "answer": "screening",
                         "by": "code", "facts": [], "reason": "Confirmed at screening (consent, pregnancy or protocol)."})
            continue
        a = _grounded(first.get(c.id), c, patient)
        row = {"id": c.id, "kind": c.kind, "text": c.text, "answer": a["answer"], "facts": a["facts"],
               "reason": a["reason"], "by": "writer"}
        if a["answer"] in DECISIVE:
            b = _grounded(second.get(c.id), c, patient)
            row["checker"] = b["answer"]
            if b["answer"] == a["answer"]:
                row["by"] = "both"
            else:
                row.update(answer="disputed", by="disputed",
                           reason=f"Writer said {a['answer'].replace('_', ' ')}, checker said "
                                  f"{b['answer'].replace('_', ' ')}. {a['reason']}")
        rows.append(row)

    site, distance = nearest_site(trial, patient.point)
    return {"trial": trial.to_dict(), "rows": rows, "outcome": outcome(rows),
            "nearest_site": site.__dict__ if site else None, "distance_km": distance,
            "writer": writer.name, "checker": checker.name}


def outcome(rows: list[dict]) -> dict:
    """Plain rules on the verdicts, so the result can be explained line by line."""
    blockers = [r for r in rows if (r["kind"] == "inclusion" and r["answer"] == "not_met")
                or (r["kind"] == "exclusion" and r["answer"] == "applies")]
    open_q = [r for r in rows if r["answer"] in ("unknown", "disputed")]
    clear = [r for r in rows if r["answer"] in ("met", "does_not_apply")]
    judged = [r for r in rows if r["answer"] != "screening"]
    if blockers:
        status = "not_eligible"
    elif open_q:
        status = "possible"
    else:
        status = "likely"
    return {"status": status, "blockers": [r["id"] for r in blockers], "open": [r["id"] for r in open_q],
            "cleared": len(clear), "judged": len(judged),
            "coverage": round(len(clear) / len(judged), 2) if judged else 0.0}


def rank_key(result: dict):
    order = {"likely": 0, "possible": 1, "not_eligible": 2}
    o = result["outcome"]
    return (order[o["status"]], len(o["open"]), -(o["coverage"]), result["distance_km"] or 1e9)


def to_json(results: list[dict]) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False)
