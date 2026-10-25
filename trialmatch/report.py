"""HTML pages: one per patient, plus an index of patients."""

from __future__ import annotations

from html import escape

STATUS = {
    "likely": ("Likely eligible", "Every judged criterion is met, confirmed by both models."),
    "possible": ("Possible", "Nothing rules the patient out, but some criteria need an answer."),
    "not_eligible": ("Not eligible", "At least one criterion rules the patient out."),
}
ANSWER = {
    "met": ("Met", "ok"), "does_not_apply": ("Does not apply", "ok"),
    "not_met": ("Not met", "no"), "applies": ("Applies, excludes", "no"),
    "unknown": ("Unknown", "open"), "disputed": ("Models disagree", "dispute"),
    "screening": ("At screening", "screen"),
}
BY = {"both": "both models", "code": "code", "writer": "first model only", "disputed": "models disagree"}


def _e(x) -> str:
    return escape("" if x is None else str(x))


def _phase(phases: list[str]) -> str:
    return ", ".join(p.replace("PHASE", "Phase ").replace("EARLY_", "Early ").replace("NA", "n/a") for p in phases) or "Phase not given"


def _facts_ref(facts: list[str], patient: dict) -> str:
    out = []
    for f in facts:
        n = int(f[1:])
        text = f"Age {patient['age']:g}, {patient['sex'].lower()}." if n == 1 else patient["facts"][n - 2]
        out.append(f'<abbr title="{_e(text)}">{_e(f)}</abbr>')
    return " ".join(out)


def _strip(rows: list[dict], key: str) -> str:
    cells = "".join(
        f'<a class="sq {ANSWER[r["answer"]][1]}" href="#{key}-{_e(r["id"])}" '
        f'title="{_e(r["id"])}: {_e(ANSWER[r["answer"]][0])}"><span class="sr">{_e(r["id"])} {_e(ANSWER[r["answer"]][0])}</span></a>'
        for r in rows)
    return f'<div class="strip" role="list" aria-label="Criteria, one square each">{cells}</div>'


def _trial(r: dict, patient: dict, i: int) -> str:
    t, o, key = r["trial"], r["outcome"], f"t{i}"
    label, _ = STATUS[o["status"]]
    site = r.get("nearest_site")
    where = (f'{_e(site["city"])}, {_e(site["country"])}, {r["distance_km"]} km' if site else "No recruiting site with location")
    by_id = {x["id"]: x for x in r["rows"]}
    blockers = "".join(f'<li><b>{_e(b)}</b> {_e(by_id[b]["text"])}<span class="why">{_e(by_id[b].get("reason", ""))}</span></li>'
                       for b in o["blockers"])
    questions = "".join(f'<li><b>{_e(q)}</b> {_e(by_id[q]["text"])}<span class="why">{_e(by_id[q].get("reason", ""))}</span></li>'
                        for q in o["open"])
    rows = "".join(
        f'<tr id="{key}-{_e(x["id"])}" class="{ANSWER[x["answer"]][1]}"><th scope="row">{_e(x["id"])}</th>'
        f'<td>{_e(x["text"])}</td><td class="ans"><span class="pill {ANSWER[x["answer"]][1]}">{_e(ANSWER[x["answer"]][0])}</span>'
        f'<span class="by">{_e(BY.get(x["by"], x["by"]))}</span></td>'
        f'<td class="facts">{_facts_ref(x.get("facts", []), patient)}</td><td class="reason">{_e(x.get("reason", ""))}</td></tr>'
        for x in r["rows"])
    detail = ""
    if blockers:
        detail += f'<div class="callout no"><h4>Rules the patient out</h4><ul>{blockers}</ul></div>'
    if questions:
        detail += f'<div class="callout open"><h4>To clarify before referral</h4><ul>{questions}</ul></div>'
    return f"""
<details class="trial {o['status']}" id="{key}">
  <summary>
    <span class="status">{_e(label)}</span>
    <span class="title">{_e(t['title'])}</span>
    <span class="meta">{_e(t['nct'])} · {_e(_phase(t['phases']))} · {_e(t['sponsor'])}</span>
    <span class="meta where">Nearest recruiting site: {where}</span>
    {_strip(r['rows'], key)}
    <span class="meta">{o['cleared']} of {o['judged']} judged criteria cleared{f", {len(o['open'])} open" if o['open'] else ""}</span>
  </summary>
  <div class="body">
    {detail}
    <div class="table-wrap"><table>
      <thead><tr><th scope="col">Criterion</th><th scope="col">Text from the registry</th><th scope="col">Verdict</th><th scope="col">Patient facts</th><th scope="col">Reason</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
    <p class="src"><a href="{_e(t['url'])}">Full record on ClinicalTrials.gov</a></p>
  </div>
</details>"""


def page(run: dict) -> str:
    p, q, results = run["patient"], run["query"], run["results"]
    counts = {k: sum(1 for r in results if r["outcome"]["status"] == k) for k in STATUS}
    facts = "".join(f"<li><b>F{i}</b> {_e(f)}</li>" for i, f in
                    enumerate([f"Age {p['age']:g}, {p['sex'].lower()}, lives in {p['city']}."] + p["facts"], start=1))
    trials = "".join(_trial(r, p, i) for i, r in enumerate(results))
    incomplete = ("" if run["complete"] else
                  f'<p class="note warn">This run stopped early ({_e(run.get("stopped") or "not all trials were matched")}). '
                  'The next run continues from the cache.</p>')
    a = run["audit"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>{_e(p['label'])}: trial matches</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap">
<style>{CSS}</style></head><body>
<p class="banner">Synthetic patient. A research demonstration, not medical advice: trial details come from ClinicalTrials.gov and must be confirmed with the trial team.</p>
<header class="wrap top">
  <p class="crumb"><a href="index.html">trial-match</a></p>
  <h1>{_e(p['label'])}</h1>
  <p class="lede">Recruiting trials for <b>{_e(q['condition'])}</b>{f" mentioning <b>{_e(q['term'])}</b>" if q['term'] else ""} within {q['radius_km']} km of {_e(p['city'])}:
    {q['found']} found, the {len(results)} closest matched criterion by criterion.</p>
  <dl class="tally">
    <div class="likely"><dt>Likely eligible</dt><dd>{counts['likely']}</dd></div>
    <div class="possible"><dt>Possible</dt><dd>{counts['possible']}</dd></div>
    <div class="not_eligible"><dt>Not eligible</dt><dd>{counts['not_eligible']}</dd></div>
  </dl>
  {incomplete}
</header>
<main class="wrap grid">
  <aside class="profile"><h2>Patient facts</h2><ol>{facts}</ol>
    <h2>How to read a trial</h2>
    <ul class="legend">
      <li><span class="sq ok"></span> met, or exclusion does not apply</li>
      <li><span class="sq no"></span> rules the patient out</li>
      <li><span class="sq dispute"></span> the two models disagree</li>
      <li><span class="sq open"></span> unknown from the facts</li>
      <li><span class="sq screen"></span> consent or pregnancy, at screening</li>
    </ul>
    <p class="small">Age and sex are checked by code. Every other verdict cites the facts it used; one model judges, a second model from a different provider re-judges every decisive verdict.</p>
  </aside>
  <section class="trials"><h2 class="sr">Trials</h2>{trials or '<p>No trials matched yet.</p>'}</section>
</main>
<footer class="wrap"><p>Matched {_e(a['finished'])} with {_e(a['writer'])}, checked by {_e(a['checker'])}. Prompt {_e(a['prompt'])}, trial-match {_e(a['version'])}. Source: {_e(a['source'])}.</p></footer>
</body></html>"""


def index(runs: list[dict]) -> str:
    items = ""
    for run in runs:
        p, rs = run["patient"], run["results"]
        c = {k: sum(1 for r in rs if r["outcome"]["status"] == k) for k in STATUS}
        items += (f'<li><a href="{_e(p["id"])}.html"><span class="title">{_e(p["label"])}</span>'
                  f'<span class="meta">{_e(p["facts"][1] if len(p["facts"]) > 1 else "")}</span>'
                  f'<span class="meta">{c["likely"]} likely, {c["possible"]} possible, {c["not_eligible"]} not eligible '
                  f'among {len(rs)} trials near {_e(p["city"])}</span></a></li>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>trial-match</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap">
<style>{CSS}</style></head><body>
<p class="banner">Synthetic patients. A research demonstration, not medical advice.</p>
<header class="wrap top"><h1>trial-match</h1>
<p class="lede">Which recruiting clinical trials could this patient join, and why? Each trial's eligibility criteria are split into single criteria and judged against the patient's facts, with every verdict tied to the facts it used and checked by a second, independent model.</p></header>
<main class="wrap"><ul class="patients">{items}</ul></main>
<footer class="wrap"><p>Trial data from the ClinicalTrials.gov API.</p></footer></body></html>"""


CSS = """
:root { --bg: #F4F6F5; --card: #FCFDFC; --ink: #1C2422; --muted: #56625E; --rule: #D3DAD7;
  --ok: #2F6B4F; --ok-bg: #E2EFE8; --no: #9C3B3B; --no-bg: #F5E3E1; --open: #8A9692; --open-bg: #E9EDEB;
  --dispute: #A5660B; --dispute-bg: #F6EAD3; --link: #2C5A8A;
  --sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif; --cond: "IBM Plex Sans Condensed", "Arial Narrow", sans-serif; }
* { box-sizing: border-box; }
html { background: var(--bg); color: var(--ink); }
body { margin: 0; font: 16px/1.55 var(--sans); }
a { color: var(--link); }
a:focus-visible, summary:focus-visible { outline: 3px solid var(--link); outline-offset: 2px; }
.wrap { max-width: 76rem; margin: 0 auto; padding-inline: 1.25rem; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.banner { margin: 0; padding: 0.6rem 1.25rem; background: var(--ink); color: #EEF2F0; font-size: 0.9rem; text-align: center; }
.top { padding-block: 2.5rem 1.5rem; }
.crumb { margin: 0 0 0.5rem; font: 600 0.9rem var(--cond); }
h1 { font: 600 clamp(1.9rem, 4vw, 2.6rem)/1.1 var(--cond); margin: 0; letter-spacing: -0.01em; }
h2 { font: 600 1.05rem var(--cond); margin: 0 0 0.6rem; }
h4 { font: 600 0.95rem var(--cond); margin: 0 0 0.4rem; }
.lede { max-width: 62ch; color: var(--muted); margin: 0.8rem 0 0; }
.tally { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 1.5rem 0 0; }
.tally div { background: var(--card); border: 1px solid var(--rule); border-top: 4px solid; padding: 0.6rem 1rem; min-width: 9rem; }
.tally .likely { border-top-color: var(--ok); } .tally .possible { border-top-color: var(--dispute); } .tally .not_eligible { border-top-color: var(--no); }
.tally dt { font-size: 0.85rem; color: var(--muted); } .tally dd { margin: 0; font: 600 1.8rem/1.1 var(--cond); }
.note.warn { background: var(--dispute-bg); padding: 0.6rem 0.9rem; max-width: 62ch; }
.grid { display: grid; grid-template-columns: 19rem 1fr; gap: 2rem; align-items: start; padding-bottom: 2rem; }
.profile { position: sticky; top: 1rem; background: var(--card); border: 1px solid var(--rule); padding: 1.1rem 1.2rem; font-size: 0.92rem; }
.profile ol { list-style: none; padding: 0; margin: 0 0 1.4rem; }
.profile li { margin: 0 0 0.45rem; }
.profile li b { display: inline-block; width: 2.1rem; color: var(--muted); font: 600 0.85rem var(--cond); }
.legend { list-style: none; padding: 0; margin: 0 0 1rem; }
.legend li { display: flex; align-items: center; gap: 0.5rem; margin: 0 0 0.35rem; }
.small { color: var(--muted); font-size: 0.85rem; margin: 0; }

.trial { background: var(--card); border: 1px solid var(--rule); border-left: 5px solid var(--open); margin: 0 0 0.9rem; }
.trial.likely { border-left-color: var(--ok); } .trial.possible { border-left-color: var(--dispute); } .trial.not_eligible { border-left-color: var(--no); }
.trial > summary { list-style: none; cursor: pointer; padding: 1rem 1.2rem; display: grid; gap: 0.3rem; }
.trial > summary::-webkit-details-marker { display: none; }
.status { font: 600 0.85rem var(--cond); }
.likely .status { color: var(--ok); } .possible .status { color: var(--dispute); } .not_eligible .status { color: var(--no); }
.title { font-weight: 600; line-height: 1.35; }
.meta { color: var(--muted); font-size: 0.88rem; }
.strip { display: flex; flex-wrap: wrap; gap: 3px; margin: 0.35rem 0 0.1rem; }
.sq { display: inline-block; width: 14px; height: 14px; border-radius: 2px; background: var(--open-bg); border: 1px solid var(--open); }
.sq.ok { background: var(--ok); border-color: var(--ok); } .sq.no { background: var(--no); border-color: var(--no); }
.sq.dispute { background: var(--dispute); border-color: var(--dispute); }
.sq.screen { background: transparent; border: 1px dashed var(--open); }
a.sq:hover { outline: 2px solid var(--ink); outline-offset: 1px; }
.body { padding: 0 1.2rem 1.2rem; }
.callout { padding: 0.8rem 1rem; margin: 0 0 0.9rem; }
.callout.no { background: var(--no-bg); } .callout.open { background: var(--open-bg); }
.callout ul { margin: 0; padding-left: 1.1rem; } .callout li { margin: 0.25rem 0; }
.why { display: block; color: var(--muted); font-size: 0.88rem; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; vertical-align: top; padding: 0.5rem 0.6rem 0.5rem 0; border-bottom: 1px solid var(--rule); }
thead th { font: 600 0.82rem var(--cond); color: var(--muted); border-bottom-color: var(--ink); }
tbody th { font: 600 0.85rem var(--cond); white-space: nowrap; }
tr:target { background: #FFF6D6; }
.ans { white-space: nowrap; }
.pill { display: inline-block; font: 600 0.8rem var(--cond); padding: 0.1rem 0.45rem; border-radius: 3px; }
.pill.ok { background: var(--ok-bg); color: var(--ok); } .pill.no { background: var(--no-bg); color: var(--no); }
.pill.open { background: var(--open-bg); color: var(--muted); } .pill.dispute { background: var(--dispute-bg); color: var(--dispute); }
.pill.screen { border: 1px dashed var(--open); color: var(--muted); }
.by { display: block; color: var(--muted); font-size: 0.78rem; margin-top: 0.15rem; }
.facts abbr { text-decoration: underline dotted; cursor: help; font: 600 0.85rem var(--cond); margin-right: 0.2rem; }
.reason { color: var(--muted); min-width: 12rem; }
.src { margin: 0.8rem 0 0; font-size: 0.9rem; }
.patients { list-style: none; padding: 0; margin: 0 0 3rem; display: grid; gap: 0.8rem; }
.patients a { display: grid; gap: 0.2rem; padding: 1rem 1.2rem; background: var(--card); border: 1px solid var(--rule); color: var(--ink); text-decoration: none; }
.patients a:hover { border-color: var(--link); }
footer { color: var(--muted); font-size: 0.82rem; padding-block: 1rem 3rem; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .profile { position: static; } }
"""
