"""Split free-text eligibility criteria into individual, numbered criteria.

Registry texts mix bullets, numbered lists, nested items and loose paragraphs,
in many styles. This is plain code on purpose: the list of criteria every later
decision refers to must be reproducible and inspectable, not a model's reading.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_HEADER = re.compile(
    r"^\s*(?:key\s+|main\s+|major\s+|general\s+)?(inclusion|exclusion)\s*(?:criteria|criterion)?\s*[:\-]?\s*$",
    re.I)
_INLINE_HEADER = re.compile(r"^\s*(?:key\s+)?(inclusion|exclusion)\s+criteria\s*[:\-]\s*(.+)$", re.I)
_BULLET = re.compile(r"^(\s*)(?:[*\-•·▪◦●]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)](?=\s)|[ivxIVX]{1,4}[.)](?=\s))\s+(.*)$")


@dataclass
class Criterion:
    id: str            # I1, I2 ... for inclusion, E1, E2 ... for exclusion
    kind: str          # "inclusion" or "exclusion"
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(s: str) -> str:
    s = s.replace("\u2265", ">=").replace("\u2264", "<=").replace("\u00a0", " ")
    s = re.sub(r"\\([<>*_\[\]()#~-])", r"\1", s)   # the registry escapes Markdown characters
    return re.sub(r"\s+", " ", s).strip()


def parse(text: str) -> list[Criterion]:
    if not text or not text.strip():
        return []
    section = None
    items: list[dict] = []          # {"kind", "text", "indent"}
    for raw in text.replace("\r", "").split("\n"):
        if not raw.strip():
            continue
        m = _HEADER.match(raw)
        if m:
            section = m.group(1).lower()
            continue
        m = _INLINE_HEADER.match(raw)
        if m:
            section = m.group(1).lower()
            raw = m.group(2)
        if section is None:
            section = "inclusion"   # texts that never say "inclusion" list inclusion first
        b = _BULLET.match(raw)
        if b:
            indent = len(b.group(1).expandtabs(4))
            body = b.group(2)
            parent = items[-1] if items else None
            if parent and parent["kind"] == section and indent > parent["indent"]:
                # A nested item belongs to its parent criterion ("Adequate organ function: ANC >= 1.5 ...").
                parent["text"] += "; " + body
                parent["nested"] = True
            else:
                items.append({"kind": section, "text": body, "indent": indent})
        elif items and items[-1]["kind"] == section:
            # A loose paragraph continues the criterion above it.
            items[-1]["text"] += " " + raw.strip()
        else:
            items.append({"kind": section, "text": raw.strip(), "indent": 0})

    out, counts = [], {"inclusion": 0, "exclusion": 0}
    for it in items:
        txt = _clean(it["text"])
        if not txt or len(txt) < 4:
            continue
        counts[it["kind"]] += 1
        prefix = "I" if it["kind"] == "inclusion" else "E"
        out.append(Criterion(id=f"{prefix}{counts[it['kind']]}", kind=it["kind"], text=txt))
    return out


# Criteria that cannot be judged from a clinical profile: consent, contraception,
# willingness, administrative boilerplate. They are shown, but not sent to a model.
_ADMIN = re.compile(
    r"informed consent|sign(ed|ing)? (the )?consent|willing(ness)? (and able )?to|able to comply|"
    r"contracept|pregnan|breast[- ]?feed|lactat|childbearing|"
    r"other protocol[- ]defined|per protocol|investigator'?s (judg|opinion)",
    re.I)


_CLINICAL = re.compile(
    r"\d\s*(?:%|mg|g/dl|g/l|ml/min|x\s*10|x\s*uln|mm|cm|years?)|uln|creatinine|clearance|bilirubin|neutrophil|anc\b|"
    r"platelet|h(a)?emoglobin|ecog|performance status|metasta|mutation|deletion|insertion|amplification|stage|"
    r"therap|treatment|tki|chemo|radiation|surgery|disease|cancer|carcinoma|nsclc|tumou?r|lesion|recist|"
    r"function|infection|hepatitis|hiv|cardiac|qtc|interstitial|pneumonitis|autoimmune",
    re.I)


_CONDITIONAL = re.compile(
    r"^\s*(?:for\s+(?:patients|participants|subjects|those|aga|cohort|arm|part)\b|for\s+[\w\s+/-]{0,40}\bonly\b|"
    r"(?:cohort|arm|part|group|module|substudy)\s*[\w.-]{0,6}\s*[:(]|only\s+for\b|if\s+applicable)",
    re.I)


def is_conditional(c: Criterion) -> bool:
    """Criteria that apply to one cohort or arm only ("For AGA-negative NSCLC only: ...").
    Failing one of them rules a patient out of that cohort, not out of the trial."""
    return bool(_CONDITIONAL.search(c.text))


def is_administrative(c: Criterion) -> bool:
    """Consent, contraception or compliance only. Any clinical content keeps it in."""
    return bool(_ADMIN.search(c.text)) and not _CLINICAL.search(c.text)
