"""Adzuna source adapter stub.

Adzuna offers a multi-country REST API documented at https://developer.adzuna.com.
The future implementation should use:
- ADZUNA_APP_ID
- ADZUNA_APP_KEY

Expected endpoint shape: https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
with query parameters such as `app_id`, `app_key`, `what`, `where`, and `results_per_page`.
"""


class Source:
    name = "adzuna"

    def search(self, targeting: dict, settings: dict) -> list[dict]:
        raise NotImplementedError("Adzuna source is documented as a stub for a later sprint.")
