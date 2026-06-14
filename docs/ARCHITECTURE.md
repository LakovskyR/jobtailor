# jobtailor — Architecture

## Principle
One structured profile in, tailored documents out. The **engine is generic**; the only
person-specific input is `config/experience-library.yaml` (gitignored). This separation is what makes
the repo safe to publish: fork it, keep your profile local.

## Data flow

```
config/experience-library.yaml ─┐
                                ├─► tailor ──► generate-cv.js ──► output/cv/*.docx
job offer (URL or text) ─► parse_offer.py ─► offer.json ─┘            │
                                                                     ▼
                                              ats_scorer.py ── CV vs offer ─► coverage % + gaps
generate-cover-letter.js ◄── library + offer ──► output/cover-letters/*.docx
bilingual_audit.py ◄── two-language CVs ──► consistency diff
find_offers.py ◄── targeting (from library) + sources ──► ranked openings
```

## Modules

| Module | Lang | Responsibility |
|---|---|---|
| `src/python/parse_offer.py` | Py | URL/text → `{title, company, language, must_have[], nice_to_have[], keywords[]}` |
| `src/node/generate-cv.js` | Node | Rank achievements vs offer, render a 1–2 page `.docx` in the offer's language |
| `src/node/generate-cover-letter.js` | Node | Compose a tailored letter grounded in the library + offer |
| `src/python/ats_scorer.py` | Py | Keyword coverage of a CV against an offer; lists missing keywords |
| `src/python/bilingual_audit.py` | Py | Diff two language versions for missing roles/claims |
| `src/python/find_offers.py` | Py | Query enabled sources with `targeting`, rank by fit |
| `src/python/sources/` | Py | Pluggable `JobSource` adapters (see below) |

## The tailoring step (where the LLM is used)
Selection and phrasing only. Given the parsed offer and the library, the LLM **ranks** which
achievements/skills to include and **phrases** them for the target language and keywords — it never
invents experience. The OpenAI API is configured in `.env` (`OPENAI_API_KEY`). Everything else
(parsing, scoring, docx rendering, file IO) is deterministic code.

## Offer sources (pluggable, legal by default)
`find_offers.py` loads adapters from `src/python/sources/`. Each implements:

```python
class JobSource:
    name: str
    def search(self, targeting: dict, settings: dict) -> list[Offer]: ...
```

Ship a `sample` adapter (reads a local `jobs/*.json` you paste in) so the repo runs with zero
credentials and no scraping. Adapters that hit a real provider go behind a documented API key and are
opt-in via `settings.find_offers.enabled_sources`. **Do not bundle a LinkedIn scraper** — it breaks
their ToS; leave that to the user's own adapter.

## Non-goals (v1)
No web UI, no MCP server, no auto-apply. CLI scripts only. MCP wrapping is a documented v2 upgrade
(see `worksearch2/archive/planning/MCP_vs_CLI_Decision.md`).
