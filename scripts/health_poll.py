"""Poll a deployed app's `/health` until the deployment is ready.

Stdlib only, Python 3.10+: `features.verify_deployment_ready` runs this from a
Terraform `local-exec`, and `just public-test` runs the same script. `/health`
returns 503 until Atlas is reachable, so a 503 and a connection error are both
treated as pending. The script polls until `data_ingested` and `indexes_ready`
are both true or the deadline passes, then exits non-zero with the last payload.

The URL resolves from `--url`, else the module's `https_url` Terraform output at
the repository root, else `HYBRID_SEARCH_URL`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The module root is the repository root; the app lives at chatbot/.
DEFAULT_MODULE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_S = 900
DEFAULT_INTERVAL_S = 10
URL_OUTPUT_NAME = "https_url"


def resolve_url(module_dir: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["terraform", f"-chdir={module_dir}", "output", "-raw", URL_OUTPUT_NAME],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("HYBRID_SEARCH_URL")
    value = completed.stdout.strip()
    if not value or value == "null":
        return os.environ.get("HYBRID_SEARCH_URL")
    return value


def health_is_ready(payload: dict) -> bool:
    return bool(payload.get("data_ingested")) and bool(payload.get("indexes_ready"))


def fetch(endpoint: str) -> dict:
    with urllib.request.urlopen(endpoint, timeout=10) as response:
        return json.loads(response.read())


def poll_health(url: str, timeout_s: int, interval_s: int) -> tuple[bool, dict | None]:
    endpoint = f"{url.rstrip('/')}/health"
    deadline = time.monotonic() + timeout_s
    last: dict | None = None
    while time.monotonic() < deadline:
        try:
            last = fetch(endpoint)
            if health_is_ready(last):
                return True, last
        except urllib.error.HTTPError as error:
            # 503 is "Atlas not reachable yet"; any other status is surfaced.
            last = {"status": error.code}
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
            last = {"error": str(error)}
        time.sleep(interval_s)
    return False, last


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Override the resolved URL.")
    parser.add_argument("--module-dir", type=Path, default=DEFAULT_MODULE_DIR)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_S)
    args = parser.parse_args()

    url = args.url or resolve_url(args.module_dir)
    if not url:
        print(
            "no URL: apply the module, set HYBRID_SEARCH_URL, or pass --url",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"polling {url.rstrip('/')}/health for up to {args.timeout}s")
    ready, payload = poll_health(url, args.timeout, args.interval)
    if ready:
        print(f"healthy: {json.dumps(payload)}")
        return

    print(
        f"timed out waiting for a healthy deployment; last payload: {json.dumps(payload)}",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
