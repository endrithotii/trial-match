"""Search trials near a patient, match each one, cache results, keep an audit trail."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .ctgov import Trial, nearest_site, search
from .llm import Model, QuotaExhausted
from .match import JUDGE_SYSTEM, match, rank_key
from .patient import Patient
from .textutil import sha256


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Cache:
    """One file per patient and trial, keyed by everything that shapes the answer:
    the trial's criteria text, the patient's facts, both models and the prompt."""

    def __init__(self, folder: Path | None):
        self.folder = folder
        if folder:
            folder.mkdir(parents=True, exist_ok=True)

    def path(self, trial: Trial, patient: Patient, writer: Model, checker: Model) -> Path | None:
        if not self.folder:
            return None
        key = sha256(json.dumps([trial.criteria_text, trial.min_age, trial.max_age, trial.sex,
                                 patient.to_dict(), writer.name, checker.name, JUDGE_SYSTEM]))[:16]
        return self.folder / f"{patient.id}-{trial.nct}-{key}.json"

    def get(self, *args) -> dict | None:
        p = self.path(*args)
        return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None

    def put(self, result: dict, *args) -> None:
        p = self.path(*args)
        if p:
            p.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def run(patient: Patient, condition: str, term: str, radius_km: int, limit: int,
        writer: Model, checker: Model, cache_dir: Path | None = None) -> dict:
    started = datetime.now(timezone.utc)
    log(f"Searching recruiting trials within {radius_km} km of {patient.city}")
    trials = search(condition, term, near=patient.point, radius_km=radius_km)
    # Closest first: a trial a patient can reach is worth judging first.
    trials.sort(key=lambda t: nearest_site(t, patient.point)[1] or 1e9)
    found = len(trials)
    trials = trials[:limit]
    log(f"  {found} found, matching the {len(trials)} closest")

    cache, results, stopped = Cache(cache_dir), [], None
    for t in trials:
        hit = cache.get(t, patient, writer, checker)
        if hit:
            results.append(hit)
            continue
        try:
            r = match(t, patient, writer, checker)
        except QuotaExhausted as e:
            stopped = str(e)
            log(f"Stopped: {e}")
            break
        except Exception as e:  # one malformed trial must not stop the run
            log(f"  {t.nct}: failed ({e})")
            continue
        cache.put(r, t, patient, writer, checker)
        log(f"  {t.nct}: {r['outcome']['status']}")
        results.append(r)

    results.sort(key=rank_key)
    return {
        "patient": patient.to_dict(),
        "query": {"condition": condition, "term": term, "radius_km": radius_km, "found": found, "limit": limit},
        "results": results,
        "complete": stopped is None and len(results) == len(trials),
        "stopped": stopped,
        "audit": {"started": started.isoformat(timespec="seconds"),
                  "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "version": __version__, "writer": writer.name, "checker": checker.name,
                  "prompt": sha256(JUDGE_SYSTEM)[:12], "source": "ClinicalTrials.gov API v2"},
    }
