#!/usr/bin/env python3
"""Create/update the scheduled updater incident or close it after confirmed recovery."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"
REPOSITORY = "getsotto/homebrew-tap"
LABEL = "sotto-release-updater-failure"
TITLE = "Scheduled Sotto release updater failed"
MARKER = "<!-- sotto-release-updater-incident:v1 -->"


class IncidentError(RuntimeError):
    pass


def request(method: str, path: str, body: dict | None = None) -> object:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise IncidentError("GitHub token is missing")
    data = json.dumps(body).encode() if body is not None else None
    req = Request(
        API + path,
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
        with urlopen(req, timeout=30) as response:
            raw = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise IncidentError(f"GitHub API {method} {path} failed ({error.code}): {detail}") from error
    return json.loads(raw) if raw else None


def open_incidents() -> list[dict]:
    query = urlencode({"state": "open", "labels": LABEL, "per_page": 100})
    issues = request("GET", f"/repos/{REPOSITORY}/issues?{query}")
    if not isinstance(issues, list):
        raise IncidentError("GitHub returned an invalid incident list")
    return [issue for issue in issues if "pull_request" not in issue and MARKER in (issue.get("body") or "")]


def ensure_label() -> None:
    try:
        request("POST", f"/repos/{REPOSITORY}/labels", {
            "name": LABEL,
            "color": "b60205",
            "description": "Scheduled Sotto release updater incident",
        })
    except IncidentError as error:
        if "(422)" not in str(error):
            raise


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("GITHUB_REF", "")
    if repository != REPOSITORY or ref != "refs/heads/main":
        raise IncidentError("incident reporting is restricted to the canonical tap default branch")
    mode = os.environ.get("INCIDENT_MODE", "failure")
    incidents = open_incidents()
    if len(incidents) > 1:
        raise IncidentError("multiple open updater incidents exist; deduplication needs maintainer attention")
    run_url = os.environ.get("RUN_URL", "")
    if mode == "recover":
        if os.environ.get("CONFIRMED_RECOVERY") != "true":
            raise IncidentError("incident closure requires a confirmed successful proposal and current-head checks")
        if incidents:
            issue = incidents[0]
            request("POST", f"/repos/{REPOSITORY}/issues/{issue['number']}/comments", {
                "body": f"The updater completed the same proposal path and current-head formula checks passed. Recovery confirmed by {run_url}.",
            })
            request("PATCH", f"/repos/{REPOSITORY}/issues/{issue['number']}", {"state": "closed"})
            print(f"Closed updater incident #{issue['number']} after confirmed recovery.")
        else:
            print("No open updater incident to recover.")
        return 0
    if mode != "failure":
        raise IncidentError("unknown incident mode")
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        raise IncidentError("failure incidents are created only for scheduled runs")

    ensure_label()
    details = (
        f"{MARKER}\n\n"
        "The scheduled release updater failed. Review the workflow log and resolve the underlying cause before closing this issue.\n\n"
        f"- Stage: {os.environ.get('FAILURE_STAGE', 'release proposal or validation')}\n"
        f"- Candidate version: {os.environ.get('CANDIDATE_VERSION') or 'not selected'}\n"
        f"- Workflow run: {run_url}\n"
    )
    if incidents:
        issue = incidents[0]
        request("PATCH", f"/repos/{REPOSITORY}/issues/{issue['number']}", {"title": TITLE, "body": details})
        request("POST", f"/repos/{REPOSITORY}/issues/{issue['number']}/comments", {"body": f"Another scheduled updater run failed. {run_url}"})
        print(f"Updated existing updater incident #{issue['number']}.")
    else:
        issue = request("POST", f"/repos/{REPOSITORY}/issues", {"title": TITLE, "body": details, "labels": [LABEL]})
        print(f"Created updater incident #{issue.get('number') if isinstance(issue, dict) else 'unknown'}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (IncidentError, OSError, json.JSONDecodeError) as error:
        print(f"updater incident reporting failed: {error}")
        raise SystemExit(1)
