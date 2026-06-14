#!/usr/bin/env python3
"""Audit two CV texts for cross-language consistency."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def read_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".docx":
        try:
            from docx import Document
        except ImportError:
            sys.exit("Install python-docx to read .docx files (pip install -r requirements.txt)")
        return "\n".join(par.text for par in Document(str(p)).paragraphs)
    return p.read_text(encoding="utf-8")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_metrics(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\s*(?:%|\+|k|m|users|utilisateurs|ans|years)?", text.lower()))


def extract_claims(text: str) -> list[str]:
    claims = []
    for raw in text.splitlines():
        line = raw.strip(" -\t")
        if len(line.split()) >= 4:
            claims.append(line)
    return claims


def extract_roles(text: str) -> list[str]:
    roles = []
    for line in text.splitlines():
        clean = line.strip()
        if "|" in clean or re.search(r"\b(analyst|analytics|manager|lead|responsable|chef|consultant)\b", clean, re.I):
            if len(clean.split()) <= 12:
                roles.append(clean)
    return roles


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-zà-ÿ0-9][a-zà-ÿ0-9+#/-]*", text.lower()))


def best_overlap(item: str, candidates: list[str]) -> float:
    source = token_set(item)
    if not source:
        return 0.0
    return max((len(source & token_set(candidate)) / len(source) for candidate in candidates), default=0.0)


def missing_items(left_items: list[str], right_items: list[str], threshold: float = 0.35) -> list[str]:
    return [item for item in left_items if best_overlap(item, right_items) < threshold]


def audit(left_text: str, right_text: str, left_label: str = "left", right_label: str = "right") -> dict:
    left_roles, right_roles = extract_roles(left_text), extract_roles(right_text)
    left_claims, right_claims = extract_claims(left_text), extract_claims(right_text)
    left_metrics, right_metrics = extract_metrics(left_text), extract_metrics(right_text)
    return {
        "missing_roles": {
            left_label: missing_items(right_roles, left_roles, 0.4),
            right_label: missing_items(left_roles, right_roles, 0.4),
        },
        "missing_claims": {
            left_label: missing_items(right_claims, left_claims),
            right_label: missing_items(left_claims, right_claims),
        },
        "metric_mismatches": {
            left_label: sorted(right_metrics - left_metrics),
            right_label: sorted(left_metrics - right_metrics),
        },
    }


def has_issues(report: dict) -> bool:
    return any(items for group in report.values() for items in group.values())


def print_report(report: dict) -> None:
    if not has_issues(report):
        print("No bilingual inconsistencies found.")
        return
    print("Bilingual inconsistencies found:")
    for section, sides in report.items():
        printed = False
        for side, items in sides.items():
            if not items:
                continue
            if not printed:
                print(f"\n{section.replace('_', ' ').title()}:")
                printed = True
            print(f"  Missing from {side}:")
            for item in items:
                print(f"    - {item}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Diff two language CVs for missing roles, claims, and metrics.")
    ap.add_argument("--left", required=True, help="first CV text/docx")
    ap.add_argument("--right", required=True, help="second CV text/docx")
    ap.add_argument("--left-label", default="left")
    ap.add_argument("--right-label", default="right")
    args = ap.parse_args(argv)

    report = audit(read_text(args.left), read_text(args.right), args.left_label, args.right_label)
    print_report(report)
    return 1 if has_issues(report) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
