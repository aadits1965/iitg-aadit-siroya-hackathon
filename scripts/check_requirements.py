"""Compares every third-party import actually used in src/ and scripts/ against
requirements.txt, so a dependency can never silently work locally (already installed
for some other reason) while being missing from the file a clean clone relies on.

This is exactly the gap that caused this round's rapidfuzz surprise: it IS pinned in
requirements.txt, but had gone missing from this dev sandbox's environment, and
nothing would have caught it quickly if a newly-added import were missing from the
file itself instead. Run directly (`python scripts/check_requirements.py`) or import
check_imports_against_requirements() from a test.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [ROOT / "src", ROOT / "scripts"]
REQUIREMENTS_FILE = ROOT / "requirements.txt"

# Import name -> PyPI distribution name, for the cases where they differ.
IMPORT_TO_PACKAGE = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "pptx": "python-pptx",
}

# First-party top-level packages within this repo -- never third-party.
FIRST_PARTY = {"src", "scripts", "tests", "config"}

STDLIB_MODULES = set(sys.stdlib_module_names) | {"__future__"}


def iter_py_files() -> list[Path]:
    files = []
    for d in SCAN_DIRS:
        files.extend(sorted(d.rglob("*.py")))
    return files


def extract_top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import -- always first-party
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def parse_requirements(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
        if name:
            names.add(name.lower())
    return names


def local_module_names() -> set[str]:
    """Module/package stems that exist as files or directories under src/ or
    scripts/ -- a sibling import like `from generate_readme import x` in
    scripts/generate_deck.py resolves to one of these, not a PyPI package."""
    names = set()
    for d in SCAN_DIRS:
        for path in d.rglob("*.py"):
            names.add(path.stem)
        for path in d.rglob("*"):
            if path.is_dir():
                names.add(path.name)
    return names


def check_imports_against_requirements() -> list[str]:
    """Returns a list of import names used in src/scripts with no matching entry in
    requirements.txt. Empty list means everything used is pinned."""
    required = parse_requirements(REQUIREMENTS_FILE)
    used = set()
    for path in iter_py_files():
        used |= extract_top_level_imports(path)

    third_party = used - STDLIB_MODULES - FIRST_PARTY - local_module_names()
    missing = []
    for name in sorted(third_party):
        package = IMPORT_TO_PACKAGE.get(name, name).lower()
        if package not in required:
            missing.append(name)
    return missing


def main() -> int:
    missing = check_imports_against_requirements()
    if missing:
        print("[FAIL] Imports used in src/ or scripts/ with no matching requirements.txt entry:")
        for name in missing:
            package_hint = IMPORT_TO_PACKAGE.get(name, name)
            print(f"    - import {name!r} (expected package name: {package_hint!r})")
        return 1
    print("[PASS] Every third-party import in src/ and scripts/ is pinned in requirements.txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
