#!/usr/bin/env python3
"""Verify a generated .docx by reading back the rendered text layer.

This is intentionally portable: python-docx is the only hard dependency. Optional PDF
conversion is attempted only when explicitly requested and the required tools exist.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

import ats_scorer

ROOT = Path(__file__).resolve().parents[2]
BAD_CHARS = "\u200b\u200c\u200d\ufeff\u00ad\u2060"
CONTROL_CHARS = {chr(i) for i in list(range(0, 9)) + [11, 12] + list(range(14, 32)) + list(range(127, 160))}
LANG_HINTS = {
    "en": {"the", "and", "with", "for", "by", "data", "analytics", "experience", "skills"},
    "fr": {"le", "la", "les", "des", "avec", "pour", "par", "donnee", "donnees", "experience", "competences"},
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def load_yaml_config(name: str) -> dict:
    for candidate in (f"{name}.yaml", f"{name}.example.yaml"):
        path = ROOT / "config" / candidate
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def read_docx_text(path: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        sys.exit("Install python-docx to verify .docx files (pip install -r requirements.txt)")
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def normalize_for_language(text: str) -> set[str]:
    import re
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
    return set(re.findall(r"[a-z0-9]+", ascii_text))


def infer_language(text: str) -> str:
    tokens = normalize_for_language(text)
    scores = {lang: len(tokens & hints) for lang, hints in LANG_HINTS.items()}
    if scores["fr"] > scores["en"]:
        return "fr"
    return "en"


def expected_contacts(library: dict) -> list[str]:
    person = library.get("person", {}) or {}
    contacts = [person.get("name"), person.get("email"), person.get("phone")]
    return [str(item) for item in contacts if item]


def contains_bad_chars(text: str) -> bool:
    return any(ch in text for ch in BAD_CHARS) or any(ch in CONTROL_CHARS for ch in text)


def estimate_pages(text: str, max_lines_per_page: int = 45) -> int:
    """Naive page heuristic: count wrapped paragraph lines, not exact Word pagination."""
    lines = 0
    for paragraph in text.splitlines():
        length = len(paragraph.strip())
        lines += max(1, (length + 89) // 90)
    return max(1, (lines + max_lines_per_page - 1) // max_lines_per_page)


def optional_pdf_text(docx_path: Path) -> tuple[str, str]:
    soffice = shutil.which("soffice")
    pdftotext = shutil.which("pdftotext")
    if not soffice:
        return "", "LibreOffice/soffice not found; skipped PDF extraction."
    if not pdftotext:
        return "", "pdftotext not found; skipped PDF extraction."
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(docx_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            return "", f"LibreOffice conversion failed: {result.stderr.strip() or result.stdout.strip()}"
        pdf_path = tmp_path / f"{docx_path.stem}.pdf"
        if not pdf_path.exists():
            return "", "LibreOffice did not produce a PDF."
        text_path = tmp_path / f"{docx_path.stem}.txt"
        result = subprocess.run([pdftotext, str(pdf_path), str(text_path)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            return "", f"pdftotext failed: {result.stderr.strip()}"
        return text_path.read_text(encoding="utf-8", errors="replace"), "PDF text extracted."


def verify(file_path: Path, offer: dict, library: dict, settings: dict, include_pdf: bool = False) -> dict:
    text = read_docx_text(file_path)
    keywords = offer.get("must_have", []) + offer.get("keywords", [])
    min_ats = float(settings.get("verify", {}).get("min_ats", settings.get("ats", {}).get("pass_threshold", 0.7)))
    max_pages = int(settings.get("cv", {}).get("max_pages", 2))
    contacts = expected_contacts(library)
    ats_result = ats_scorer.score(text, keywords)
    pages = estimate_pages(text)
    language = infer_language(text)
    expected_language = offer.get("language") or "en"

    checks = [
        Check("contact", all(contact in text for contact in contacts), f"required: {', '.join(contacts) or 'none'}"),
        Check("characters", not contains_bad_chars(text), "zero-width/control characters absent"),
        Check("language", language == expected_language, f"expected {expected_language}, detected {language}"),
        Check("ats", ats_result["coverage"] >= min_ats, f"{ats_result['coverage']:.3f} >= {min_ats:.3f}"),
        Check("pages", pages <= max_pages, f"estimated {pages} <= max {max_pages}"),
    ]
    pdf_note = "not requested"
    pdf_text = ""
    if include_pdf:
        pdf_text, pdf_note = optional_pdf_text(file_path)
    return {
        "file": str(file_path),
        "passed": all(check.passed for check in checks),
        "checks": checks,
        "ats": ats_result,
        "estimated_pages": pages,
        "text": text,
        "pdf_text": pdf_text,
        "pdf_note": pdf_note,
    }


def print_report(report: dict) -> None:
    print(f"Verification report: {report['file']}")
    for check in report["checks"]:
        mark = "PASS" if check.passed else "FAIL"
        print(f"[{mark}] {check.name}: {check.detail}")
    print(f"ATS coverage: {report['ats']['coverage']:.0%}")
    if report["ats"]["missing"]:
        print("Missing keywords:")
        for keyword in report["ats"]["missing"]:
            print(f"  - {keyword}")
    print(f"Page estimate: {report['estimated_pages']}")
    print(f"PDF extraction: {report['pdf_note']}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify generated .docx output.")
    parser.add_argument("--file", required=True, help="generated .docx path")
    parser.add_argument("--offer", required=True, help="parsed offer JSON")
    parser.add_argument("--library", default=None, help="experience library YAML; defaults to config fallback")
    parser.add_argument("--settings", default=None, help="settings YAML; defaults to config fallback")
    parser.add_argument("--pdf", action="store_true", help="also try optional docx->pdf text extraction")
    args = parser.parse_args(argv)

    offer = json.loads(Path(args.offer).read_text(encoding="utf-8"))
    library = yaml.safe_load(Path(args.library).read_text(encoding="utf-8")) if args.library else load_yaml_config("experience-library")
    settings = yaml.safe_load(Path(args.settings).read_text(encoding="utf-8")) if args.settings else load_yaml_config("settings")
    report = verify(Path(args.file), offer, library or {}, settings or {}, include_pdf=args.pdf)
    print_report(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
