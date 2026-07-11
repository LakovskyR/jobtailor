# Review Prompt

Review this {{kind}} draft before it is written.

Return JSON only:

```json
{
  "issues": [
    { "type": "fabrication|coverage_gap|language_drift|structure", "detail": "short actionable finding" }
  ],
  "edits": {
    "drop": [{ "role": "company name or role index", "achievementId": "achievement id or index" }],
    "rephrase": [{ "role": "company name or role index", "achievementId": "achievement id or index", "text": "replacement text grounded in the same achievement" }],
    "reorder": [{ "role": "company name or role index", "achievementIds": ["existing achievement ids or indexes in desired order"] }]
  }
}
```

Flag only:
- Claims, metrics, skills, tools, employers, degrees, certifications, or outcomes that are not grounded in the library.
- Must-have or keyword coverage gaps that can be fixed by selecting real facts from the library.
- Text that is not in the offer language.
- Length or structure problems that would make the document weaker.

Do not suggest invented experience. If the library cannot support a missing requirement, report the gap but do not fill it.

For `kind = cv`, use `edits` only for changes that can be expressed against existing CV inputs:
- `drop`: remove an existing achievement from an existing role.
- `rephrase`: rewrite an existing achievement without adding any new claim, metric, skill, tool, employer, or outcome.
- `reorder`: reorder existing achievements inside an existing role.

Never add a new role, achievement, metric, or skill in `edits`. Do not include replacement text that relies on facts outside the library. If a concern cannot be represented by drop/rephrase/reorder of existing items, leave `edits` empty for that concern and report it in `issues`.

For non-CV documents, `edits` may be empty; the calling code will request one prose revision separately when issues exist.

## Offer

{{offer}}

## Library

{{library}}

## Style Profile

{{style_profile}}

## Draft

{{draft_text}}
