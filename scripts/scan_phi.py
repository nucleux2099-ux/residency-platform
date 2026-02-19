#!/usr/bin/env python3
"""
Lightweight PHI scanner for thesis vault artifacts.

Scans markdown/csv/txt files for high-risk identifiers and prints findings.
Use this as a governance guard before ingestion/analysis snapshots.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_ROOT = REPO_ROOT.parent

INCLUDE_SUFFIXES = {".md", ".csv", ".txt"}
SKIP_DIR_NAMES = {
    ".git",
    ".next",
    ".obsidian",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str


RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "cr_number",
        re.compile(
            r"\|\s*(?:\*\*)?CR\s*No\.?(?:\*\*)?\s*\|\s*\d{6,}\s*\||\bCR\s*No\.?\s*[:\-]\s*\d{6,}",
            re.IGNORECASE,
        ),
    ),
    (
        "mrn_uhid",
        re.compile(r"\b(?:MRN|UHID)\b\s*[:\-]?\s*\d{5,}", re.IGNORECASE),
    ),
    (
        "phone_number",
        re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)"),
    ),
    (
        "address_field",
        re.compile(
            r"^\|\s*(?:\*\*)?Address(?:\*\*)?\s*\|\s*(?!\s*(?:\[\s*REDACTED_ADDRESS\s*\]|[_\-.]+)\s*\|)[^|]{3,}\||"
            r"^\*\*Complete\s+Postal\s+Address:\*\*\s*(?!\s*(?:\[\s*REDACTED_ADDRESS\s*\]|[_\-.]+)\s*$).+|"
            r"^\*\*Address:\*\*\s*(?!\s*(?:\[\s*REDACTED_ADDRESS\s*\]|[_\-.]+)\s*$).+",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "name_field_with_value",
        re.compile(r"\|\s*\*\*Name\*\*\s*\|\s*[A-Za-z][A-Za-z .'-]{1,}", re.IGNORECASE),
    ),
]


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def iter_candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES:
            continue
        files.append(path)
    return files


def scan_file(path: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        for rule_name, pattern in RULES:
            if pattern.search(line):
                findings.append(
                    Finding(
                        path=str(path.relative_to(root)),
                        line=line_number,
                        rule=rule_name,
                        excerpt=line.strip()[:240],
                    )
                )
    return findings


def render_text(findings: list[Finding]) -> str:
    if not findings:
        return "No PHI findings detected."

    lines = [f"PHI findings: {len(findings)}"]
    for item in findings:
        lines.append(f"- {item.path}:{item.line} [{item.rule}] {item.excerpt}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan vault text artifacts for potential PHI.")
    parser.add_argument("--root", type=Path, default=DEFAULT_SCAN_ROOT, help="Root directory to scan.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=100,
        help="Limit printed findings (full scan still runs).",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit non-zero if at least one finding is detected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()

    if not root.exists() or not root.is_dir():
        print(f"Scan root does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    for file_path in iter_candidate_files(root):
        findings.extend(scan_file(file_path, root))

    displayed = findings[: args.max_findings]

    if args.format == "json":
        payload = {
            "root": str(root),
            "total_findings": len(findings),
            "displayed_findings": len(displayed),
            "findings": [asdict(item) for item in displayed],
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(render_text(displayed))
        if len(findings) > len(displayed):
            print(f"... truncated output ({len(findings) - len(displayed)} additional findings).")

    if args.fail_on_findings and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
