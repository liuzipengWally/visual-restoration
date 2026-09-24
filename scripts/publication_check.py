#!/usr/bin/env python3
"""Check a skill tree for common accidental publication leaks.

This is a conservative release sanity check, not a DLP system. It intentionally
does not contain project-specific deny-lists so the public package stays
portable; reviewers must still inspect screenshots, archives and provenance.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
CREDENTIAL_URL = re.compile(r"https?://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)
ABSOLUTE_PATH = re.compile(r"/(?:Users|home|private|var/folders|tmp)/|^[A-Za-z]:\\\\")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PRIVATE) KEY-----")
TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})"
)


def files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        yield path


def check(root: Path) -> list[str]:
    findings: list[str] = []
    for path in files(root):
        rel = path.relative_to(root)
        if path.name == ".DS_Store" or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            findings.append(f"{rel}: generated or filesystem metadata must not ship")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, label in (
            (EMAIL, "email-like address"),
            (CREDENTIAL_URL, "credential-bearing URL"),
            (ABSOLUTE_PATH, "absolute local path"),
            (PRIVATE_KEY, "private-key marker"),
            (TOKEN, "credential/token pattern"),
        ):
            if pattern.search(text):
                findings.append(f"{rel}: {label}")
    return findings


def main(argv: list[str] | None = None) -> int:
    target = Path((argv or sys.argv[1:] or ["."])[0]).resolve()
    if not target.is_dir():
        print(f"publication-check: target is not a directory: {target}")
        return 2
    findings = check(target)
    if findings:
        print(f"publication-check: FAIL ({len(findings)} finding(s))")
        print("\n".join(findings))
        return 1
    print(f"publication-check: PASS — {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
