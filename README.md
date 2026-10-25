# trial-match

Which recruiting clinical trials could this patient join, and why?

trial-match searches ClinicalTrials.gov for recruiting trials near a patient, splits each trial's free-text eligibility criteria into single criteria, and judges every criterion against the patient's facts. Each verdict names the facts it relied on, and a second model from a different provider re-judges every decisive verdict. Where they disagree, the criterion becomes a question for the clinician instead of a guess.

The output is a ranked list per patient: **likely eligible**, **possible** (nothing rules the patient out, but some criteria need an answer), or **not eligible** (with the criterion that rules them out), plus the nearest recruiting site and its distance.

The patients in `patients/` are synthetic. This is a research demonstration, not a clinical tool.

## How a decision is made

| Step | By | What happens |
|---|---|---|
| Search | code | Recruiting trials within a radius of the patient (ClinicalTrials.gov API v2, `filter.geo`), closest first |
| Parse | code | Eligibility text split into numbered criteria (`I1…` inclusion, `E1…` exclusion); handles bullets, numbered lists, nested items and loose paragraphs |
| Structured limits | code | Age and sex checked against the registry's own fields |
| Administrative items | code | Consent, pregnancy and "other protocol-defined criteria" shown as *at screening*, never judged by a model |
| Judge | first model | Every other criterion: met / not met / unknown (or applies / does not apply for exclusions), with the patient facts it used |
| Ground | code | A decisive verdict with no cited fact, or a fact that does not exist, becomes *unknown* |
| Check | second model | Every decisive verdict re-judged independently; disagreement becomes *disputed* |
| Decide | code | Any agreed blocker means not eligible; open or disputed criteria mean possible; otherwise likely |

Two rules from real registry texts:

- **Cohort-specific criteria** ("For AGA-negative NSCLC only: …", "Cohort 1B: …") rule a patient out of that cohort, not out of the trial. Failing one turns it into a question.
- **Bundled criteria** count as met only if every part is met.

The decision rules are plain code, so they can be changed and re-applied to saved model answers without calling a model again (`python -m trialmatch site`).

## Run it

Python 3.10 or newer, standard library only. Two model keys from different providers; the defaults use Groq's free tier for both, with models from different developers.

```bash
export GROQ_API_KEY=...
python -m trialmatch run --patient patients/a-egfr-ex19-post-osimertinib.json
open out/index.html
```

Options: `--condition`, `--term` (a gene or drug), `--radius` in km (default 600), `--limit` (how many of the closest trials to match, default 12), `--writer` and `--checker` as `provider:model` (`groq`, `gemini`, `openai`, `anthropic`, `ollama`).

Results are cached per patient and trial, keyed by the trial's criteria, the patient's facts, both models and the prompt. A run that hits a provider's daily limit stops cleanly (exit code 3) and the next run continues.

## Tests

```bash
python -m unittest discover -s tests
```

The parser tests use formats taken from real registry entries.

## Limits

- The registry's eligibility text is all there is to go on; trial protocols often contain more.
- Criteria that depend on information the profile does not contain stay *unknown*, by design. Better profiles give fewer open questions.
- Cohort detection is pattern-based and will miss unusual phrasings.
- A model can misread a criterion in a way both models share. The criterion text, the cited facts and the reason are always shown so a person can check.

Trial data: ClinicalTrials.gov, U.S. National Library of Medicine.
