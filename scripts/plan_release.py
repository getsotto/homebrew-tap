#!/usr/bin/env python3
"""Verify an upstream Sotto release and print a dry-run formula update plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from release_planner import PlanningError, plan_release
from verify_release import VerifiedRelease, VerificationError, verify_release_inputs

API = "https://api.github.com/repos/getsotto/sotto/releases"
DOWNLOAD = "https://github.com/getsotto/sotto/releases/download"
USER_AGENT = "sotto-homebrew-release-planner"
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def clean_version(value: str) -> str:
    version = value.removeprefix("v")
    if not SEMVER.fullmatch(version):
        raise ValueError("version must be a plain semantic version such as 0.9.0")
    return version


def read_json(path: Path | None, default: dict) -> dict:
    if path is None or not path.exists():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def read_records(path: Path | None, key: str, default: dict | list) -> dict | list:
    document = read_json(path, {"schema_version": 1, key: default})
    if document.get("schema_version") != 1:
        raise ValueError(f"{path} has an unsupported schema version")
    value = document.get(key, default)
    expected = list if isinstance(default, list) else Mapping
    if not isinstance(value, expected):
        raise ValueError(f"{path} field {key} has the wrong shape")
    return value


def _request_json(endpoint: str) -> Any:
    request = Request(endpoint, headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_stable_release(releases: list[dict]) -> dict:
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.startswith("v"):
            continue
        try:
            version = clean_version(tag)
        except ValueError:
            continue
        candidates.append((tuple(int(part) for part in version.split(".")), release))
    if not candidates:
        raise ValueError("GitHub has no published stable semantic-version release")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def fetch_release(version: str | None) -> dict:
    if version is not None:
        value = _request_json(f"{API}/tags/v{version}")
        if not isinstance(value, dict):
            raise ValueError("GitHub release API returned an unexpected response")
        return value

    releases = []
    page = 1
    while True:
        value = _request_json(f"{API}?per_page=100&page={page}")
        if not isinstance(value, list):
            raise ValueError("GitHub releases API returned an unexpected response")
        releases.extend(value)
        if len(value) < 100:
            break
        page += 1
    value = latest_stable_release(releases)
    if not isinstance(value, dict):
        raise ValueError("GitHub release API returned an unexpected response")
    return value


def download_inputs(version: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    names = (
        "SHA256SUMS",
        "SHA256SUMS.sigstore.json",
        f"sotto-v{version}-aarch64-apple-darwin.tar.gz",
        f"sotto-v{version}-x86_64-apple-darwin.tar.gz",
    )
    for name in names:
        url = f"{DOWNLOAD}/v{version}/{name}"
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            (directory / name).write_bytes(response.read())


def print_report(result: dict, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, sort_keys=True, indent=2))
        return
    print(f"status: {result['status']}")
    if result.get("version"):
        print(f"version: {result['version']}")
    if result.get("branch"):
        print(f"branch: {result['branch']}")
    print(f"reason: {result['reason']}")
    if result.get("formula_sha256"):
        print(f"formula sha256: {result['formula_sha256']}")
    if result.get("manifest_sha256"):
        print(f"manifest sha256: {result['manifest_sha256']}")
    inputs = result.get("verified_inputs", {})
    if inputs.get("manifest_sha256") and not result.get("manifest_sha256"):
        print(f"manifest sha256: {inputs['manifest_sha256']}")
    for name, digest in inputs.get("archive_sha256", {}).items():
        print(f"{digest}  {name}")
    if result.get("patch"):
        print(result["patch"], end="" if result["patch"].endswith("\n") else "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="select one exact published version; defaults to latest stable")
    parser.add_argument("--manual-retry", action="store_true", help="retry a previously closed proposal for this exact version")
    parser.add_argument("--formula", type=Path, default=Path("Formula/sotto.rb"))
    parser.add_argument("--proposals", type=Path, help="version-keyed proposal state JSON from the GitHub adapter")
    parser.add_argument("--held-versions", type=Path, default=Path("releases/held-versions.json"))
    parser.add_argument("--rollbacks", type=Path, default=Path("releases/rollbacks.json"))
    parser.add_argument("--release-metadata", type=Path, help="use a saved GitHub release JSON response")
    parser.add_argument("--release-dir", type=Path, help="verify already downloaded release input files")
    parser.add_argument("--cache-dir", type=Path, help="keep downloaded inputs in this temporary workflow directory")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    try:
        selected_version = clean_version(args.version) if args.version else None
        if args.manual_retry and selected_version is None:
            raise ValueError("--manual-retry requires an explicit --version")
        if args.release_metadata:
            release = read_json(args.release_metadata, {})
        else:
            release = fetch_release(selected_version)
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.startswith("v"):
            raise ValueError("release metadata has no valid v-prefixed tag")
        version = clean_version(tag)
        if tag != f"v{version}":
            raise ValueError("release metadata tag is not canonical")
        if selected_version and version != selected_version:
            raise ValueError("selected release tag does not match --version")

        current_formula = args.formula.read_text(encoding="utf-8")
        proposals = read_records(args.proposals, "proposals", {})
        held_versions = read_records(args.held_versions, "versions", {})
        rollbacks = {"rollbacks": read_records(args.rollbacks, "rollbacks", [])}
        verified = VerifiedRelease(version=version, manifest_sha256="", archive_sha256={})
        if (
            release.get("draft") is True
            or release.get("prerelease") is True
            or not isinstance(release.get("draft"), bool)
            or not isinstance(release.get("prerelease"), bool)
            or version in held_versions
        ):
            result = plan_release(
                current_formula=current_formula,
                release=release,
                verified=verified,
                proposals=proposals,
                held_versions=held_versions,
                rollbacks=rollbacks,
                manual_retry=args.manual_retry,
            )
        else:
            if args.release_dir:
                verified = verify_release_inputs(args.release_dir, version)
            elif args.cache_dir:
                download_inputs(version, args.cache_dir)
                verified = verify_release_inputs(args.cache_dir, version)
            else:
                with tempfile.TemporaryDirectory(prefix="sotto-release-plan-") as temporary:
                    inputs_dir = Path(temporary)
                    download_inputs(version, inputs_dir)
                    verified = verify_release_inputs(inputs_dir, version)
            result = plan_release(
                current_formula=current_formula,
                release=release,
                verified=verified,
                proposals=proposals,
                held_versions=held_versions,
                rollbacks=rollbacks,
                manual_retry=args.manual_retry,
            )
        print_report(result, args.format)
        return 1 if result["status"] == "failure" else 0
    except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError, PlanningError, VerificationError) as error:
        result = {"status": "failure", "version": args.version, "reason": str(error)}
        print_report(result, args.format)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
