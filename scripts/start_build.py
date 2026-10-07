#!/usr/bin/env python3
"""Start a CodeBuild build, poll to a terminal status, and record the result.

CodeBuild has no Terraform build object and no CLI waiter, so a script owns the
start-and-wait. This one starts the project's build with an IMAGE_TAG override,
polls `batch-get-builds`, and writes the service-reported times to JSON. It exits
non-zero on a non-SUCCEEDED status so a failed build fails the apply, and prints
the CloudWatch deep link so the failure is one click away.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = {"SUCCEEDED", "FAILED", "FAULT", "STOPPED", "TIMED_OUT"}


def aws(region: str, *args: str) -> dict:
    out = subprocess.run(
        ["aws", "--region", region, *args, "--output", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def aws_ok(region: str, *args: str) -> bool:
    """Run an AWS CLI call and report success without raising."""
    result = subprocess.run(
        ["aws", "--region", region, *args, "--output", "json"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def tag_exists(region: str, repo: str, tag: str) -> bool:
    return aws_ok(
        region,
        "ecr",
        "describe-images",
        "--repository-name",
        repo,
        "--image-ids",
        f"imageTag={tag}",
    )


def start(project: str, tag: str, region: str) -> str:
    build = aws(
        region,
        "codebuild",
        "start-build",
        "--project-name",
        project,
        "--environment-variables-override",
        f"name=IMAGE_TAG,value={tag},type=PLAINTEXT",
    )["build"]
    return build["id"]


def poll(build_id: str, region: str, interval: int, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        build = aws(region, "codebuild", "batch-get-builds", "--ids", build_id)["builds"][0]
        status = build["buildStatus"]
        print(f"{datetime.now(timezone.utc):%H:%M:%S} {status}", flush=True)
        if status in TERMINAL:
            return build
        if time.monotonic() > deadline:
            raise SystemExit(f"Timed out after {timeout}s waiting for {build_id}")
        time.sleep(interval)


def seconds(start_iso: str, end_iso: str) -> float:
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return (parse(end_iso) - parse(start_iso)).total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--ecr-repo",
        help="Repository to check for a duplicate tag before building",
    )
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    if not args.tag:
        raise SystemExit("--tag must not be empty")

    # ECR is IMMUTABLE, so a push over an existing tag fails mid-build. Fail
    # fast instead, with a message that names the collision.
    if args.ecr_repo and tag_exists(args.region, args.ecr_repo, args.tag):
        raise SystemExit(
            f"Tag {args.tag} already exists in {args.ecr_repo}. "
            "ECR is IMMUTABLE; bump the source or the tag."
        )

    started = time.monotonic()
    build_id = start(args.project, args.tag, args.region)
    print(f"Started {build_id}", flush=True)

    build = poll(build_id, args.region, args.interval, args.timeout)
    elapsed = round(time.monotonic() - started, 1)

    codebuild_start = build.get("startTime")
    codebuild_end = build.get("endTime")
    logs = build.get("logs", {})
    result = {
        "build_id": build_id,
        "status": build["buildStatus"],
        "tag": args.tag,
        "elapsed_s": elapsed,
        "codebuild_start": codebuild_start,
        "codebuild_end": codebuild_end,
        "codebuild_duration_s": seconds(codebuild_start, codebuild_end)
        if codebuild_start and codebuild_end
        else None,
        "log_group": logs.get("groupName"),
        "log_stream": logs.get("streamName"),
        "log_deep_link": logs.get("deepLink"),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

    if result["status"] != "SUCCEEDED":
        link = result.get("log_deep_link")
        if link:
            print(f"Build failed. Logs: {link}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
