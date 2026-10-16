import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from release_planner import plan_release
from verify_release import VerifiedRelease
from verify_release import formula_pins
from plan_release import clean_version, latest_stable_release


ROOT = Path(__file__).resolve().parents[1]
FORMULA = ROOT / "Formula/sotto.rb"


def release(version="0.9.0", *, draft=False, prerelease=False, assets=None):
    names = assets or [
        "SHA256SUMS",
        "SHA256SUMS.sigstore.json",
        f"sotto-v{version}-aarch64-apple-darwin.tar.gz",
        f"sotto-v{version}-x86_64-apple-darwin.tar.gz",
    ]
    return {
        "tag_name": f"v{version}",
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": name} for name in names],
    }


def verified(version="0.9.0", *, manifest="a" * 64):
    if version == "0.9.0":
        archive_hashes = {
            "sotto-v0.9.0-aarch64-apple-darwin.tar.gz": "0c62436bd0864c3a710c3bef1e62f9281ec794fe6d4263e3288659fa7b9cdc8c",
            "sotto-v0.9.0-x86_64-apple-darwin.tar.gz": "a6c650f02ee09c3cc2418e287a56f96e14266813a55a59c1bc8c6e0db2cf3725",
        }
    else:
        archive_hashes = {
            f"sotto-v{version}-aarch64-apple-darwin.tar.gz": "b" * 64,
            f"sotto-v{version}-x86_64-apple-darwin.tar.gz": "c" * 64,
        }
    return VerifiedRelease(
        version=version,
        manifest_sha256=manifest,
        archive_sha256=archive_hashes,
    )


class ReleasePlannerTests(unittest.TestCase):
    def plan(self, version="0.9.0", **kwargs):
        return plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release(version, **kwargs),
            verified=verified(version),
        )

    def test_current_verified_release_is_a_noop(self):
        result = self.plan()
        self.assertEqual(result["status"], "no-op")
        self.assertEqual(result["version"], "0.9.0")
        self.assertIn("already packaged", result["reason"])

    def test_current_formula_pins_must_match_verified_release(self):
        inputs = verified("0.9.0")
        changed = dict(inputs.archive_sha256)
        changed["sotto-v0.9.0-aarch64-apple-darwin.tar.gz"] = "d" * 64
        result = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.9.0"),
            verified=VerifiedRelease(inputs.version, inputs.manifest_sha256, changed),
        )
        self.assertEqual(result["status"], "failure")
        self.assertIn("current formula pin differs", result["reason"])

    def test_newer_verified_release_returns_repeatable_formula_patch(self):
        metadata = release("0.10.0")
        inputs = verified("0.10.0")
        args = {
            "current_formula": FORMULA.read_text(encoding="utf-8"),
            "release": metadata,
            "verified": inputs,
        }
        first = plan_release(**args)
        second = plan_release(**args)
        self.assertEqual(first["status"], "update")
        self.assertEqual(first["branch"], "update/sotto-v0.10.0")
        self.assertEqual(first["patch"], second["patch"])
        self.assertIn("v0.10.0", first["formula"])
        self.assertIn("b" * 64, first["formula"])
        self.assertIn("c" * 64, first["formula"])
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "sotto.rb"
            candidate.write_text(first["formula"], encoding="utf-8")
            self.assertEqual(set(formula_pins(candidate, "0.10.0").values()), {
                ("https://github.com/getsotto/sotto/releases/download/v0.10.0/sotto-v0.10.0-aarch64-apple-darwin.tar.gz", "b" * 64),
                ("https://github.com/getsotto/sotto/releases/download/v0.10.0/sotto-v0.10.0-x86_64-apple-darwin.tar.gz", "c" * 64),
            })

    def test_prerelease_is_skipped_without_admission(self):
        result = self.plan("0.10.0", prerelease=True)
        self.assertEqual(result["status"], "skip")
        self.assertIn("prereleases", result["reason"])

    def test_draft_release_is_skipped_without_admission(self):
        result = self.plan("0.10.0", draft=True)
        self.assertEqual(result["status"], "skip")
        self.assertIn("draft releases", result["reason"])

    def test_incomplete_release_fails_before_formula_update(self):
        result = self.plan("0.10.0", assets=["SHA256SUMS"])
        self.assertEqual(result["status"], "failure")
        self.assertIn("missing assets", result["reason"])

    def test_duplicate_required_assets_are_rejected(self):
        assets = ["SHA256SUMS", "SHA256SUMS", "SHA256SUMS.sigstore.json", "sotto-v0.10.0-aarch64-apple-darwin.tar.gz", "sotto-v0.10.0-x86_64-apple-darwin.tar.gz"]
        result = self.plan("0.10.0", assets=assets)
        self.assertEqual(result["status"], "failure")
        self.assertIn("duplicate assets", result["reason"])

    def test_verified_inputs_must_match_release_tag(self):
        result = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.10.0"),
            verified=verified("0.11.0"),
        )
        self.assertEqual(result["status"], "failure")
        self.assertIn("do not match", result["reason"])

    def test_held_version_is_blocked(self):
        result = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.10.0"),
            verified=verified("0.10.0"),
            held_versions={"0.10.0": {"reason": "known data migration fault"}},
            manual_retry=True,
        )
        self.assertEqual(result["status"], "held")
        self.assertEqual(result["reason"], "known data migration fault")

    def test_closed_proposal_is_suppressed_until_manual_retry(self):
        args = {
            "current_formula": FORMULA.read_text(encoding="utf-8"),
            "release": release("0.10.0"),
            "verified": verified("0.10.0"),
        }
        initial = plan_release(**args)
        args["proposals"] = {
            "0.10.0": {
                "status": "closed",
                "branch": initial["branch"],
                "formula_sha256": initial["formula_sha256"],
                "manifest_sha256": initial["manifest_sha256"],
            }
        }
        suppressed = plan_release(**args)
        retried = plan_release(**args, manual_retry=True)
        self.assertEqual(suppressed["status"], "skip")
        self.assertIn("closed proposal", suppressed["reason"])
        self.assertEqual(retried["status"], "update")
        self.assertEqual(retried["action"], "reopen")
        self.assertEqual(retried["branch"], initial["branch"])

    def test_manual_retry_requires_a_closed_proposal_record(self):
        result = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.10.0"),
            verified=verified("0.10.0"),
            manual_retry=True,
        )
        self.assertEqual(result["status"], "failure")
        self.assertIn("existing closed proposal", result["reason"])

    def test_open_proposal_is_reused_and_changed_inputs_fail_closed(self):
        args = {
            "current_formula": FORMULA.read_text(encoding="utf-8"),
            "release": release("0.10.0"),
            "verified": verified("0.10.0"),
        }
        initial = plan_release(**args)
        proposal = {
            "status": "open",
            "branch": initial["branch"],
            "formula_sha256": initial["formula_sha256"],
            "manifest_sha256": initial["manifest_sha256"],
        }
        reused = plan_release(**args, proposals={"0.10.0": proposal})
        self.assertEqual(reused["status"], "no-op")
        self.assertEqual(reused["branch"], initial["branch"])
        changed = plan_release(
            **{**args, "verified": verified("0.10.0", manifest="d" * 64)},
            proposals={"0.10.0": proposal},
        )
        self.assertEqual(changed["status"], "failure")
        self.assertIn("inputs changed", changed["reason"])

    def test_older_release_is_not_admitted_as_an_update(self):
        newer = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.11.0"),
            verified=verified("0.11.0"),
        )
        result = plan_release(
            current_formula=newer["formula"],
            release=release("0.10.0"),
            verified=verified("0.10.0"),
        )
        self.assertEqual(result["status"], "skip")
        self.assertIn("older than the packaged", result["reason"])

    def test_newer_release_uses_a_distinct_version_proposal(self):
        older = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.10.0"),
            verified=verified("0.10.0"),
        )
        newer = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.11.0"),
            verified=verified("0.11.0"),
            proposals={"0.10.0": {"status": "open", "branch": older["branch"], "formula_sha256": older["formula_sha256"], "manifest_sha256": older["manifest_sha256"]}},
        )
        self.assertEqual(older["branch"], "update/sotto-v0.10.0")
        self.assertEqual(newer["branch"], "update/sotto-v0.11.0")

    def test_reviewed_rollback_requires_explicit_data_compatibility_evidence(self):
        newer = plan_release(
            current_formula=FORMULA.read_text(encoding="utf-8"),
            release=release("0.10.0"),
            verified=verified("0.10.0"),
        )
        record = {
            "from": "0.10.0",
            "to": "0.9.0",
            "incident": "0.10.0 corrupts project configuration",
            "compatibility_evidence": "https://example.test/recovery/compatibility-report",
            "compatibility_verified": True,
            "reviewed_by": "maintainer",
            "reviewed_at": "2026-10-16",
        }
        result = plan_release(
            current_formula=newer["formula"],
            release=release("0.9.0"),
            verified=verified("0.9.0"),
            rollbacks={"schema_version": 1, "rollbacks": [record]},
        )
        self.assertEqual(result["status"], "update")
        self.assertEqual(result["action"], "rollback")
        self.assertIn("v0.9.0", result["formula"])
        self.assertEqual(
            formula_pins(result["formula"], "0.9.0")["sotto-v0.9.0-aarch64-apple-darwin.tar.gz"][1],
            "0c62436bd0864c3a710c3bef1e62f9281ec794fe6d4263e3288659fa7b9cdc8c",
        )
        record["compatibility_verified"] = False
        rejected = plan_release(
            current_formula=newer["formula"],
            release=release("0.9.0"),
            verified=verified("0.9.0"),
            rollbacks={"schema_version": 1, "rollbacks": [record]},
        )
        self.assertEqual(rejected["status"], "failure")

    def test_explicit_version_is_validated_before_use(self):
        self.assertEqual(clean_version("v0.9.0"), "0.9.0")
        with self.assertRaisesRegex(ValueError, "plain semantic version"):
            clean_version("0.9.0/../../main")

    def test_discovery_chooses_highest_stable_semantic_version(self):
        selected = latest_stable_release([
            {"tag_name": "v0.9.9", "draft": False, "prerelease": False},
            {"tag_name": "v0.10.0", "draft": False, "prerelease": False},
            {"tag_name": "v99.0.0-rc.1", "draft": False, "prerelease": True},
            {"tag_name": "v100.0.0", "draft": True, "prerelease": False},
        ])
        self.assertEqual(selected["tag_name"], "v0.10.0")


if __name__ == "__main__":
    unittest.main()
