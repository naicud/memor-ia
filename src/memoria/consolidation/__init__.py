"""MEMORIA consolidation — lock, prompt templates, auto-dream, and dream task."""

from .lock import (
    HOLDER_STALE_S,
    LOCK_FILE_NAME,
    list_sessions_touched_since,
    read_last_consolidated_at,
    record_consolidation,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from .prompt_template import (
    ENTRYPOINT_NAME,
    MAX_ENTRYPOINT_BYTES,
    MAX_ENTRYPOINT_LINES,
    build_consolidation_prompt,
)
from .auto import (
    SESSION_SCAN_INTERVAL,
    AutoDreamConfig,
    execute_auto_dream,
    get_dream_config,
    init_auto_dream,
    is_auto_dream_enabled,
)

__all__ = [
    # lock
    "HOLDER_STALE_S",
    "LOCK_FILE_NAME",
    "list_sessions_touched_since",
    "read_last_consolidated_at",
    "record_consolidation",
    "rollback_consolidation_lock",
    "try_acquire_consolidation_lock",
    # prompt_template
    "ENTRYPOINT_NAME",
    "MAX_ENTRYPOINT_BYTES",
    "MAX_ENTRYPOINT_LINES",
    "build_consolidation_prompt",
    # auto
    "SESSION_SCAN_INTERVAL",
    "AutoDreamConfig",
    "execute_auto_dream",
    "get_dream_config",
    "init_auto_dream",
    "is_auto_dream_enabled",
]
