import json
import pathlib
import sys

import yaml
from docx import Document

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))

import verify_output  # noqa: E402


def write_docx(path, paragraphs):
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def test_verify_output_passes_good_docx(tmp_path):
    offer = json.loads((ROOT / "jobs" / "sample-offer.json").read_text(encoding="utf-8"))
    library = yaml.safe_load((ROOT / "config" / "experience-library.example.yaml").read_text(encoding="utf-8"))
    settings = yaml.safe_load((ROOT / "config" / "settings.example.yaml").read_text(encoding="utf-8"))
    path = tmp_path / "good.docx"
    write_docx(
        path,
        [
            "Alex Doe",
            "Paris, France | alex.doe@example.com",
            "Data analyst experience with SQL, Python, Power BI, stakeholder management.",
            "Built dashboards, segmentation, A/B testing, and ETL pipelines.",
        ],
    )

    report = verify_output.verify(path, offer, library, settings)

    assert report["passed"]
    assert report["ats"]["coverage"] >= 0.7


def test_verify_output_fails_missing_contact_and_ats(tmp_path):
    offer = json.loads((ROOT / "jobs" / "sample-offer.json").read_text(encoding="utf-8"))
    library = yaml.safe_load((ROOT / "config" / "experience-library.example.yaml").read_text(encoding="utf-8"))
    settings = yaml.safe_load((ROOT / "config" / "settings.example.yaml").read_text(encoding="utf-8"))
    path = tmp_path / "broken.docx"
    write_docx(path, ["Anonymous", "General marketing background."])

    report = verify_output.verify(path, offer, library, settings)

    assert not report["passed"]
    failed = {check.name for check in report["checks"] if not check.passed}
    assert "contact" in failed
    assert "ats" in failed
