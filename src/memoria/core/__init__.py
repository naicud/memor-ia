"""MEMORIA core — paths, types, store, scanner, recall, transcript, importance, and self-edit."""

from __future__ import annotations

# Paths
from .paths import (
    AUTO_MEM_DIRNAME,
    AUTO_MEM_ENTRYPOINT_NAME,
    CLAUDE_CONFIG_DIR,
    ensure_memory_dir_exists,
    get_auto_mem_entrypoint,
    get_auto_mem_path,
    get_claude_config_home,
    get_daily_log_path,
    get_project_dir,
    get_session_dir,
    get_session_memory_path,
    get_transcript_path,
    is_auto_mem_path,
    is_auto_memory_enabled,
)

# Memory types
from .types import (
    MEMORY_TYPE_DESCRIPTIONS,
    MemoryFrontmatter,
    MemoryType,
    format_frontmatter,
    parse_frontmatter,
    parse_memory_type,
)

# Memory store
from .store import (
    EntrypointTruncation,
    create_memory_file,
    delete_memory_file,
    list_memory_files,
    read_entrypoint,
    read_memory_file,
    truncate_entrypoint,
    update_entrypoint,
    write_memory_file,
)

# Scanner
from .scanner import (
    FRONTMATTER_MAX_LINES,
    MAX_MEMORY_FILES,
    MemoryHeader,
    format_memory_manifest,
    scan_memory_files,
)

# Recall
from .recall import (
    MAX_RELEVANT,
    RelevantMemory,
    find_relevant_memories,
)

# Session transcript
from .transcript import (
    SessionInfo,
    SessionTranscript,
    append_message,
    create_session,
    list_sessions,
    list_sessions_touched_since,
    read_head_and_tail,
    read_transcript,
)

# Importance scoring
from .importance import (
    ImportanceScorer,
    ImportanceSignals,
    ImportanceTracker,
)

# Self-editing memory
from .self_edit import (
    EditAction,
    EditDecision,
    MemoryBudget,
    SelfEditingMemory,
)

__all__ = [
    # paths
    "AUTO_MEM_DIRNAME",
    "AUTO_MEM_ENTRYPOINT_NAME",
    "CLAUDE_CONFIG_DIR",
    "ensure_memory_dir_exists",
    "get_auto_mem_entrypoint",
    "get_auto_mem_path",
    "get_claude_config_home",
    "get_daily_log_path",
    "get_project_dir",
    "get_session_dir",
    "get_session_memory_path",
    "get_transcript_path",
    "is_auto_mem_path",
    "is_auto_memory_enabled",
    # types
    "MEMORY_TYPE_DESCRIPTIONS",
    "MemoryFrontmatter",
    "MemoryType",
    "format_frontmatter",
    "parse_frontmatter",
    "parse_memory_type",
    # store
    "EntrypointTruncation",
    "create_memory_file",
    "delete_memory_file",
    "list_memory_files",
    "read_entrypoint",
    "read_memory_file",
    "truncate_entrypoint",
    "update_entrypoint",
    "write_memory_file",
    # scanner
    "FRONTMATTER_MAX_LINES",
    "MAX_MEMORY_FILES",
    "MemoryHeader",
    "format_memory_manifest",
    "scan_memory_files",
    # recall
    "MAX_RELEVANT",
    "RelevantMemory",
    "find_relevant_memories",
    # transcript
    "SessionInfo",
    "SessionTranscript",
    "append_message",
    "create_session",
    "list_sessions",
    "list_sessions_touched_since",
    "read_head_and_tail",
    "read_transcript",
    # importance
    "ImportanceScorer",
    "ImportanceSignals",
    "ImportanceTracker",
    # self-edit
    "EditAction",
    "EditDecision",
    "MemoryBudget",
    "SelfEditingMemory",
]
