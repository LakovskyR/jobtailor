import csv
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run_tracker(csv_path, *args):
    return subprocess.run(
        [sys.executable, "src/python/tracker.py", "--csv", str(csv_path), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_tracker_log_update_list_stats_round_trip(tmp_path):
    csv_path = tmp_path / "applications.csv"

    result = run_tracker(csv_path, "log", "--company", "Acme", "--role", "Data Scientist", "--lang", "en")
    assert result.returncode == 0, result.stderr
    assert csv_path.exists()

    duplicate = run_tracker(csv_path, "log", "--company", "Acme", "--role", "Data Scientist", "--lang", "en")
    assert duplicate.returncode == 2
    assert "Duplicate" in duplicate.stderr

    result = run_tracker(csv_path, "update", "--company", "Acme", "--role", "Data Scientist", "--status", "interview", "--outcome", "screen", "--notes", "Recruiter call")
    assert result.returncode == 0, result.stderr

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
      rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "interview"
    assert rows[0]["outcome"] == "screen"

    listed = run_tracker(csv_path, "list", "--status", "interview")
    assert listed.returncode == 0
    assert "Acme" in listed.stdout

    stats = run_tracker(csv_path, "stats")
    assert stats.returncode == 0
    assert "interview: 1" in stats.stdout
    assert "Interview rate: 100%" in stats.stdout
