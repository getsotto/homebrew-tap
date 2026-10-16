import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_formula_version import version_from
from verify_release import VerificationError, formula_pins, read_manifest


class ManifestTests(unittest.TestCase):
    def test_reads_unique_sha256_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "SHA256SUMS"
            manifest.write_text("a" * 64 + "  archive.tar.gz\n", encoding="utf-8")
            self.assertEqual(read_manifest(manifest), {"archive.tar.gz": "a" * 64})

    def test_rejects_duplicate_filenames(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "SHA256SUMS"
            manifest.write_text("a" * 64 + " archive.tar.gz\n" + "b" * 64 + " archive.tar.gz\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "duplicate"):
                read_manifest(manifest)

    def test_rejects_unsafe_paths_and_malformed_entries(self):
        for line in ("a" * 64 + " ../archive.tar.gz\n", "not-a-digest archive.tar.gz\n"):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as temporary:
                manifest = Path(temporary) / "SHA256SUMS"
                manifest.write_text(line, encoding="utf-8")
                with self.assertRaises(VerificationError):
                    read_manifest(manifest)


class FormulaPinTests(unittest.TestCase):
    def test_extracts_architecture_specific_release_pins(self):
        formula = Path(__file__).resolve().parents[1] / "Formula/sotto.rb"
        pins = formula_pins(formula, "0.9.0")
        self.assertEqual(set(pins), {
            "sotto-v0.9.0-aarch64-apple-darwin.tar.gz",
            "sotto-v0.9.0-x86_64-apple-darwin.tar.gz",
        })

    def test_rejects_formula_version_mismatch(self):
        formula = Path(__file__).resolve().parents[1] / "Formula/sotto.rb"
        with self.assertRaisesRegex(VerificationError, "release URLs"):
            formula_pins(formula, "0.9.1")


class VersionAdmissionTests(unittest.TestCase):
    def test_compares_semantic_version_components(self):
        self.assertGreater(
            version_from('url "https://example.com/releases/download/v0.10.0/sotto.tar.gz"'),
            version_from('url "https://example.com/releases/download/v0.9.9/sotto.tar.gz"'),
        )

    def test_rejects_non_semantic_formula_version(self):
        with self.assertRaises(ValueError):
            version_from('url "https://example.com/releases/download/v0.9.0-rc.1/sotto.tar.gz"')


if __name__ == "__main__":
    unittest.main()
