#!/usr/bin/env python3
"""Local CSV application tracker. Deterministic, private, and human-editable."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = [
    "date",
    "company",
    "role",
    "language",
    "offer_url",
    "ats_score",
    "cv_path",
    "cover_letter_path",
    "status",
    "outcome",
    "notes",
]


def default_csv_path() -> Path:
    private_dir = ROOT / "private"
    if private_dir.exists():
        return private_dir / "applications.csv"
    return ROOT / "output" / "applications.csv"


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_row(path: Path, row: dict) -> None:
    ensure_parent(path)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def write_rows_atomic(path: Path, rows: list[dict]) -> None:
    ensure_parent(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in FIELDS})
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def is_duplicate(rows: list[dict], row: dict) -> bool:
    return any(
        existing.get("date") == row.get("date")
        and existing.get("company", "").lower() == row.get("company", "").lower()
        and existing.get("role", "").lower() == row.get("role", "").lower()
        for existing in rows
    )


def load_generation(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def log(args: argparse.Namespace) -> int:
    path = Path(args.csv) if args.csv else default_csv_path()
    generation = load_generation(args.from_generation)
    row = {
        "date": args.date,
        "company": args.company,
        "role": args.role,
        "language": args.lang or generation.get("language", ""),
        "offer_url": args.offer_url or generation.get("offer_url", ""),
        "ats_score": args.ats_score or generation.get("ats_score", ""),
        "cv_path": args.cv_path or generation.get("cv_path", ""),
        "cover_letter_path": args.cover_letter_path or generation.get("cover_letter_path", ""),
        "status": args.status,
        "outcome": args.outcome,
        "notes": args.notes,
    }
    rows = read_rows(path)
    if is_duplicate(rows, row) and not args.force:
        print("Duplicate company+role+date; pass --force to log anyway.", file=sys.stderr)
        return 2
    append_row(path, row)
    print(f"Logged {row['company']} - {row['role']} to {path}")
    return 0


def update(args: argparse.Namespace) -> int:
    path = Path(args.csv) if args.csv else default_csv_path()
    rows = read_rows(path)
    target_index: int | None = None
    if args.row is not None:
        idx = args.row - 1
        if 0 <= idx < len(rows):
            target_index = idx
    else:
        for idx, row in enumerate(rows):
            company_ok = row.get("company", "").lower() == (args.company or "").lower()
            role_ok = row.get("role", "").lower() == (args.role or "").lower()
            if company_ok and role_ok:
                target_index = idx
                break
    if target_index is None:
        print("No matching application row found.", file=sys.stderr)
        return 1
    for field in ("status", "outcome", "notes"):
        value = getattr(args, field)
        if value is not None:
            rows[target_index][field] = value
    write_rows_atomic(path, rows)
    print(f"Updated row {target_index + 1} in {path}")
    return 0


def format_table(rows: list[dict]) -> str:
    headers = ["#", "date", "company", "role", "status", "outcome"]
    table = []
    for idx, row in enumerate(rows, start=1):
        table.append([str(idx), row.get("date", ""), row.get("company", ""), row.get("role", ""), row.get("status", ""), row.get("outcome", "")])
    widths = [len(header) for header in headers]
    for row in table:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(cell.ljust(width) for cell, width in zip(row, widths)) for row in table)
    return "\n".join(lines)


def list_rows(args: argparse.Namespace) -> int:
    path = Path(args.csv) if args.csv else default_csv_path()
    rows = read_rows(path)
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    print(format_table(rows) if rows else "No applications logged.")
    return 0


def stats(args: argparse.Namespace) -> int:
    path = Path(args.csv) if args.csv else default_csv_path()
    rows = read_rows(path)
    status_counts = Counter(row.get("status", "") or "unknown" for row in rows)
    outcome_counts = Counter(row.get("outcome", "") or "none" for row in rows)
    total = len(rows)
    responses = sum(1 for row in rows if row.get("status") in {"response", "interview", "offer"} or row.get("outcome"))
    interviews = sum(1 for row in rows if row.get("status") in {"interview", "offer"} or row.get("outcome") == "interview")
    print(f"Total: {total}")
    print("By status:")
    for key, value in sorted(status_counts.items()):
        print(f"  {key}: {value}")
    print("By outcome:")
    for key, value in sorted(outcome_counts.items()):
        print(f"  {key}: {value}")
    denominator = total or 1
    print(f"Response rate: {responses / denominator:.0%}")
    print(f"Interview rate: {interviews / denominator:.0%}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track job applications in a private CSV.")
    parser.add_argument("--csv", default=None, help="override tracker CSV path")
    sub = parser.add_subparsers(dest="command", required=True)

    log_parser = sub.add_parser("log", help="append an application row")
    log_parser.add_argument("--company", required=True)
    log_parser.add_argument("--role", required=True)
    log_parser.add_argument("--lang", default="")
    log_parser.add_argument("--date", default=date.today().isoformat())
    log_parser.add_argument("--offer-url", default="")
    log_parser.add_argument("--ats-score", default="")
    log_parser.add_argument("--cv-path", default="")
    log_parser.add_argument("--cover-letter-path", default="")
    log_parser.add_argument("--status", default="applied")
    log_parser.add_argument("--outcome", default="")
    log_parser.add_argument("--notes", default="")
    log_parser.add_argument("--from-generation", default=None, help="optional JSON with ats_score/paths from a generation run")
    log_parser.add_argument("--force", action="store_true")
    log_parser.set_defaults(func=log)

    update_parser = sub.add_parser("update", help="update status/outcome/notes by row or company+role")
    update_parser.add_argument("--row", type=int)
    update_parser.add_argument("--company")
    update_parser.add_argument("--role")
    update_parser.add_argument("--status")
    update_parser.add_argument("--outcome")
    update_parser.add_argument("--notes")
    update_parser.set_defaults(func=update)

    list_parser = sub.add_parser("list", help="print logged applications")
    list_parser.add_argument("--status")
    list_parser.set_defaults(func=list_rows)

    stats_parser = sub.add_parser("stats", help="print counts and rates")
    stats_parser.set_defaults(func=stats)
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
