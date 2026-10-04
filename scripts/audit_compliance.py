#!/usr/bin/env python
"""Phase 11 compliance audit: walks docs/COMPLIANCE.md's checklist with
evidence, not just a visual check. Exits non-zero (fails loudly) if any
required file is missing -- in particular docs/presentation.pdf, which
LibreOffice (needed to export it from the .pptx) is not installed to produce
in this dev sandbox, so it is EXPECTED to fail here until Aadit exports it
locally (see docs/USER_TODO.md) and it gets committed.

Run this again in Phase 11 after Aadit's local data refresh, per the review
instruction -- don't mark Phase 7/11 passed until a run like this one is
clean.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "requirements.txt",
    "LICENSE",
    "docs/architecture.png",
    "docs/presentation.pptx",
    "docs/presentation.pdf",  # EXPECTED MISSING until Aadit exports it locally -- see docs/USER_TODO.md
]

MAX_FILE_SIZE_MB = 5


def check_required_files() -> list[str]:
    failures = []
    for rel_path in REQUIRED_FILES:
        p = ROOT / rel_path
        if not p.exists():
            failures.append(f"MISSING required file: {rel_path}")
    return failures


def check_file_sizes() -> list[str]:
    failures = []
    for p in ROOT.rglob("*"):
        if ".git" in p.parts or ".venv" in p.parts:
            continue
        if p.is_file() and p.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            failures.append(f"OVERSIZED file (>{MAX_FILE_SIZE_MB}MB): {p.relative_to(ROOT)}")
    return failures


def check_tests_pass() -> list[str]:
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return [f"pytest FAILED (exit {result.returncode}):\n{result.stdout[-2000:]}"]
    return []


def check_no_secrets_committed() -> list[str]:
    failures = []
    for pattern in [".env"]:
        result = subprocess.run(["git", "ls-files", pattern], cwd=ROOT, capture_output=True, text=True)
        if result.stdout.strip():
            failures.append(f"Tracked file matching secret pattern {pattern!r}: {result.stdout.strip()}")
    return failures


def main():
    all_failures = []
    checks = [
        ("Required files present", check_required_files),
        ("No oversized files", check_file_sizes),
        ("No secrets committed", check_no_secrets_committed),
        ("Test suite passes", check_tests_pass),
    ]

    for name, check_fn in checks:
        failures = check_fn()
        status = "PASS" if not failures else "FAIL"
        print(f"[{status}] {name}")
        for f in failures:
            print(f"    - {f}")
        all_failures.extend(failures)

    print()
    if all_failures:
        print(f"AUDIT FAILED: {len(all_failures)} issue(s) found.")
        sys.exit(1)
    else:
        print("AUDIT PASSED.")


if __name__ == "__main__":
    main()
