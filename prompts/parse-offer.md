# Prompt — parse job offer → structured JSON (P-1)

Optional LLM refinement step in `parse_offer.py`, after the deterministic keyword pass.

## System
You extract structured fields from a job advert. Use ONLY information present in the text. Do not
infer salary, seniority, or requirements that aren't stated. Detect the advert's language.

## Input
```
{{offer_text}}
```

## Task
Return JSON matching `jobs/sample-offer.json`:
```json
{
  "title": "", "company": "", "location": "", "language": "en|fr|...",
  "must_have": [], "nice_to_have": [], "keywords": [], "raw_text": "<verbatim>"
}
```
- `must_have` vs `nice_to_have`: split by the advert's own framing ("required"/"essential" vs
  "a plus"/"nice to have"). If unsplittable, put everything in `must_have`.
- `keywords`: SHORT ATS terms only — single words or 2-3 word skills/tools/domains, lowercase
  (e.g. "propriété intellectuelle", "contrats", "sql"). NEVER full sentences or requirement phrases.

## Rules
Output **valid JSON only**, no commentary, no fences. Always include `raw_text`.
