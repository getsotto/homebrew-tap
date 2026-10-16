from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import report_updater_incident
import update_release_pr
from plan_release import read_records


def proposal_body(version="0.10.0", manifest="a" * 64, formula="b" * 64):
    return (
        f"<!-- sotto-release-proposal:v1 version={version} "
        f"manifest_sha256={manifest} formula_sha256={formula} -->"
    )


class ProposalStateTests(unittest.TestCase):
    def test_existing_open_proposal_records_verified_identity(self):
        formula = "class Sotto < Formula\nend\n"
        digest = hashlib.sha256(formula.encode()).hexdigest()
        pr = {
            "state": "open",
            "merged_at": None,
            "base": {"ref": "main"},
            "head": {"ref": "update/sotto-v0.10.0"},
            "body": proposal_body(formula=digest),
        }
        with (
            patch.object(update_release_pr, "branch_exists", return_value=True),
            patch.object(update_release_pr, "inspect_branch", return_value=(formula, digest)),
        ):
            record = update_release_pr.proposal_record(pr, "update/sotto-v0.10.0", "base-sha")
        self.assertEqual(record["status"], "open")
        self.assertEqual(record["formula_sha256"], digest)
        self.assertEqual(record["manifest_sha256"], "a" * 64)

    def test_existing_formula_edits_fail_closed(self):
        original = "class Sotto < Formula\nend\n"
        edited = original + "# maintainer change\n"
        pr = {
            "state": "open",
            "merged_at": None,
            "base": {"ref": "main"},
            "head": {"ref": "update/sotto-v0.10.0"},
            "body": proposal_body(formula=hashlib.sha256(original.encode()).hexdigest()),
        }
        with (
            patch.object(update_release_pr, "branch_exists", return_value=True),
            patch.object(
                update_release_pr,
                "inspect_branch",
                return_value=(edited, hashlib.sha256(edited.encode()).hexdigest()),
            ),
        ):
            with self.assertRaisesRegex(update_release_pr.UpdaterError, "edited after creation"):
                update_release_pr.proposal_record(pr, "update/sotto-v0.10.0", "base-sha")

    def test_old_proposal_branch_is_not_treated_as_current_base(self):
        result = subprocess.CompletedProcess(args=[], returncode=1)
        with (
            patch.object(update_release_pr, "git") as git,
            patch.object(update_release_pr.subprocess, "run", return_value=result),
        ):
            with self.assertRaisesRegex(update_release_pr.UpdaterError, "behind current main"):
                update_release_pr.inspect_branch("update/sotto-v0.10.0", "current-main")
        git.assert_called_once()

    def test_proposal_body_carries_deterministic_review_metadata(self):
        report = {
            "version": "0.10.0",
            "manifest_sha256": "a" * 64,
            "formula_sha256": "b" * 64,
        }
        body = update_release_pr.proposal_body(report)
        match = update_release_pr.MARKER.search(body)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("version"), "0.10.0")
        self.assertIn("never approves or merges", body)

    def test_temporary_proposal_state_uses_the_planner_schema(self):
        record = {
            "status": "open",
            "branch": "update/sotto-v0.10.0",
            "formula_sha256": "b" * 64,
            "manifest_sha256": "a" * 64,
            "branch_exists": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proposals.json"
            path.write_text(
                json.dumps(update_release_pr.proposal_state_document("0.10.0", record)),
                encoding="utf-8",
            )
            parsed = read_records(path, "proposals", {})
        self.assertEqual(parsed["0.10.0"]["branch"], record["branch"])

    def test_incomplete_or_failed_required_checks_request_a_dispatch(self):
        response = {"check_runs": [
            {"id": index, "name": name, "status": "completed", "conclusion": "success"}
            for index, name in enumerate(update_release_pr.REQUIRED_CHECKS, start=1)
        ]}
        with patch.object(update_release_pr, "request_json", return_value=response):
            self.assertTrue(update_release_pr.proposal_checks_pass("head-sha"))
        response["check_runs"][0]["conclusion"] = "failure"
        with patch.object(update_release_pr, "request_json", return_value=response):
            self.assertFalse(update_release_pr.proposal_checks_pass("head-sha"))

    def test_later_failed_rerun_overrides_an_older_success(self):
        name = next(iter(update_release_pr.REQUIRED_CHECKS))
        response = {"check_runs": [
            {"id": 10, "name": name, "status": "completed", "conclusion": "success"},
            {"id": 11, "name": name, "status": "completed", "conclusion": "failure"},
            *[
                {"id": index, "name": other, "status": "completed", "conclusion": "success"}
                for index, other in enumerate(update_release_pr.REQUIRED_CHECKS - {name}, start=12)
            ],
        ]}
        with patch.object(update_release_pr, "request_json", return_value=response):
            self.assertFalse(update_release_pr.proposal_checks_pass("head-sha"))

    def test_older_failed_check_does_not_override_the_latest_success(self):
        name = next(iter(update_release_pr.REQUIRED_CHECKS))
        response = {"check_runs": [
            {"id": 10, "name": name, "status": "completed", "conclusion": "failure"},
            {"id": 11, "name": name, "status": "completed", "conclusion": "success"},
            *[
                {"id": index, "name": other, "status": "completed", "conclusion": "success"}
                for index, other in enumerate(update_release_pr.REQUIRED_CHECKS - {name}, start=12)
            ],
        ]}
        with patch.object(update_release_pr, "request_json", return_value=response):
            self.assertTrue(update_release_pr.proposal_checks_pass("head-sha"))

    def test_verified_orphan_branch_is_reused_after_pull_request_api_failure(self):
        formula = "class Sotto < Formula\nend\n"
        report = {
            "version": "0.10.0",
            "branch": "update/sotto-v0.10.0",
            "formula": formula,
            "formula_sha256": hashlib.sha256(formula.encode()).hexdigest(),
            "manifest_sha256": "a" * 64,
        }
        with (
            patch.object(update_release_pr, "branch_exists", return_value=True),
            patch.object(update_release_pr, "inspect_branch", return_value=(formula, report["formula_sha256"])),
            patch.object(update_release_pr, "ensure_base_unchanged"),
            patch.object(update_release_pr, "request_json") as request,
        ):
            self.assertTrue(update_release_pr.apply_report(report, None, None, "base-sha"))
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertEqual(request.call_args.args[1], "/repos/getsotto/homebrew-tap/pulls")

    def test_orphan_branch_with_different_formula_is_never_overwritten(self):
        formula = "class Sotto < Formula\nend\n"
        report = {
            "version": "0.10.0",
            "branch": "update/sotto-v0.10.0",
            "formula": formula,
            "formula_sha256": hashlib.sha256(formula.encode()).hexdigest(),
            "manifest_sha256": "a" * 64,
        }
        with (
            patch.object(update_release_pr, "branch_exists", return_value=True),
            patch.object(update_release_pr, "inspect_branch", return_value=(formula + "# edit\n", "c" * 64)),
            patch.object(update_release_pr, "request_json") as request,
        ):
            with self.assertRaisesRegex(update_release_pr.UpdaterError, "orphan proposal branch differs"):
                update_release_pr.apply_report(report, None, None, "base-sha")
        request.assert_not_called()


class IncidentReporterTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "getsotto/homebrew-tap",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_EVENT_NAME": "schedule",
            "RUN_URL": "https://github.test/run/123",
            "CANDIDATE_VERSION": "0.10.0",
            "FAILURE_STAGE": "validation",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_repeated_scheduled_failures_update_the_same_incident(self):
        issue = {"number": 17, "body": report_updater_incident.MARKER}
        with (
            patch.object(report_updater_incident, "open_incidents", return_value=[issue]),
            patch.object(report_updater_incident, "ensure_label") as ensure_label,
            patch.object(report_updater_incident, "request") as request,
        ):
            self.assertEqual(report_updater_incident.main(), 0)
        ensure_label.assert_called_once()
        self.assertEqual(request.call_count, 2)
        self.assertIn("/issues/17", request.call_args_list[0].args[1])
        self.assertIn("/comments", request.call_args_list[1].args[1])

    def test_first_failure_creates_one_labelled_issue(self):
        with (
            patch.object(report_updater_incident, "open_incidents", return_value=[]),
            patch.object(report_updater_incident, "ensure_label"),
            patch.object(report_updater_incident, "request", return_value={"number": 18}) as request,
        ):
            self.assertEqual(report_updater_incident.main(), 0)
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertEqual(request.call_args.args[1], "/repos/getsotto/homebrew-tap/issues")
        self.assertEqual(request.call_args.args[2]["labels"], [report_updater_incident.LABEL])

    def test_incident_cannot_close_without_confirmed_recovery(self):
        os.environ["INCIDENT_MODE"] = "recover"
        os.environ["CONFIRMED_RECOVERY"] = "false"
        with patch.object(report_updater_incident, "open_incidents", return_value=[]):
            with self.assertRaisesRegex(report_updater_incident.IncidentError, "requires a confirmed"):
                report_updater_incident.main()

    def test_confirmed_recovery_closes_the_open_incident(self):
        os.environ["INCIDENT_MODE"] = "recover"
        os.environ["CONFIRMED_RECOVERY"] = "true"
        issue = {"number": 19, "body": report_updater_incident.MARKER}
        with (
            patch.object(report_updater_incident, "open_incidents", return_value=[issue]),
            patch.object(report_updater_incident, "request") as request,
        ):
            self.assertEqual(report_updater_incident.main(), 0)
        self.assertIn("/comments", request.call_args_list[0].args[1])
        self.assertEqual(request.call_args_list[1].args[2], {"state": "closed"})


if __name__ == "__main__":
    unittest.main()
