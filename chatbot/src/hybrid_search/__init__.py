from hybrid_search.chainlit_root import ensure_chainlit_app_root
from hybrid_search.generate import generate_answer, unique_source_files
from hybrid_search.indexes import (
    create_chunks_indexes_if_missing,
    format_index_ready_line,
    wait_chunks_indexes_ready,
)
from hybrid_search.ingest import ingest_file
from hybrid_search.search import build_rank_fusion_pipeline, search
from hybrid_search.settings import HybridSearchSettings, get_settings

__all__ = [
    "HybridSearchSettings",
    "build_rank_fusion_pipeline",
    "create_chunks_indexes_if_missing",
    "format_index_ready_line",
    "generate_answer",
    "get_settings",
    "ingest_file",
    "search",
    "unique_source_files",
    "wait_chunks_indexes_ready",
]

# Chainlit reads CHAINLIT_APP_ROOT when chainlit.config is first imported and falls
# back to the working directory when it is unset. Set it here so any import of the
# package (for example pytest collecting the ui tests, which import chainlit before
# hybrid_search.app) reads assets/ instead of scaffolding a .chainlit/ directory into
# the working directory. app.py keeps its own call so the server path is explicit.
ensure_chainlit_app_root()
