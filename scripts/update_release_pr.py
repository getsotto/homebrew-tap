#!/usr/bin/env python3
"""Create, reuse, or retry one verified Sotto formula PR per release version."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
REPOSITORY = "getsotto/homebrew-tap"
MARKER = re.compile(
    r"<!-- sotto-release-proposal:v1 version=(?P<version>[0-9.]+) "
    r"manifest_sha256=(?P<manifest>[0-9a-f]{64}) "
    r"formula_sha256=(?P<formula>[0-9a-f]{64}) -->"
)
REQUIRED_CHECKS = {
    "verify signed release inputs",
    "Homebrew style and audit",
    "install and preserve state (macos-15)",
    "install and preserve state (macos-26)",
    "install and preserve state (macos-15-intel)",
    "install and preserve state (macos-26-intel)",
}


class UpdaterError(RuntimeError):
    """The proposal could not be safely prepared or applied."""


def request_json(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise UpdaterError("GitHub token is missing")
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "sotto-homebrew-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise UpdaterError(f"GitHub API {method} {path} failed ({error.code}): {detail}") from error
    return json.loads(raw) if raw else None


def git(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def write_output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")


def run_planner(
    *, version: str | None, cache_dir: Path, proposal_path: Path | None = None,
    manual_retry: bool = False, reuse_cache: bool = False,
) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "scripts/plan_release.py"), "--format", "json"]
    if version:
        command.extend(("--version", version))
        command.extend(("--release-dir" if reuse_cache else "--cache-dir", str(cache_dir)))
    else:
        command.extend(("--cache-dir", str(cache_dir)))
    if proposal_path:
        command.extend(("--proposals", str(proposal_path)))
    if manual_retry:
        command.append("--manual-retry")
    result = subprocess.run(command, cwd=ROOT, check=False, text=True, capture_output=True)
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise UpdaterError(f"release planner did not return a JSON report: {result.stderr[-500:]}") from error
    if result.returncode and report.get("status") != "failure":
        raise UpdaterError(f"release planner failed: {result.stderr[-500:]}")
    return report


def find_proposal(version: str) -> dict[str, Any] | None:
    branch = f"update/sotto-v{version}"
    query = urlencode({"state": "all", "head": f"getsotto:{branch}", "base": "main", "per_page": 100})
    matches = request_json("GET", f"/repos/{REPOSITORY}/pulls?{query}")
    if not isinstance(matches, list):
        raise UpdaterError("GitHub returned an invalid pull request list")
    if len(matches) > 1:
        raise UpdaterError(f"multiple proposals exist for v{version}; resolve the duplicate manually")
    return matches[0] if matches else None


def proposal_checks_pass(head_sha: str) -> bool:
    query = urlencode({"per_page": 100})
    result = request_json("GET", f"/repos/{REPOSITORY}/commits/{head_sha}/check-runs?{query}")
    if not isinstance(result, dict) or not isinstance(result.get("check_runs"), list):
        raise UpdaterError("GitHub returned an invalid proposal check list")
    latest_by_name: dict[str, dict[str, Any]] = {}
    for item in result["check_runs"]:
        name = item.get("name")
        if not isinstance(name, str):
            continue
        previous = latest_by_name.get(name)
        if previous is None or item.get("id", 0) > previous.get("id", 0):
            latest_by_name[name] = item
    return all(
        (run := latest_by_name.get(name)) is not None
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        for name in REQUIRED_CHECKS
    )


def ensure_base_unchanged(base_sha: str) -> None:
    git("fetch", "origin", "main")
    latest_base = git("rev-parse", "FETCH_HEAD", capture=True)
    if latest_base != base_sha:
        raise UpdaterError("main advanced during planning; rerun against the current default branch")


def branch_exists(branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode not in (0, 2):
        raise UpdaterError(f"could not inspect proposal branch: {result.stderr.strip()}")
    return result.returncode == 0


def inspect_branch(branch: str, base_sha: str) -> tuple[str, str]:
    git("fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
    ref = f"origin/{branch}"
    base_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, ref],
        cwd=ROOT,
        check=False,
    )
    if base_is_ancestor.returncode == 1:
        raise UpdaterError("proposal branch is behind current main; update it and rerun the required checks")
    if base_is_ancestor.returncode:
        raise UpdaterError("could not verify the proposal branch base")
    changed = set(git("diff", "--name-only", f"{base_sha}...{ref}", capture=True).splitlines())
    if changed != {"Formula/sotto.rb"}:
        raise UpdaterError("proposal branch contains unexpected files; refusing to overwrite maintainer edits")
    formula = git("show", f"{ref}:Formula/sotto.rb", capture=True)
    return formula, hashlib.sha256(formula.encode("utf-8")).hexdigest()


def proposal_record(pr: dict[str, Any], branch: str, base_sha: str) -> dict[str, Any]:
    state = str(pr.get("state", "")).lower()
    if state not in {"open", "closed"} or pr.get("merged_at"):
        raise UpdaterError("a merged or malformed proposal already exists for this version")
    if pr.get("base", {}).get("ref") != "main" or pr.get("head", {}).get("ref") != branch:
        raise UpdaterError("existing proposal does not target the canonical branch and version branch")
    match = MARKER.search(pr.get("body") or "")
    if not match:
        raise UpdaterError("existing proposal is missing its verified-input marker")
    exists = branch_exists(branch)
    if state == "open" and not exists:
        raise UpdaterError("open proposal branch is missing")
    formula_sha = match.group("formula")
    if exists:
        _, actual_sha = inspect_branch(branch, base_sha)
        if actual_sha != formula_sha:
            raise UpdaterError("proposal formula was edited after creation; refusing to overwrite maintainer changes")
    return {
        "status": state,
        "branch": branch,
        "formula_sha256": formula_sha,
        "manifest_sha256": match.group("manifest"),
        "branch_exists": exists,
    }


def proposal_body(report: dict[str, Any]) -> str:
    marker = (
        f"<!-- sotto-release-proposal:v1 version={report['version']} "
        f"manifest_sha256={report['manifest_sha256']} "
        f"formula_sha256={report['formula_sha256']} -->"
    )
    return (
        f"## Verified Sotto release v{report['version']}\n\n"
        "This update was prepared by the scheduled/manual release planner. The release signature, "
        "checksum manifest, and both Mac archives were verified before the formula pins were changed.\n\n"
        f"Manifest SHA-256: `{report['manifest_sha256']}`\n\n"
        "The required formula checks must pass on this pull request's current head. Review and merge "
        "this change manually; the updater never approves or merges its own proposal.\n\n"
        f"{marker}\n"
    )


def proposal_state_document(version: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "proposals": {
            version: {
                key: record[key]
                for key in ("status", "branch", "formula_sha256", "manifest_sha256")
            }
        },
    }


def apply_report(report: dict[str, Any], pr: dict[str, Any] | None, record: dict[str, Any] | None, base_sha: str) -> bool:
    branch = report["branch"]
    exists = bool(record and record["branch_exists"])
    if not exists and pr is None and branch_exists(branch):
        formula, digest = inspect_branch(branch, base_sha)
        if digest != report["formula_sha256"] or formula != report["formula"]:
            raise UpdaterError("orphan proposal branch differs from the verified candidate; refusing to overwrite it")
        exists = True
    if exists:
        formula, digest = inspect_branch(branch, base_sha)
        if digest != report["formula_sha256"] or formula != report["formula"]:
            raise UpdaterError("proposal branch differs from the deterministic verified formula")
    else:
        if branch_exists(branch):
            raise UpdaterError("proposal branch exists without a matching pull request; investigate before retrying")
        ensure_base_unchanged(base_sha)
        git("switch", "--detach", base_sha)
        git("switch", "-c", branch)
        (ROOT / "Formula/sotto.rb").write_text(report["formula"], encoding="utf-8")
        git("add", "Formula/sotto.rb")
        git(
            "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-s", "-m", f"update sotto formula to v{report['version']}",
        )
        ensure_base_unchanged(base_sha)
        git("push", "--set-upstream", "origin", branch)

    ensure_base_unchanged(base_sha)
    body = proposal_body(report)
    if pr is None:
        request_json("POST", f"/repos/{REPOSITORY}/pulls", {
            "title": f"build: update Sotto to v{report['version']}",
            "head": branch,
            "base": "main",
            "body": body,
            "draft": False,
        })
        return True
    number = pr.get("number")
    if not isinstance(number, int):
        raise UpdaterError("existing proposal has no valid pull request number")
    request_json("PATCH", f"/repos/{REPOSITORY}/pulls/{number}", {"state": "open", "body": body})
    return True


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("GITHUB_REF", "")
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    version = os.environ.get("RELEASE_VERSION", "").strip() or None
    manual_retry = os.environ.get("MANUAL_RETRY", "false").lower() == "true"
    if repository != REPOSITORY or ref != "refs/heads/main" or event not in {"schedule", "workflow_dispatch"}:
        raise UpdaterError("updater may run only on the canonical repository's default branch")
    if event == "workflow_dispatch" and not version:
        raise UpdaterError("manual runs require an explicit published release version")
    if manual_retry and not version:
        raise UpdaterError("manual retry requires an explicit release version")

    git("fetch", "origin", "main")
    base_sha = git("rev-parse", "FETCH_HEAD", capture=True)
    if git("rev-parse", "HEAD", capture=True) != base_sha:
        raise UpdaterError("default branch advanced before the workflow checkout; rerun on the current main")
    cache = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "sotto-release-inputs"
    first = run_planner(version=version, cache_dir=cache)
    if first.get("status") == "failure":
        raise UpdaterError(first.get("reason", "release planning failed"))
    selected = first.get("version")
    write_output(version=selected or "", status=first.get("status", "failure"))
    print(f"Release planning status: {first.get('status')} for {selected}: {first.get('reason')}")
    if first.get("status") != "update":
        write_output(needs_validation="false", recovered="false")
        return 0

    branch = first["branch"]
    pr = find_proposal(selected)
    record = proposal_record(pr, branch, base_sha) if pr else None
    if record:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as state_file:
            json.dump(proposal_state_document(selected, record), state_file)
            proposal_path = Path(state_file.name)
    else:
        proposal_path = None
    try:
        report = run_planner(
            version=selected,
            cache_dir=cache,
            proposal_path=proposal_path,
            manual_retry=manual_retry,
            reuse_cache=True,
        )
    finally:
        if proposal_path:
            proposal_path.unlink(missing_ok=True)
    if report.get("status") == "failure":
        raise UpdaterError(report.get("reason", "proposal policy rejected this release"))
    print(f"Proposal status: {report.get('status')} for {selected}: {report.get('reason')}")
    if report.get("status") != "update":
        if report.get("status") == "no-op" and pr and str(pr.get("state", "")).lower() == "open":
            head_sha = pr.get("head", {}).get("sha")
            if not isinstance(head_sha, str):
                raise UpdaterError("open proposal has no current head commit")
            needs_validation = not proposal_checks_pass(head_sha)
            write_output(
                status="no-op",
                branch=branch,
                needs_validation=str(needs_validation).lower(),
                recovered=str(needs_validation).lower(),
            )
            return 0
        write_output(status=report.get("status", "failure"), needs_validation="false", recovered="false")
        return 0

    needs_validation = apply_report(report, pr, record, base_sha)
    write_output(
        version=selected,
        branch=branch,
        status=report.get("action", "create"),
        needs_validation=str(needs_validation).lower(),
        recovered="true",
    )
    print(f"Prepared ready-for-review proposal for v{selected}: {branch}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (UpdaterError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"release updater failed: {error}", file=sys.stderr)
        raise SystemExit(1)
