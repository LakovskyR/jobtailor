import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src" / "python"))

import bilingual_audit  # noqa: E402


def test_bilingual_audit_flags_missing_metric():
    left = "Analytics Lead\nCut reporting time 35% with SQL."
    right = "Responsable Analytics\nRéduit le temps de reporting avec SQL."
    report = bilingual_audit.audit(left, right, "en", "fr")
    assert report["metric_mismatches"]["fr"] == ["35%"]
    assert bilingual_audit.has_issues(report)


def test_bilingual_audit_accepts_matching_metric():
    left = "Analytics Lead\nCut reporting time 35% with SQL."
    right = "Responsable Analytics\nRéduit le temps de reporting 35% avec SQL."
    report = bilingual_audit.audit(left, right, "en", "fr")
    assert report["metric_mismatches"]["fr"] == []
