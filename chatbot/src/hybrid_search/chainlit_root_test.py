"""CHAINLIT_APP_ROOT must resolve to the app's assets/ directory.

Importing ``hybrid_search`` sets the variable so a path that reaches a ``ui/*``
module before ``hybrid_search.app`` (for example pytest collecting the ui tests)
reads ``assets/`` instead of writing a ``.chainlit/`` scaffold into the working
directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from hybrid_search import chainlit_root


def test_sets_assets_dir_when_unset(monkeypatch):
    monkeypatch.delenv("CHAINLIT_APP_ROOT", raising=False)

    chainlit_root.ensure_chainlit_app_root()

    assert Path(os.environ["CHAINLIT_APP_ROOT"]).name == "assets"


def test_keeps_a_caller_value(monkeypatch):
    monkeypatch.setenv("CHAINLIT_APP_ROOT", "/custom/assets")

    chainlit_root.ensure_chainlit_app_root()

    assert os.environ["CHAINLIT_APP_ROOT"] == "/custom/assets"


def test_package_import_sets_the_default():
    env = {key: value for key, value in os.environ.items() if key != "CHAINLIT_APP_ROOT"}

    result = subprocess.run(
        [sys.executable, "-c", "import os, hybrid_search; print(os.environ['CHAINLIT_APP_ROOT'])"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert Path(result.stdout.strip()).name == "assets"
