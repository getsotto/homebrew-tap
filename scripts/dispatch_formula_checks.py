#!/usr/bin/env python3
"""Run the required formula workflow on the current bot-created PR head."""

from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"
REPOSITORY = "getsotto/homebrew-tap"


class DispatchError(RuntimeError):
    pass


def request(method: str, path: str, body: dict | None = None) -> object:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise DispatchError("GitHub token is missing")
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
        raise DispatchError(f"GitHub API {method} {path} failed ({error.code}): {detail}") from error
    return json.loads(raw) if raw else None


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("PROPOSAL_BRANCH", "")
    if repository != REPOSITORY or not branch.startswith("update/sotto-v"):
        raise DispatchError("validation dispatch is restricted to version proposal branches in the canonical tap")
    query = urlencode({"state": "open", "head": f"getsotto:{branch}", "base": "main", "per_page": 100})
    prs = request("GET", f"/repos/{REPOSITORY}/pulls?{query}")
    if not isinstance(prs, list) or len(prs) != 1:
        raise DispatchError("expected exactly one open version proposal for validation")
    pr = prs[0]
    head_sha = pr.get("head", {}).get("sha")
    if not isinstance(head_sha, str):
        raise DispatchError("proposal has no current head commit")

    previous = request("GET", f"/repos/{REPOSITORY}/actions/workflows/formula.yml/runs?" + urlencode({
        "branch": branch, "event": "workflow_dispatch", "per_page": 100,
    }))
    previous_ids = {
        item.get("id") for item in previous.get("workflow_runs", [])
    } if isinstance(previous, dict) else set()
    request("POST", f"/repos/{REPOSITORY}/actions/workflows/formula.yml/dispatches", {"ref": branch})
    deadline = time.monotonic() + 60 * 60
    run = None
    while time.monotonic() < deadline:
        query = urlencode({"branch": branch, "event": "workflow_dispatch", "per_page": 20})
        runs = request("GET", f"/repos/{REPOSITORY}/actions/workflows/formula.yml/runs?{query}")
        values = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
        run = next((
            item for item in values
            if item.get("head_sha") == head_sha
            and item.get("id") not in previous_ids
        ), None)
        if run and run.get("status") == "completed":
            break
        time.sleep(15)
    if not run or run.get("status") != "completed":
        raise DispatchError("formula checks did not complete within 60 minutes")
    if run.get("conclusion") != "success":
        raise DispatchError(f"formula checks finished with conclusion {run.get('conclusion')}")

    current = request("GET", f"/repos/{REPOSITORY}/pulls/{pr['number']}")
    if not isinstance(current, dict) or current.get("head", {}).get("sha") != head_sha:
        raise DispatchError("proposal head changed while its formula checks were running")
    print(f"All required formula checks passed for PR #{pr['number']} at {head_sha}: {run.get('html_url')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DispatchError, OSError, json.JSONDecodeError) as error:
        print(f"formula validation dispatch failed: {error}")
        raise SystemExit(1)
