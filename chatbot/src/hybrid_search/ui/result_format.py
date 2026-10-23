from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hybrid_search.search import RetrievalPipeline

_BACKTICK_RUN_RE = re.compile(r"`+")


def retrieval_header(pipeline: RetrievalPipeline) -> str:
    match pipeline:
        case RetrievalPipeline.KEYWORD:
            return "Keyword search only"
        case RetrievalPipeline.VECTOR:
            return "Vector search only"
        case RetrievalPipeline.RANK_FUSION:
            return "Keyword + vector retrieval ($rankFusion)"


def format_location(ref: dict[str, Any]) -> str:
    page = ref.get("page")
    if page is not None:
        return f"p. {page}"
    start = ref.get("start_line")
    end = ref.get("end_line")
    if start is not None and end is not None:
        return f"lines {start}-{end}"
    return ""


def _fence_for(content: str) -> str:
    # A closing fence must be at least as long as the opening one, so outgrow the
    # longest backtick run in the content by one.
    longest = max((len(run) for run in _BACKTICK_RUN_RE.findall(content)), default=0)
    return "`" * max(3, longest + 1)


def hit_label(index: int, ref: dict[str, Any]) -> str:
    filename = Path(ref.get("file_path", "")).name or "unknown"
    location = format_location(ref)
    label = f"{filename} · {location}" if location else filename
    score = float(ref.get("score") or 0.0)
    return f"{index} · {label} · {score:.3f}"


def format_hit_body(ref: dict[str, Any]) -> str:
    # Fenced so the chunk's own markdown cannot break out and render as structure.
    body = str(ref.get("content", "")).strip() or "(no preview)"
    fence = _fence_for(body)
    return f"{fence}\n{body}\n{fence}"
