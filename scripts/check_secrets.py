#!/usr/bin/env python3
"""
scripts/check_secrets.py – Scan the repo for leaked keys / tokens.

Run before every git push:
    python scripts/check_secrets.py

Exits 0 if clean, 1 if potential secrets are detected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Patterns ────────────────────────────────────────────────────────────────

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Google API key",          re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Generic secret assign",   re.compile(r"""(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['"][A-Za-z0-9/+=_\-]{16,}['"]""")),
    ("JWT",                     re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("AWS access key",          re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key header",      re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
    ("GCP service account key", re.compile(r'"private_key_id"\s*:\s*"[a-f0-9]{40}"')),
]

# Files / dirs to skip
SKIP_NAMES: set[str] = {
    ".env", ".env.local", ".env.example",
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "check_secrets.py",  # don't flag our own pattern strings
}

SKIP_EXTENSIONS: set[str] = {".pyc", ".pyo", ".whl", ".tar", ".gz", ".zip", ".png", ".jpg"}


# ── Scanner ─────────────────────────────────────────────────────────────────

def scan_file(path: Path) -> list[str]:
    """Return a list of findings for a single file."""
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return findings

    for line_no, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"  ⚠  {path}:{line_no}  [{label}]  {line.strip()[:120]}")
    return findings


def scan_repo(root: Path) -> list[str]:
    """Walk the repo tree and collect all findings."""
    all_findings: list[str] = []
    for item in sorted(root.rglob("*")):
        if any(part in SKIP_NAMES for part in item.parts):
            continue
        if item.suffix in SKIP_EXTENSIONS:
            continue
        if item.is_file():
            all_findings.extend(scan_file(item))
    return all_findings


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    root = Path(__file__).resolve().parent.parent  # AgentArena/
    findings = scan_repo(root)

    if findings:
        print(f"\n🚨  Found {len(findings)} potential secret(s):\n")
        for f in findings:
            print(f)
        print("\nFix these before pushing!\n")
        sys.exit(1)
    else:
        print("✅  No secrets detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
