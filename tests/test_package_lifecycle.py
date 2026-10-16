#!/usr/bin/env python3
"""Exercise upgrade and recovery with disposable local Homebrew formulae."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_FORMULA = ROOT / "Formula/sotto.rb"
VERSIONS = ("0.8.0", "0.9.0")
TARGETS = ("aarch64-apple-darwin", "x86_64-apple-darwin")


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def make_archive(directory: Path, version: str, target: str) -> str:
    root = directory / f"sotto-v{version}-{target}"
    (root / "completions").mkdir(parents=True)
    (root / "sotto").write_text(
        f"#!/bin/sh\nprintf 'sotto {version} fixture\\n'\n", encoding="utf-8"
    )
    (root / "sotto").chmod(0o755)
    for name in ("sotto.bash", "sotto.zsh", "sotto.fish"):
        (root / "completions" / name).write_text("# controlled fixture\n", encoding="utf-8")
    for name in ("LICENSE", "SECURITY.md", "THREAT-MODEL.md"):
        (root / name).write_text("controlled package fixture\n", encoding="utf-8")
    archive = directory / f"sotto-v{version}-{target}.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(root, arcname=root.name)
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def formula_for(directory: Path, version: str, digests: dict[str, str]) -> str:
    formula = CURRENT_FORMULA.read_text(encoding="utf-8")
    formula = formula.replace("0.9.0", version)
    for target in TARGETS:
        digest = digests[target]
        archive = directory / f"sotto-v{version}-{target}.tar.gz"
        formula = formula.replace(
            f"https://github.com/getsotto/sotto/releases/download/v{version}/sotto-v{version}-{target}.tar.gz",
            archive.as_uri(),
        )
        marker = f'    sha256 "{digest}"'
        # Replace the matching architecture pin without touching the other one.
        lines = formula.splitlines()
        for index, line in enumerate(lines):
            if f"sotto-v{version}-{target}.tar.gz" in line:
                for pin_index in range(index + 1, min(index + 4, len(lines))):
                    if "sha256" in lines[pin_index]:
                        lines[pin_index] = marker
                        break
                break
        formula = "\n".join(lines) + "\n"
    return formula


def main() -> None:
    brew = shutil.which("brew")
    if brew is None:
        raise SystemExit("Homebrew is required for the package lifecycle fixture")

    with tempfile.TemporaryDirectory(prefix="sotto-lifecycle-") as temporary:
        root = Path(temporary)
        tap = Path(subprocess.check_output([brew, "--repository"], text=True).strip())
        tap /= "Library/Taps/getsotto/homebrew-lifecycle-test"
        tap.parent.mkdir(parents=True, exist_ok=True)
        tap.mkdir()
        run("git", "-C", str(tap), "init", "--quiet")
        run("git", "-C", str(tap), "config", "user.name", "Sotto lifecycle fixture")
        run("git", "-C", str(tap), "config", "user.email", "fixture@example.invalid")
        data = root / "existing-project-data.txt"
        data.write_text("preserve controlled fixture\n", encoding="utf-8")
        prefix_bin = Path(subprocess.check_output([brew, "--prefix"], text=True).strip()) / "bin"
        try:
            for version in VERSIONS:
                digests = {
                    target: make_archive(root, version, target) for target in TARGETS
                }
                (tap / "Formula").mkdir(exist_ok=True)
                (tap / "Formula/sotto.rb").write_text(
                    formula_for(root, version, digests), encoding="utf-8"
                )
                run("git", "-C", str(tap), "add", "Formula/sotto.rb")
                run("git", "-C", str(tap), "commit", "--quiet", "-m", f"fixture {version}")
                if version == VERSIONS[0]:
                    run(brew, "install", "--formula", "getsotto/lifecycle-test/sotto")
                    output = subprocess.check_output([str(prefix_bin / "sotto"), "--version"], text=True)
                    assert version in output, output
                else:
                    run(brew, "upgrade", "--formula", "getsotto/lifecycle-test/sotto")
                    output = subprocess.check_output([str(prefix_bin / "sotto"), "--version"], text=True)
                    assert version in output, output
                    assert data.read_text(encoding="utf-8") == "preserve controlled fixture\n"

            # Reinstalling the explicitly selected older fixture exercises the
            # package recovery mechanics only; it makes no Sotto data-safety claim.
            old_digests = {
                target: hashlib.sha256(
                    (root / f"sotto-v{VERSIONS[0]}-{target}.tar.gz").read_bytes()
                ).hexdigest()
                for target in TARGETS
            }
            (tap / "Formula/sotto.rb").write_text(
                formula_for(root, VERSIONS[0], old_digests), encoding="utf-8"
            )
            run("git", "-C", str(tap), "add", "Formula/sotto.rb")
            run("git", "-C", str(tap), "commit", "--quiet", "-m", "fixture recovery")
            run(brew, "reinstall", "--formula", "getsotto/lifecycle-test/sotto")
            output = subprocess.check_output([str(prefix_bin / "sotto"), "--version"], text=True)
            assert VERSIONS[0] in output, output
            assert data.read_text(encoding="utf-8") == "preserve controlled fixture\n"
        finally:
            subprocess.run([brew, "uninstall", "--formula", "--force", "getsotto/lifecycle-test/sotto"], check=False)
            shutil.rmtree(tap, ignore_errors=True)
        assert data.read_text(encoding="utf-8") == "preserve controlled fixture\n"


if __name__ == "__main__":
    main()
