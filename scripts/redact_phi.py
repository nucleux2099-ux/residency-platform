#!/usr/bin/env python3
"""
Redact common PHI patterns in markdown files.

This utility targets field/value style identifiers used in thesis documents.
It is intentionally conservative and only edits markdown files.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_ROOT = REPO_ROOT.parent

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
class FileRedactionResult:
    path: Path
    replacements: int


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def iter_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if should_skip(path):
            continue
        files.append(path)
    return files


def _is_placeholder(value: str) -> bool:
    token = value.strip()
    if not token:
        return True
    upper = token.upper()
    if "REDACTED" in upper:
        return True
    if re.fullmatch(r"[_\-\s.]+", token):
        return True
    if token.lower() in {"na", "n/a", "none", "data not available", "not available"}:
        return True
    return False


def _replace_table_value(text: str, field_regex: str, replacement: str) -> tuple[str, int]:
    pattern = re.compile(rf"(^\|\s*(?:\*\*)?{field_regex}(?:\*\*)?\s*\|)\s*([^|]+?)\s*(\|.*$)", re.MULTILINE | re.IGNORECASE)
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        value = match.group(2)
        if _is_placeholder(value):
            return match.group(0)
        changed += 1
        return f"{match.group(1)} {replacement} {match.group(3)}"

    return pattern.sub(repl, text), changed


def _replace_labeled_value(text: str, label_regex: str, replacement: str) -> tuple[str, int]:
    pattern = re.compile(rf"(^\*\*{label_regex}:\*\*\s*)(.+)$", re.MULTILINE | re.IGNORECASE)
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        value = match.group(2).strip()
        if _is_placeholder(value):
            return match.group(0)
        changed += 1
        return f"{match.group(1)}{replacement}"

    return pattern.sub(repl, text), changed


def _replace_phone_numbers(text: str) -> tuple[str, int]:
    pattern = re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)")
    updated, count = pattern.subn("[REDACTED_PHONE]", text)
    return updated, count


def redact_text(text: str) -> tuple[str, int]:
    total = 0
    updated = text

    for field, replacement in (
        (r"Patient\s+Name", "[REDACTED_NAME]"),
        (r"Name", "[REDACTED_NAME]"),
        (r"CR\s*No\.?", "[REDACTED_CR]"),
        (r"Contact\s*No\.?", "[REDACTED_PHONE]"),
        (r"Address", "[REDACTED_ADDRESS]"),
    ):
        updated, count = _replace_table_value(updated, field, replacement)
        total += count

    for label, replacement in (
        (r"Name\s+of\s+Participant", "[REDACTED_NAME]"),
        (r"Patient\s+Name", "[REDACTED_NAME]"),
        (r"CR\s*No\.?", "[REDACTED_CR]"),
        (r"Complete\s+Postal\s+Address", "[REDACTED_ADDRESS]"),
        (r"Address", "[REDACTED_ADDRESS]"),
        (r"Contact\s*No\.?", "[REDACTED_PHONE]"),
    ):
        updated, count = _replace_labeled_value(updated, label, replacement)
        total += count

    updated, count = _replace_phone_numbers(updated)
    total += count

    return updated, total


def redact_markdown_file(path: Path) -> int:
    original = path.read_text(encoding="utf-8", errors="ignore")
    updated, replacements = redact_text(original)
    if replacements > 0 and updated != original:
        path.write_text(updated, encoding="utf-8")
    return replacements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redact PHI fields from markdown files.")
    parser.add_argument("--root", type=Path, default=DEFAULT_SCAN_ROOT, help="Root directory to process.")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Root does not exist: {root}")

    results: list[FileRedactionResult] = []
    for path in iter_markdown_files(root):
        original = path.read_text(encoding="utf-8", errors="ignore")
        updated, replacements = redact_text(original)
        if replacements <= 0:
            continue
        if not args.dry_run and updated != original:
            path.write_text(updated, encoding="utf-8")
        results.append(FileRedactionResult(path=path, replacements=replacements))

    total_replacements = sum(item.replacements for item in results)
    print(f"Files changed: {len(results)}")
    print(f"Total replacements: {total_replacements}")
    for item in results[:80]:
        print(f"- {item.path.relative_to(root)}: {item.replacements}")
    if len(results) > 80:
        print(f"... truncated output ({len(results) - 80} more files)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

