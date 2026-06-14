import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src" / "python"))

import find_offers  # noqa: E402


def test_rank_scores_title_keywords_and_location():
    targeting = {
        "titles": ["Data Analyst"],
        "locations": ["Paris"],
        "keywords_boost": ["python", "sql"],
    }
    offers = [
        {"title": "Senior Data Analyst", "location": "Paris", "keywords": ["python"], "raw_text": "SQL"},
        {"title": "Marketing Manager", "location": "Berlin", "keywords": [], "raw_text": ""},
    ]
    ranked = find_offers.rank(offers, targeting)
    assert ranked[0]["title"] == "Senior Data Analyst"
    assert ranked[0]["fit_score"] > ranked[1]["fit_score"]
    assert "title:data analyst" in ranked[0]["fit_reasons"]
