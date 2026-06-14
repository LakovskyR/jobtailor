#!/usr/bin/env python3
"""Find relevant job offers for the profile's targeting, across pluggable sources.

Usage:
    python src/python/find_offers.py            # uses config/settings.yaml enabled_sources

Loads adapters from src/python/sources/, queries each with the library's `targeting`,
ranks by fit, prints a ranked list. Ships with a credential-free `sample` source so it runs
out of the box. STATUS: scaffold — ranking is TODO (see CODEX_BUILD.md task P-4).
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Install PyYAML (pip install -r requirements.txt)")

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_yaml(rel: str) -> dict:
    for name in (rel, rel.replace(".yaml", ".example.yaml")):
        p = ROOT / "config" / name
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def load_sources(enabled: list[str]):
    """TODO: import each enabled adapter from src/python/sources/<name>.py (P-4)."""
    from importlib import import_module
    sources = []
    for name in enabled:
        try:
            mod = import_module(f"sources.{name}")
            sources.append(mod.Source())
        except Exception as e:  # noqa: BLE001
            print(f"[warn] source '{name}' unavailable: {e}", file=sys.stderr)
    return sources


def rank(offers: list[dict], targeting: dict) -> list[dict]:
    """Score offers against targeting: title match, boosted keywords, and location."""
    ranked = []
    titles = [str(x).lower() for x in targeting.get("titles", [])]
    boosts = [str(x).lower() for x in targeting.get("keywords_boost", [])]
    locations = [str(x).lower() for x in targeting.get("locations", [])]
    for offer in offers:
        haystack = " ".join(
            str(offer.get(key, ""))
            for key in ("title", "company", "location", "raw_text", "description")
        ).lower()
        haystack += " " + " ".join(map(str, offer.get("must_have", []) + offer.get("keywords", []))).lower()
        score = 0
        reasons = []
        title = str(offer.get("title", "")).lower()
        location = str(offer.get("location", "")).lower()
        for wanted in titles:
            if wanted and (wanted in title or token_overlap(wanted, title) >= 0.5):
                score += 5
                reasons.append(f"title:{wanted}")
        for keyword in boosts:
            if keyword and keyword in haystack:
                score += 2
                reasons.append(f"keyword:{keyword}")
        for wanted_location in locations:
            if wanted_location and (wanted_location in location or wanted_location in haystack):
                score += 3
                reasons.append(f"location:{wanted_location}")
        enriched = dict(offer)
        enriched["fit_score"] = score
        enriched["fit_reasons"] = reasons
        ranked.append(enriched)
    return sorted(ranked, key=lambda item: item.get("fit_score", 0), reverse=True)


def token_overlap(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[a-zà-ÿ0-9]+", left.lower()))
    right_tokens = set(re.findall(r"[a-zà-ÿ0-9]+", right.lower()))
    return len(left_tokens & right_tokens) / (len(left_tokens) or 1)


def main() -> int:
    load_env()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    lib = load_yaml("experience-library.yaml")
    settings = load_yaml("settings.yaml")
    targeting = lib.get("targeting", {})
    enabled = settings.get("find_offers", {}).get("enabled_sources", ["sample"])

    offers: list[dict] = []
    for src in load_sources(enabled):
        offers.extend(src.search(targeting, settings))

    ranked = rank(offers, targeting)[: settings.get("find_offers", {}).get("max_results", 25)]
    json.dump(ranked, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
