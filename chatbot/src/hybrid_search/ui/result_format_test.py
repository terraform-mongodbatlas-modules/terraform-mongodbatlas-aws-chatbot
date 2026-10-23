from __future__ import annotations

import pytest

from hybrid_search.search import RetrievalPipeline
from hybrid_search.ui.result_format import (
    _fence_for,
    format_hit_body,
    format_location,
    hit_label,
    retrieval_header,
)


def test_retrieval_header_fused():
    assert retrieval_header(RetrievalPipeline.RANK_FUSION) == (
        "Keyword + vector retrieval ($rankFusion)"
    )


def test_retrieval_header_keyword_only():
    assert retrieval_header(RetrievalPipeline.KEYWORD) == "Keyword search only"


def test_format_location_page():
    assert format_location({"page": 12}) == "p. 12"


def test_format_location_line_range():
    assert format_location({"start_line": 40, "end_line": 58}) == "lines 40-58"


def test_format_location_none():
    assert format_location({}) == ""


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (
            {"file_path": "docs/NIST.AI.100-1.pdf", "score": 0.9, "page": 12},
            "1 · NIST.AI.100-1.pdf · p. 12 · 0.900",
        ),
        (
            {"file_path": "notes.md", "score": 0.5, "start_line": 40, "end_line": 58},
            "1 · notes.md · lines 40-58 · 0.500",
        ),
        ({"file_path": "a.txt", "score": 0.5}, "1 · a.txt · 0.500"),
        ({"score": 0.5}, "1 · unknown · 0.500"),
    ],
)
def test_hit_label(ref, expected):
    assert hit_label(1, ref) == expected


_FENCED_CHUNK = """```hcl
queries = [
  { label = "Why one database", message = "Why would an agent store retrieval and memory in the same database?" },
]
```"""

_IMAGE_CHUNK = (
    "![The aws-chatbot abstraction iceberg](images/iceberg.svg)\n\n"
    "The iceberg counts the same deployment: one module call declares 90 managed resources."
)


def test_format_hit_body_keeps_fenced_chunk_intact():
    body = format_hit_body(
        {"file_path": "make-it-your-own.md", "content": _FENCED_CHUNK, "score": 7.962}
    )
    assert "````\n```hcl\n" in body
    assert "queries = [" in body
    assert body.endswith("```\n````")


def test_format_hit_body_keeps_image_reference_literal():
    body = format_hit_body(
        {"file_path": "architecture.md", "content": _IMAGE_CHUNK, "score": 4.526}
    )
    assert "```\n![The aws-chatbot abstraction iceberg](images/iceberg.svg)" in body


def test_format_hit_body_keeps_markdown_verbatim():
    body = format_hit_body({"content": "## Description\n\n9. Vector-store protection"})
    assert "## Description" in body
    assert "9. Vector-store protection" in body
    assert "> " not in body


def test_format_hit_body_keeps_full_content():
    body = format_hit_body({"content": "x" * 250})
    assert "x" * 250 in body
    assert "…" not in body


def test_format_hit_body_empty_content_shows_placeholder():
    body = format_hit_body({"content": "   "})
    assert "```\n(no preview)\n```" in body


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("plain prose", "```"),
        ("```hcl\nx\n```", "````"),
        ("`````\nx\n`````", "``````"),
        ("````\n``````\n````", "```````"),
    ],
)
def test_fence_for(content, expected):
    assert _fence_for(content) == expected
