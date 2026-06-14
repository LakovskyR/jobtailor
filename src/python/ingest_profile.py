#!/usr/bin/env python3
"""Onboard a user's CV/cover letter into reviewed, gitignored profile YAML files."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from subprocess import run

try:
    import yaml
except ImportError:
    sys.exit("Install PyYAML (pip install -r requirements.txt)")

try:
    from llm import complete
except ImportError:  # pragma: no cover
    complete = None

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
PROMPTS = ROOT / "prompts"


def read_text_document(path: str) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            sys.exit("Install pdfplumber to read PDFs (pip install -r requirements.txt)")
        with pdfplumber.open(str(p)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError:
            sys.exit("Install python-docx to read DOCX files (pip install -r requirements.txt)")
        return "\n".join(par.text for par in Document(str(p)).paragraphs).strip()
    return p.read_text(encoding="utf-8").strip()


def load_prompt(name: str, placeholders: dict[str, str]) -> tuple[str, str]:
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", value)
    system = _section(text, "## System")
    return system, text


def _section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    match = re.search(r"\n##\s+", text[start:])
    end = start + match.start() if match else len(text)
    return text[start:end].strip()


def llm_yaml(prompt_name: str, placeholders: dict[str, str]) -> dict | None:
    if complete is None:
        return None
    system, user = load_prompt(prompt_name, placeholders)
    try:
        raw = complete(system, user)
    except RuntimeError as exc:
        print(f"[warn] {exc} Falling back to deterministic draft.", file=sys.stderr)
        return None
    raw = strip_fences(raw)
    for parser in (json.loads, yaml.safe_load):
        try:
            data = parser(raw)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            return data
    print("[warn] Could not parse model output; falling back to deterministic draft.", file=sys.stderr)
    return None


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def intake_from_args(args: argparse.Namespace) -> dict:
    if args.targeting:
        return yaml.safe_load(Path(args.targeting).read_text(encoding="utf-8")) or {}
    if args.non_interactive:
        return {
            "titles": split_csv(args.titles or ""),
            "locations": split_csv(args.locations or ""),
            "seniority": args.seniority or "",
            "keywords_boost": split_csv(args.keywords_boost or ""),
        }
    print("Targeting intake (comma-separated where relevant):", file=sys.stderr)
    return {
        "titles": split_csv(input("Target titles: ")),
        "locations": split_csv(input("Locations: ")),
        "seniority": input("Seniority: ").strip(),
        "keywords_boost": split_csv(input("Keywords to boost: ")),
    }


def draft_library(cv_text: str, targeting: dict) -> dict:
    draft = llm_yaml("ingest-cv.md", {"cv_text": cv_text})
    if draft is None:
        draft = heuristic_library(cv_text)
    draft.setdefault("targeting", targeting)
    if not draft.get("targeting"):
        draft["targeting"] = targeting
    return draft


def heuristic_library(text: str) -> dict:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)

    def _is_contact(line: str) -> bool:
        return ("@" in line) or bool(re.search(r"\+?\d[\d\s().\-]{6,}\d", line))

    # Don't let a contact line (email/phone/address) become the name or headline.
    non_contact = [line for line in lines if not _is_contact(line)]
    name = non_contact[0] if non_contact else (lines[0] if lines else "")
    headline = non_contact[1] if len(non_contact) > 1 else ""
    skills = extract_skills(text)
    achievements = []
    for line in lines:
        if re.search(r"\d", line) and len(line.split()) >= 4:
            metric = re.search(r"(\d+[%+]?\+?|\d+\s*%)", line)
            item = {"text": {"en": line}, "tags": infer_tags(line, skills)}
            if metric:
                item["metrics"] = {"delta": metric.group(1), "topic": "achievement"}
            achievements.append(item)
    role = {
        "company": "",
        "title": {"en": ""},
        "start": "",
        "end": "",
        "tags": infer_tags(text, skills),
        "achievements": achievements[:6],
    }
    return {
        "person": {
            "name": name,
            "headline": {"en": headline},
            "location": "",
            "email": email_match.group(0) if email_match else "",
            "links": {"linkedin": "", "portfolio": ""},
            "languages": [],
        },
        "roles": [role],
        "skills": {"technical": skills, "business": []},
        "education": [],
        "certifications": [],
        "targeting": {},
    }


def extract_skills(text: str) -> list[str]:
    known = [
        "Python", "SQL", "Power BI", "Tableau", "dbt", "AWS", "Azure", "Excel",
        "Stakeholder management", "A/B testing", "Forecasting", "ETL",
    ]
    lower = text.lower()
    return [skill for skill in known if skill.lower() in lower]


def infer_tags(text: str, skills: list[str]) -> list[str]:
    tags = [skill.lower().replace(" ", "-") for skill in skills if skill.lower() in text.lower()]
    return tags[:8]


def draft_style(cl_text: str) -> dict:
    draft = llm_yaml("ingest-style.md", {"cover_letter_text": cl_text})
    if draft is not None:
        return draft
    lines = [line.strip() for line in cl_text.splitlines() if line.strip()]
    return {
        "language": detect_language(cl_text),
        "register": "formal",
        "person": "first" if re.search(r"\b(I|me|my|je|mon|ma)\b", cl_text, re.I) else "impersonal",
        "tone": ["professional", "concise"],
        "sentence_length": "medium",
        "paragraph_count": max(3, min(5, len(lines))),
        "salutation": lines[0] if lines else "Dear Hiring Manager,",
        "sign_off": next((line for line in reversed(lines) if "," in line), "Kind regards,"),
        "signature": lines[-1] if lines else "",
        "signature_phrases": [],
        "avoid": ["I am writing to apply for the position of"],
        "notes": "Uses a concise professional structure.",
    }


def detect_language(text: str) -> str:
    fr_hits = len(re.findall(r"\b(et|avec|pour|vous|des|une|dans|je)\b", text.lower()))
    en_hits = len(re.findall(r"\b(and|with|for|you|the|in|I)\b", text.lower()))
    return "fr" if fr_hits > en_hits else "en"


def validate_shape(data: dict, example_name: str) -> None:
    example = yaml.safe_load((CONFIG / example_name).read_text(encoding="utf-8")) or {}
    missing = [key for key in example if key not in data]
    if missing:
        raise ValueError(f"Draft is missing top-level keys required by {example_name}: {', '.join(missing)}")


def review_yaml(label: str, data: dict, edit: bool) -> dict:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    print(f"\n--- Draft {label} ---\n{text}", file=sys.stderr)
    if edit:
        with NamedTemporaryFile("w+", suffix=".yaml", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
        run([*shlex.split(editor, posix=os.name != "nt"), str(tmp_path)], check=False)
        return yaml.safe_load(tmp_path.read_text(encoding="utf-8")) or {}
    answer = input(f"Write this {label}? Type 'yes' to confirm: ").strip().lower()
    if answer != "yes":
        raise SystemExit("Review not approved; no files written.")
    return data


def write_yaml(path: Path, data: dict, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; pass --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {path}", file=sys.stderr)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Draft reviewed profile YAML from a CV and optional cover letter.")
    ap.add_argument("--cv", required=True, help="PDF/DOCX/text CV path")
    ap.add_argument("--cl", help="optional cover letter path for style extraction only")
    ap.add_argument("--targeting", help="YAML file containing the targeting block")
    ap.add_argument("--titles", help="comma-separated target titles for non-interactive intake")
    ap.add_argument("--locations", help="comma-separated locations for non-interactive intake")
    ap.add_argument("--seniority", help="target seniority for non-interactive intake")
    ap.add_argument("--keywords-boost", help="comma-separated keywords to boost")
    ap.add_argument("--non-interactive", action="store_true", help="do not prompt for intake questions")
    ap.add_argument("--edit", action="store_true", help="open a temporary YAML draft for review before confirmation")
    ap.add_argument("--force", action="store_true", help="overwrite existing gitignored config outputs")
    args = ap.parse_args(argv)

    targeting = intake_from_args(args)
    library = draft_library(read_text_document(args.cv), targeting)
    validate_shape(library, "experience-library.example.yaml")
    library = review_yaml("experience-library.yaml", library, args.edit)
    write_yaml(CONFIG / "experience-library.yaml", library, args.force)

    if args.cl:
        style = draft_style(read_text_document(args.cl))
        validate_shape(style, "style-profile.example.yaml")
        style = review_yaml("style-profile.yaml", style, args.edit)
        write_yaml(CONFIG / "style-profile.yaml", style, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
