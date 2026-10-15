"""Check that doctor.sh reports the required tools and guides installs.

The stubs shadow the tools doctor.sh checks, so the cases do not depend on what
the host has installed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = REPO_ROOT / "doctor.sh"

STUBS = {
    "terraform": "Terraform v1.10.3",
    "python3": "Python 3.12.1",
    "aws": "aws-cli/2.15.0 Python/3.11.6 Darwin/23.0.0",
}

# Keep the real coreutils on PATH; the stubs shadow the tools doctor.sh checks.
SYSTEM_PATH = "/usr/bin:/bin"


def write_stub(bin_dir: Path, name: str, output: str) -> None:
    stub = bin_dir / name
    stub.write_text(f'#!/usr/bin/env bash\necho "{output}"\n')
    stub.chmod(0o755)


def run_doctor(
    bin_dir: Path, *args: str, platform: str = "macos"
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{bin_dir}:{SYSTEM_PATH}", "DOCTOR_PLATFORM": platform}
    return subprocess.run(
        ["bash", str(DOCTOR), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_all_present_exits_zero(tmp_path: Path) -> None:
    for name, output in STUBS.items():
        write_stub(tmp_path, name, output)
    result = run_doctor(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in STUBS:
        assert name in result.stdout
    assert "[missing]" not in result.stdout


def test_missing_tool_fails_and_names_it(tmp_path: Path) -> None:
    for name, output in STUBS.items():
        if name != "aws":
            write_stub(tmp_path, name, output)
    result = run_doctor(tmp_path)
    assert result.returncode == 1
    assert "[missing]  aws" in result.stdout
    assert "brew install awscli" in result.stdout


def test_below_minimum_fails(tmp_path: Path) -> None:
    write_stub(tmp_path, "terraform", "Terraform v1.9.8")
    write_stub(tmp_path, "python3", STUBS["python3"])
    write_stub(tmp_path, "aws", STUBS["aws"])
    result = run_doctor(tmp_path)
    assert result.returncode == 1
    assert "[outdated] terraform 1.9.8" in result.stdout
    assert "1.10" in result.stdout


def test_optional_missing_does_not_fail(tmp_path: Path) -> None:
    for name, output in STUBS.items():
        write_stub(tmp_path, name, output)
    result = run_doctor(tmp_path, "--optional")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[missing]  just (optional)" in result.stdout
    assert "[missing]  docker (optional)" in result.stdout
