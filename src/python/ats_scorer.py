#!/usr/bin/env python3
"""Score a CV against a parsed offer by keyword coverage. Deterministic, no LLM.

Usage:
    python src/python/ats_scorer.py --cv output/cv/CV_EN.docx --offer jobs/offer.json
    python src/python/ats_scorer.py --cv mytext.txt --offer jobs/offer.json

Prints coverage % and the list of offer keywords missing from the CV.
This one is intentionally fully implemented so the repo runs end-to-end for at least one step.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


def read_cv_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".docx":
        try:
            from docx import Document  # python-docx
        except ImportError:
            sys.exit("Install python-docx to read .docx CVs (pip install -r requirements.txt)")
        return "\n".join(par.text for par in Document(str(p)).paragraphs)
    return p.read_text(encoding="utf-8")


def normalize(text: str) -> set[str]:
    # words, keeping + and # (c++, c#) but NOT trailing punctuation like sentence periods
    return set(re.findall(r"[a-zà-ÿ0-9][a-zà-ÿ0-9+#]*", text.lower()))


def score(cv_text: str, keywords: list[str]) -> dict:
    cv_tokens = normalize(cv_text)
    present, missing = [], []
    for kw in keywords:
        # multi-word keyword present if all its tokens appear
        toks = normalize(kw)
        (present if toks and toks <= cv_tokens else missing).append(kw)
    total = len(keywords) or 1
    return {
        "coverage": round(len(present) / total, 3),
        "present": present,
        "missing": missing,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="ATS keyword coverage of a CV vs an offer.")
    ap.add_argument("--cv", required=True, help="path to CV (.docx or .txt)")
    ap.add_argument("--offer", required=True, help="parsed offer JSON (from parse_offer.py)")
    args = ap.parse_args(argv)

    offer = json.loads(Path(args.offer).read_text(encoding="utf-8"))
    keywords = offer.get("must_have", []) + offer.get("keywords", [])
    result = score(read_cv_text(args.cv), keywords)

    print(f"Coverage: {result['coverage'] * 100:.0f}%  ({len(result['present'])}/{len(keywords)})")
    if result["missing"]:
        print("Missing keywords:")
        for kw in result["missing"]:
            print(f"  - {kw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
