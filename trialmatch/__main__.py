"""Command line.

  python -m trialmatch run --patient patients/a-egfr-ex19-post-osimertinib.json
  python -m trialmatch site out/          # rebuild the HTML from saved runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .criteria import Criterion, is_conditional
from .llm import make_model
from .match import outcome, rank_key
from .patient import load
from .report import index, page
from .run import log, run


def reapply_rules(run_result: dict) -> dict:
    """The decision rules are plain code, so they can be re-applied to saved model
    answers whenever they change, without calling a model again."""
    for r in run_result["results"]:
        for row in r["rows"]:
            if row["id"][:1] in "IE" and row["id"][1:].isdigit():
                c = Criterion(row["id"], row["kind"], row["text"])
                row["conditional"] = is_conditional(c)
        r["outcome"] = outcome(r["rows"])
    run_result["results"].sort(key=rank_key)
    return run_result


def build_site(out: Path) -> None:
    runs = [reapply_rules(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(out.glob("*.json"))]
    for r in runs:
        (out / f"{r['patient']['id']}.html").write_text(page(r), encoding="utf-8")
    (out / "index.html").write_text(index(runs), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trialmatch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="match one patient to recruiting trials nearby")
    r.add_argument("--patient", required=True, type=Path)
    r.add_argument("--condition", default="non-small cell lung cancer")
    r.add_argument("--term", default="EGFR", help="extra search term, e.g. a gene or drug")
    r.add_argument("--radius", type=int, default=600, help="km around the patient")
    r.add_argument("--limit", type=int, default=12, help="match at most this many of the closest trials")
    r.add_argument("--writer", default="groq:qwen/qwen3.8-27b")
    r.add_argument("--checker", default="groq:openai/gpt-oss-120b")
    r.add_argument("--out", type=Path, default=Path("out"))
    r.add_argument("--cache", type=Path, default=Path("cache"))
    s = sub.add_parser("site", help="rebuild the HTML pages from saved runs")
    s.add_argument("out", type=Path, nargs="?", default=Path("out"))
    args = ap.parse_args(argv)

    if args.cmd == "site":
        build_site(args.out)
        print(args.out / "index.html")
        return 0

    try:
        writer, checker = make_model(args.writer), make_model(args.checker)
    except (RuntimeError, ValueError) as e:
        log(f"Cannot start: {e}. See README.md.")
        return 2
    patient = load(args.patient)
    result = run(patient, args.condition, args.term, args.radius, args.limit, writer, checker, args.cache)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{patient.id}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    build_site(args.out)
    print(args.out / f"{patient.id}.html")
    return 0 if result["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
