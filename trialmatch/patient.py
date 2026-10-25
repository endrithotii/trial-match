"""A patient profile: structured fields for code checks, numbered facts for the models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Patient:
    id: str
    label: str
    age: float
    sex: str                        # FEMALE or MALE
    lat: float
    lon: float
    city: str
    facts: list[str]
    synthetic: bool = True

    @property
    def point(self) -> tuple[float, float]:
        return (self.lat, self.lon)

    def numbered_facts(self) -> str:
        lines = [f"F1. Age {self.age:g}, {self.sex.lower()}."]
        lines += [f"F{i}. {f}" for i, f in enumerate(self.facts, start=2)]
        return "\n".join(lines)

    def fact(self, ref: str) -> str | None:
        """'F3' -> the text of fact 3, or None if there is no such fact."""
        try:
            n = int(str(ref).strip().upper().lstrip("F"))
        except ValueError:
            return None
        if n == 1:
            return f"Age {self.age:g}, {self.sex.lower()}."
        return self.facts[n - 2] if 2 <= n <= len(self.facts) + 1 else None

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "age": self.age, "sex": self.sex, "city": self.city,
                "lat": self.lat, "lon": self.lon, "facts": self.facts, "synthetic": self.synthetic}


def load(path: str | Path) -> Patient:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    loc = d["location"]
    return Patient(id=d["id"], label=d["label"], age=float(d["age"]), sex=d["sex"].upper(),
                   lat=loc["lat"], lon=loc["lon"], city=loc["city"], facts=d["facts"],
                   synthetic=d.get("synthetic", True))
