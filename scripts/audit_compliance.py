#!/usr/bin/env python
"""Compliance audit: checks the submission's required files and hygiene with
evidence, not just a visual check. Exits non-zero (fails loudly) if any
required file is missing, including docs/presentation.pdf.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_requirements import check_imports_against_requirements  # noqa: E402

REQUIRED_FILES = [
    "README.md",
    "requirements.txt",
    "LICENSE",
    "docs/architecture.png",
    "docs/presentation.pptx",
    "docs/presentation.pdf",
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


def check_requirements_pinned() -> list[str]:
    missing = check_imports_against_requirements()
    return [f"import {name!r} used in src/ or scripts/ but not pinned in requirements.txt" for name in missing]


def main():
    all_failures = []
    checks = [
        ("Required files present", check_required_files),
        ("No oversized files", check_file_sizes),
        ("No secrets committed", check_no_secrets_committed),
        ("All imports pinned in requirements.txt", check_requirements_pinned),
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
