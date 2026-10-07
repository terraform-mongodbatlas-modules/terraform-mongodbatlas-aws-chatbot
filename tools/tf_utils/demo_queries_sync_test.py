"""Guard the demo starter questions against drift.

The bundled `chatbot/assets/demo_queries.yaml` is the app default and the
`queries` list in `examples/minimal/main.tf` is the copy-paste example. The
example README is hand-written (`docs/examples.yaml` skips the minimal
example), so this test keeps all three the same ordered list and proves
`render_queries` preserves the authored order.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import hcl2
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_QUERIES = _REPO_ROOT / "chatbot" / "assets" / "demo_queries.yaml"
_EXAMPLE_MAIN = _REPO_ROOT / "examples" / "minimal" / "main.tf"
_EXAMPLE_README = _REPO_ROOT / "examples" / "minimal" / "README.md"


def _strip_quotes(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        return json.loads(value)
    return value


def _hcl_queries(source: str) -> list[tuple[str, str]]:
    parsed = hcl2.loads(source)
    module = parsed["module"][0]['"chatbot"']
    return [
        (_strip_quotes(query["label"]), _strip_quotes(query["message"]))
        for query in module["queries"]
    ]


def _bundled_queries() -> list[tuple[str, str]]:
    data = yaml.safe_load(_BUNDLED_QUERIES.read_text())
    return [(entry["label"], entry["message"]) for entry in data["queries"]]


def _example_queries() -> list[tuple[str, str]]:
    return _hcl_queries(_EXAMPLE_MAIN.read_text())


def _readme_queries() -> list[tuple[str, str]]:
    blocks = re.findall(r"```hcl\n(.*?)```", _EXAMPLE_README.read_text(), re.DOTALL)
    return _hcl_queries(next(block for block in blocks if "queries" in block))


def _render_queries(staging: Path, queries: list[dict[str, str]]) -> None:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import render_assets

    render_assets.render_queries(staging, queries)


def test_example_and_bundled_queries_are_the_same_ordered_list() -> None:
    assert _example_queries() == _bundled_queries()


def test_readme_snippet_matches_the_example() -> None:
    assert _readme_queries() == _example_queries()


def test_render_queries_preserves_the_authored_order(tmp_path: Path) -> None:
    example = [{"label": label, "message": message} for label, message in _example_queries()]
    _render_queries(tmp_path, example)
    rendered = yaml.safe_load((tmp_path / "demo_queries.yaml").read_text())
    assert [
        (entry["label"], entry["message"]) for entry in rendered["queries"]
    ] == _bundled_queries()
