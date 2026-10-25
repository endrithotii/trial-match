"""ClinicalTrials.gov API v2: search recruiting trials and read the fields we match on.

Plain code, no model. Everything a decision later rests on (age limits, sex,
sites, the eligibility text) comes from here, unchanged, with the trial's URL.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

API = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = "trial-match/0.1 (+https://github.com/endrithotii/trial-match)"


@dataclass
class Site:
    facility: str
    city: str
    country: str
    status: str
    lat: float | None
    lon: float | None


@dataclass
class Trial:
    nct: str
    title: str
    phases: list[str]
    conditions: list[str]
    interventions: list[str]
    sponsor: str
    min_age: float | None          # years
    max_age: float | None          # years
    sex: str                       # ALL, FEMALE or MALE
    criteria_text: str
    sites: list[Site] = field(default_factory=list)
    last_update: str = ""

    @property
    def url(self) -> str:
        return f"https://clinicaltrials.gov/study/{self.nct}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Trial":
        d = {k: v for k, v in d.items() if k != "url"}
        d["sites"] = [Site(**s) for s in d.get("sites", [])]
        return cls(**d)


def parse_age(text: str | None) -> float | None:
    """'18 Years' -> 18.0, '6 Months' -> 0.5, 'N/A' or missing -> None."""
    if not text:
        return None
    parts = text.split()
    try:
        value = float(parts[0])
    except (ValueError, IndexError):
        return None
    unit = parts[1].lower() if len(parts) > 1 else "years"
    factor = {"year": 1, "years": 1, "month": 1 / 12, "months": 1 / 12,
              "week": 1 / 52, "weeks": 1 / 52, "day": 1 / 365, "days": 1 / 365}.get(unit, 1)
    return round(value * factor, 2)


def _trial(study: dict) -> Trial:
    p = study["protocolSection"]
    ident, elig = p["identificationModule"], p.get("eligibilityModule", {})
    sites = []
    for loc in p.get("contactsLocationsModule", {}).get("locations", []):
        geo = loc.get("geoPoint") or {}
        sites.append(Site(facility=loc.get("facility", ""), city=loc.get("city", ""),
                          country=loc.get("country", ""), status=loc.get("status", ""),
                          lat=geo.get("lat"), lon=geo.get("lon")))
    interventions = [i.get("name", "") for i in p.get("armsInterventionsModule", {}).get("interventions", [])]
    return Trial(
        nct=ident["nctId"],
        title=ident.get("briefTitle", ""),
        phases=p.get("designModule", {}).get("phases", []) or [],
        conditions=p.get("conditionsModule", {}).get("conditions", []) or [],
        interventions=[i for i in interventions if i],
        sponsor=p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", ""),
        min_age=parse_age(elig.get("minimumAge")),
        max_age=parse_age(elig.get("maximumAge")),
        sex=elig.get("sex", "ALL"),
        criteria_text=elig.get("eligibilityCriteria", ""),
        sites=sites,
        last_update=p.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date", ""),
    )


def _get(params: dict) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"user-agent": USER_AGENT, "accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def search(condition: str, term: str = "", near: tuple[float, float] | None = None,
           radius_km: int = 600, status: str = "RECRUITING", limit: int = 200) -> list[Trial]:
    params = {"query.cond": condition, "filter.overallStatus": status, "pageSize": 100}
    if term:
        params["query.term"] = term
    if near:
        params["filter.geo"] = f"distance({near[0]},{near[1]},{radius_km}km)"
    trials: list[Trial] = []
    while len(trials) < limit:
        page = _get(params)
        trials.extend(_trial(s) for s in page.get("studies", []))
        token = page.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    return trials[:limit]


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in kilometres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def nearest_site(trial: Trial, point: tuple[float, float], recruiting_only: bool = True) -> tuple[Site | None, float | None]:
    best, best_d = None, None
    for s in trial.sites:
        if s.lat is None or s.lon is None:
            continue
        if recruiting_only and s.status and s.status not in ("RECRUITING", "NOT_YET_RECRUITING"):
            continue
        d = km(point, (s.lat, s.lon))
        if best_d is None or d < best_d:
            best, best_d = s, d
    return best, (round(best_d) if best_d is not None else None)
