"""MEMORIA MCP Server — FastMCP-based Model Context Protocol server.

Exposes MEMORIA's full memory management capabilities as MCP tools, resources,
and prompts for integration with LLM clients (Claude Desktop, Cursor, etc.).

Provides 97 tools, 7 resources, and 5 prompts covering:
- Core CRUD with hybrid recall (keyword + vector + graph)
- Tiered storage (working / recall / archival)
- Episodic memory (sessions, events, timelines)
- Procedural memory (tool patterns, workflows, procedures)
- Importance scoring & self-editing memory management
- Access control, entity extraction, sync, proactive intelligence

Usage:
    # Run with stdio (default, for Claude Desktop / Cursor):
    python -m memoria.mcp.server

    # Run with HTTP streamable transport:
    python -m memoria.mcp.server --transport http --port 8080

    # Or install in Claude Desktop:
    fastmcp install claude-desktop memoria/mcp/server.py

    # Or use programmatically:
    from memoria.mcp import create_server
    server = create_server(project_dir="/path/to/project")
    server.run()                                    # stdio
    server.run(transport="http", port=8080)         # HTTP streamable
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
from typing import Any, Optional

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Global state & lazy singletons
# ---------------------------------------------------------------------------

_PROJECT_DIR = os.environ.get("MEMORIA_DATA_DIR") or os.environ.get("MEMORIA_PROJECT_DIR", os.getcwd())
_memoria_instance = None
_episodic_instance = None
_procedural_instance = None
_importance_scorer = None
_importance_tracker = None
_self_edit_instance = None

_product_tracker = None
_usage_profiler = None
_behavior_fusion = None
_churn_predictor = None
_workflow_detector = None
_habit_tracker = None
_situation_awareness = None
_intent_inference = None
_revenue_signals = None
_lifecycle_tracker = None

_poison_detector = None
_hallucination_guard = None
_tamper_proof = None
_load_tracker = None
_overload_prevention = None
_focus_optimizer = None



def _get_version():
    """Get the current MEMORIA version."""
    from memoria import __version__
    return __version__


def _get_memoria():
    """Lazy-initialize the Memoria instance.

    Backend selection via environment variables:
      MEMORIA_GRAPH_HOST    — FalkorDB host (enables real graph backend)
      MEMORIA_GRAPH_PORT    — FalkorDB port (default: 6379)
      MEMORIA_VECTOR_DB     — Path to SQLite vector DB file (enables persistence)
      MEMORIA_EMBEDDING_DIM — Embedding dimension (default: 384)
    """
    global _memoria_instance
    if _memoria_instance is None:
        from memoria import Memoria
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph
        from memoria.vector.client import VectorClient
        from memoria.vector.embeddings import TFIDFEmbedder

        dim = int(os.environ.get("MEMORIA_EMBEDDING_DIM", "384"))
        graph_host = os.environ.get("MEMORIA_GRAPH_HOST")
        graph_port = int(os.environ.get("MEMORIA_GRAPH_PORT", "6379"))
        vector_db = os.environ.get("MEMORIA_VECTOR_DB")

        graph_client = GraphClient(
            host=graph_host,
            port=graph_port if graph_host else None,
        )
        kg = KnowledgeGraph(client=graph_client)
        embedder = TFIDFEmbedder(dimension=dim)
        vector_client = VectorClient(db_path=vector_db, dimension=dim)

        _memoria_instance = Memoria(
            project_dir=_PROJECT_DIR,
            config={
                "knowledge_graph": kg,
                "embedder": embedder,
                "vector_client": vector_client,
            },
        )
    return _memoria_instance


def _get_episodic():
    """Lazy-initialize EpisodicMemory."""
    global _episodic_instance
    if _episodic_instance is None:
        from memoria.episodic import EpisodicMemory

        _episodic_instance = EpisodicMemory()
    return _episodic_instance


def _get_procedural():
    """Lazy-initialize ProceduralMemory."""
    global _procedural_instance
    if _procedural_instance is None:
        from memoria.procedural import ProceduralMemory

        _procedural_instance = ProceduralMemory()
    return _procedural_instance


def _get_importance():
    """Lazy-initialize ImportanceScorer and ImportanceTracker."""
    global _importance_scorer, _importance_tracker
    if _importance_scorer is None:
        from memoria.core.importance import ImportanceScorer, ImportanceTracker

        _importance_scorer = ImportanceScorer()
        _importance_tracker = ImportanceTracker()
    return _importance_scorer, _importance_tracker


def _get_self_edit():
    """Lazy-initialize SelfEditingMemory."""
    global _self_edit_instance
    if _self_edit_instance is None:
        from memoria.core.self_edit import SelfEditingMemory

        _self_edit_instance = SelfEditingMemory()
    return _self_edit_instance


_user_dna_store = None
_dna_collector = None
_dna_analyzer = None
_dream_engine_instance = None
_preference_store = None
_pref_detector = None
_snapshot_manager = None
_thread_tracker = None
_sharing_coordinator = None
_action_predictor = None
_anomaly_detector = None
_emotion_analyzer = None
_empathy_engine = None
_fatigue_detector = None


def _get_user_dna():
    global _user_dna_store, _dna_collector, _dna_analyzer
    if _user_dna_store is None:
        from memoria.user_dna import DNAAnalyzer, PassiveCollector, UserDNAStore
        _user_dna_store = UserDNAStore()
        _dna_collector = PassiveCollector()
        _dna_analyzer = DNAAnalyzer()
    return _user_dna_store


def _get_dream():
    global _dream_engine_instance
    if _dream_engine_instance is None:
        from memoria.dream import DreamEngine
        _dream_engine_instance = DreamEngine()
    return _dream_engine_instance


def _get_preferences():
    global _preference_store, _pref_detector
    if _preference_store is None:
        from memoria.preferences import PreferenceDetector, PreferenceStore
        _preference_store = PreferenceStore()
        _pref_detector = PreferenceDetector()
    return _preference_store


def _get_resurrection():
    global _snapshot_manager, _thread_tracker
    if _snapshot_manager is None:
        from memoria.resurrection import SnapshotManager, ThreadTracker
        _snapshot_manager = SnapshotManager()
        _thread_tracker = ThreadTracker()
    return _snapshot_manager


def _get_sharing():
    global _sharing_coordinator
    if _sharing_coordinator is None:
        from memoria.sharing import MemoryCoordinator
        _sharing_coordinator = MemoryCoordinator()
    return _sharing_coordinator


def _get_predictor():
    global _action_predictor
    if _action_predictor is None:
        from memoria.prediction import ActionPredictor
        _action_predictor = ActionPredictor()
    return _action_predictor


def _get_anomaly():
    global _anomaly_detector
    if _anomaly_detector is None:
        from memoria.prediction import AnomalyDetector
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector


def _get_emotion():
    global _emotion_analyzer
    if _emotion_analyzer is None:
        from memoria.emotional import EmotionAnalyzer
        _emotion_analyzer = EmotionAnalyzer()
    return _emotion_analyzer


def _get_empathy():
    global _empathy_engine
    if _empathy_engine is None:
        from memoria.emotional import EmpathyEngine
        _empathy_engine = EmpathyEngine()
    return _empathy_engine


def _get_fatigue():
    global _fatigue_detector
    if _fatigue_detector is None:
        from memoria.emotional import FatigueDetector
        _fatigue_detector = FatigueDetector()
    return _fatigue_detector


def _get_product_tracker():
    global _product_tracker
    if _product_tracker is None:
        from memoria.product_intel import ProductTracker
        _product_tracker = ProductTracker()
    return _product_tracker


def _get_usage_profiler():
    global _usage_profiler
    if _usage_profiler is None:
        from memoria.product_intel import UsageProfiler
        _usage_profiler = UsageProfiler()
    return _usage_profiler


def _get_behavior_fusion():
    global _behavior_fusion
    if _behavior_fusion is None:
        from memoria.fusion import BehaviorFusion
        _behavior_fusion = BehaviorFusion()
    return _behavior_fusion


def _get_churn_predictor():
    global _churn_predictor
    if _churn_predictor is None:
        from memoria.fusion import ChurnPredictor
        _churn_predictor = ChurnPredictor()
    return _churn_predictor


def _get_workflow_detector():
    global _workflow_detector
    if _workflow_detector is None:
        from memoria.fusion import WorkflowDetector
        _workflow_detector = WorkflowDetector()
    return _workflow_detector


def _get_habit_tracker():
    global _habit_tracker
    if _habit_tracker is None:
        from memoria.habits import HabitTracker
        _habit_tracker = HabitTracker()
    return _habit_tracker


def _get_situation_awareness():
    global _situation_awareness
    if _situation_awareness is None:
        from memoria.contextual import SituationAwareness
        _situation_awareness = SituationAwareness()
    return _situation_awareness


def _get_intent_inference():
    global _intent_inference
    if _intent_inference is None:
        from memoria.contextual import IntentInference
        _intent_inference = IntentInference()
    return _intent_inference


def _get_revenue_signals():
    global _revenue_signals
    if _revenue_signals is None:
        from memoria.biz_intel import RevenueSignals
        _revenue_signals = RevenueSignals()
    return _revenue_signals


def _get_lifecycle_tracker():
    global _lifecycle_tracker
    if _lifecycle_tracker is None:
        from memoria.biz_intel import LifecycleTracker
        _lifecycle_tracker = LifecycleTracker()
    return _lifecycle_tracker


def _get_poison_detector():
    global _poison_detector
    if _poison_detector is None:
        from memoria.adversarial import PoisonDetector
        _poison_detector = PoisonDetector()
    return _poison_detector


def _get_hallucination_guard():
    global _hallucination_guard
    if _hallucination_guard is None:
        from memoria.adversarial import HallucinationGuard
        _hallucination_guard = HallucinationGuard()
    return _hallucination_guard


def _get_tamper_proof():
    global _tamper_proof
    if _tamper_proof is None:
        from memoria.adversarial import TamperProof
        _tamper_proof = TamperProof()
    return _tamper_proof


def _get_load_tracker():
    global _load_tracker
    if _load_tracker is None:
        from memoria.cognitive import LoadTracker
        _load_tracker = LoadTracker()
    return _load_tracker


def _get_overload_prevention():
    global _overload_prevention
    if _overload_prevention is None:
        from memoria.cognitive import OverloadPrevention
        _overload_prevention = OverloadPrevention()
    return _overload_prevention


def _get_focus_optimizer():
    global _focus_optimizer
    if _focus_optimizer is None:
        from memoria.cognitive import FocusOptimizer
        _focus_optimizer = FocusOptimizer()
    return _focus_optimizer


def _reset_singletons():
    """Reset all lazy singletons (for testing and programmatic resets)."""
    global _memoria_instance, _episodic_instance, _procedural_instance
    global _importance_scorer, _importance_tracker, _self_edit_instance
    global _user_dna_store, _dna_collector, _dna_analyzer
    global _dream_engine_instance, _preference_store, _pref_detector
    global _snapshot_manager, _thread_tracker, _sharing_coordinator
    global _action_predictor, _anomaly_detector
    global _emotion_analyzer, _empathy_engine, _fatigue_detector
    global _product_tracker, _usage_profiler, _behavior_fusion, _churn_predictor
    global _workflow_detector, _habit_tracker, _situation_awareness, _intent_inference
    global _revenue_signals, _lifecycle_tracker
    global _poison_detector, _hallucination_guard, _tamper_proof
    global _load_tracker, _overload_prevention, _focus_optimizer
    _memoria_instance = None
    _episodic_instance = None
    _procedural_instance = None
    _importance_scorer = None
    _importance_tracker = None
    _self_edit_instance = None
    _user_dna_store = None
    _dna_collector = None
    _dna_analyzer = None
    _dream_engine_instance = None
    _preference_store = None
    _pref_detector = None
    _snapshot_manager = None
    _thread_tracker = None
    _sharing_coordinator = None
    _action_predictor = None
    _anomaly_detector = None
    _emotion_analyzer = None
    _empathy_engine = None
    _fatigue_detector = None
    _product_tracker = None
    _usage_profiler = None
    _behavior_fusion = None
    _churn_predictor = None
    _workflow_detector = None
    _habit_tracker = None
    _situation_awareness = None
    _intent_inference = None
    _revenue_signals = None
    _lifecycle_tracker = None
    _poison_detector = None
    _hallucination_guard = None
    _tamper_proof = None
    _load_tracker = None
    _overload_prevention = None
    _focus_optimizer = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_dict(obj: Any) -> Any:
    """Convert dataclasses, enums, and nested structures to JSON-safe dicts."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, enum.Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = {}
        for f in dataclasses.fields(obj):
            if f.name == "embedding":
                continue  # skip large vector fields
            d[f.name] = _to_dict(getattr(obj, f.name))
        return d
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _episode_summary(ep: Any) -> dict:
    """Convert an Episode to a dict without the full events list."""
    d = _to_dict(ep)
    if isinstance(d, dict) and "events" in d:
        d["event_count"] = len(d["events"])
        del d["events"]
    return d


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_server(project_dir: Optional[str] = None) -> FastMCP:
    """Create a configured MEMORIA MCP server.

    Args:
        project_dir: Directory for memory storage. Defaults to cwd or
                     MEMORIA_PROJECT_DIR env var.
    """
    global _PROJECT_DIR
    if project_dir:
        _PROJECT_DIR = project_dir

    return mcp


# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="MEMORIA",
    instructions=(
        "MEMORIA is a comprehensive AI memory framework providing persistent, "
        "multi-modal memory for AI agents. Capabilities include:\n\n"
        "• Core memory: store, search (hybrid recall), retrieve, delete memories\n"
        "• Tiered storage: working (ephemeral) → recall (persistent) → archival (cold)\n"
        "• Episodic memory: session-based episodes with chronological event timelines\n"
        "• Procedural memory: learned tool patterns, workflows, and reusable procedures\n"
        "• Importance scoring: multi-signal analysis (recency, frequency, connections)\n"
        "• Self-editing: autonomous memory management (compress, promote, demote, discard)\n"
        "• Memory budget: tier-aware capacity tracking and overflow handling\n"
        "• Access control: namespace-scoped ACL with role-based permissions\n"
        "• Proactive intelligence: suggestions, user profiling, cross-database insights\n"
        "• Entity extraction: automatic category, tag, and entity enrichment\n"
        "• Sync: bidirectional federation across instances\n\n"
        "Use episodic tools to track conversation flow. Use procedural tools to learn "
        "from tool usage. Use importance/self-edit tools to maintain memory health."
    ),
)


# ===================================================================
# TOOLS (1-7) — Core CRUD + Proactive Intelligence
# ===================================================================


@mcp.tool
def memoria_add(
    content: str,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    memory_type: Optional[str] = None,
) -> dict:
    """Store a new memory in MEMORIA.

    Persists content as a markdown file with YAML frontmatter.
    Optionally scope to a user_id, agent_id, or memory_type (user/project/system).

    Returns the created memory's path/id.
    """
    try:
        m = _get_memoria()
        path = m.add(
            content,
            user_id=user_id,
            agent_id=agent_id,
            memory_type=memory_type,
        )
        return {"status": "created", "id": path, "content_preview": content[:100]}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_search(
    query: str,
    user_id: Optional[str] = None,
    limit: int = 5,
    offset: int = 0,
) -> list[dict]:
    """Search memories using the hybrid recall pipeline.

    Combines keyword matching, vector similarity (TF-IDF), and knowledge
    graph traversal. Results are merged via Reciprocal Rank Fusion (RRF).

    Returns ranked results with scores and metadata.
    """
    try:
        m = _get_memoria()
        return m.search(query, user_id=user_id, limit=limit, offset=offset)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def memoria_get(memory_id: str) -> dict:
    """Retrieve a specific memory by its path/id.

    Returns the memory content and metadata, or an error if not found.
    """
    try:
        m = _get_memoria()
        result = m.get(memory_id)
        if result is None:
            return {"status": "not_found", "id": memory_id}
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_delete(memory_id: str) -> dict:
    """Delete a memory by its path/id.

    Permanently removes the memory file. Returns success/failure status.
    """
    try:
        m = _get_memoria()
        deleted = m.delete(memory_id)
        return {"status": "deleted" if deleted else "not_found", "id": memory_id}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_suggest(
    context: str = "",
    user_id: Optional[str] = None,
) -> list[dict]:
    """Generate proactive suggestions based on current context.

    Analyzes user patterns, stored memories, and knowledge graph to
    produce actionable suggestions. Uses cooldowns to avoid repetition.

    Returns a list of suggestions with type, content, and confidence.
    """
    try:
        m = _get_memoria()
        suggestions = m.suggest(context=context, user_id=user_id)
        return [
            {
                "type": getattr(s, "type", "unknown"),
                "content": getattr(s, "content", str(s)),
                "confidence": getattr(s, "confidence", 0.0),
                "reason": getattr(s, "reason", ""),
            }
            for s in suggestions
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def memoria_profile(user_id: Optional[str] = None) -> dict:
    """Get the user's profile built from interaction history.

    Returns expertise areas, working patterns, preferred topics,
    and interaction statistics.
    """
    try:
        m = _get_memoria()
        profile = m.profile(user_id=user_id)
        return {
            "user_id": getattr(profile, "user_id", user_id or "default"),
            "expertise": getattr(profile, "expertise", {}),
            "topics": getattr(profile, "topics", []),
            "message_count": getattr(profile, "message_count", 0),
            "session_count": getattr(profile, "session_count", 0),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_insights(user_id: Optional[str] = None) -> list[dict]:
    """Generate cross-database insights from stored memories.

    Discovers hidden connections between memories, identifies knowledge
    gaps, and maps expertise areas by cross-referencing graph, vector,
    and file storage.

    Returns a list of insights with type and description.
    """
    try:
        m = _get_memoria()
        insights = m.insights(user_id=user_id)
        return [
            {
                "type": getattr(i, "type", "unknown"),
                "description": getattr(i, "description", str(i)),
                "confidence": getattr(i, "confidence", 0.0),
            }
            for i in insights
        ]
    except Exception as e:
        return [{"error": str(e)}]


# ===================================================================
# TOOLS (8-12) — Tiered, ACL, Extraction, Sync
# ===================================================================


@mcp.tool
def memoria_add_to_tier(
    content: str,
    tier: str = "working",
    metadata: Optional[str] = None,
    importance: Optional[float] = None,
) -> dict:
    """Add a memory to a specific tier (working / recall / archival).

    Working memory is ephemeral and session-scoped. Recall memory persists
    across sessions. Archival is long-term cold storage.

    Returns the created memory id and the tier it was stored in.
    """
    try:
        m = _get_memoria()
        kwargs = {}
        if metadata:
            try:
                kwargs["metadata"] = json.loads(metadata)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in metadata: {e}"}
        if importance is not None:
            kwargs["importance"] = importance
        mem_id = m.add_to_tier(content, tier=tier, **kwargs)
        return {"status": "created", "id": mem_id, "tier": tier}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_search_tiers(
    query: str,
    tiers: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """Search across memory tiers (working, recall, archival).

    Optionally restrict to specific tiers via a comma-separated string
    (e.g. "working,recall"). Returns results with tier labels.
    """
    try:
        m = _get_memoria()
        tier_list = [t.strip() for t in tiers.split(",")] if tiers else None
        return m.search_tiers(query, tiers=tier_list, limit=limit, offset=offset)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def memoria_grant_access(
    agent_id: str,
    namespace: str,
    role: str = "reader",
    granted_by: str = "system",
) -> dict:
    """Grant an agent access to a namespace.

    Roles: reader, writer, admin, owner. Higher roles inherit lower
    permissions. Returns the grant id.
    """
    try:
        m = _get_memoria()
        grant_id = m.grant_access(agent_id, namespace, role=role, granted_by=granted_by)
        return {"status": "granted", "grant_id": grant_id, "agent_id": agent_id,
                "namespace": namespace, "role": role}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_enrich(content: str) -> dict:
    """Enrich content with automatic category, tags, and entity extraction.

    Uses regex-based extraction to detect categories (fact, preference,
    event, relationship, skill, opinion), tags, and named entities.

    Returns the enrichment metadata.
    """
    try:
        m = _get_memoria()
        return m.enrich(content)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_sync(namespace: Optional[str] = None) -> dict:
    """Sync memories with configured remote transport.

    Performs bidirectional sync (push then pull). Optionally scope to
    a single namespace.

    Returns pushed/pulled/conflicts/resolved counts.
    """
    try:
        m = _get_memoria()
        return m.sync(namespace=namespace)
    except Exception as e:
        return {"error": str(e)}


# ===================================================================
# TOOLS (13-17) — Episodic Memory
# ===================================================================


@mcp.tool
def episodic_start(
    title: str = "",
    agent_id: str = "",
    session_id: str = "",
) -> dict:
    """Start a new episode (session/conversation unit).

    Auto-closes any active episode. Returns episode details.
    """
    try:
        em = _get_episodic()
        active = em.get_active_episode()
        if active is not None:
            em.end_episode(
                episode_id=active.episode_id,
                summary="Auto-closed by new episode",
            )
        episode = em.start_episode(
            agent_id=agent_id, session_id=session_id, title=title,
        )
        return _episode_summary(episode)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def episodic_end(
    episode_id: str = "",
    summary: str = "",
    outcome: str = "",
) -> dict:
    """End the current or specified episode.

    Outcomes: success, failure, partial, unknown.
    """
    _valid_outcomes = {"success", "failure", "partial", "unknown", ""}
    if outcome not in _valid_outcomes:
        return {
            "error": (
                f"Invalid outcome '{outcome}'. "
                f"Must be one of: success, failure, partial, unknown"
            ),
        }
    try:
        em = _get_episodic()
        episode = em.end_episode(
            episode_id=episode_id, summary=summary, outcome=outcome,
        )
        if episode is None:
            msg = (
                "No active episode to end"
                if not episode_id
                else f"Episode '{episode_id}' not found"
            )
            return {"error": msg}
        return _episode_summary(episode)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def episodic_record(
    content: str,
    event_type: str = "interaction",
    importance: float = 0.5,
    agent_id: str = "",
    user_id: str = "",
) -> dict:
    """Record an event in the active episode.

    Types: interaction, decision, observation, tool_use, error,
    milestone, context_switch, insight.
    """
    _valid_types = {
        "interaction", "decision", "observation", "tool_use",
        "error", "milestone", "context_switch", "insight",
    }
    if event_type not in _valid_types:
        return {
            "error": (
                f"Invalid event_type '{event_type}'. "
                f"Must be one of: {', '.join(sorted(_valid_types))}"
            ),
        }
    try:
        from memoria.episodic import EventType

        em = _get_episodic()
        event = em.record_event(
            content=content,
            event_type=EventType(event_type),
            importance=importance,
            agent_id=agent_id,
            user_id=user_id,
        )
        return _to_dict(event)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def episodic_timeline(
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    event_types: Optional[str] = None,
    min_importance: float = 0.0,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Query events across episodes in a time range.

    event_types is a comma-separated list (e.g. "decision,milestone").
    """
    try:
        from memoria.episodic import EventType

        em = _get_episodic()
        type_list = None
        if event_types:
            type_list = []
            for t in event_types.split(","):
                t = t.strip()
                try:
                    type_list.append(EventType(t))
                except ValueError:
                    return [{"error": f"Invalid event_type '{t}'"}]
        events = em.query_timeline(
            start_time=start_time,
            end_time=end_time,
            event_types=type_list,
            min_importance=min_importance,
            limit=limit + offset,
        )
        events = events[offset:offset + limit]
        return _to_dict(events)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def episodic_search(query: str, limit: int = 5, offset: int = 0) -> list[dict]:
    """Search episodes by content similarity."""
    try:
        em = _get_episodic()
        episodes = em.search_episodes(query, limit=limit + offset)
        episodes = episodes[offset:offset + limit]
        return [_episode_summary(ep) for ep in episodes]
    except Exception as e:
        return [{"error": str(e)}]


# ===================================================================
# TOOLS (18-21) — Procedural Memory
# ===================================================================


@mcp.tool
def procedural_record(
    tool_name: str,
    input_data: str,
    result: str,
    success: bool = True,
    context: str = "",
    duration_ms: float = 0,
) -> dict:
    """Record a tool use for procedural learning.

    Builds usage patterns over time. Tracks success rates, durations,
    and common error patterns for each tool.
    """
    try:
        pm = _get_procedural()
        pattern = pm.record_tool_use(
            tool_name=tool_name,
            input_data=input_data,
            result=result,
            success=success,
            context=context,
            duration_ms=duration_ms,
        )
        return _to_dict(pattern)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def procedural_suggest(context: str) -> dict:
    """Suggest the best tool/procedure for the current context.

    Searches learned patterns and procedures for the best match.
    Returns tool and/or procedure suggestions based on past usage.
    """
    try:
        pm = _get_procedural()
        result: dict[str, Any] = {}
        try:
            tool = pm.suggest_tool(context)
            if tool is not None:
                result["suggested_tool"] = _to_dict(tool)
        except Exception:
            pass
        try:
            proc = pm.suggest_procedure(context)
            if proc is not None:
                result["suggested_procedure"] = _to_dict(proc)
        except Exception:
            pass
        if not result:
            result["message"] = "No matching patterns found for this context."
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def procedural_workflows(
    context: str = "",
    tags: Optional[str] = None,
) -> list[dict]:
    """Find relevant workflows. Tags is comma-separated."""
    try:
        pm = _get_procedural()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        workflows = pm.find_workflows(context=context, tags=tag_list)
        return _to_dict(workflows)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def procedural_add_workflow(
    name: str,
    steps: str,
    description: str = "",
    trigger_context: str = "",
    tags: Optional[str] = None,
) -> dict:
    """Register a workflow template.

    Steps is a JSON array of objects with keys: tool_name, description,
    input_template. Example:
    [{"tool_name":"memoria_search","description":"Find context","input_template":"{}"}]
    """
    try:
        parsed_steps = json.loads(steps)
        if not isinstance(parsed_steps, list):
            return {"error": "steps must be a JSON array"}
        for i, step in enumerate(parsed_steps):
            if not isinstance(step, dict):
                return {"error": f"Step {i} must be an object"}
            if "step_index" not in step:
                step["step_index"] = i
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON in steps: {e}"}

    try:
        pm = _get_procedural()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        wf = pm.add_workflow(
            name=name,
            steps=parsed_steps,
            description=description,
            trigger_context=trigger_context,
            tags=tag_list,
        )
        return _to_dict(wf)
    except Exception as e:
        return {"error": str(e)}


# ===================================================================
# TOOLS (22-24) — Importance & Self-Edit
# ===================================================================


@mcp.tool
def importance_score(
    memory_id: str,
    access_count: int = 0,
    connection_count: int = 0,
) -> dict:
    """Score a memory's importance (0-1) using multi-signal analysis.

    Combines recency, access frequency, connectivity, and content
    signals into a single importance score.
    """
    try:
        scorer, tracker = _get_importance()
        try:
            signals = tracker.get_signals(memory_id)
        except Exception:
            from memoria.core.importance import ImportanceSignals

            signals = ImportanceSignals()
        if access_count:
            signals.access_count = access_count
        if connection_count:
            signals.connection_count = connection_count
        score = scorer.score(signals)
        return {
            "memory_id": memory_id,
            "score": score,
            "signals": _to_dict(signals),
            "should_forget": scorer.should_forget(signals),
            "should_compress": scorer.should_compress(signals),
            "should_promote": scorer.should_promote(signals),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def self_edit(
    memory_id: str,
    action: str,
    reason: str = "",
    new_content: str = "",
    target_tier: str = "",
) -> dict:
    """Edit a memory: keep, discard, compress, promote, demote.

    Actions:
    - keep: mark as important, never auto-discard
    - discard: mark for deletion
    - compress: replace with shorter version (requires new_content)
    - promote: move to higher tier (requires target_tier)
    - demote: move to lower tier (requires target_tier)
    """
    _valid_actions = {"keep", "discard", "compress", "promote", "demote"}
    if action not in _valid_actions:
        return {
            "error": (
                f"Invalid action '{action}'. "
                f"Must be one of: {', '.join(sorted(_valid_actions))}"
            ),
        }
    if action == "compress" and not new_content:
        return {"error": "compress action requires non-empty new_content"}
    if action in ("promote", "demote") and not target_tier:
        return {"error": f"{action} action requires non-empty target_tier"}
    try:
        sem = _get_self_edit()
        if action == "keep":
            decision = sem.keep(memory_id, reason=reason)
        elif action == "discard":
            decision = sem.discard(memory_id, reason=reason)
        elif action == "compress":
            decision = sem.compress(
                memory_id, new_content=new_content, reason=reason,
            )
        elif action == "promote":
            decision = sem.promote(
                memory_id, target_tier=target_tier, reason=reason,
            )
        else:  # demote
            decision = sem.demote(
                memory_id, target_tier=target_tier, reason=reason,
            )
        return _to_dict(decision)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memory_budget() -> dict:
    """Check memory budget usage across tiers.

    Returns current/max counts and usage ratios for working, recall,
    and archival tiers, plus whether action is needed (compress/forget).
    """
    try:
        sem = _get_self_edit()
        counts: dict[str, int] = {"working": 0, "recall": 0, "archival": 0}
        try:
            m = _get_memoria()
            if hasattr(m, "_tiered_store") and m._tiered_store is not None:
                ts = m._tiered_store
                for tier_name in ("working", "recall", "archival"):
                    if hasattr(ts, "count"):
                        counts[tier_name] = ts.count(tier_name)
                    elif hasattr(ts, "list_memories"):
                        counts[tier_name] = len(ts.list_memories(tier_name))
        except Exception:
            pass
        return sem.check_budget(counts)
    except Exception as e:
        return {"error": str(e)}


# ===================================================================
# TOOLS (25-26) — Missing Core Tools
# ===================================================================


@mcp.tool
def memoria_check_access(
    agent_id: str,
    namespace: str,
    operation: str = "read",
) -> dict:
    """Check if an agent has access to a namespace.

    Operations: read, write, admin.
    """
    _valid_ops = {"read", "write", "admin"}
    if operation not in _valid_ops:
        return {
            "error": (
                f"Invalid operation '{operation}'. "
                f"Must be one of: {', '.join(sorted(_valid_ops))}"
            ),
        }
    try:
        m = _get_memoria()
        allowed = m.check_access(agent_id, namespace, operation=operation)
        return {
            "agent_id": agent_id,
            "namespace": namespace,
            "operation": operation,
            "allowed": allowed,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def memoria_stats() -> dict:
    """Get comprehensive memory statistics: counts, tiers, patterns, episodes.

    Aggregates stats from all subsystems into a single overview.
    """
    stats: dict[str, Any] = {}

    try:
        m = _get_memoria()
        from memoria.core.scanner import scan_memory_files

        files = scan_memory_files(m._mem_dir)
        stats["core"] = {
            "total_memories": len(files),
            "memory_dir": str(m._mem_dir),
        }
    except Exception as e:
        stats["core"] = {"error": str(e)}

    try:
        stats["episodic"] = _get_episodic().stats()
    except Exception as e:
        stats["episodic"] = {"error": str(e)}

    try:
        stats["procedural"] = _get_procedural().stats()
    except Exception as e:
        stats["procedural"] = {"error": str(e)}

    try:
        stats["self_edit"] = _get_self_edit().stats()
    except Exception as e:
        stats["self_edit"] = {"error": str(e)}

    return stats


# ===================================================================
# RESOURCES (1-3) — Original read-only data access
# ===================================================================


@mcp.resource("memoria://memories")
def list_memories() -> str:
    """List all stored memories with metadata.

    Returns a JSON array of all memory files in the current project.
    """
    m = _get_memoria()
    from memoria.core.scanner import scan_memory_files

    files = scan_memory_files(m._mem_dir)
    memories = []
    for f in files:
        try:
            from memoria.core.store import read_memory_file
            fm, body = read_memory_file(f)
            memories.append({
                "id": str(f),
                "name": fm.name,
                "type": fm.type.value if fm.type else None,
                "preview": body.strip()[:120],
            })
        except Exception:
            memories.append({"id": str(f), "error": "unreadable"})
    return json.dumps(memories, indent=2, default=str)


@mcp.resource("memoria://config")
def get_config() -> str:
    """Get the current MEMORIA configuration.

    Returns active backends, project directory, and feature flags.
    """
    m = _get_memoria()
    config = {
        "project_dir": str(m._cwd),
        "memory_dir": str(m._mem_dir),
        "version": _get_version(),
        "backends": {
            "graph": type(m._config.get("knowledge_graph")).__name__
            if m._config.get("knowledge_graph")
            else "none",
            "vector": type(m._config.get("vector_client")).__name__
            if m._config.get("vector_client")
            else "none",
            "embedder": type(m._config.get("embedder")).__name__
            if m._config.get("embedder")
            else "none",
        },
        "features": {
            "hybrid_recall": True,
            "proactive_suggestions": True,
            "knowledge_graph": m._config.get("knowledge_graph") is not None,
            "vector_search": m._config.get("vector_client") is not None,
            "episodic_memory": True,
            "procedural_memory": True,
            "importance_scoring": True,
            "self_editing": True,
        },
    }
    return json.dumps(config, indent=2)


@mcp.resource("memoria://profile/{user_id}")
def get_user_profile(user_id: str) -> str:
    """Get the profile for a specific user.

    Returns expertise map, topics, interaction statistics,
    and working patterns inferred from message history.
    """
    m = _get_memoria()
    profile = m.profile(user_id=user_id)
    return json.dumps(
        {
            "user_id": getattr(profile, "user_id", user_id),
            "expertise": getattr(profile, "expertise", {}),
            "topics": getattr(profile, "topics", []),
            "message_count": getattr(profile, "message_count", 0),
            "session_count": getattr(profile, "session_count", 0),
        },
        indent=2,
    )


# ===================================================================
# RESOURCES (4-7) — New read-only data access
# ===================================================================


@mcp.resource("memoria://stats")
def get_stats() -> str:
    """Comprehensive memory statistics including all subsystems."""
    return json.dumps(memoria_stats(), indent=2, default=str)


@mcp.resource("memoria://episodic/timeline")
def get_episodic_timeline() -> str:
    """Recent episodic timeline (last 20 events)."""
    try:
        em = _get_episodic()
        events = em.get_recent_events(n=20)
        return json.dumps(_to_dict(events), indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("memoria://procedural/patterns")
def get_procedural_patterns() -> str:
    """All learned tool patterns and workflows."""
    try:
        pm = _get_procedural()
        result = {
            "stats": pm.stats(),
            "procedures": _to_dict(pm.list_procedures()),
        }
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("memoria://budget")
def get_budget() -> str:
    """Current memory budget usage across tiers."""
    return json.dumps(memory_budget(), indent=2, default=str)


# ===================================================================
# PROMPTS (1-2) — Original reusable prompt templates
# ===================================================================


@mcp.prompt
def recall_context(query: str, user_id: Optional[str] = None, limit: int = 5, offset: int = 0) -> str:
    """Recall relevant memories and inject them as context.

    Searches MEMORIA for memories related to the query and formats
    them as context for the LLM to use in its response.
    """
    m = _get_memoria()
    results = m.search(query, user_id=user_id, limit=limit, offset=offset)

    if not results:
        return f"No relevant memories found for: '{query}'"

    lines = [f"## Relevant Memories for: '{query}'\n"]
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        memory = r.get("memory", "")
        sources = r.get("metadata", {}).get("sources", [])
        lines.append(f"### Memory {i} (score: {score:.3f}, via: {', '.join(sources)})")
        lines.append(memory.strip())
        lines.append("")

    lines.append(
        "---\n*Use these memories to inform your response. "
        "Cite specific memories when relevant.*"
    )
    return "\n".join(lines)


@mcp.prompt
def suggest_next(context: str = "", user_id: Optional[str] = None) -> str:
    """Generate proactive suggestions and format as an advisory prompt.

    Analyzes patterns and memories to suggest what the user might
    need next, formatted as actionable recommendations.
    """
    m = _get_memoria()
    suggestions = m.suggest(context=context, user_id=user_id)

    if not suggestions:
        return "No proactive suggestions at this time."

    lines = ["## Proactive Suggestions\n"]
    lines.append(
        "Based on your interaction history and stored knowledge, "
        "here are some suggestions:\n"
    )
    for i, s in enumerate(suggestions, 1):
        stype = getattr(s, "type", "general")
        content = getattr(s, "content", str(s))
        confidence = getattr(s, "confidence", 0.0)
        lines.append(f"{i}. **[{stype}]** {content} (confidence: {confidence:.1%})")

    lines.append(
        "\n---\n*Consider these suggestions when planning your next steps.*"
    )
    return "\n".join(lines)


# ===================================================================
# PROMPTS (3-5) — New prompt templates
# ===================================================================


@mcp.prompt
def deep_recall(query: str, user_id: Optional[str] = None) -> str:
    """Deep recall: search memories + episodic events + procedural patterns.

    Combines all memory types into comprehensive context.
    """
    lines = [f"## Deep Recall for: '{query}'\n"]

    # --- Core memories ---
    try:
        m = _get_memoria()
        results = m.search(query, user_id=user_id, limit=5)
        if results:
            lines.append("### Stored Memories")
            for i, r in enumerate(results, 1):
                score = r.get("score", 0)
                memory = r.get("memory", "")
                lines.append(f"{i}. (score: {score:.3f}) {memory.strip()[:200]}")
            lines.append("")
    except Exception:
        pass

    # --- Episodic episodes ---
    try:
        em = _get_episodic()
        episodes = em.search_episodes(query, limit=3)
        if episodes:
            lines.append("### Related Episodes")
            for ep in episodes:
                title = ep.title or ep.episode_id
                outcome = ep.outcome or "ongoing"
                summary = (ep.summary[:200]) if ep.summary else "No summary"
                lines.append(f"- **{title}** [{outcome}]: {summary}")
            lines.append("")
    except Exception:
        pass

    # --- Procedural workflows ---
    try:
        pm = _get_procedural()
        workflows = pm.find_workflows(context=query)
        if workflows:
            lines.append("### Relevant Workflows")
            for wf in workflows[:3]:
                lines.append(f"- **{wf.name}**: {wf.description[:200]}")
            lines.append("")
    except Exception:
        pass

    if len(lines) == 1:
        return f"No memories found for: '{query}'"

    lines.append(
        "---\n*Use these memories to inform your response. "
        "Cite specific memories when relevant.*"
    )
    return "\n".join(lines)


@mcp.prompt
def consolidation_report(user_id: Optional[str] = None) -> str:
    """Generate a full memory health report: stats, budget, stale patterns."""
    lines = ["## Memory Consolidation Report\n"]

    # --- System statistics ---
    try:
        stats = memoria_stats()
        lines.append("### System Statistics")
        lines.append(f"```json\n{json.dumps(stats, indent=2, default=str)}\n```\n")
    except Exception:
        lines.append("### System Statistics\n*Unavailable*\n")

    # --- Budget status ---
    try:
        budget = memory_budget()
        lines.append("### Budget Status")
        lines.append(f"```json\n{json.dumps(budget, indent=2, default=str)}\n```\n")
    except Exception:
        lines.append("### Budget Status\n*Unavailable*\n")

    # --- Stale procedures ---
    try:
        pm = _get_procedural()
        deprecated = pm.list_procedures(status="deprecated")
        if deprecated:
            lines.append(f"### Stale Procedures ({len(deprecated)})")
            for p in deprecated[:5]:
                lines.append(
                    f"- {p.name}: {p.description[:100]}"
                )
            lines.append("")
        else:
            lines.append("### Stale Procedures\nNone detected.\n")
    except Exception:
        pass

    lines.append(
        "---\n*Review this report to maintain memory health. "
        "Use self_edit to compress, promote, or discard memories as needed.*"
    )
    return "\n".join(lines)


@mcp.prompt
def episodic_recap(limit: int = 5, offset: int = 0) -> str:
    """Recap of recent episodes with summaries and outcomes."""
    try:
        em = _get_episodic()
        episodes = em.list_episodes(limit=limit + offset)
        episodes = episodes[offset:offset + limit]
    except Exception:
        return "Episodic memory not available."

    if not episodes:
        return "No episodes recorded yet."

    lines = [f"## Recent Episodes (last {limit})\n"]
    for ep in episodes:
        active = ep.is_active()
        status = "🟢 Active" if active else f"✅ {ep.outcome or 'completed'}"
        lines.append(f"### {ep.title or ep.episode_id} [{status}]")
        if ep.summary:
            lines.append(f"**Summary:** {ep.summary}")
        lines.append(f"- Events: {ep.event_count}")
        lines.append(f"- Duration: {ep.duration_s:.1f}s")
        if ep.agent_id:
            lines.append(f"- Agent: {ep.agent_id}")
        lines.append("")

    lines.append(
        "---\n*These episodes represent your recent work sessions.*"
    )
    return "\n".join(lines)


# ===================================================================
# User DNA tools
# ===================================================================


@mcp.tool()
def user_dna_snapshot(user_id: str) -> dict:
    """Get the complete behavioral DNA profile for a user."""
    try:
        store = _get_user_dna()
        return store.export(user_id)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def user_dna_collect(user_id: str, message: str = "", code: str = "", role: str = "user") -> dict:
    """Collect behavioral signals from user interaction to update their DNA profile."""
    try:
        store = _get_user_dna()
        global _dna_collector, _dna_analyzer
        signals = []
        if message:
            signals.append(_dna_collector.collect_from_message(message, role=role))
        if code:
            signals.append(_dna_collector.collect_from_code(code))
        dna = store.get(user_id)
        if signals:
            _dna_analyzer.analyze(dna, signals)
            store.save(dna)
        return {"user_id": user_id, "version": dna.version, "signals": len(signals)}
    except Exception as e:
        return {"error": str(e)}


# ===================================================================
# Dream Engine tools
# ===================================================================


@mcp.tool()
def dream_consolidate(memories: Optional[str] = None) -> dict:
    """Run a dream consolidation cycle to promote, compress, and forget memories."""
    try:
        from memoria.dream import MemoryCandidate
        engine = _get_dream()
        candidates = []
        if memories:
            import json
            try:
                items = json.loads(memories)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in memories: {e}"}
            for m in items:
                candidates.append(MemoryCandidate(
                    memory_id=m.get("id", ""),
                    content=m.get("content", ""),
                    tier=m.get("tier", "working"),
                    importance=m.get("importance", 0.5),
                    access_count=m.get("access_count", 0),
                ))
        result = engine.dream(candidates)
        return {
            "cycle_id": result.cycle_id,
            "success": result.success,
            "total_scanned": result.total_scanned,
            "promoted": result.promoted,
            "compressed": result.compressed,
            "forgotten": result.forgotten,
            "insights_generated": result.insights_generated,
            "duration_seconds": result.duration_seconds,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def dream_journal(limit: int = 10, offset: int = 0) -> dict:
    """View recent dream consolidation journal entries."""
    try:
        engine = _get_dream()
        entries = engine.journal.get_entries(limit=limit + offset)
        entries = entries[offset:offset + limit]
        return {"entries": [{"cycle_id": e.cycle_id, "started_at": e.started_at, "memories_scanned": e.memories_scanned, "decisions": len(e.decisions), "insights": len(e.insights)} for e in entries], "total": len(entries)}
    except Exception as e:
        return {"error": str(e)}


# ===================================================================
# Preference Engine tools
# ===================================================================


@mcp.tool()
def preference_query(user_id: str, category: str = "", min_confidence: float = 0.3) -> dict:
    """Query learned user preferences by category and confidence."""
    try:
        from memoria.preferences import PreferenceCategory, PreferenceQuery
        store = _get_preferences()
        cat = PreferenceCategory(category) if category else None
        q = PreferenceQuery(user_id=user_id, category=cat, min_confidence=min_confidence)
        prefs = store.query(q)
        return {"preferences": [{"id": p.preference_id, "category": p.category.value, "key": p.key, "value": p.value, "confidence": p.confidence, "observations": p.observation_count} for p in prefs], "total": len(prefs)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def preference_teach(user_id: str, category: str, key: str, value: str, context: str = "") -> dict:
    """Explicitly teach a user preference with high confidence."""
    try:
        from memoria.preferences import PreferenceCategory
        store = _get_preferences()
        cat = PreferenceCategory(category)
        p = store.teach(user_id, cat, key, value, context=context)
        return {"id": p.preference_id, "category": p.category.value, "key": p.key, "value": p.value, "confidence": p.confidence}
    except Exception as e:
        return {"error": str(e)}


# ===================================================================
# Context Resurrection tools
# ===================================================================


@mcp.tool()
def session_snapshot(user_id: str, session_id: str, messages: Optional[str] = None, duration_minutes: float = 0.0, outcome: str = "unknown") -> dict:
    """Capture a session snapshot for future context resurrection."""
    try:
        from memoria.resurrection import SessionOutcome
        mgr = _get_resurrection()
        msg_list = None
        if messages:
            import json
            try:
                msg_list = json.loads(messages)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in messages: {e}"}
        snap = mgr.capture(user_id=user_id, session_id=session_id, messages=msg_list, duration_minutes=duration_minutes, outcome=SessionOutcome(outcome))
        return {"snapshot_id": snap.snapshot_id, "user_id": snap.user_id, "outcome": snap.outcome.value, "message_count": snap.message_count}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def session_resume(user_id: str) -> dict:
    """Get context resurrection hints for resuming a session."""
    try:
        mgr = _get_resurrection()
        ctx = mgr.generate_resume_context(user_id)
        return {
            "user_id": ctx.user_id,
            "last_outcome": ctx.last_session_outcome.value,
            "days_since_last": ctx.days_since_last_session,
            "greeting": ctx.greeting_suggestion,
            "hints": [{"type": h.hint_type, "title": h.title, "description": h.description, "priority": h.priority} for h in ctx.hints],
            "active_threads": len(ctx.active_threads),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def team_share_memory(agent_id: str, namespace: str, key: str, value: str,
                      topics: str = "") -> dict:
    """Share a memory across team agents via the broadcast system."""
    try:
        coord = _get_sharing()
        topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else []
        result = coord.share_memory(agent_id, namespace, key, value, topics=topic_list)
        return result if isinstance(result, dict) else {"status": "shared", "key": key}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def team_coherence_check(team_id: str) -> dict:
    """Check memory coherence within a team, detecting conflicts."""
    try:
        coord = _get_sharing()
        report = coord.check_coherence(team_id)
        return report._to_dict() if hasattr(report, '_to_dict') else {"team_id": team_id, "status": "checked"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def predict_next_action(action: str = "", top_k: int = 3) -> dict:
    """Record an action and predict the next user action using Markov chains."""
    try:
        predictor = _get_predictor()
        if action:
            predictor.record_action(action)
        pred = predictor.predict_next(top_k=top_k)
        return pred.to_dict() if hasattr(pred, 'to_dict') else pred._to_dict() if hasattr(pred, '_to_dict') else {"predicted_value": pred.predicted_value, "confidence": pred.confidence}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def estimate_difficulty(description: str, keywords: str = "") -> dict:
    """Estimate task difficulty based on user's expertise profile."""
    try:
        from memoria.prediction import DifficultyEstimator
        estimator = DifficultyEstimator()
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
        est = estimator.estimate_difficulty(description, kw_list)
        return est.to_dict() if hasattr(est, 'to_dict') else est._to_dict() if hasattr(est, '_to_dict') else {"difficulty": est.estimated_difficulty.value}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def emotion_analyze(text: str, context: str = "") -> dict:
    """Analyze emotional content of text with multi-signal sentiment analysis."""
    try:
        analyzer = _get_emotion()
        reading = analyzer.analyze(text, context=context)
        return reading._to_dict() if hasattr(reading, '_to_dict') else {"emotion": reading.emotion.value, "intensity": reading.intensity}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def emotion_fatigue_check() -> dict:
    """Check current fatigue level and burnout risk."""
    try:
        detector = _get_fatigue()
        score = detector.get_fatigue_score()
        return score._to_dict() if hasattr(score, '_to_dict') else {"current_level": score.current_level, "burnout_risk": score.burnout_risk}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# v6 — Cross-Product Intelligence tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def product_register(product_id: str, name: str, category: str,
                           version: str = "", features: str = "") -> dict:
    """Register a product in the user's ecosystem for cross-product intelligence."""
    try:
        tracker = _get_product_tracker()
        from memoria.product_intel import ProductCategory
        cat = ProductCategory(category)
        feat_list = [f.strip() for f in features.split(",") if f.strip()] if features else []
        info = tracker.register_product(product_id, name, cat, version=version, features=feat_list)
        return _to_dict(info)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def product_usage_record(product_id: str, feature: str, action: str,
                                duration: float = 0.0, session_id: str = "") -> dict:
    """Record a product usage event for behavioral analysis."""
    try:
        profiler = _get_usage_profiler()
        event = profiler.record_event(product_id, feature, action, duration=duration, session_id=session_id)
        profile = profiler.get_profile(product_id)
        return {"event": _to_dict(event), "profile_summary": {"total_events": profile.total_events if profile else 0, "frequency": profile.frequency.value if profile else "inactive"}}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def fusion_unified_model() -> dict:
    """Get the unified user model across all products."""
    try:
        fusion = _get_behavior_fusion()
        model = fusion.get_unified_model()
        return _to_dict(model)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def fusion_churn_predict(product_id: str) -> dict:
    """Predict churn risk for a specific product."""
    try:
        predictor = _get_churn_predictor()
        prediction = predictor.predict_churn(product_id)
        return _to_dict(prediction)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def fusion_detect_workflows(min_frequency: int = 3) -> dict:
    """Detect cross-product workflows from usage patterns."""
    try:
        detector = _get_workflow_detector()
        workflows = detector.detect_workflows(min_frequency=min_frequency)
        return {"workflows": [_to_dict(w) for w in workflows], "total": len(workflows)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def habit_detect(action: str = "", product_id: str = "") -> dict:
    """Record an action and detect user habits."""
    try:
        tracker = _get_habit_tracker()
        if action:
            tracker.record_action(action, product_id=product_id)
        habits = tracker.detect_habits()
        return {"habits": [_to_dict(h) for h in habits], "total": len(habits)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def context_situation(product_id: str, action: str) -> dict:
    """Update situation awareness and get current context."""
    try:
        awareness = _get_situation_awareness()
        snapshot = awareness.update(product_id, action)
        return _to_dict(snapshot)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def context_infer_intent(product_id: str, action: str) -> dict:
    """Observe action and infer user intent."""
    try:
        inference = _get_intent_inference()
        intent = inference.observe_action(product_id, action)
        if intent:
            return _to_dict(intent)
        return {"intent": None, "confidence": 0.0, "message": "No intent inferred"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def biz_revenue_signal(signal_type: str, product_id: str,
                              description: str, impact: float = 0.5,
                              confidence: float = 0.5, evidence: str = "") -> dict:
    """Record a revenue-relevant business signal."""
    try:
        signals = _get_revenue_signals()
        from memoria.biz_intel import RevenueSignalType
        st = RevenueSignalType(signal_type)
        evidence_list = [e.strip() for e in evidence.split(",") if e.strip()] if evidence else None
        signal = signals.add_signal(st, product_id, description, impact=impact, confidence=confidence, evidence=evidence_list)
        return _to_dict(signal)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def biz_lifecycle_update(product_id: str, days_active: int = 0,
                                total_events: int = 0, feature_count: int = 0,
                                engagement_score: float = 0.5,
                                usage_trend: str = "stable",
                                is_expanding: bool = False) -> dict:
    """Update and get lifecycle position for a product."""
    try:
        tracker = _get_lifecycle_tracker()
        metrics = {
            "days_active": days_active,
            "total_events": total_events,
            "feature_count": feature_count,
            "engagement_score": engagement_score,
            "usage_trend": usage_trend,
            "is_expanding": is_expanding,
        }
        pos = tracker.update_position(product_id, metrics)
        return _to_dict(pos)
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# v7 — Defensive Intelligence tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def adversarial_scan(content: str) -> str:
    """Scan content for injection/poisoning threats."""
    try:
        detector = _get_poison_detector()
        det = detector.scan_content(content)
        return json.dumps(_to_dict(det), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def adversarial_check_consistency(content: str, facts: str = "[]") -> str:
    """Check content consistency against known facts. Pass facts as JSON array string."""
    try:
        guard = _get_hallucination_guard()
        facts_list = json.loads(facts) if facts else []
        if not isinstance(facts_list, list):
            return json.dumps({"error": "facts must be a JSON array of strings"})
        facts_list = [str(f) for f in facts_list]
        report = guard.check_consistency(content, facts_list)
        return json.dumps(_to_dict(report), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def adversarial_verify_integrity(content: str, content_id: str) -> str:
    """Hash content and verify its integrity."""
    try:
        tp = _get_tamper_proof()
        record = tp.hash_content(content, content_id)
        status = tp.verify_integrity(content, content_id)
        result = _to_dict(record)
        result["verification"] = _to_dict(status)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def cognitive_record(topic: str, complexity: float = 0.5) -> str:
    """Record a cognitive interaction and return current load."""
    try:
        tracker = _get_load_tracker()
        tracker.record_interaction(topic, complexity)
        snapshot = tracker.get_current_load()
        return json.dumps(_to_dict(snapshot), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def cognitive_check_overload() -> str:
    """Check for cognitive overload."""
    try:
        tracker = _get_load_tracker()
        snapshot = tracker.get_current_load()
        prevention = _get_overload_prevention()
        alert = prevention.check_overload(snapshot)
        return json.dumps(_to_dict(alert), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def cognitive_focus_session(action: str = "start", session_id: str = "") -> str:
    """Start or check a focus session. action='start' creates new, action='status' checks existing."""
    try:
        fo = _get_focus_optimizer()
        if action == "start":
            session = fo.start_session()
            return json.dumps(_to_dict(session), default=str)
        else:
            state = fo.detect_focus_state(session_id)
            stats = fo.get_session_stats(session_id)
            return json.dumps({"focus_state": _to_dict(state), "stats": _to_dict(stats)}, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Cache management tools (v2.1)
# ---------------------------------------------------------------------------


def _get_cache():
    """Return the global cache backend (lazy init)."""
    from memoria.cache import create_cache
    global _cache_backend
    if "_cache_backend" not in globals() or _cache_backend is None:
        _cache_backend = create_cache()
    return _cache_backend


@mcp.tool()
async def cache_stats() -> str:
    """Get cache statistics: hits, misses, hit rate, backend type, size."""
    try:
        return json.dumps(_get_cache().stats(), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def cache_clear(pattern: str = "") -> str:
    """Clear cache entries. Pass a glob pattern to selectively invalidate, or empty for full flush."""
    try:
        cache = _get_cache()
        if pattern:
            count = cache.invalidate_pattern(pattern)
            return json.dumps({"cleared": count, "pattern": pattern})
        cache.clear()
        return json.dumps({"cleared": "all"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def cache_warmup(queries: str = "[]") -> str:
    """Pre-warm the cache with a list of common search queries (JSON array of strings)."""
    try:
        import json as _json
        query_list = _json.loads(queries) if queries else []
        m = _get_memoria()
        warmed = 0
        for q in query_list:
            m.search(str(q), limit=5)
            warmed += 1
        return json.dumps({"warmed": warmed, "queries": query_list})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# GDPR operations (v2.1)
# ---------------------------------------------------------------------------

@mcp.tool()
async def gdpr_forget_user(user_id: str) -> str:
    """Delete ALL data for a user across every subsystem (GDPR right to erasure).

    Returns a deletion certificate documenting what was removed.

    ⚠️  This action is **irreversible**. All memories, preferences, DNA profile,
    episodic events, audit logs, and ACL grants for the user will be permanently
    deleted.
    """
    try:
        m = _get_memoria()
        result = m.gdpr_forget(user_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def gdpr_export_data(user_id: str) -> str:
    """Export all data for a user as a portable JSON bundle (GDPR right to portability).

    Returns all memories, preferences, and profile data associated with
    the given user_id.
    """
    try:
        m = _get_memoria()
        result = m.gdpr_export(user_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def gdpr_scan_pii(content: str) -> str:
    """Scan text for personally identifiable information (PII).

    Detects: email addresses, phone numbers, SSNs, credit card numbers,
    and IP addresses. Returns matches and a redacted version of the text.
    """
    try:
        m = _get_memoria()
        result = m.gdpr_scan_pii(content)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Webhook operations (v2.1)
# ---------------------------------------------------------------------------

@mcp.tool()
async def webhook_register(
    url: str,
    events: str = '["*"]',
    secret: str = "",
    description: str = "",
) -> str:
    """Register a webhook endpoint to receive event notifications.

    The webhook will receive HTTP POST requests with JSON payloads when
    matching events occur. Supports HMAC-SHA256 signature verification.

    Events: memory.created, memory.updated, memory.deleted, memory.promoted,
    episode.started, episode.ended, churn.detected, anomaly.detected,
    overload.detected (or "*" for all).
    """
    try:
        import json as _json
        event_list = _json.loads(events) if events else ["*"]
        m = _get_memoria()
        result = m.webhook_register(
            url, events=event_list, secret=secret, description=description
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def webhook_unregister(webhook_id: str) -> str:
    """Remove a registered webhook by its ID."""
    try:
        m = _get_memoria()
        result = m.webhook_unregister(webhook_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def webhook_list(active_only: bool = False) -> str:
    """List all registered webhooks and their status.

    Set active_only=true to only show active webhooks.
    """
    try:
        m = _get_memoria()
        result = m.webhook_list(active_only=active_only)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Summarization (v2.2)
# ---------------------------------------------------------------------------

@mcp.tool()
async def memoria_summarize(content: str, max_tokens: int = 200) -> str:
    """Summarize text using the configured LLM provider.

    Uses the provider set via MEMORIA_LLM_PROVIDER env var (default: none).
    Providers: none (truncation), ollama, openai, anthropic.
    """
    try:
        m = _get_memoria()
        result = m.summarize(content, max_tokens=max_tokens)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def memoria_summarize_all(
    namespace: str = "",
    user_id: str = "",
    limit: int = 10,
) -> str:
    """Summarize stored memories that exceed the length threshold.

    Fetches memories from the store and summarizes verbose ones.
    Returns a report with original/summary lengths and compression ratios.
    """
    try:
        m = _get_memoria()
        result = m.summarize_memories(
            namespace=namespace or None,
            user_id=user_id or None,
            limit=limit,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Deduplication tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def memoria_find_duplicates(
    content: str,
    limit: int = 10,
    threshold: float | None = None,
    user_id: str = "",
) -> str:
    """Find memories similar to the given content.

    Returns ranked duplicate candidates with similarity scores.
    """
    try:
        result = _get_memoria().find_duplicates(
            content,
            limit=limit,
            user_id=user_id or None,
            threshold=threshold,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def memoria_merge_duplicates(
    memory_id: str,
    new_content: str,
    namespace: str = "default",
) -> str:
    """Merge new content into an existing memory.

    Uses the configured merge strategy (longer, combine, newer).
    """
    try:
        result = _get_memoria().merge_duplicates(
            memory_id,
            new_content,
            namespace=namespace,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Template tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def template_list(category: str = "") -> str:
    """List available memory templates.

    Optionally filter by category (developer, engineering, collaboration, etc.).
    """
    try:
        result = _get_memoria().template_list(
            category=category or None,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def template_apply(
    template_name: str,
    data: str,
    namespace: str = "default",
    user_id: str = "",
    agent_id: str = "",
) -> str:
    """Apply a memory template to create a structured memory.

    Pass template field data as a JSON string, e.g.
    ``{"language": "Python", "framework": "FastAPI"}``.
    """
    try:
        parsed = json.loads(data)
        result = _get_memoria().template_apply(
            template_name,
            parsed,
            namespace=namespace,
            user_id=user_id or None,
            agent_id=agent_id or None,
        )
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in 'data' parameter"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def template_create(
    name: str,
    description: str,
    fields: str,
    content_template: str,
    category: str = "custom",
    tags: str = "[]",
) -> str:
    """Create a custom memory template.

    *fields* and *tags* should be JSON strings.
    """
    try:
        parsed_fields = json.loads(fields)
        parsed_tags = json.loads(tags) if tags else []
        result = _get_memoria().template_create(
            name=name,
            description=description,
            fields=parsed_fields,
            content_template=content_template,
            category=category,
            tags=parsed_tags,
        )
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in 'fields' or 'tags' parameter"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Real-time Streaming Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def stream_subscribe(
    channel_type: str = "sse",
    channel_id: str = "",
    event_types: str = "[]",
    user_ids: str = "[]",
    namespaces: str = "[]",
) -> str:
    """Create a streaming subscription for real-time memory events.

    *channel_type*: ``sse`` or ``ws``.
    *event_types*, *user_ids*, *namespaces*: JSON arrays for filtering.
    Returns channel info with the channel_id for consuming events.
    """
    try:
        et = json.loads(event_types) if event_types else []
        ui = json.loads(user_ids) if user_ids else []
        ns = json.loads(namespaces) if namespaces else []
        result = _get_memoria().stream_subscribe(
            channel_type=channel_type,
            channel_id=channel_id or None,
            event_types=et or None,
            user_ids=ui or None,
            namespaces=ns or None,
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def stream_unsubscribe(channel_id: str) -> str:
    """Close a streaming channel by ID."""
    try:
        result = _get_memoria().stream_unsubscribe(channel_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def stream_list() -> str:
    """List all active streaming channels with their filters and stats."""
    try:
        channels = _get_memoria().stream_list_channels()
        return json.dumps(channels, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def stream_broadcast(event_type: str, data: str = "{}") -> str:
    """Manually broadcast an event to all streaming channels.

    *data* should be a JSON string.
    """
    try:
        parsed_data = json.loads(data) if data else {}
        result = _get_memoria().stream_broadcast(event_type, parsed_data)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def stream_stats() -> str:
    """Return streaming manager statistics (channel counts, events dispatched)."""
    try:
        result = _get_memoria().stream_stats()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Multi-modal Memory Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_attachment(
    memory_id: str,
    data_base64: str,
    filename: str,
    mime_type: str = "application/octet-stream",
    description: str = "",
) -> str:
    """Attach a binary file (image, audio, document) to a memory.

    *data_base64*: base64-encoded binary content.
    """
    import base64
    try:
        raw = base64.b64decode(data_base64)
        result = _get_memoria().add_attachment(
            memory_id=memory_id,
            data=raw,
            filename=filename,
            mime_type=mime_type,
            description=description,
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_attachment(attachment_id: str) -> str:
    """Get attachment metadata by ID."""
    try:
        result = _get_memoria().get_attachment(attachment_id)
        if result is None:
            return json.dumps({"error": "Attachment not found"})
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def list_attachments(
    memory_id: str = "",
    limit: int = 100,
    offset: int = 0,
) -> str:
    """List attachments, optionally filtered by memory_id."""
    try:
        result = _get_memoria().list_attachments(
            memory_id=memory_id or None,
            limit=limit,
            offset=offset,
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def delete_attachment(attachment_id: str) -> str:
    """Delete an attachment by ID."""
    try:
        result = _get_memoria().delete_attachment(attachment_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def attachment_stats() -> str:
    """Return attachment storage statistics (count, disk usage)."""
    try:
        result = _get_memoria().attachment_stats()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Plugin System Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def plugin_list() -> str:
    """List all registered plugins with their status."""
    try:
        result = _get_memoria().plugin_list()
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def plugin_discover() -> str:
    """Discover and register plugins from Python entry points."""
    try:
        result = _get_memoria().plugin_discover()
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def plugin_activate(name: str) -> str:
    """Activate a registered plugin by name."""
    try:
        result = _get_memoria().plugin_activate(name)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def plugin_deactivate(name: str) -> str:
    """Deactivate a plugin by name."""
    try:
        result = _get_memoria().plugin_deactivate(name)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def plugin_stats() -> str:
    """Return plugin system statistics (registered, active, names)."""
    try:
        result = _get_memoria().plugin_stats()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Web Dashboard Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def start_dashboard(host: str = "127.0.0.1", port: int = 8080) -> str:
    """Start the Memoria web dashboard server.

    Returns the URL where the dashboard is accessible.
    """
    try:
        result = _get_memoria().start_dashboard(host=host, port=port)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def stop_dashboard() -> str:
    """Stop the Memoria web dashboard server."""
    try:
        result = _get_memoria().stop_dashboard()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def dashboard_status() -> str:
    """Get the status of the Memoria web dashboard (running, URL, uptime)."""
    try:
        result = _get_memoria().dashboard_status()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def dashboard_config() -> str:
    """Get dashboard configuration (host, port, running state)."""
    try:
        result = _get_memoria().dashboard_config()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def dashboard_url() -> str:
    """Get the dashboard URL for the running server."""
    try:
        url = _get_memoria().dashboard_url()
        return json.dumps({"url": url})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Federation Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def federation_connect(endpoint: str, instance_id: str = "",
                             public_key: str = "",
                             shared_namespaces: str = "",
                             direction: str = "bidirectional") -> str:
    """Connect to a federation peer for cross-instance memory sharing.

    Args:
        endpoint: URL of the peer's federation endpoint
        instance_id: Optional peer instance identifier
        public_key: Optional public key for trust verification
        shared_namespaces: Comma-separated list of namespaces to share
        direction: Sync direction (bidirectional, push, pull)
    """
    try:
        ns_list = [n.strip() for n in shared_namespaces.split(",") if n.strip()] if shared_namespaces else None
        result = _get_memoria().federation_connect(
            endpoint=endpoint,
            instance_id=instance_id or None,
            public_key=public_key,
            shared_namespaces=ns_list,
            direction=direction,
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def federation_disconnect(peer_id: str) -> str:
    """Disconnect from a federation peer."""
    try:
        result = _get_memoria().federation_disconnect(peer_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def federation_sync(peer_id: str, namespace: str = "general") -> str:
    """Sync memories with a federation peer for a given namespace.

    Returns sync result with counts of sent/received/conflicted memories.
    """
    try:
        result = _get_memoria().federation_sync(peer_id=peer_id, namespace=namespace)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def federation_status() -> str:
    """Get federation status (peers, trust, sync engine state)."""
    try:
        result = _get_memoria().federation_status()
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def federation_trust(instance_id: str, public_key: str = "",
                           action: str = "add",
                           trust_level: str = "standard") -> str:
    """Manage federation trust (add/revoke peers).

    Args:
        instance_id: The peer instance ID
        public_key: Public key for the peer (required for 'add')
        action: 'add' or 'revoke'
        trust_level: Trust level (untrusted, standard, elevated, full)
    """
    try:
        if action == "revoke":
            result = _get_memoria().federation_trust_revoke(instance_id)
        else:
            result = _get_memoria().federation_trust_add(
                instance_id, public_key, trust_level)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _cli():
    """Parse CLI args and run the server."""
    import argparse

    parser = argparse.ArgumentParser(description="MEMORIA MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("MEMORIA_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio, or set MEMORIA_TRANSPORT env)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MEMORIA_HOST", "127.0.0.1"),
        help="HTTP host (default: 127.0.0.1, or set MEMORIA_HOST env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MEMORIA_PORT", "8080")),
        help="HTTP port (default: 8080, or set MEMORIA_PORT env)",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Project directory for memory storage (default: cwd)",
    )

    args = parser.parse_args()

    if args.project_dir:
        global _PROJECT_DIR
        _PROJECT_DIR = args.project_dir

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    _cli()
