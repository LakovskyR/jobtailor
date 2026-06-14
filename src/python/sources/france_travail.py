"""France Travail source adapter for the public Offres d'emploi v2 API.

Docs verified against https://francetravail.io/ on 2026-06-13. France Travail currently exposes
OAuth2 client_credentials through entreprise.francetravail.fr and the partner search endpoint under
api.francetravail.io. Keep endpoint/scope constants here so future doc changes are localized.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any

import requests

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2"


class Source:
    name = "france_travail"

    def __init__(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    def search(self, targeting: dict, settings: dict) -> list[dict]:
        client_id = os.environ.get("FRANCE_TRAVAIL_CLIENT_ID")
        client_secret = os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError("FRANCE_TRAVAIL_CLIENT_ID/SECRET are not set")
        max_results = int(settings.get("find_offers", {}).get("max_results", 25))
        params = {
            "range": f"0-{max(0, max_results - 1)}",
            "motsCles": " ".join(targeting.get("titles", [])[:2] or targeting.get("keywords_boost", [])[:3]),
        }
        response = requests.get(
            SEARCH_URL,
            params={k: v for k, v in params.items() if v},
            headers={"Authorization": f"Bearer {self._access_token(client_id, client_secret)}"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return [self._map_offer(item) for item in data.get("resultats", [])]

    def _access_token(self, client_id: str, client_secret: str) -> str:
        if self._token and time.time() < self._expires_at - 30:
            return self._token
        auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        response = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "scope": SCOPE},
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 1500))
        return self._token

    def _map_offer(self, item: dict[str, Any]) -> dict:
        skills = [entry.get("libelle", "") for entry in item.get("competences", []) if entry.get("libelle")]
        qualities = [
            entry.get("libelle", "")
            for entry in item.get("qualitesProfessionnelles", [])
            if entry.get("libelle")
        ]
        description = item.get("description", "")
        return {
            "id": item.get("id", ""),
            "source": self.name,
            "title": item.get("intitule", ""),
            "company": (item.get("entreprise") or {}).get("nom", ""),
            "location": (item.get("lieuTravail") or {}).get("libelle", ""),
            "language": "fr",
            "must_have": skills,
            "nice_to_have": qualities,
            "keywords": [value.lower() for value in skills + qualities],
            "url": item.get("origineOffre", {}).get("urlOrigine", ""),
            "raw_text": description,
        }
