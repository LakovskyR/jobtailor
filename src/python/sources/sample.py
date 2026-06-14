"""Sample, credential-free job source: reads offers you paste into jobs/*.json.

Lets the repo run end-to-end with no scraping and no API keys. Real adapters (a public job
board API, etc.) implement the same Source.search() interface and live alongside this file.
Do NOT add a LinkedIn scraper here — it breaks their ToS.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class Source:
    name = "sample"

    def search(self, targeting: dict, settings: dict) -> list[dict]:
        jobs_dir = ROOT / "jobs"
        offers: list[dict] = []
        for f in sorted(jobs_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            offers.extend(data if isinstance(data, list) else [data])
        return offers
