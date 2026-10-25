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
GLYPH = {"ok": "✓", "no": "✕", "open": "?", "dispute": "⇄", "screen": "○"}
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
    # One segment per criterion, grouped by outcome so the bar reads at a glance.
    order = ["no", "dispute", "open", "screen", "ok"]
    rows = sorted(rows, key=lambda r: order.index(ANSWER[r["answer"]][1]))
    cells = "".join(
        f'<a class="seg {ANSWER[r["answer"]][1]}" href="#{key}-{_e(r["id"])}" '
        f'title="{_e(r["id"])}: {_e(ANSWER[r["answer"]][0])}"><span class="sr">{_e(r["id"])} {_e(ANSWER[r["answer"]][0])}</span></a>'
        for r in rows)
    return f'<span class="capsule" role="list" aria-label="Criteria, one segment each">{cells}</span>'



def _why(x: dict) -> str:
    return f'<p class="why">{_e(x["reason"])}</p>' if x.get("reason") else ""


def _trial(r: dict, patient: dict, i: int) -> str:
    t, o, key = r["trial"], r["outcome"], f"t{i}"
    label, _ = STATUS[o["status"]]
    site = r.get("nearest_site")
    where = (f'{_e(site["city"])}, {_e(site["country"])}, {r["distance_km"]} km away' if site else "No recruiting site with a location")
    by_id = {x["id"]: x for x in r["rows"]}
    blockers = "".join(f'<li><b>{_e(b)}</b> {_e(by_id[b]["text"])}<span class="why">{_e(by_id[b].get("reason", ""))}</span></li>'
                       for b in o["blockers"])
    questions = "".join(f'<li><b>{_e(q)}</b> {_e(by_id[q]["text"])}<span class="why">{_e(by_id[q].get("reason", ""))}</span></li>'
                        for q in o["open"])
    rows = "".join(
        f'<li id="{key}-{_e(x["id"])}" class="crit {ANSWER[x["answer"]][1]}">'
        f'<span class="glyph" aria-hidden="true">{GLYPH[ANSWER[x["answer"]][1]]}</span>'
        f'<div class="ctext"><p class="cline"><b>{_e(x["id"])}</b> {_e(x["text"])}</p>'
        f'<p class="cverdict"><strong>{_e(ANSWER[x["answer"]][0])}</strong>, judged by {_e(BY.get(x["by"], x["by"]))}'
        f'{(", using " + _facts_ref(x.get("facts", []), patient)) if x.get("facts") else ""}</p>'
        f'{_why(x)}'
        f'</div></li>'
        for x in r["rows"])
    detail = ""
    if questions:
        detail += f'<div class="ask"><h4>Ask before referring</h4><ul>{questions}</ul></div>'
    if blockers:
        detail += f'<div class="stop"><h4>What rules the patient out</h4><ul>{blockers}</ul></div>'
    n_open = len(o["open"])
    return f"""
<details class="trial {o['status']}" id="{key}">
  <summary>
    <span class="disc" aria-hidden="true">{o['cleared']}<small>of {o['judged']}</small></span>
    <span class="head">
      <span class="status">{_e(label)}</span>
      <span class="title">{_e(t['title'])}</span>
      {_strip(r['rows'], key)}
      <span class="facts-line">{_e(_phase(t['phases']))}, {_e(t['sponsor'])}. Nearest site: {where}.{f" {n_open} question{'s' if n_open != 1 else ''} to clarify." if n_open else ""}</span>
    </span>
  </summary>
  <div class="body">
    {detail}
    <h4 class="all">Every criterion, as written in the registry</h4>
    <ol class="crits">{rows}</ol>
    <p class="src"><a href="{_e(t['url'])}">{_e(t['nct'])} on ClinicalTrials.gov</a></p>
  </div>
</details>"""


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Young+Serif&display=swap">')


def page(run: dict) -> str:
    p, q, results = run["patient"], run["query"], run["results"]
    counts = {k: sum(1 for r in results if r["outcome"]["status"] == k) for k in STATUS}
    facts = "".join(f"<li><b>F{i}</b> {_e(f)}</li>" for i, f in
                    enumerate([f"Age {p['age']:g}, {p['sex'].lower()}, lives in {p['city']}."] + p["facts"], start=1))
    trials = "".join(_trial(r, p, i) for i, r in enumerate(results))
    incomplete = ("" if run["complete"] else
                  f'<p class="warn">This run stopped early ({_e(run.get("stopped") or "not all trials were matched")}). '
                  'The next run continues where it stopped.</p>')
    a = run["audit"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>{_e(p['label'])}: trial matches</title>{FONTS}
<style>{CSS}</style></head><body>
<header class="band">
  <div class="wrap">
    <p class="back"><a href="index.html">All patients</a></p>
    <h1>{_e(p['label'])}</h1>
    <p class="lede">Recruiting trials for {_e(q['condition'])}{f" that mention {_e(q['term'])}" if q['term'] else ""}, within {q['radius_km']} km of {_e(p['city'])}.
      {q['found']} found; the {len(results)} closest were checked criterion by criterion.</p>
    <ul class="tally">
      <li class="likely"><b>{counts['likely']}</b> likely eligible</li>
      <li class="possible"><b>{counts['possible']}</b> possible, with questions</li>
      <li class="not_eligible"><b>{counts['not_eligible']}</b> ruled out</li>
    </ul>
    {incomplete}
  </div>
</header>
<main class="wrap grid">
  <aside class="wristband">
    <h2>What we know about this patient</h2>
    <ol class="facts">{facts}</ol>
    <h2>Reading the bars</h2>
    <ul class="legend">
      <li><span class="key ok">✓</span> met, or the exclusion does not apply</li>
      <li><span class="key no">✕</span> rules the patient out</li>
      <li><span class="key dispute">⇄</span> the two models disagree</li>
      <li><span class="key open">?</span> not known from these facts</li>
      <li><span class="key screen">○</span> checked at screening (consent, pregnancy test)</li>
    </ul>
    <p class="how">Age and sex are checked by code. Every other verdict names the facts it used. One model judges; a second model from another company re-judges every verdict that decides the outcome.</p>
  </aside>
  <section class="trials" aria-label="Trials">{trials or '<p>No trials matched yet.</p>'}</section>
</main>
<footer class="wrap foot"><p>Synthetic patient, for demonstration. Not medical advice: confirm every detail with the trial team.</p>
<p>Matched {_e(a['finished'][:10])} by {_e(a['writer'])}, checked by {_e(a['checker'])}. Data: {_e(a['source'])}.</p></footer>
</body></html>"""


def index(runs: list[dict]) -> str:
    items = ""
    for run in runs:
        p, rs = run["patient"], run["results"]
        c = {k: sum(1 for r in rs if r["outcome"]["status"] == k) for k in STATUS}
        total = max(len(rs), 1)
        bar = "".join(f'<span class="seg {cls}" style="flex:{c[k]}"></span>'
                      for k, cls in (("not_eligible", "no"), ("possible", "open"), ("likely", "ok")) if c[k])
        items += (f'<li><a href="{_e(p["id"])}.html">'
                  f'<span class="who">{_e(p["label"])}</span>'
                  f'<span class="what">{_e(p["facts"][1] if len(p["facts"]) > 1 else "")}</span>'
                  f'<span class="capsule big" aria-hidden="true">{bar}</span>'
                  f'<span class="counts">{c["likely"]} likely, {c["possible"]} possible, {c["not_eligible"]} ruled out, '
                  f'of {len(rs)} trials near {_e(p["city"])}</span></a></li>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>trial-match</title>{FONTS}
<style>{CSS}</style></head><body>
<header class="band home">
  <div class="wrap">
    <h1>Which clinical trials could this patient join?</h1>
    <p class="lede">For each patient, recruiting trials nearby are pulled from ClinicalTrials.gov. Every eligibility criterion is judged on its own against the patient's facts, each verdict says which facts it used, and a second, independent model checks the verdicts that decide the outcome.</p>
  </div>
</header>
<main class="wrap"><h2 class="pick">Pick a patient</h2><ul class="patients">{items}</ul></main>
<footer class="wrap foot"><p>The three patients are synthetic. Trial data from the ClinicalTrials.gov API. Not medical advice.</p></footer></body></html>"""


# White and cobalt: clean, clinical and trustworthy for a reader who may be a
# patient. Outcome colours follow traffic logic people already know (green go,
# rose stop), and sunflower yellow is kept for the one thing to act on:
# questions to clarify. Every colour is paired with a glyph.
CSS = """
:root { --ground: #F2F4FD; --sheet: #FFFFFF; --navy: #2443E8; --text: #0B1033; --soft: #4B5275; --line: #DDE1F0;
  --go: #13A876; --go-tint: #E2F6EE; --stop: #E8475B; --stop-tint: #FDE7EA;
  --ask: #FFD23F; --ask-tint: #FFF6D1; --ask-ink: #6E5300; --dispute: #0B1033; --dispute-tint: #E6E8F2; --idle: #A3A9C6;
  --body: "Atkinson Hyperlegible", Verdana, sans-serif; --display: "Young Serif", Georgia, serif; }
* { box-sizing: border-box; }
html { background: var(--ground); color: var(--text); }
body { margin: 0; font: 17px/1.6 var(--body); }
a { color: var(--navy); text-decoration-thickness: 2px; text-underline-offset: 3px; }
:focus-visible { outline: 3px solid var(--ask); outline-offset: 3px; border-radius: 6px; }
.wrap { max-width: 78rem; margin: 0 auto; padding-inline: 1.25rem; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

.band { background: var(--navy); color: #FFFFFF; padding-block: 2.2rem 2.6rem; border-radius: 0 0 2.5rem 2.5rem; }
.band a { color: #FFFFFF; }
.back { margin: 0 0 1rem; font-size: 0.95rem; }
.back a::before { content: "‹ "; }
h1 { color: #FFFFFF; font: 400 clamp(2rem, 4.6vw, 3.2rem)/1.1 var(--display); margin: 0; max-width: 22ch; }
.lede { max-width: 60ch; margin: 1rem 0 0; color: #DCE2FF; }
.tally { list-style: none; display: flex; flex-wrap: wrap; gap: 0.6rem; padding: 0; margin: 1.6rem 0 0; }
.tally li { display: flex; align-items: center; gap: 0.6rem; background: rgba(255,255,255,0.14); border-radius: 999px; padding: 0.35rem 1.1rem 0.35rem 0.35rem; }
.tally b { display: grid; place-items: center; min-width: 2.4rem; height: 2.4rem; border-radius: 50%; font-size: 1.15rem; color: #fff; }
.tally .likely b { background: var(--go); } .tally .possible b { background: var(--ask); color: var(--navy); } .tally .not_eligible b { background: var(--stop); }
.warn { background: var(--ask); color: var(--navy); border-radius: 1rem; padding: 0.6rem 1rem; max-width: 60ch; }

.grid { display: grid; grid-template-columns: 20rem minmax(0, 1fr); gap: 2rem; align-items: start; padding-block: 2rem; }
.wristband { position: sticky; top: 1rem; background: var(--sheet); border-radius: 1.6rem; padding: 1.4rem 1.4rem 1.2rem; border-top: 0.9rem solid var(--navy); }
.wristband h2 { font: 400 1.15rem var(--display); color: var(--navy); margin: 0 0 0.7rem; }
.facts { list-style: none; padding: 0; margin: 0 0 1.6rem; font-size: 0.95rem; }
.facts li { padding: 0.35rem 0; display: grid; grid-template-columns: 2.4rem 1fr; }
.facts b, abbr { color: var(--navy); }
.legend { list-style: none; padding: 0; margin: 0 0 1rem; font-size: 0.92rem; }
.legend li { display: flex; gap: 0.6rem; align-items: center; margin: 0.35rem 0; }
.key { display: inline-grid; place-items: center; width: 1.6rem; height: 1.6rem; border-radius: 50%; font-weight: 700; font-size: 0.9rem; flex: none; }
.key.ok { background: var(--go); color: #fff; } .key.no { background: var(--stop); color: #fff; }
.key.dispute { background: var(--dispute); color: #fff; } .key.open { background: var(--ask); color: var(--navy); }
.key.screen { background: var(--sheet); color: var(--soft); box-shadow: inset 0 0 0 2px var(--idle); }
.how { font-size: 0.88rem; color: var(--soft); margin: 0; }

.trial { background: var(--sheet); border-radius: 1.6rem; margin: 0 0 1rem; overflow: hidden; }
.trial > summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 5.2rem minmax(0, 1fr); gap: 1.1rem; padding: 1.3rem 1.4rem; }
.trial > summary::-webkit-details-marker { display: none; }
.trial[open] > summary { background: #F7F8FE; }
.disc { display: grid; place-items: center; align-content: center; width: 5.2rem; height: 5.2rem; border-radius: 50%; font: 400 1.9rem/1 var(--display); color: #fff; background: var(--idle); }
.disc small { font: 400 0.75rem var(--body); opacity: 0.9; margin-top: 0.2rem; }
.likely .disc { background: var(--go); } .possible .disc { background: var(--ask); color: var(--navy); } .not_eligible .disc { background: var(--stop); }
.head { display: grid; gap: 0.45rem; min-width: 0; }
.status { font-weight: 700; font-size: 0.95rem; }
.likely .status { color: var(--go); } .possible .status { color: var(--ask-ink); } .not_eligible .status { color: var(--stop); }
.title { font: 400 1.18rem/1.35 var(--display); color: var(--text); }
.facts-line { color: var(--soft); font-size: 0.93rem; }
.capsule { display: flex; gap: 3px; height: 1.1rem; border-radius: 999px; overflow: hidden; background: var(--line); max-width: 34rem; }
.capsule.big { height: 0.9rem; max-width: none; }
.seg { flex: 1; min-width: 6px; background: var(--idle); }
.seg.ok { background: var(--go); } .seg.no { background: var(--stop); } .seg.dispute { background: var(--dispute); }
.seg.open { background: var(--ask); } .seg.screen { background: repeating-linear-gradient(135deg, var(--idle) 0 3px, var(--sheet) 3px 6px); }
a.seg:hover { filter: brightness(0.85); }

.body { padding: 0.4rem 1.4rem 1.4rem; }
.body h4 { font: 400 1.05rem var(--display); margin: 1rem 0 0.5rem; color: var(--navy); }
.ask, .stop { border-radius: 1.1rem; padding: 0.4rem 1.1rem 0.8rem; margin: 0.8rem 0; }
.ask { background: var(--ask-tint); } .stop { background: var(--stop-tint); }
.ask ul, .stop ul { margin: 0; padding-left: 1.1rem; } .ask li, .stop li { margin: 0.35rem 0; }
.why { display: block; color: var(--soft); font-size: 0.9rem; margin: 0.1rem 0 0; }
.crits { list-style: none; padding: 0; margin: 0; }
.crit { display: grid; grid-template-columns: 2rem minmax(0, 1fr); gap: 0.8rem; padding: 0.7rem 0; border-top: 1px solid var(--line); scroll-margin-top: 1rem; }
.crit:target { background: var(--ask-tint); border-radius: 0.8rem; }
.glyph { display: grid; place-items: center; width: 1.8rem; height: 1.8rem; border-radius: 50%; font-weight: 700; color: #fff; background: var(--idle); }
.crit.ok .glyph { background: var(--go); } .crit.no .glyph { background: var(--stop); } .crit.dispute .glyph { background: var(--dispute); }
.crit.open .glyph { background: var(--ask); color: var(--navy); } .crit.screen .glyph { background: var(--sheet); color: var(--soft); box-shadow: inset 0 0 0 2px var(--idle); }
.cline, .cverdict { margin: 0; }
.cline b { color: var(--soft); font-weight: 700; margin-right: 0.3rem; }
.cverdict { font-size: 0.92rem; margin-top: 0.2rem; }
.crit.ok strong { color: var(--go); } .crit.no strong { color: var(--stop); } .crit.dispute strong { color: var(--dispute); } .crit.open strong { color: var(--ask-ink); }
abbr { text-decoration: underline dotted; cursor: help; font-weight: 700; }
.src { margin: 1rem 0 0; }

.home { padding-block: 3rem 3.4rem; }
.pick { font: 400 1.4rem var(--display); color: var(--navy); margin: 2.2rem 0 1rem; }
.patients { list-style: none; padding: 0; margin: 0 0 2rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1rem; }
.patients a { display: grid; gap: 0.6rem; padding: 1.4rem; background: var(--sheet); border-radius: 1.6rem; color: var(--text); text-decoration: none; border-top: 0.9rem solid var(--navy); height: 100%; }
.patients a:hover { border-top-color: var(--go); }
.who { font: 400 1.35rem/1.2 var(--display); color: var(--text); }
.what { color: var(--soft); }
.counts { font-size: 0.92rem; }
.foot { color: var(--soft); font-size: 0.88rem; padding-block: 0.5rem 3rem; }
.foot p { margin: 0.3rem 0; max-width: 80ch; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .wristband { position: static; } }
@media (max-width: 520px) { .trial > summary { grid-template-columns: 1fr; } .disc { width: 4rem; height: 4rem; font-size: 1.5rem; } .band { border-radius: 0 0 1.5rem 1.5rem; } }
"""
