"""Unit tests for the deterministic ATS scorer."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src" / "python"))

import ats_scorer  # noqa: E402


def test_basic_coverage():
    result = ats_scorer.score("I know SQL and Python.", ["SQL", "Python", "Java"])
    assert result["coverage"] == round(2 / 3, 3)
    assert set(result["present"]) == {"SQL", "Python"}
    assert result["missing"] == ["Java"]


def test_trailing_punctuation_does_not_break_match():
    # regression: "segmentation." must still match the keyword "segmentation"
    result = ats_scorer.score("We did segmentation. And A/B testing.", ["segmentation", "A/B testing"])
    assert result["missing"] == []
    assert result["coverage"] == 1.0


def test_multiword_keyword_requires_all_tokens():
    result = ats_scorer.score("Strong Power user.", ["Power BI"])
    assert result["missing"] == ["Power BI"]


def test_case_insensitive():
    result = ats_scorer.score("python and sql", ["Python", "SQL"])
    assert result["coverage"] == 1.0
