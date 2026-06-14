#!/usr/bin/env python3
"""Parse a job offer (URL or raw text) into a structured JSON the rest of the pipeline consumes.

Usage:
    python src/python/parse_offer.py "https://example.com/jobs/123"
    python src/python/parse_offer.py --text "We are hiring a Data Analyst ..."

Output (stdout, JSON):
    {
      "title": str, "company": str, "language": "en|fr|...",
      "must_have": [str], "nice_to_have": [str], "keywords": [str],
      "raw_text": str
    }

STATUS: scaffold. The HTML fetch + LLM extraction are TODO (see CODEX_BUILD.md task P-1).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER_AGENT = "Mozilla/5.0 (compatible; jobtailor/0.1; +https://github.com/)"
PASTE_TEXT_FALLBACK = "Couldn't read that page. Paste the description text instead."

try:
    from llm import complete
except ImportError:  # pragma: no cover
    complete = None


@dataclass
class FetchResult:
    text: str
    title: str = ""
    h1: str = ""
    meta_description: str = ""
    fetch_method: str = ""
    error: str = ""


def repair_text(value: str) -> str:
    """Repair common mojibake from scraped pages and normalize line endings."""
    replacements = {
        "Ã¢â‚¬â„¢": "'",
        "Ã¢â‚¬Å“": '"',
        "Ã¢â‚¬ï¿½": '"',
        "Ã¢â‚¬â€": "—",
        "Ã¢â‚¬â€œ": "–",
        "Ã¢â‚¬Â¦": "...",
        "ÃƒÂ©": "é",
        "ÃƒÂ¨": "è",
        "ÃƒÂª": "ê",
        "ÃƒÂ«": "ë",
        "Ãƒ ": "à",
        "ÃƒÂ¢": "â",
        "ÃƒÂ§": "ç",
        "ÃƒÂ´": "ô",
        "ÃƒÂ¹": "ù",
        "ÃƒÂ»": "û",
        "ÃƒÂ¼": "ü",
        "Ãƒâ€°": "É",
        "Ãƒâ‚¬": "À",
        "Ã‚": "",
    }
    text = value or ""
    for broken, fixed in replacements.items():
        text = text.replace(broken, fixed)
    text = unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def compact_text(value: str) -> str:
    return " ".join(repair_text(value).split())


def extract_text_from_html(html: str) -> FetchResult:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("Install beautifulsoup4 (pip install -r requirements.txt)")

    soup = BeautifulSoup(html, "lxml")
    title = compact_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    og_title = compact_text((soup.find("meta", property="og:title") or {}).get("content", ""))
    og_description = repair_text((soup.find("meta", property="og:description") or {}).get("content", ""))
    first_h1 = soup.find("h1")
    h1 = compact_text(first_h1.get_text(" ", strip=True)) if first_h1 else ""

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    content_node = None
    for selector in [
        ".description__text",
        ".show-more-less-html__markup",
        "div.description",
        "article",
        "main",
        ".job-description",
        "#job-description",
    ]:
        content_node = soup.select_one(selector)
        if content_node and compact_text(content_node.get_text(" ", strip=True)):
            break

    if not content_node:
        content_node = max(
            soup.find_all("div"),
            key=lambda node: len(compact_text(node.get_text(" ", strip=True))),
            default=None,
        )

    body = repair_text(content_node.get_text("\n", strip=True)) if content_node else ""
    if og_description:
        body = f"{og_description}\n{body}".strip()
    return FetchResult(text=body, title=og_title or title, h1=h1 or og_title, meta_description=og_description)


def fetch_basic(url: str) -> FetchResult:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests (pip install -r requirements.txt)")

    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    except requests.exceptions.SSLError:
        resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT}, verify=False)
    resp.raise_for_status()
    result = extract_text_from_html(resp.text)
    if not result.text:
        raise RuntimeError("basic scraper extracted no text")
    result.fetch_method = "basic"
    return result


def normalize_firecrawl_payload(data: dict) -> FetchResult:
    candidate = data.get("data", data)
    if isinstance(candidate, list):
        candidate = candidate[0] if candidate else {}
    if not isinstance(candidate, dict):
        raise RuntimeError("Firecrawl returned an unexpected response")

    metadata = candidate.get("metadata", {}) or {}
    text = repair_text(candidate.get("markdown", ""))
    title = compact_text(metadata.get("title", "") or candidate.get("title", ""))
    h1 = compact_text(candidate.get("h1", ""))
    meta_description = repair_text(metadata.get("description", "") or "")
    html = candidate.get("html", "")

    if not text and html:
        extracted = extract_text_from_html(html)
        text = extracted.text
        title = title or extracted.title
        h1 = h1 or extracted.h1
        meta_description = meta_description or extracted.meta_description
    if not text:
        raise RuntimeError("Firecrawl returned no extractable text")
    return FetchResult(text=text, title=title, h1=h1, meta_description=meta_description, fetch_method="firecrawl")


def fetch_firecrawl(url: str) -> FetchResult:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")
    try:
        import requests
    except ImportError:
        sys.exit("Install requests (pip install -r requirements.txt)")
    resp = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown", "html"], "onlyMainContent": True},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Firecrawl failed with HTTP {resp.status_code}")
    return normalize_firecrawl_payload(resp.json())


def score_fetch(result: FetchResult) -> int:
    return (
        len(result.text)
        + (300 if result.title else 0)
        + (300 if result.h1 else 0)
        + (200 if result.meta_description else 0)
    )


def fetch_offer(url: str) -> FetchResult:
    """Fetch a job URL with basic HTML first, then optional Firecrawl."""
    errors: list[str] = []
    successes: list[FetchResult] = []
    for label, handler in [("basic", fetch_basic), ("firecrawl", fetch_firecrawl)]:
        if label == "firecrawl" and not os.environ.get("FIRECRAWL_API_KEY"):
            continue
        try:
            successes.append(handler(url))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
    if successes:
        return max(successes, key=score_fetch)
    return FetchResult(text="", error="; ".join(errors) or "no scraper strategies available")


def fetch_text(url: str) -> str:
    """Fetch the URL and strip HTML to readable text."""
    return fetch_offer(url).text


def parse_title_company(value: str) -> tuple[str, str]:
    text = compact_text(value)
    text = re.sub(r"\s+\|\s+LinkedIn.*$", "", text, flags=re.I)
    patterns = [
        r"^(?P<company>.+?)\s+is hiring\s+(?P<title>.+)$",
        r"^(?P<company>.+?)\s+hiring\s+(?P<title>.+)$",
        r"^(?P<company>.+?)\s+recrute\s+(?P<title>.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return clean_item(match.group("title")), clean_item(match.group("company"))
    for sep in [" | ", " - ", " @ "]:
        if sep in text:
            left, right = [clean_item(part) for part in text.split(sep, 1)]
            if sep == " @ ":
                return left, right
            return left, right
    return "", ""


def parse_url(url: str) -> dict:
    fetched = fetch_offer(url)
    if not fetched.text:
        return normalize_result(
            {
                "raw_text": "",
                "read_error": fetched.error or PASTE_TEXT_FALLBACK,
                "fallback_message": PASTE_TEXT_FALLBACK,
                "source_url": url,
            },
            "",
        )
    result = extract_fields(fetched.text)
    title, company = parse_title_company(fetched.title or fetched.h1)
    # A "{company} hiring {role}" page title (LinkedIn etc.) is a far stronger signal than the
    # body-text guess — let it override rather than only fill when the body guess is empty.
    if company:
        result["company"] = company
        if title:
            result["title"] = title
    elif title and not result.get("title"):
        result["title"] = title
    result["source_url"] = url
    result["fetch_method"] = fetched.fetch_method
    result["page_title"] = fetched.title
    result["meta_description"] = fetched.meta_description
    return normalize_result(result, fetched.text)


def extract_fields(text: str) -> dict:
    """Detect language and extract title/company/requirements/keywords."""
    result = deterministic_extract(text)
    refined = llm_refine(text) if os.environ.get("OPENAI_API_KEY") else None
    if refined:
        refined.setdefault("raw_text", text)
        return normalize_result(refined, text)
    return normalize_result(result, text)


def deterministic_extract(text: str) -> dict:
    flat = re.sub(r"\s+", " ", text).strip()
    language = detect_language(flat)
    title, company = extract_title_company(flat)
    must = extract_requirement_list(flat, required=True)
    nice = extract_requirement_list(flat, required=False)
    keywords = extract_keywords(flat, must + nice)
    return {
        "title": title,
        "company": company,
        "location": extract_location(flat),
        "language": language,
        "must_have": must,
        "nice_to_have": nice,
        "keywords": keywords,
        "raw_text": text,
    }


def detect_language(text: str) -> str:
    lower = text.lower()
    fr = len(re.findall(r"\b(nous|vous|avec|pour|poste|expérience|souhaité|required)\b", lower))
    en = len(re.findall(r"\b(we|you|with|for|role|required|hiring|experience)\b", lower))
    return "fr" if fr > en else "en"


def extract_title_company(text: str) -> tuple[str, str]:
    patterns = [
        r"(?P<company>[A-Z][\w& .'-]{1,80})\s+is hiring\s+(?:an?\s+)?(?P<title>[A-Z][\w& /+-]{2,80})[.!]",
        r"(?P<company>[A-Z][\w& .'-]{1,80})\s+recrute\s+(?:un|une)?\s*(?P<title>[A-ZÉÈÀÂÊÎÔÛÇ][\w& /+À-ÿ-]{2,80})[.!]",
        r"(?:Title|Poste)\s*:\s*(?P<title>[^\n|]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            title = clean_item(match.groupdict().get("title", ""))
            company = clean_item(match.groupdict().get("company", ""))
            return title, company
    first = next((part.strip() for part in re.split(r"[.\n]", text) if part.strip()), "")
    return first[:80], ""


def extract_location(text: str) -> str:
    match = re.search(r"(?:Location|Lieu|Based in|Basé à)\s*:?\s*([A-ZÀ-ÿ][\w ,'/.-]{1,80})", text, re.I)
    return clean_item(match.group(1)) if match else ""


def extract_requirement_list(text: str, required: bool) -> list[str]:
    labels = (
        ["required", "requirements", "must have", "essential", "profil requis", "obligatoire", "requis"]
        if required
        else ["nice to have", "preferred", "a plus", "bonus", "souhaité", "apprécié"]
    )
    stop = (
        ["nice to have", "preferred", "a plus", "bonus", "souhaité", "apprécié"]
        if required
        else ["responsibilities", "about", "benefits", "required", "requirements", "must have"]
    )
    items: list[str] = []
    for label in labels:
        pattern = rf"{re.escape(label)}\s*:?\s*(.+?)(?=(?:{'|'.join(map(re.escape, stop))})\s*:|$)"
        match = re.search(pattern, text, re.I)
        if match:
            items.extend(split_items(match.group(1)))
    if not items and required:
        items = known_skill_hits(text)
    return dedupe(items)


def split_items(value: str) -> list[str]:
    value = re.split(r"[.]\s+(?:Nice|Preferred|Responsibilities|About|Benefits)\b", value, maxsplit=1)[0]
    parts = re.split(r",|;|\s+\|\s+|\n|(?:\s+and\s+)", value)
    return [clean_item(part) for part in parts if clean_item(part)]


def clean_item(value: str) -> str:
    return re.sub(r"^(?:strong|solid|good|excellent)\s+", "", value.strip(" -:.;"), flags=re.I).strip()


def known_skill_hits(text: str) -> list[str]:
    known = [
        "SQL", "Python", "Power BI", "Tableau", "dbt", "AWS", "Azure", "stakeholder management",
        "A/B testing", "forecasting", "dashboards", "segmentation", "ETL", "data analyst",
    ]
    lower = text.lower()
    return [skill for skill in known if skill.lower() in lower]


def extract_keywords(text: str, requirements: list[str]) -> list[str]:
    keywords = [item.lower() for item in requirements]
    keywords.extend(skill.lower() for skill in known_skill_hits(text))
    for phrase in re.findall(r"\b(?:own|build|run|manage|automate|analyze)\s+([a-zA-Z][\w /+-]{3,35})", text, re.I):
        keywords.append(clean_item(phrase).lower())
    return dedupe([kw for kw in keywords if 2 <= len(kw) <= 40])


def dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def llm_refine(text: str) -> dict | None:
    if complete is None:
        return None
    prompt = (ROOT / "prompts" / "parse-offer.md").read_text(encoding="utf-8")
    prompt = prompt.replace("{{offer_text}}", text)
    system = prompt.split("## System", 1)[1].split("## Input", 1)[0].strip()
    try:
        raw = complete(system, prompt)
        return json.loads(strip_fences(raw))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] LLM offer refinement skipped: {exc}", file=sys.stderr)
        return None


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def normalize_result(result: dict, raw_text: str) -> dict:
    normalized = {
        "title": str(result.get("title") or ""),
        "company": str(result.get("company") or ""),
        "location": str(result.get("location") or ""),
        "language": str(result.get("language") or detect_language(raw_text)),
        "must_have": [str(x) for x in result.get("must_have", [])],
        "nice_to_have": [str(x) for x in result.get("nice_to_have", [])],
        "keywords": [str(x).lower() for x in result.get("keywords", [])],
        "raw_text": str(result.get("raw_text") or raw_text),
    }
    for key in ["source_url", "fetch_method", "page_title", "meta_description", "read_error", "fallback_message"]:
        if result.get(key):
            normalized[key] = str(result[key])
    return normalized


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Parse a job offer into structured JSON.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("url", nargs="?", help="job offer URL")
    src.add_argument("--text", help="raw offer text instead of a URL")
    args = ap.parse_args(argv)

    result = extract_fields(args.text) if args.text else parse_url(args.url)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
