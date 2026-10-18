"""Every third-party import under src/ or scripts/ must be pinned in
requirements.txt -- this is what caught rapidfuzz being pinned in the file but
missing from this dev sandbox's actual environment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_requirements import (  # noqa: E402
    check_imports_against_requirements,
    extract_top_level_imports,
    parse_requirements,
)


class TestRealRepoHasNoGaps:
    def test_every_import_in_src_and_scripts_is_pinned(self):
        missing = check_imports_against_requirements()
        assert missing == [], (
            f"These imports are used in src/ or scripts/ but have no matching "
            f"requirements.txt entry: {missing}"
        )


class TestDetectorCatchesRealGaps:
    """Proves the detector isn't a no-op -- it must actually flag a known-missing
    package, not just always pass."""

    def test_flags_an_import_name_pypi_mismatch_if_unmapped(self, tmp_path):
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.32.3\n")  # yaml/pyyaml deliberately absent

        src_file = tmp_path / "uses_yaml.py"
        src_file.write_text("import yaml\nimport requests\n")

        required = parse_requirements(req_file)
        used = extract_top_level_imports(src_file)
        assert "yaml" in used
        # yaml isn't in the stub requirements file at all (as "pyyaml" or "yaml")
        assert "pyyaml" not in required
        assert "yaml" not in required

    def test_parse_requirements_strips_version_pins(self, tmp_path):
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("# comment\nfoo==1.2.3\nbar>=4.5\n\nbaz\n")
        assert parse_requirements(req_file) == {"foo", "bar", "baz"}

    def test_extract_top_level_imports_skips_relative_imports(self, tmp_path):
        src_file = tmp_path / "mod.py"
        src_file.write_text("from . import sibling\nfrom .pkg import thing\nimport os\n")
        tree_names = extract_top_level_imports(src_file)
        assert tree_names == {"os"}
