"""Check that doctor.sh reports the required tools and guides installs.

The stubs shadow the tools doctor.sh checks, so the cases do not depend on what
the host has installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = REPO_ROOT / "doctor.sh"

STUBS = {
    "terraform": "Terraform v1.10.3",
    "python3": "Python 3.12.1",
    "aws": "aws-cli/2.15.0 Python/3.11.6 Darwin/23.0.0",
}

# Utilities doctor.sh resolves on PATH, symlinked into an allowlist directory so
# the test PATH is stubs plus these and never a host-installed CLI.
ALLOWLIST = ("bash", "env", "uname", "sed", "grep", "tr")


def write_stub(bin_dir: Path, name: str, output: str, exit_code: int = 0) -> None:
    stub = bin_dir / name
    stub.write_text(f'#!/usr/bin/env bash\necho "{output}"\nexit {exit_code}\n')
    stub.chmod(0o755)


def make_allowlist(root: Path) -> Path:
    allow = root / "allowlist"
    allow.mkdir(exist_ok=True)
    for name in ALLOWLIST:
        target = shutil.which(name)
        assert target, f"{name} is required on the host to run doctor.sh"
        (allow / name).symlink_to(target)
    return allow


def run_doctor(
    bin_dir: Path, *args: str, platform: str = "macos"
) -> subprocess.CompletedProcess[str]:
    allow_dir = make_allowlist(bin_dir)
    env = {**os.environ, "PATH": f"{bin_dir}:{allow_dir}", "DOCTOR_PLATFORM": platform}
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


def test_required_probe_failure_is_reported_and_continues(tmp_path: Path) -> None:
    write_stub(tmp_path, "terraform", "terraform probe produced no version")
    write_stub(tmp_path, "python3", STUBS["python3"])
    write_stub(tmp_path, "aws", STUBS["aws"])
    result = run_doctor(tmp_path)
    assert result.returncode == 1
    assert "[unknown]  terraform" in result.stdout
    assert "brew install hashicorp/tap/terraform" in result.stdout
    assert "[ok]       python3" in result.stdout
    assert "[ok]       aws" in result.stdout
    assert "Some tools are missing or outdated" in result.stderr


def test_optional_probe_failure_stays_advisory(tmp_path: Path) -> None:
    for name, output in STUBS.items():
        write_stub(tmp_path, name, output)
    write_stub(tmp_path, "just", "just says no")
    result = run_doctor(tmp_path, "--optional")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[ok]       just unknown (optional)" in result.stdout
    assert "[missing]  docker (optional)" in result.stdout


def test_install_runs_missing_tool_command(tmp_path: Path) -> None:
    write_stub(tmp_path, "terraform", STUBS["terraform"])
    write_stub(tmp_path, "python3", STUBS["python3"])
    write_stub(tmp_path, "brew", "Installed awscli")
    result = run_doctor(tmp_path, "--install")
    assert result.returncode == 1
    assert "[missing]  aws" in result.stdout
    assert "running: brew install awscli" in result.stdout
    assert "failed:" not in result.stderr


def test_install_failure_prints_failure_line_and_continues(tmp_path: Path) -> None:
    write_stub(tmp_path, "python3", STUBS["python3"])
    write_stub(tmp_path, "aws", STUBS["aws"])
    write_stub(tmp_path, "brew", "Error: install refused", exit_code=1)
    result = run_doctor(tmp_path, "--install")
    assert result.returncode == 1
    assert "[missing]  terraform" in result.stdout
    assert "running: brew install hashicorp/tap/terraform" in result.stdout
    assert "failed: brew install hashicorp/tap/terraform" in result.stderr
    assert "[ok]       python3" in result.stdout
    assert "[ok]       aws" in result.stdout
    assert "Some tools are missing or outdated" in result.stderr
