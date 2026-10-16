#!/usr/bin/env python3
"""Verify Sotto release inputs before a version is admitted to the tap."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ISSUER = "https://token.actions.githubusercontent.com"
IDENTITY = (
    "https://github.com/getsotto/sotto/.github/workflows/release.yml"
    "@refs/tags/v{version}"
)
MAC_TARGETS = {
    "arm": "aarch64-apple-darwin",
    "intel": "x86_64-apple-darwin",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class VerificationError(Exception):
    """An input failed the release admission policy."""


@dataclass(frozen=True)
class VerifiedRelease:
    version: str
    manifest_sha256: str
    archive_sha256: Mapping[str, str]


def read_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != 2 or not SHA256.fullmatch(fields[0]):
            raise VerificationError(f"malformed checksum entry on line {line_number}")
        digest, name = fields
        if name.startswith("*") or "/" in name or "\\" in name or name in {".", ".."}:
            raise VerificationError(f"unsafe checksum filename on line {line_number}")
        if name in entries:
            raise VerificationError(f"duplicate checksum entry for {name}")
        entries[name] = digest
    return entries


def formula_pins(formula: Path | str, version: str) -> dict[str, tuple[str, str]]:
    source = formula.read_text(encoding="utf-8") if isinstance(formula, Path) else formula
    selected_versions = set(re.findall(r"/releases/download/v(\d+\.\d+\.\d+)/", source))
    if selected_versions != {version}:
        raise VerificationError(f"formula release URLs must select v{version}")

    pins: dict[str, tuple[str, str]] = {}
    branches = re.search(
        r"^\s*if Hardware::CPU\.arm\?\s*$(.*?)^\s*else\s*$(.*?)^\s*end\s*$",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if not branches:
        raise VerificationError("formula must select separate Apple Silicon and Intel release inputs")
    for architecture, branch in zip(MAC_TARGETS, branches.groups(), strict=True):
        urls = re.findall(r'^\s*url\s+["\']([^"\']+)["\']\s*$', branch, re.MULTILINE)
        hashes = re.findall(r'^\s*sha256\s+["\']([^"\']+)["\']\s*$', branch, re.MULTILINE)
        target = MAC_TARGETS[architecture]
        expected_name = f"sotto-v{version}-{target}.tar.gz"
        expected_url = f"https://github.com/getsotto/sotto/releases/download/v{version}/{expected_name}"
        if urls != [expected_url] or len(hashes) != 1 or not SHA256.fullmatch(hashes[0]):
            raise VerificationError(f"formula has an invalid v{version} {architecture} URL or SHA-256 pin")
        pins[expected_name] = (expected_url, hashes[0])
    return pins


def run_cosign(bundle: Path, manifest: Path, version: str, *, identity: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        "cosign", "verify-blob", "--bundle", str(bundle),
        "--certificate-identity", identity or IDENTITY.format(version=version),
        "--certificate-oidc-issuer", ISSUER,
        str(manifest),
    ]
    return subprocess.run(command, text=True, capture_output=True, check=False)


def verify_release_inputs(directory: Path, version: str) -> VerifiedRelease:
    if not VERSION.fullmatch(version):
        raise VerificationError("version must be a plain semantic version such as 0.9.0")
    if shutil.which("cosign") is None:
        raise VerificationError("cosign is required for release verification")

    manifest = directory / "SHA256SUMS"
    bundle = directory / "SHA256SUMS.sigstore.json"
    for required in (manifest, bundle):
        if not required.is_file():
            raise VerificationError(f"missing release input: {required.name}")

    entries = read_manifest(manifest)
    observed: dict[str, str] = {}
    for name in (f"sotto-v{version}-{MAC_TARGETS['arm']}.tar.gz", f"sotto-v{version}-{MAC_TARGETS['intel']}.tar.gz"):
        if name not in entries:
            raise VerificationError(f"checksum manifest is missing {name}")
        archive = directory / name
        if not archive.is_file():
            raise VerificationError(f"missing release archive: {name}")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != entries[name]:
            raise VerificationError(f"archive digest does not match SHA256SUMS: {name}")
        observed[name] = digest

    result = run_cosign(bundle, manifest, version)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise VerificationError(f"Sigstore verification failed: {detail}")
    return VerifiedRelease(
        version=version,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        archive_sha256=observed,
    )


def verify(directory: Path, formula: Path, version: str) -> tuple[Path, dict[str, str]]:
    pins = formula_pins(formula, version)
    verified = verify_release_inputs(directory, version)
    for name, (_, formula_digest) in pins.items():
        if verified.archive_sha256.get(name) != formula_digest:
            raise VerificationError(f"formula SHA-256 does not match the release archive: {name}")
    return directory / "SHA256SUMS", dict(verified.archive_sha256)


def verify_negative_cases(directory: Path, manifest: Path, bundle: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="sotto-release-negative-") as temporary:
        altered = Path(temporary) / "SHA256SUMS"
        original = manifest.read_bytes()
        altered.write_bytes(original + b"\n")
        if run_cosign(bundle, altered, version).returncode == 0:
            raise VerificationError("cosign accepted an altered checksum manifest")

    wrong_identity = "https://github.com/attacker/sotto/.github/workflows/release.yml@refs/tags/v" + version
    if run_cosign(bundle, manifest, version, identity=wrong_identity).returncode == 0:
        raise VerificationError("cosign accepted a checksum manifest from the wrong signer")
    print("negative checks passed: altered manifest and wrong signer were rejected")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--formula", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--negative-tests", action="store_true")
    args = parser.parse_args()
    try:
        _, observed = verify(args.release_dir, args.formula, args.version)
        manifest = args.release_dir / "SHA256SUMS"
        print(f"verified SHA256SUMS for v{args.version} with the expected Sigstore identity")
        for name, digest in sorted(observed.items()):
            print(f"{digest}  {name}")
        if args.negative_tests:
            verify_negative_cases(args.release_dir, manifest, args.release_dir / "SHA256SUMS.sigstore.json", args.version)
    except (OSError, VerificationError) as error:
        print(f"release verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
