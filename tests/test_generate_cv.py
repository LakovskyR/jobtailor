import json
import os
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))

import ats_scorer  # noqa: E402


def test_generate_cv_smoke(tmp_path):
    # Force the example library so the test is deterministic and independent of any local,
    # auto-persisted config/experience-library.yaml a real run may have written.
    library = yaml.safe_load((ROOT / "config" / "experience-library.example.yaml").read_text(encoding="utf-8"))
    env = {**os.environ, "JOBTAILOR_LIBRARY_JSON": json.dumps(library)}
    out = tmp_path / "CV_EN.docx"
    subprocess.run(
        ["node", "src/node/generate-cv.js", "--lang", "en", "--offer", "jobs/sample-offer.json", "--out", str(out)],
        check=True,
        env=env,
    )
    offer = json.loads(pathlib.Path("jobs/sample-offer.json").read_text(encoding="utf-8"))
    result = ats_scorer.score(ats_scorer.read_cv_text(str(out)), offer["must_have"] + offer["keywords"])
    assert out.exists()
    assert result["coverage"] >= 0.7
