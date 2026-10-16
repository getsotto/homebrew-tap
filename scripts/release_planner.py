#!/usr/bin/env python3
"""Plan a verified Sotto formula update without writing to GitHub or the checkout."""

from __future__ import annotations

import difflib
import hashlib
import re
from datetime import date
from typing import Any, Mapping

from check_formula_version import version_from
from verify_release import VerifiedRelease, VerificationError, formula_pins

MAC_TARGETS = ("aarch64-apple-darwin", "x86_64-apple-darwin")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
RELEASE_ASSETS = ("SHA256SUMS", "SHA256SUMS.sigstore.json")


class PlanningError(ValueError):
    """Release metadata or verified inputs cannot be safely planned."""


def _input_report(verified: VerifiedRelease) -> dict[str, Any]:
    return {
        "manifest_sha256": verified.manifest_sha256,
        "archive_sha256": dict(sorted(verified.archive_sha256.items())),
    }


def _version_tuple(version: str) -> tuple[int, int, int]:
    if not VERSION.fullmatch(version):
        raise PlanningError("release tag must contain a plain semantic version")
    return tuple(int(part) for part in version.split("."))


def _release_version(release: Mapping[str, Any]) -> str:
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise PlanningError("release tag must use the v<major>.<minor>.<patch> form")
    version = tag[1:]
    _version_tuple(version)
    return version


def _verified_inputs(release: Mapping[str, Any], verified: VerifiedRelease, version: str) -> str | None:
    if verified.version != version:
        return "verified inputs do not match the selected release tag"
    if not SHA256.fullmatch(verified.manifest_sha256):
        return "verified checksum manifest has an invalid SHA-256 digest"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise PlanningError("release metadata has no asset list")
    names = [asset.get("name") for asset in assets if isinstance(asset, Mapping)]
    expected = set(RELEASE_ASSETS)
    expected.update(f"sotto-v{version}-{target}.tar.gz" for target in MAC_TARGETS)
    missing = sorted(name for name in expected if names.count(name) == 0)
    duplicates = sorted(name for name in expected if names.count(name) > 1)
    if missing or duplicates:
        details = []
        if missing:
            details.append("missing assets: " + ", ".join(missing))
        if duplicates:
            details.append("duplicate assets: " + ", ".join(duplicates))
        raise PlanningError("release is incomplete; " + "; ".join(details))
    for name in sorted(expected - set(RELEASE_ASSETS)):
        if not SHA256.fullmatch(verified.archive_sha256.get(name, "")):
            return f"verified archive digest is missing or invalid: {name}"
    return None


def _updated_formula(current: str, current_version: str, verified: VerifiedRelease) -> str:
    updated = current.replace(f"v{current_version}", f"v{verified.version}")
    lines = updated.splitlines(keepends=True)
    for target in MAC_TARGETS:
        name = f"sotto-v{verified.version}-{target}.tar.gz"
        digest = verified.archive_sha256[name]
        matches = [index for index, line in enumerate(lines) if name in line]
        if len(matches) != 1:
            raise PlanningError(f"could not update exactly one formula pin for {target}")
        for index in range(matches[0] + 1, min(matches[0] + 4, len(lines))):
            if "sha256" in lines[index]:
                lines[index] = re.sub(r'(^\s*sha256\s+")[0-9a-f]{64}(")', rf"\g<1>{digest}\g<2>", lines[index])
                break
        else:
            raise PlanningError(f"could not find the formula SHA-256 pin for {target}")
    return "".join(lines)


def plan_release(
    *,
    current_formula: str,
    release: Mapping[str, Any],
    verified: VerifiedRelease,
    proposals: Mapping[str, Any] | None = None,
    held_versions: Mapping[str, Any] | None = None,
    rollbacks: Mapping[str, Any] | None = None,
    manual_retry: bool = False,
) -> dict[str, Any]:
    """Return a deterministic report and patch; this function has no side effects."""
    try:
        version = _release_version(release)
        current_version = ".".join(map(str, version_from(current_formula)))
    except (PlanningError, ValueError) as error:
        return {"status": "failure", "version": None, "reason": str(error)}

    if release.get("draft") is True:
        return {"status": "skip", "version": version, "reason": "draft releases are not eligible"}
    if release.get("prerelease") is True:
        return {"status": "skip", "version": version, "reason": "prereleases are not eligible"}
    if not isinstance(release.get("draft"), bool) or not isinstance(release.get("prerelease"), bool):
        return {"status": "failure", "version": version, "reason": "release metadata has invalid eligibility flags"}

    if version in (held_versions or {}):
        record = (held_versions or {})[version]
        reason = record.get("reason", "version is held") if isinstance(record, Mapping) else "version is held"
        return {"status": "held", "version": version, "reason": reason}

    try:
        invalid = _verified_inputs(release, verified, version)
    except PlanningError as error:
        return {"status": "failure", "version": version, "reason": str(error)}
    if invalid:
        return {"status": "failure", "version": version, "reason": invalid}

    candidate = _version_tuple(version)
    current = _version_tuple(current_version)
    if candidate == current:
        try:
            pins = formula_pins(current_formula, version)
        except (OSError, VerificationError) as error:
            return {"status": "failure", "version": version, "reason": str(error)}
        for name, (_, pin) in pins.items():
            if verified.archive_sha256.get(name) != pin:
                return {"status": "failure", "version": version, "reason": f"current formula pin differs from verified release input: {name}"}
        return {
            "status": "no-op",
            "version": version,
            "reason": "version is already packaged",
            "verified_inputs": _input_report(verified),
        }
    action = "create"
    rollback_record = None
    if candidate < current:
        records = (rollbacks or {}).get("rollbacks", [])
        rollback_record = next((
            item for item in records
            if isinstance(item, Mapping) and item.get("from") == current_version and item.get("to") == version
        ), None)
        if rollback_record is None:
            return {"status": "skip", "version": version, "reason": "candidate is older than the packaged version"}
        evidence_fields = ("incident", "compatibility_evidence", "reviewed_by")
        if any(not isinstance(rollback_record.get(field), str) or not rollback_record[field].strip() for field in evidence_fields):
            return {"status": "failure", "version": version, "reason": "rollback record lacks incident, compatibility evidence, or reviewer"}
        if rollback_record.get("compatibility_verified") is not True:
            return {"status": "failure", "version": version, "reason": "rollback data compatibility is not verified"}
        try:
            date.fromisoformat(rollback_record.get("reviewed_at", ""))
        except (TypeError, ValueError):
            return {"status": "failure", "version": version, "reason": "rollback record has no valid review date"}
        action = "rollback"

    updated = _updated_formula(current_formula, current_version, verified)
    formula_digest = hashlib.sha256(updated.encode("utf-8")).hexdigest()
    branch = f"update/sotto-v{version}"
    proposal = (proposals or {}).get(version)
    if manual_retry and proposal is None:
        return {"status": "failure", "version": version, "reason": "manual retry requires an existing closed proposal"}
    if proposal is not None:
        if not isinstance(proposal, Mapping) or proposal.get("status") not in {"open", "closed"}:
            return {"status": "failure", "version": version, "reason": "proposal state is malformed"}
        if proposal.get("manifest_sha256") != verified.manifest_sha256:
            return {"status": "failure", "version": version, "reason": "verified inputs changed under an existing proposal"}
        if proposal.get("formula_sha256") != formula_digest:
            return {"status": "failure", "version": version, "reason": "existing proposal formula differs from the verified candidate"}
        existing_branch = proposal.get("branch")
        if not isinstance(existing_branch, str) or not existing_branch:
            return {"status": "failure", "version": version, "reason": "proposal branch identity is missing"}
        branch = existing_branch
        if proposal["status"] == "open":
            return {
                "status": "no-op",
                "version": version,
                "reason": "unchanged proposal is already open",
                "branch": branch,
                "formula_sha256": formula_digest,
                "manifest_sha256": verified.manifest_sha256,
                "verified_inputs": _input_report(verified),
            }
        if not manual_retry:
            return {"status": "skip", "version": version, "reason": "closed proposal suppresses this version"}
        action = "reopen"
    patch = "".join(difflib.unified_diff(
        current_formula.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile="a/Formula/sotto.rb",
        tofile="b/Formula/sotto.rb",
    ))
    return {
        "status": "update",
        "action": action,
        "version": version,
        "reason": (
            "verified rollback is explicitly approved with compatibility evidence"
            if rollback_record is not None
            else "verified eligible release is newer than the packaged version"
        ),
        "branch": branch,
        "formula_sha256": formula_digest,
        "manifest_sha256": verified.manifest_sha256,
        "verified_inputs": _input_report(verified),
        "rollback": rollback_record,
        "formula": updated,
        "patch": patch,
    }
