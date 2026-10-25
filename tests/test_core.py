import unittest

from trialmatch import criteria
from trialmatch.ctgov import Site, Trial, km, nearest_site, parse_age
from trialmatch.match import _grounded, outcome, structured_checks
from trialmatch.patient import Patient

PATIENT = Patient(id="p", label="P", age=61, sex="FEMALE", lat=47.5596, lon=7.5886, city="Basel",
                  facts=["Stage IV NSCLC.", "EGFR exon 19 deletion.", "ECOG 1."])


def trial(**kw):
    base = dict(nct="NCT0", title="t", phases=[], conditions=[], interventions=[], sponsor="",
                min_age=18, max_age=None, sex="ALL", criteria_text="")
    base.update(kw)
    return Trial(**base)


class ParseCriteria(unittest.TestCase):
    def test_bullets_with_headers(self):
        text = ("Inclusion Criteria:\n\n* Stage IV NSCLC.\n* EGFR mutation.\n\n"
                "Exclusion Criteria:\n\n* Leptomeningeal metastases.\n")
        cs = criteria.parse(text)
        self.assertEqual([(c.id, c.kind) for c in cs], [("I1", "inclusion"), ("I2", "inclusion"), ("E1", "exclusion")])

    def test_numbered_list(self):
        text = "Inclusion Criteria:\n\n1. Age >= 18\n2. ECOG 0 or 1\n10. Normal swallowing\n"
        self.assertEqual([c.text for c in criteria.parse(text)], ["Age >= 18", "ECOG 0 or 1", "Normal swallowing"])

    def test_nested_items_join_their_parent(self):
        text = ("Inclusion Criteria:\n\n* Adequate organ function:\n\n  * ANC >= 1.5 x 10^9/L\n"
                "  * Platelets >= 75 x 10^9/L\n* ECOG <= 1\n")
        cs = criteria.parse(text)
        self.assertEqual(len(cs), 2)
        self.assertIn("Platelets", cs[0].text)

    def test_loose_paragraph_continues_criterion(self):
        text = "Inclusion Criteria:\n\n* Adequate labs obtained within 14 days:\nNo transfusion in 14 days.\n* ECOG 1\n"
        cs = criteria.parse(text)
        self.assertEqual(len(cs), 2)
        self.assertIn("No transfusion", cs[0].text)

    def test_markdown_escapes_and_symbols(self):
        cs = criteria.parse("Inclusion Criteria:\n\n* Creatinine \\<1.5 x ULN and clearance \\>45 mL/min, age ≥ 18\n")
        self.assertEqual(cs[0].text, "Creatinine <1.5 x ULN and clearance >45 mL/min, age >= 18")

    def test_no_headers_means_inclusion(self):
        self.assertEqual(criteria.parse("* Stage IV disease\n")[0].kind, "inclusion")

    def test_administrative_only_without_clinical_content(self):
        consent = criteria.Criterion("I1", "inclusion", "Signed written informed consent.")
        mixed = criteria.Criterion("I2", "inclusion", "Creatinine clearance > 45 mL/min; adequate contraception.")
        self.assertTrue(criteria.is_administrative(consent))
        self.assertFalse(criteria.is_administrative(mixed))


class Registry(unittest.TestCase):
    def test_parse_age(self):
        self.assertEqual(parse_age("18 Years"), 18)
        self.assertEqual(parse_age("6 Months"), 0.5)
        self.assertIsNone(parse_age(None))
        self.assertIsNone(parse_age("N/A"))

    def test_distance_basel_zurich(self):
        self.assertAlmostEqual(km((47.5596, 7.5886), (47.3769, 8.5417)), 74, delta=3)

    def test_nearest_recruiting_site(self):
        t = trial(sites=[Site("Far", "Rome", "Italy", "RECRUITING", 41.9, 12.5),
                         Site("Closed", "Basel", "Switzerland", "COMPLETED", 47.56, 7.59),
                         Site("Near", "Bern", "Switzerland", "RECRUITING", 46.95, 7.45)])
        site, d = nearest_site(t, PATIENT.point)
        self.assertEqual(site.facility, "Near")
        self.assertLess(d, 80)


class Decisions(unittest.TestCase):
    def test_age_and_sex_by_code(self):
        rows = structured_checks(trial(min_age=18, max_age=60, sex="MALE"), PATIENT)
        self.assertEqual({r["id"]: r["answer"] for r in rows}, {"AGE-MIN": "met", "AGE-MAX": "not_met", "SEX": "not_met"})

    def test_verdict_without_facts_is_unknown(self):
        c = criteria.Criterion("I1", "inclusion", "ECOG 0-1")
        self.assertEqual(_grounded({"answer": "met", "facts": []}, c, PATIENT)["answer"], "unknown")
        self.assertEqual(_grounded({"answer": "met", "facts": ["F99"]}, c, PATIENT)["answer"], "unknown")
        self.assertEqual(_grounded({"answer": "met", "facts": ["F4"]}, c, PATIENT)["answer"], "met")

    def test_answer_must_fit_the_criterion_kind(self):
        c = criteria.Criterion("E1", "exclusion", "Brain metastases")
        self.assertEqual(_grounded({"answer": "met", "facts": ["F2"]}, c, PATIENT)["answer"], "unknown")

    def test_outcome_rules(self):
        clean = [{"id": "I1", "kind": "inclusion", "answer": "met"}, {"id": "E1", "kind": "exclusion", "answer": "does_not_apply"}]
        self.assertEqual(outcome(clean)["status"], "likely")
        self.assertEqual(outcome(clean + [{"id": "I2", "kind": "inclusion", "answer": "disputed"}])["status"], "possible")
        self.assertEqual(outcome(clean + [{"id": "E2", "kind": "exclusion", "answer": "applies"}])["status"], "not_eligible")
        screening = clean + [{"id": "I3", "kind": "inclusion", "answer": "screening"}]
        self.assertEqual(outcome(screening)["judged"], 2)

    def test_cohort_specific_failure_is_a_question_not_a_blocker(self):
        rows = [{"id": "I1", "kind": "inclusion", "answer": "met"},
                {"id": "I7", "kind": "inclusion", "answer": "not_met", "conditional": True}]
        o = outcome(rows)
        self.assertEqual((o["status"], o["blockers"], o["open"]), ("possible", [], ["I7"]))

    def test_conditional_detection(self):
        yes = ["for AGA-negative NSCLC only: no actionable alterations", "Cohort 1B: no prior therapy",
               "For patients with brain metastases: stable for 4 weeks", "Part A (dose escalation): ECOG 0-2"]
        no = ["ECOG 0-1", "Formalin-fixed tumour tissue available", "Documented EGFR mutation"]
        for t in yes:
            self.assertTrue(criteria.is_conditional(criteria.Criterion("I1", "inclusion", t)), t)
        for t in no:
            self.assertFalse(criteria.is_conditional(criteria.Criterion("I1", "inclusion", t)), t)


if __name__ == "__main__":
    unittest.main()
