"""MEMORIA — Proactive Memory Framework for AI Agents."""

__version__ = "2.0.0"

from memoria.core.paths import (
    ensure_memory_dir_exists,
    get_auto_mem_path,
    get_memoria_home,
    get_project_dir,
)
from memoria.core.recall import find_relevant_memories
from memoria.core.scanner import format_memory_manifest, scan_memory_files
from memoria.core.store import (
    create_memory_file,
    delete_memory_file,
    list_memory_files,
    read_entrypoint,
    read_memory_file,
    update_entrypoint,
    write_memory_file,
)
from memoria.core.transcript import append_message, create_session, read_transcript
from memoria.core.types import MemoryFrontmatter, MemoryType


class Memoria:
    """Unified API for memory operations (v2).

    Wraps file-based memory storage with add/search/get/delete semantics
    and extends with namespace, tiered, ACL, versioning, extraction,
    reasoning, and sync capabilities.
    """

    def __init__(self, project_dir=None, config=None):
        import os
        self._cwd = project_dir or os.getcwd()
        self._config = config or {}
        self._mem_dir = ensure_memory_dir_exists(self._cwd)
        self._cache_backend = self._config.get("cache_backend")

    # ------------------------------------------------------------------
    # Core CRUD (v1 — backward compatible)
    # ------------------------------------------------------------------

    def add(self, content, *, user_id=None, session_id=None, agent_id=None,
            memory_type=None, namespace=None):
        """Store a new memory.

        When *namespace* is provided the memory is stored in the
        SharedMemoryStore; otherwise the original file-based storage is
        used, preserving full backward compatibility.

        If deduplication is enabled (``MEMORIA_DEDUP_ENABLED=true``), the
        content is checked against existing memories before storing.
        Behaviour depends on ``MEMORIA_DEDUP_MODE``:
        - ``reject`` — refuse to store if a duplicate exists.
        - ``merge``  — merge the new content into the existing memory.
        - ``warn``   — store the memory but include a warning.

        Returns the memory id (path for file-based, UUID for namespace).
        """
        # Dedup gate (opt-in)
        if self._dedup_enabled:
            try:
                match = self._get_dedup_detector().is_duplicate(content, user_id=user_id)
                if match:
                    mode = self._dedup_mode
                    if mode == "reject":
                        return {
                            "status": "duplicate",
                            "existing_id": match.memory_id,
                            "similarity": match.similarity,
                        }
                    if mode == "merge":
                        return self.merge_duplicates(
                            match.memory_id,
                            content,
                            namespace=namespace or "default",
                            new_metadata={"user_id": user_id, "agent_id": agent_id}
                            if (user_id or agent_id) else None,
                        )
                    # mode == "warn" — fall through, store with warning
                    _dedup_warning = {
                        "warning": "similar_memory_exists",
                        "existing_id": match.memory_id,
                        "similarity": match.similarity,
                    }
                else:
                    _dedup_warning = None
            except Exception:
                _dedup_warning = None
        else:
            _dedup_warning = None

        if namespace is not None:
            store = self._get_namespace_store()
            metadata = {}
            if user_id:
                metadata["user_id"] = user_id
            if agent_id:
                metadata["agent_id"] = agent_id
            if memory_type:
                mt = memory_type if isinstance(memory_type, str) else memory_type.value
                metadata["memory_type"] = mt
            memory_id = store.add(namespace, content, metadata=metadata or None,
                             user_id=user_id, agent_id=agent_id)
            if _dedup_warning:
                return {"id": memory_id, "status": "created", **_dedup_warning}
            return memory_id

        import hashlib
        import time

        from memoria.core.types import format_frontmatter

        mt = MemoryType.USER
        if memory_type is not None:
            if isinstance(memory_type, str):
                mt = MemoryType(memory_type)
            else:
                mt = memory_type

        fm = MemoryFrontmatter(
            name=content[:60].strip(),
            description=content[:120].strip(),
            type=mt,
        )
        if user_id:
            fm.raw["user_id"] = user_id
        if agent_id:
            fm.raw["agent_id"] = agent_id

        slug = hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()[:8]
        filename = f"{slug}.md"
        path = self._mem_dir / filename

        write_memory_file(path, fm, content)
        result = str(path)
        if _dedup_warning:
            return {"id": result, "status": "created", **_dedup_warning}
        return result

    def search(self, query, *, user_id=None, limit=5, offset=0, namespace=None):
        """Search memories.

        When *namespace* is provided searches the SharedMemoryStore;
        otherwise falls back to the hybrid recall pipeline (v1 path).

        Returns a list of dicts with id, score, memory, and metadata.
        """
        if namespace is not None:
            store = self._get_namespace_store()
            results = store.search(query, namespace=namespace,
                                   user_id=user_id, limit=limit, offset=offset)
            out = []
            for r in results:
                out.append({
                    "id": r.get("id", ""),
                    "score": r.get("score", 0.0),
                    "memory": r.get("content", ""),
                    "metadata": r.get("metadata", {}),
                })
            return out

        from memoria.recall.context_filter import RecallContext
        from memoria.recall.pipeline import RecallPipeline

        pipeline = RecallPipeline.create_default(
            memory_dir=self._mem_dir,
            vector_client=self._config.get("vector_client"),
            embedder=self._config.get("embedder"),
            knowledge_graph=self._config.get("knowledge_graph"),
        )

        ctx = RecallContext(user_id=user_id) if user_id else None
        ranked = pipeline.recall(query, limit=limit, offset=offset, context=ctx)

        out = []
        for r in ranked:
            out.append({
                "id": r.id,
                "score": r.final_score,
                "memory": r.content,
                "metadata": {
                    "sources": r.sources,
                    "strategy_scores": r.strategy_scores,
                    **r.metadata,
                },
            })
        return out

    def get(self, memory_id):
        """Retrieve a single memory by path/id.

        Returns a dict with the memory content and metadata, or None.
        """
        from pathlib import Path

        p = Path(memory_id)
        if not p.exists():
            return None
        try:
            fm, body = read_memory_file(p)
            return {
                "id": str(p),
                "memory": body.strip(),
                "metadata": {
                    "name": fm.name,
                    "type": fm.type.value if fm.type else None,
                    **fm.raw,
                },
            }
        except Exception:
            return None

    def delete(self, memory_id):
        """Delete a memory by path/id.

        Returns True if deleted, False otherwise.
        """
        from pathlib import Path

        p = Path(memory_id)
        if p.exists():
            p.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Proactive Intelligence Engine (v1)
    # ------------------------------------------------------------------

    def _get_profiler(self):
        if not hasattr(self, "_profiler"):
            from memoria.proactive.profiler import Profiler
            kg = self._config.get("knowledge_graph")
            self._profiler = Profiler(kg=kg)
        return self._profiler

    def _get_analyzer(self):
        if not hasattr(self, "_analyzer"):
            from memoria.proactive.analyzer import PatternAnalyzer
            self._analyzer = PatternAnalyzer()
        return self._analyzer

    def _get_suggestion_engine(self):
        if not hasattr(self, "_suggestion_engine"):
            from memoria.proactive.suggestions import SuggestionEngine
            from memoria.recall.pipeline import RecallPipeline

            pipeline = RecallPipeline.create_default(
                memory_dir=self._mem_dir,
                vector_client=self._config.get("vector_client"),
                embedder=self._config.get("embedder"),
                knowledge_graph=self._config.get("knowledge_graph"),
            )
            self._suggestion_engine = SuggestionEngine(
                profiler=self._get_profiler(),
                analyzer=self._get_analyzer(),
                pipeline=pipeline,
            )
        return self._suggestion_engine

    def _get_insight_generator(self):
        if not hasattr(self, "_insight_generator"):
            from memoria.proactive.insights import InsightGenerator
            kg = self._config.get("knowledge_graph")
            vs = self._config.get("vector_client")
            self._insight_generator = InsightGenerator(kg=kg, search=vs)
        return self._insight_generator

    def suggest(self, context="", user_id=None):
        """Generate proactive suggestions for the user.

        Returns a list of Suggestion objects.
        """
        uid = user_id or "default"
        engine = self._get_suggestion_engine()
        return engine.generate(uid, current_context=context)

    def profile(self, user_id=None):
        """Get the client profile for a user.

        Returns a ClientProfile object.
        """
        uid = user_id or "default"
        return self._get_profiler().get_profile(uid)

    def insights(self, user_id=None):
        """Generate insights from cross-referencing memory sources.

        Returns a list of Insight objects.
        """
        uid = user_id or "default"
        gen = self._get_insight_generator()
        return gen.generate_all(uid)

    # ------------------------------------------------------------------
    # v2 — Lazy initialisers for new subsystems
    # ------------------------------------------------------------------

    def _get_namespace_store(self):
        if not hasattr(self, "_namespace_store"):
            from memoria.namespace import SharedMemoryStore
            self._namespace_store = SharedMemoryStore()
        return self._namespace_store

    def _get_tiered_manager(self):
        if not hasattr(self, "_tiered_manager"):
            from memoria.tiered import TieredMemoryManager
            self._tiered_manager = TieredMemoryManager()
        return self._tiered_manager

    def _get_policy_engine(self):
        if not hasattr(self, "_policy_engine"):
            from memoria.acl import GrantStore, PolicyEngine
            self._grant_store = GrantStore()
            self._policy_engine = PolicyEngine(grant_store=self._grant_store)
        return self._policy_engine

    def _get_grant_store(self):
        self._get_policy_engine()
        return self._grant_store

    def _get_version_history(self):
        if not hasattr(self, "_version_history"):
            from memoria.versioning import VersionHistory
            self._version_history = VersionHistory()
        return self._version_history

    def _get_enricher(self):
        if not hasattr(self, "_enricher"):
            from memoria.extraction import MemoryEnricher
            self._enricher = MemoryEnricher()
        return self._enricher

    def _get_knowledge_graph_v2(self):
        if not hasattr(self, "_graph_traverser"):
            from memoria.reasoning import ExplanationBuilder, GraphTraverser
            kg = self._config.get("knowledge_graph")
            if kg is None:
                from memoria.graph.client import GraphClient
                from memoria.graph.knowledge import KnowledgeGraph
                kg = KnowledgeGraph(client=GraphClient())
            self._graph_traverser = GraphTraverser(kg)
            self._explanation_builder = ExplanationBuilder(kg, traverser=self._graph_traverser)
        return self._graph_traverser, self._explanation_builder

    # ------------------------------------------------------------------
    # v2 — Tiered memory
    # ------------------------------------------------------------------

    def add_to_tier(self, content, tier="working", **kwargs):
        """Add memory to a specific tier (working/recall/archival).

        Returns the created memory id.
        """
        mgr = self._get_tiered_manager()
        return mgr.add(content, tier=tier, **kwargs)

    def search_tiers(self, query, tiers=None, limit=10, offset=0):
        """Search across memory tiers.

        *tiers* is an optional list of tier names to search
        (e.g. ``["working", "recall"]``).  ``None`` searches all tiers.

        Returns a list of dicts.
        """
        mgr = self._get_tiered_manager()
        results = mgr.search(query, tiers=tiers, limit=limit + offset)
        return results[offset:offset + limit]

    def flush_session(self):
        """Flush working memory to recall and run auto-promote.

        Returns a dict with ``flushed_to_recall`` and ``auto_promoted`` counts.
        """
        mgr = self._get_tiered_manager()
        return mgr.flush_session()

    # ------------------------------------------------------------------
    # v2 — ACL
    # ------------------------------------------------------------------

    def grant_access(self, agent_id, namespace, role="reader", granted_by="system"):
        """Grant an agent access to a namespace.

        *role* is one of ``"reader"``, ``"writer"``, ``"admin"``, ``"owner"``.
        Returns the grant id.
        """
        from memoria.acl import Role
        role_map = {
            "reader": Role.READER,
            "writer": Role.WRITER,
            "admin": Role.ADMIN,
            "owner": Role.OWNER,
        }
        r = role_map.get(role, Role.READER) if isinstance(role, str) else role
        store = self._get_grant_store()
        return store.grant(agent_id, namespace, r, granted_by)

    def check_access(self, agent_id, namespace, operation="read"):
        """Check if *agent_id* can perform *operation* on *namespace*.

        *operation* is ``"read"``, ``"write"``, or ``"admin"``.
        """
        engine = self._get_policy_engine()
        if operation == "write":
            return engine.can_write(agent_id, namespace)
        if operation == "admin":
            return engine.can_admin(agent_id, namespace)
        return engine.can_read(agent_id, namespace)

    # ------------------------------------------------------------------
    # v2 — Versioning
    # ------------------------------------------------------------------

    def get_history(self, memory_id):
        """Get version history for a memory.

        Returns a list of ``VersionEntry`` objects.
        """
        vh = self._get_version_history()
        return vh.get_history(memory_id)

    # ------------------------------------------------------------------
    # v2 — Extraction / Enrichment
    # ------------------------------------------------------------------

    def enrich(self, content):
        """Enrich content with categories, tags, and entities.

        Returns a dict with ``category``, ``tags``, ``entities``, and
        ``entity_types`` keys.
        """
        enricher = self._get_enricher()
        memory = {"content": content, "metadata": {}}
        enriched = enricher.enrich(memory)
        return enriched.get("metadata", {})

    # ------------------------------------------------------------------
    # v2 — Reasoning / Explanation
    # ------------------------------------------------------------------

    def explain(self, entity1_id, entity2_id):
        """Explain the connection between two entities.

        Returns a dict with ``reason``, ``confidence``, ``evidence``, and
        ``paths``.
        """
        _, builder = self._get_knowledge_graph_v2()
        explanation = builder.explain_connection(entity1_id, entity2_id)
        return {
            "reason": getattr(explanation, "reason", ""),
            "confidence": getattr(explanation, "confidence", 0.0),
            "evidence": getattr(explanation, "evidence", []),
            "paths": [
                {
                    "hops": getattr(p, "hops", 0),
                    "confidence": getattr(p, "confidence", 0.0),
                    "nodes": getattr(p, "nodes", []),
                }
                for p in getattr(explanation, "graph_paths", [])
            ],
        }

    # ------------------------------------------------------------------
    # v2 — Sync
    # ------------------------------------------------------------------

    def sync(self, namespace=None):
        """Sync memories with configured remote.

        Returns a dict with ``pushed``, ``pulled``, ``conflicts``,
        ``resolved``, and ``errors``.
        """
        if not hasattr(self, "_sync_protocol"):
            from memoria.sync import InMemoryTransport, SyncProtocol
            store = self._get_namespace_store()
            transport = self._config.get("sync_transport") or InMemoryTransport()
            self._sync_protocol = SyncProtocol(
                local_store=store, transport=transport,
            )
        result = self._sync_protocol.sync(namespace=namespace)
        return {
            "pushed": getattr(result, "pushed", 0),
            "pulled": getattr(result, "pulled", 0),
            "conflicts": getattr(result, "conflicts", 0),
            "resolved": getattr(result, "resolved", 0),
            "errors": getattr(result, "errors", []),
        }

    # ------------------------------------------------------------------
    # v3 — Episodic Memory
    # ------------------------------------------------------------------

    def _get_episodic(self):
        if not hasattr(self, "_episodic"):
            from memoria.episodic import EpisodicMemory
            self._episodic = EpisodicMemory()
        return self._episodic

    def episodic_start(self, title="", agent_id="", session_id=""):
        """Start a new episode."""
        ep = self._get_episodic()
        episode = ep.start_episode(agent_id=agent_id, session_id=session_id, title=title)
        return {"episode_id": episode.episode_id, "title": episode.title, "started_at": episode.started_at}

    def episodic_end(self, episode_id="", summary="", outcome=""):
        """End an episode."""
        ep = self._get_episodic()
        episode = ep.end_episode(episode_id=episode_id, summary=summary, outcome=outcome)
        if episode is None:
            return {"status": "not_found"}
        return {"episode_id": episode.episode_id, "ended_at": episode.ended_at, "event_count": episode.event_count, "summary": episode.summary}

    def episodic_record(self, content, event_type="interaction", importance=0.5, agent_id="", user_id="", metadata=None):
        """Record an event in the active episode."""
        from memoria.episodic import EventType
        ep = self._get_episodic()
        et = EventType(event_type) if isinstance(event_type, str) else event_type
        event = ep.record_event(content, event_type=et, importance=importance, agent_id=agent_id, user_id=user_id, metadata=metadata)
        return {"event_id": event.event_id, "event_type": event.event_type.value, "timestamp": event.timestamp}

    def episodic_timeline(self, start_time=None, end_time=None, event_types=None, min_importance=0.0, limit=50, offset=0):
        """Query events across episodes."""
        ep = self._get_episodic()
        events = ep.query_timeline(start_time=start_time, end_time=end_time, event_types=event_types, min_importance=min_importance, limit=limit + offset)
        events = events[offset:offset + limit]
        return [{"event_id": e.event_id, "event_type": e.event_type.value, "content": e.content, "timestamp": e.timestamp, "importance": e.importance} for e in events]

    def episodic_search(self, query, limit=5, offset=0):
        """Search episodes by content."""
        ep = self._get_episodic()
        episodes = ep.search_episodes(query, limit=limit + offset)
        episodes = episodes[offset:offset + limit]
        return [{"episode_id": e.episode_id, "title": e.title, "event_count": e.event_count, "summary": e.summary, "outcome": e.outcome} for e in episodes]

    def episodic_stats(self):
        """Get episodic memory statistics."""
        return self._get_episodic().stats()

    # ------------------------------------------------------------------
    # v3 — Procedural Memory
    # ------------------------------------------------------------------

    def _get_procedural(self):
        if not hasattr(self, "_procedural"):
            from memoria.procedural import ProceduralMemory
            self._procedural = ProceduralMemory()
        return self._procedural

    def procedural_record(self, tool_name, input_data, result, success=True, context="", duration_ms=0):
        """Record a tool use for procedural learning."""
        pm = self._get_procedural()
        pattern = pm.record_tool_use(tool_name, input_data, result, success=success, context=context, duration_ms=duration_ms)
        return {"pattern_id": pattern.pattern_id, "tool_name": pattern.tool_name, "success_rate": pattern.success_rate, "use_count": pattern.use_count}

    def procedural_suggest(self, context):
        """Suggest tool/procedure for context."""
        pm = self._get_procedural()
        # Try tool suggestion first
        pattern = pm.suggest_tool(context)
        if pattern:
            return {"type": "tool", "tool_name": pattern.tool_name, "context_trigger": pattern.context_trigger, "success_rate": pattern.success_rate}
        # Try procedure
        proc = pm.suggest_procedure(context)
        if proc:
            return {"type": "procedure", "name": proc.name, "description": proc.description, "confidence": proc.confidence}
        return {"type": "none", "message": "No matching pattern found"}

    def procedural_workflows(self, context="", tags=None):
        """Find relevant workflows."""
        pm = self._get_procedural()
        workflows = pm.find_workflows(context=context, tags=tags)
        return [{"workflow_id": w.workflow_id, "name": w.name, "description": w.description, "step_count": w.step_count, "success_rate": w.success_rate} for w in workflows]

    def procedural_add_workflow(self, name, steps, description="", trigger_context="", tags=None):
        """Register a workflow template."""
        pm = self._get_procedural()
        wf = pm.add_workflow(name, steps, description=description, trigger_context=trigger_context, tags=tags)
        return {"workflow_id": wf.workflow_id, "name": wf.name, "step_count": wf.step_count}

    def procedural_stats(self):
        """Get procedural memory statistics."""
        return self._get_procedural().stats()

    # ------------------------------------------------------------------
    # v3 — Importance & Self-Edit
    # ------------------------------------------------------------------

    def _get_importance(self):
        if not hasattr(self, "_importance_scorer"):
            from memoria.core.importance import ImportanceScorer, ImportanceTracker
            self._importance_scorer = ImportanceScorer()
            self._importance_tracker = ImportanceTracker()
        return self._importance_scorer, self._importance_tracker

    def _get_self_edit(self):
        if not hasattr(self, "_self_edit"):
            from memoria.core.self_edit import SelfEditingMemory
            self._self_edit = SelfEditingMemory()
        return self._self_edit

    def importance_score(self, memory_id, access_count=0, connection_count=0):
        """Score a memory's importance."""
        scorer, tracker = self._get_importance()
        signals = tracker.get_signals(memory_id)
        signals.access_count = max(signals.access_count, access_count)
        signals.connection_count = max(signals.connection_count, connection_count)
        score = scorer.score(signals)
        return {"memory_id": memory_id, "score": score, "should_forget": scorer.should_forget(signals), "should_compress": scorer.should_compress(signals), "should_promote": scorer.should_promote(signals)}

    def self_edit_action(self, memory_id, action, reason="", new_content="", target_tier="", memory_ids=None):
        """Perform a self-edit action on a memory."""
        from memoria.core.self_edit import EditAction
        se = self._get_self_edit()
        act = EditAction(action)
        if act == EditAction.KEEP:
            decision = se.keep(memory_id, reason=reason)
        elif act == EditAction.DISCARD:
            decision = se.discard(memory_id, reason=reason)
        elif act == EditAction.COMPRESS:
            decision = se.compress(memory_id, new_content, reason=reason)
        elif act == EditAction.PROMOTE:
            decision = se.promote(memory_id, target_tier, reason=reason)
        elif act == EditAction.DEMOTE:
            decision = se.demote(memory_id, target_tier, reason=reason)
        elif act == EditAction.MERGE:
            ids = memory_ids or [memory_id]
            if not new_content:
                return {"error": "MERGE action requires non-empty new_content"}
            decision = se.merge(ids, new_content, reason=reason)
        else:
            return {"error": f"Unknown action: {action}"}
        return {"memory_id": decision.memory_id, "action": decision.action.value, "reason": decision.reason, "confidence": decision.confidence}

    def memory_budget(self, memory_counts=None):
        """Check memory budget usage."""
        se = self._get_self_edit()
        counts = memory_counts or {"working": 0, "recall": 0, "archival": 0}
        return se.check_budget(counts)

    def memory_stats(self):
        """Comprehensive memory statistics across all subsystems."""
        stats = {"version": __version__}
        try:
            stats["episodic"] = self._get_episodic().stats()
        except Exception:
            stats["episodic"] = {"status": "not_initialized"}
        try:
            stats["procedural"] = self._get_procedural().stats()
        except Exception:
            stats["procedural"] = {"status": "not_initialized"}
        try:
            stats["self_edit"] = self._get_self_edit().stats()
        except Exception:
            stats["self_edit"] = {"status": "not_initialized"}
        return stats

    # ------------------------------------------------------------------
    # v4 — Lazy initialisers for Ultra subsystems
    # ------------------------------------------------------------------

    def _get_user_dna_store(self):
        if not hasattr(self, '_user_dna_store'):
            from memoria.user_dna import DNAAnalyzer, PassiveCollector, UserDNAStore
            self._user_dna_store = UserDNAStore()
            self._dna_collector = PassiveCollector()
            self._dna_analyzer = DNAAnalyzer()
        return self._user_dna_store

    def _get_dream_engine(self):
        if not hasattr(self, '_dream_engine'):
            from memoria.dream import DreamEngine
            self._dream_engine = DreamEngine()
        return self._dream_engine

    def _get_preference_store(self):
        if not hasattr(self, '_preference_store'):
            from memoria.preferences import PreferenceDetector, PreferenceStore
            self._preference_store = PreferenceStore()
            self._pref_detector = PreferenceDetector()
        return self._preference_store

    def _get_snapshot_manager(self):
        if not hasattr(self, '_snapshot_manager'):
            from memoria.resurrection import SnapshotManager, ThreadTracker
            self._snapshot_manager = SnapshotManager()
            self._thread_tracker = ThreadTracker()
        return self._snapshot_manager

    def _get_memory_coordinator(self):
        if not hasattr(self, '_memory_coordinator'):
            from memoria.sharing import MemoryCoordinator
            self._memory_coordinator = MemoryCoordinator()
        return self._memory_coordinator

    def _get_action_predictor(self):
        if not hasattr(self, '_action_predictor'):
            from memoria.prediction import ActionPredictor
            self._action_predictor = ActionPredictor()
        return self._action_predictor

    def _get_anomaly_detector(self):
        if not hasattr(self, '_anomaly_detector'):
            from memoria.prediction import AnomalyDetector
            self._anomaly_detector = AnomalyDetector()
        return self._anomaly_detector

    def _get_difficulty_estimator(self):
        if not hasattr(self, '_difficulty_estimator'):
            from memoria.prediction import DifficultyEstimator
            self._difficulty_estimator = DifficultyEstimator()
        return self._difficulty_estimator

    def _get_emotion_analyzer(self):
        if not hasattr(self, '_emotion_analyzer'):
            from memoria.emotional import EmotionAnalyzer
            self._emotion_analyzer = EmotionAnalyzer()
        return self._emotion_analyzer

    def _get_emotional_arc_tracker(self):
        if not hasattr(self, '_emotional_arc_tracker'):
            from memoria.emotional import EmotionalArcTracker
            self._emotional_arc_tracker = EmotionalArcTracker()
        return self._emotional_arc_tracker

    def _get_empathy_engine(self):
        if not hasattr(self, '_empathy_engine'):
            from memoria.emotional import EmpathyEngine
            self._empathy_engine = EmpathyEngine()
        return self._empathy_engine

    def _get_fatigue_detector(self):
        if not hasattr(self, '_fatigue_detector'):
            from memoria.emotional import FatigueDetector
            self._fatigue_detector = FatigueDetector()
        return self._fatigue_detector

    # ------------------------------------------------------------------
    # v6 lazy initializers — Cross-Product Intelligence
    # ------------------------------------------------------------------

    def _get_product_tracker(self):
        if not hasattr(self, '_product_tracker'):
            from memoria.product_intel import ProductTracker
            self._product_tracker = ProductTracker()
        return self._product_tracker

    def _get_usage_profiler(self):
        if not hasattr(self, '_usage_profiler'):
            from memoria.product_intel import UsageProfiler
            self._usage_profiler = UsageProfiler()
        return self._usage_profiler

    def _get_behavior_fusion(self):
        if not hasattr(self, '_behavior_fusion'):
            from memoria.fusion import BehaviorFusion
            self._behavior_fusion = BehaviorFusion()
        return self._behavior_fusion

    def _get_churn_predictor(self):
        if not hasattr(self, '_churn_predictor'):
            from memoria.fusion import ChurnPredictor
            self._churn_predictor = ChurnPredictor()
        return self._churn_predictor

    def _get_workflow_detector(self):
        if not hasattr(self, '_workflow_detector'):
            from memoria.fusion import WorkflowDetector
            self._workflow_detector = WorkflowDetector()
        return self._workflow_detector

    def _get_habit_tracker(self):
        if not hasattr(self, '_habit_tracker'):
            from memoria.habits import HabitTracker
            self._habit_tracker = HabitTracker()
        return self._habit_tracker

    def _get_situation_awareness(self):
        if not hasattr(self, '_situation_awareness'):
            from memoria.contextual import SituationAwareness
            self._situation_awareness = SituationAwareness()
        return self._situation_awareness

    def _get_intent_inference(self):
        if not hasattr(self, '_intent_inference'):
            from memoria.contextual import IntentInference
            self._intent_inference = IntentInference()
        return self._intent_inference

    def _get_revenue_signals(self):
        if not hasattr(self, '_revenue_signals'):
            from memoria.biz_intel import RevenueSignals
            self._revenue_signals = RevenueSignals()
        return self._revenue_signals

    def _get_lifecycle_tracker(self):
        if not hasattr(self, '_lifecycle_tracker'):
            from memoria.biz_intel import LifecycleTracker
            self._lifecycle_tracker = LifecycleTracker()
        return self._lifecycle_tracker

    # ------------------------------------------------------------------
    # v7 — Defensive Intelligence (lazy initializers)
    # ------------------------------------------------------------------

    def _get_poison_detector(self):
        if not hasattr(self, '_poison_detector'):
            from .adversarial import PoisonDetector
            self._poison_detector = PoisonDetector()
        return self._poison_detector

    def _get_hallucination_guard(self):
        if not hasattr(self, '_hallucination_guard'):
            from .adversarial import HallucinationGuard
            self._hallucination_guard = HallucinationGuard()
        return self._hallucination_guard

    def _get_tamper_proof(self):
        if not hasattr(self, '_tamper_proof'):
            from .adversarial import TamperProof
            self._tamper_proof = TamperProof()
        return self._tamper_proof

    def _get_load_tracker(self):
        if not hasattr(self, '_load_tracker'):
            from .cognitive import LoadTracker
            self._load_tracker = LoadTracker()
        return self._load_tracker

    def _get_overload_prevention(self):
        if not hasattr(self, '_overload_prevention'):
            from .cognitive import OverloadPrevention
            self._overload_prevention = OverloadPrevention()
        return self._overload_prevention

    def _get_focus_optimizer(self):
        if not hasattr(self, '_focus_optimizer'):
            from .cognitive import FocusOptimizer
            self._focus_optimizer = FocusOptimizer()
        return self._focus_optimizer

    # ------------------------------------------------------------------
    # User DNA (v4 — Ultra)
    # ------------------------------------------------------------------

    def dna_collect(self, user_id, message="", code="", role="user", session_data=None):
        """Collect behavioral signals from interaction data."""
        try:
            self._get_user_dna_store()
            signals = []
            if message:
                signals.append(self._dna_collector.collect_from_message(message, role=role))
            if code:
                signals.append(self._dna_collector.collect_from_code(code))
            if session_data:
                signals.append(self._dna_collector.collect_from_session(
                    session_data.get("messages", []),
                    duration_minutes=session_data.get("duration_minutes", 0.0),
                ))
            # Analyze and update DNA
            store = self._get_user_dna_store()
            dna = store.get(user_id)
            if signals:
                self._dna_analyzer.analyze(dna, signals)
                store.save(dna)
            return {"user_id": user_id, "version": dna.version, "signals_collected": len(signals)}
        except Exception as e:
            return {"error": str(e)}

    def dna_snapshot(self, user_id):
        """Get current UserDNA snapshot."""
        try:
            store = self._get_user_dna_store()
            _dna = store.get(user_id)
            return store.export(user_id)
        except Exception as e:
            return {"error": str(e)}

    def dna_evolution(self, user_id, domain=""):
        """Track expertise evolution over time."""
        try:
            store = self._get_user_dna_store()
            if domain:
                return store.get_evolution(user_id, domain)
            dna = store.get(user_id)
            return [{"domain": e.domain, "level": e.level, "confidence": e.confidence} for e in dna.expertise]
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Dream Engine (v4 — Ultra)
    # ------------------------------------------------------------------

    def dream_run(self, memories=None, scope="recent"):
        """Run a dream consolidation cycle."""
        try:
            from memoria.dream import MemoryCandidate
            engine = self._get_dream_engine()
            if memories is None:
                memories = []
            candidates = []
            for m in memories:
                candidates.append(MemoryCandidate(
                    memory_id=m.get("id", ""),
                    content=m.get("content", ""),
                    tier=m.get("tier", "working"),
                    importance=m.get("importance", 0.5),
                    access_count=m.get("access_count", 0),
                    last_accessed=m.get("last_accessed", 0.0),
                    created_at=m.get("created_at", 0.0),
                    metadata=m.get("metadata", {}),
                ))
            result = engine.dream(candidates, scope=scope)
            return {
                "cycle_id": result.cycle_id,
                "success": result.success,
                "total_scanned": result.total_scanned,
                "promoted": result.promoted,
                "compressed": result.compressed,
                "forgotten": result.forgotten,
                "connected": result.connected,
                "merged": result.merged,
                "insights_generated": result.insights_generated,
                "duration_seconds": result.duration_seconds,
            }
        except Exception as e:
            return {"error": str(e)}

    def dream_journal(self, limit=10, offset=0):
        """Get recent dream journal entries."""
        try:
            engine = self._get_dream_engine()
            entries = engine.journal.get_entries(limit=limit + offset)
            entries = entries[offset:offset + limit]
            result = []
            for e in entries:
                result.append({
                    "cycle_id": e.cycle_id,
                    "started_at": e.started_at,
                    "completed_at": e.completed_at,
                    "memories_scanned": e.memories_scanned,
                    "decisions_count": len(e.decisions),
                    "insights_count": len(e.insights),
                })
            return result
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Preference Engine (v4 — Ultra)
    # ------------------------------------------------------------------

    def preference_detect(self, user_id, message="", code=""):
        """Auto-detect preferences from interaction."""
        try:
            self._get_preference_store()
            prefs = []
            if message:
                prefs.extend(self._pref_detector.detect_from_message(user_id, message))
            if code:
                prefs.extend(self._pref_detector.detect_from_code(user_id, code))
            store = self._get_preference_store()
            for p in prefs:
                store.upsert(p)
            return [{"id": p.preference_id, "category": p.category.value, "key": p.key, "value": p.value, "confidence": p.confidence} for p in prefs]
        except Exception as e:
            return {"error": str(e)}

    def preference_get(self, user_id, category=None, min_confidence=0.3):
        """Get user preferences."""
        try:
            from memoria.preferences import PreferenceCategory, PreferenceQuery
            store = self._get_preference_store()
            cat = PreferenceCategory(category) if category else None
            q = PreferenceQuery(user_id=user_id, category=cat, min_confidence=min_confidence)
            prefs = store.query(q)
            return [{"id": p.preference_id, "category": p.category.value, "key": p.key, "value": p.value, "confidence": p.confidence, "observations": p.observation_count} for p in prefs]
        except Exception as e:
            return {"error": str(e)}

    def preference_teach(self, user_id, category, key, value, context=""):
        """Explicitly teach a preference."""
        try:
            from memoria.preferences import PreferenceCategory
            store = self._get_preference_store()
            cat = PreferenceCategory(category)
            p = store.teach(user_id, cat, key, value, context=context)
            return {"id": p.preference_id, "category": p.category.value, "key": p.key, "value": p.value, "confidence": p.confidence}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Context Resurrection (v4 — Ultra)
    # ------------------------------------------------------------------

    def resurrection_capture(self, user_id, session_id, messages=None, duration_minutes=0.0,
                             outcome="unknown", working_files=None, branch="", project=""):
        """Capture session snapshot for future resumption."""
        try:
            from memoria.resurrection import SessionOutcome
            mgr = self._get_snapshot_manager()
            snap = mgr.capture(
                user_id=user_id, session_id=session_id,
                messages=messages, duration_minutes=duration_minutes,
                outcome=SessionOutcome(outcome),
                working_files=working_files, branch=branch, project=project,
            )
            return {
                "snapshot_id": snap.snapshot_id, "user_id": snap.user_id,
                "session_id": snap.session_id, "outcome": snap.outcome.value,
                "message_count": snap.message_count,
            }
        except Exception as e:
            return {"error": str(e)}

    def resurrection_resume(self, user_id):
        """Get resumption context for user starting a new session."""
        try:
            mgr = self._get_snapshot_manager()
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

    def resurrection_threads(self, user_id):
        """Get active work threads for user."""
        try:
            self._get_snapshot_manager()
            threads = self._thread_tracker.get_active_threads(user_id)
            return [{"id": t.thread_id, "title": t.title, "status": t.status.value, "progress": t.progress, "sessions": len(t.session_ids)} for t in threads]
        except Exception as e:
            return {"error": str(e)}

    def resurrection_create_thread(self, user_id, title, description="", session_id="", tags=None):
        """Create a new work thread."""
        try:
            self._get_snapshot_manager()
            t = self._thread_tracker.create_thread(user_id, title, description=description, session_id=session_id, tags=tags)
            return {"thread_id": t.thread_id, "title": t.title, "status": t.status.value}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Multi-Agent Sharing (v5)
    # ------------------------------------------------------------------

    def sharing_share(self, agent_id, namespace, key, value, topics=None):
        """Share a memory across team agents."""
        try:
            coord = self._get_memory_coordinator()
            result = coord.share_memory(agent_id, namespace, key, value, topics=topics)
            return result if isinstance(result, dict) else {"status": "shared"}
        except Exception as e:
            return {"error": str(e)}

    def sharing_query(self, team_id, topic=None, namespace=None):
        """Query team memories."""
        try:
            coord = self._get_memory_coordinator()
            view = coord.query_team_memories(team_id, topic=topic, namespace=namespace)
            if hasattr(view, '_to_dict'):
                return view._to_dict()
            if hasattr(view, 'to_dict'):
                return view.to_dict()
            return {"team_id": team_id, "results": str(view)}
        except Exception as e:
            return {"error": str(e)}

    def sharing_coherence(self, team_id):
        """Check memory coherence within a team."""
        try:
            coord = self._get_memory_coordinator()
            report = coord.check_coherence(team_id)
            if hasattr(report, '_to_dict'):
                return report._to_dict()
            if hasattr(report, 'to_dict'):
                return report.to_dict()
            return {"team_id": team_id, "status": "checked"}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Behavioral Prediction (v5)
    # ------------------------------------------------------------------

    def prediction_record(self, action, context=None):
        """Record a user action for prediction."""
        try:
            predictor = self._get_action_predictor()
            predictor.record_action(action, context=context)
            return {"status": "recorded", "action": action}
        except Exception as e:
            return {"error": str(e)}

    def prediction_next(self, top_k=3):
        """Predict next user action."""
        try:
            predictor = self._get_action_predictor()
            pred = predictor.predict_next(top_k=top_k)
            if hasattr(pred, 'to_dict'):
                return pred.to_dict()
            if hasattr(pred, '_to_dict'):
                return pred._to_dict()
            return {"predicted_value": pred.predicted_value, "confidence": pred.confidence,
                    "reasoning": pred.reasoning}
        except Exception as e:
            return {"error": str(e)}

    def prediction_anomaly(self, metric=None):
        """Detect behavioral anomalies."""
        try:
            detector = self._get_anomaly_detector()
            alerts = detector.detect_anomalies(metric=metric)
            return {"anomalies": [a.to_dict() if hasattr(a, 'to_dict') else
                                  a._to_dict() if hasattr(a, '_to_dict') else str(a)
                                  for a in alerts]}
        except Exception as e:
            return {"error": str(e)}

    def prediction_difficulty(self, description, keywords=None):
        """Estimate task difficulty."""
        try:
            estimator = self._get_difficulty_estimator()
            est = estimator.estimate_difficulty(description, keywords=keywords or [])
            if hasattr(est, 'to_dict'):
                return est.to_dict()
            if hasattr(est, '_to_dict'):
                return est._to_dict()
            return {"estimated_difficulty": est.estimated_difficulty.value,
                    "struggle_probability": est.struggle_probability}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Emotional Intelligence (v5)
    # ------------------------------------------------------------------

    def emotion_analyze(self, text, context=""):
        """Analyze emotional content of text."""
        try:
            analyzer = self._get_emotion_analyzer()
            reading = analyzer.analyze(text, context=context)
            if hasattr(reading, '_to_dict'):
                return reading._to_dict()
            if hasattr(reading, 'to_dict'):
                return reading.to_dict()
            return {"emotion": reading.emotion.value, "intensity": reading.intensity,
                    "confidence": reading.confidence}
        except Exception as e:
            return {"error": str(e)}

    def emotion_arc(self, session_id="default"):
        """Get emotional arc for a session."""
        try:
            tracker = self._get_emotional_arc_tracker()
            arc = tracker.get_arc(session_id=session_id)
            if hasattr(arc, '_to_dict'):
                return arc._to_dict()
            if hasattr(arc, 'to_dict'):
                return arc.to_dict()
            return {"session_id": session_id, "trend": arc.trend.value}
        except Exception as e:
            return {"error": str(e)}

    def emotion_empathy(self, text, context=""):
        """Get empathetic response suggestion for text."""
        try:
            analyzer = self._get_emotion_analyzer()
            reading = analyzer.analyze(text, context=context)
            engine = self._get_empathy_engine()
            response = engine.get_response(reading)
            if response is None:
                return {"action": "none", "message": ""}
            return response
        except Exception as e:
            return {"error": str(e)}

    def emotion_fatigue(self):
        """Get current fatigue/burnout score."""
        try:
            detector = self._get_fatigue_detector()
            score = detector.get_fatigue_score()
            if hasattr(score, '_to_dict'):
                return score._to_dict()
            if hasattr(score, 'to_dict'):
                return score.to_dict()
            return {"current_level": score.current_level, "burnout_risk": score.burnout_risk}
        except Exception as e:
            return {"error": str(e)}

    # ── v6 — Product Ecosystem Intelligence ──────────────────────
    def product_register(self, product_id, name, category, version="", features=None):
        """Register a product in the user's ecosystem."""
        try:
            tracker = self._get_product_tracker()
            from memoria.product_intel import ProductCategory
            cat = ProductCategory(category) if isinstance(category, str) else category
            _info = tracker.register_product(product_id, name, cat, version=version, features=features or [])
            return {"status": "registered", "product_id": product_id, "name": name, "category": cat.value}
        except Exception as e:
            return {"error": str(e)}

    def product_usage(self, product_id, feature, action, duration=0.0, session_id=""):
        """Record a product usage event."""
        try:
            profiler = self._get_usage_profiler()
            _event = profiler.record_event(product_id, feature, action, duration=duration, session_id=session_id)
            return {"status": "recorded", "product_id": product_id, "feature": feature, "action": action}
        except Exception as e:
            return {"error": str(e)}

    def product_profile(self, product_id):
        """Get usage profile for a product."""
        try:
            profiler = self._get_usage_profiler()
            profile = profiler.get_profile(product_id)
            if not profile:
                return {"error": "No profile found", "product_id": product_id}
            from memoria.mcp.server import _to_dict
            return _to_dict(profile)
        except Exception as e:
            try:
                profiler = self._get_usage_profiler()
                profile = profiler.get_profile(product_id)
                return {"product_id": product_id, "total_events": profile.total_events if profile else 0}
            except Exception:
                return {"error": str(e)}

    # ── v6 — Cross-Domain Behavioral Fusion ─────────────────────
    def fusion_ingest(self, source_product, signal_type, name, value, confidence=1.0):
        """Ingest a behavioral signal from any product."""
        try:
            fusion = self._get_behavior_fusion()
            _signal = fusion.ingest_signal(source_product, signal_type, name, value, confidence=confidence)
            return {"status": "ingested", "source": source_product, "signal": name}
        except Exception as e:
            return {"error": str(e)}

    def fusion_model(self):
        """Get the unified user model across all products."""
        try:
            fusion = self._get_behavior_fusion()
            model = fusion.get_unified_model()
            return {"engagement": model.engagement_score, "consistency": model.consistency_score,
                    "cross_product": model.cross_product_activity, "products": model.products_active,
                    "total_signals": model.total_signals}
        except Exception as e:
            return {"error": str(e)}

    def fusion_churn(self, product_id):
        """Predict churn risk for a product."""
        try:
            predictor = self._get_churn_predictor()
            prediction = predictor.predict_churn(product_id)
            return {"product_id": product_id, "risk": prediction.risk_level.value,
                    "probability": prediction.probability, "warnings": prediction.warning_signals,
                    "actions": prediction.recommended_actions}
        except Exception as e:
            return {"error": str(e)}

    def fusion_workflows(self):
        """Get detected cross-product workflows."""
        try:
            detector = self._get_workflow_detector()
            workflows = detector.get_workflows()
            return {"workflows": [{"name": w.name, "steps": w.steps, "frequency": w.frequency,
                                   "type": w.workflow_type.value} for w in workflows],
                    "total": len(workflows)}
        except Exception as e:
            return {"error": str(e)}

    # ── v6 — Habit & Routine Intelligence ────────────────────────
    def habit_record(self, action, product_id=""):
        """Record an action for habit detection."""
        try:
            tracker = self._get_habit_tracker()
            tracker.record_action(action, product_id=product_id)
            return {"status": "recorded", "action": action}
        except Exception as e:
            return {"error": str(e)}

    def habit_detect(self):
        """Detect user habits from recorded actions."""
        try:
            tracker = self._get_habit_tracker()
            habits = tracker.detect_habits()
            return {"habits": [{"name": h.name, "actions": h.actions, "strength": h.strength.value,
                                "frequency": h.frequency_per_week, "products": h.products_involved}
                               for h in habits], "total": len(habits)}
        except Exception as e:
            return {"error": str(e)}

    # ── v6 — Contextual Intelligence ─────────────────────────────
    def context_update(self, product_id, action, signals=None):
        """Update situation awareness with a new action."""
        try:
            awareness = self._get_situation_awareness()
            snapshot = awareness.update(product_id, action, context_signals=signals)
            return {"situation": snapshot.situation_type.value, "product": snapshot.current_product,
                    "confidence": snapshot.confidence}
        except Exception as e:
            return {"error": str(e)}

    def context_intent(self, product_id, action):
        """Observe an action and infer user intent."""
        try:
            inference = self._get_intent_inference()
            intent = inference.observe_action(product_id, action)
            if not intent:
                return {"intent": None, "confidence": 0.0}
            return {"intent": intent.intent, "confidence": intent.confidence,
                    "level": intent.confidence_level.value, "evidence": intent.supporting_evidence}
        except Exception as e:
            return {"error": str(e)}

    # ── v6 — Business Intelligence ────────────────────────────────
    def biz_signal(self, signal_type, product_id, description, impact=0.5, confidence=0.5, evidence=None):
        """Record a revenue-relevant signal."""
        try:
            signals = self._get_revenue_signals()
            from memoria.biz_intel import RevenueSignalType
            st = RevenueSignalType(signal_type) if isinstance(signal_type, str) else signal_type
            signal = signals.add_signal(st, product_id, description, impact=impact, confidence=confidence, evidence=evidence)
            return {"status": "recorded", "signal_id": signal.signal_id, "type": st.value, "impact": impact}
        except Exception as e:
            return {"error": str(e)}

    def biz_opportunities(self, top_n=10):
        """Get top revenue opportunities."""
        try:
            signals = self._get_revenue_signals()
            opps = signals.get_top_opportunities(top_n=top_n)
            return {"opportunities": [{"type": o.signal_type.value, "product": o.product_id,
                                       "description": o.description, "impact": o.impact_score,
                                       "action": o.recommended_action} for o in opps],
                    "total": len(opps)}
        except Exception as e:
            return {"error": str(e)}

    def biz_lifecycle(self, product_id, metrics):
        """Update and get lifecycle position for a product."""
        try:
            tracker = self._get_lifecycle_tracker()
            pos = tracker.update_position(product_id, metrics)
            return {"product_id": product_id, "stage": pos.stage.value, "confidence": pos.confidence,
                    "days_in_stage": pos.days_in_stage, "health": pos.stage_health}
        except Exception as e:
            return {"error": str(e)}

    # --- v7: Defensive Intelligence ---

    def adversarial_scan(self, content: str, context: dict | None = None) -> dict:
        """Scan content for injection/poisoning threats."""
        try:
            det = self._get_poison_detector().scan_content(content, context)
            return {"threat_type": det.threat_type.value, "threat_level": det.threat_level.value,
                    "description": det.description, "confidence": det.confidence,
                    "evidence": list(det.evidence), "recommended_action": det.recommended_action}
        except Exception as e:
            return {"error": str(e)}

    def adversarial_check_consistency(self, content: str, existing_facts: list | None = None) -> dict:
        """Check content consistency against known facts."""
        try:
            facts = list(existing_facts) if existing_facts else []
            report = self._get_hallucination_guard().check_consistency(content, facts)
            return {"is_consistent": report.is_consistent, "contradictions": report.contradictions,
                    "confidence": report.confidence, "checked_against": report.checked_against}
        except Exception as e:
            return {"error": str(e)}

    def adversarial_hash(self, content: str, content_id: str) -> dict:
        """Create integrity hash for content."""
        try:
            record = self._get_tamper_proof().hash_content(content, content_id)
            return {"content_hash": record.content_hash, "content_id": record.content_id,
                    "status": record.status.value}
        except Exception as e:
            return {"error": str(e)}

    def adversarial_verify(self, content: str, content_id: str) -> dict:
        """Verify content integrity."""
        try:
            status = self._get_tamper_proof().verify_integrity(content, content_id)
            return {"status": status.value, "content_id": content_id}
        except Exception as e:
            return {"error": str(e)}

    def cognitive_record(self, topic: str, complexity: float = 0.5, info_volume: int = 1) -> dict:
        """Record a cognitive interaction."""
        try:
            self._get_load_tracker().record_interaction(topic, complexity, info_volume)
            snapshot = self._get_load_tracker().get_current_load()
            return {"load_level": snapshot.load_level.value, "load_score": snapshot.load_score,
                    "focus_state": snapshot.focus_state.value, "active_topics": snapshot.active_topics}
        except Exception as e:
            return {"error": str(e)}

    def cognitive_load(self) -> dict:
        """Get current cognitive load snapshot."""
        try:
            snapshot = self._get_load_tracker().get_current_load()
            return {"load_level": snapshot.load_level.value, "load_score": snapshot.load_score,
                    "focus_state": snapshot.focus_state.value, "active_topics": snapshot.active_topics,
                    "context_switches": snapshot.context_switches}
        except Exception as e:
            return {"error": str(e)}

    def cognitive_check_overload(self) -> dict:
        """Check for cognitive overload."""
        try:
            snapshot = self._get_load_tracker().get_current_load()
            alert = self._get_overload_prevention().check_overload(snapshot)
            return {"is_overloaded": alert.is_overloaded, "severity": alert.severity,
                    "signals": [s.value for s in alert.signals],
                    "recommendation": alert.recommendation, "cooldown_minutes": alert.cooldown_minutes}
        except Exception as e:
            return {"error": str(e)}

    def cognitive_focus(self, session_id: str = None) -> dict:
        """Start or get focus session status."""
        try:
            fo = self._get_focus_optimizer()
            if session_id:
                state = fo.detect_focus_state(session_id)
                stats = fo.get_session_stats(session_id)
                return {"focus_state": state.value, "stats": stats}
            else:
                session = fo.start_session()
                return {"session_id": session.session_id, "started_at": session.started_at}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # GDPR operations (v2.1)
    # ------------------------------------------------------------------

    def _get_vector_client(self):
        """Return (or create) the vector client."""
        if not hasattr(self, "_vector_client_instance"):
            vc = self._config.get("vector_client")
            if vc is None:
                from memoria.vector.client import VectorClient
                vc = VectorClient(db_path=self._mem_dir / "vectors.db")
            self._vector_client_instance = vc
        return self._vector_client_instance

    def _get_memory_dir(self):
        """Return the memory directory as a ``Path``."""
        from pathlib import Path
        return Path(self._mem_dir)

    def _get_audit_trail(self):
        """Return (or create) the audit trail."""
        if not hasattr(self, "_audit_trail"):
            from memoria.versioning.audit import AuditTrail
            self._audit_trail = AuditTrail(db_path=self._mem_dir / "audit.db")
        return self._audit_trail

    def _get_gdpr_manager(self):
        """Return (or create) the GDPR manager."""
        if not hasattr(self, "_gdpr_manager"):
            from memoria.gdpr.manager import GDPRManager
            self._gdpr_manager = GDPRManager(self)
        return self._gdpr_manager

    def gdpr_forget(self, user_id: str) -> dict:
        """Delete all data associated with *user_id* (GDPR right to erasure).

        Returns a deletion certificate as a dict.
        """
        mgr = self._get_gdpr_manager()
        cert = mgr.forget_user(user_id)
        return {
            "certificate_id": cert.certificate_id,
            "user_id": cert.user_id,
            "requested_at": cert.requested_at,
            "completed_at": cert.completed_at,
            "items_deleted": cert.items_deleted,
            "total_deleted": cert.total_deleted,
            "subsystems_cleared": cert.subsystems_cleared,
            "errors": cert.errors,
        }

    def gdpr_export(self, user_id: str) -> dict:
        """Export all data for *user_id* (GDPR right to portability).

        Returns an export bundle as a dict.
        """
        mgr = self._get_gdpr_manager()
        bundle = mgr.export_user_data(user_id)
        return {
            "user_id": bundle.user_id,
            "exported_at": bundle.exported_at,
            "total_items": bundle.total_items,
            "data": bundle.data,
        }

    def gdpr_scan_pii(self, content: str) -> dict:
        """Scan text for PII (personally identifiable information).

        Returns detected PII matches.
        """
        from memoria.gdpr.pii import PIIScanner
        scanner = PIIScanner()
        matches = scanner.scan(content)
        return {
            "has_pii": len(matches) > 0,
            "matches": [
                {
                    "type": m.pii_type.value,
                    "value": m.value,
                    "start": m.start,
                    "end": m.end,
                }
                for m in matches
            ],
            "redacted": scanner.redact(content) if matches else content,
        }

    # ------------------------------------------------------------------
    # Cache management (v2.1)
    # ------------------------------------------------------------------

    def _get_cache(self):
        """Return (or create) the cache backend."""
        if self._cache_backend is None:
            from memoria.cache import create_cache
            self._cache_backend = create_cache()
        return self._cache_backend

    def cache_stats(self) -> dict:
        """Return cache statistics."""
        try:
            return self._get_cache().stats()
        except Exception as e:
            return {"error": str(e)}

    def cache_clear(self, pattern: str | None = None) -> dict:
        """Clear cache entries. If *pattern* is given, only matching keys."""
        try:
            cache = self._get_cache()
            if pattern:
                count = cache.invalidate_pattern(pattern)
                return {"cleared": count, "pattern": pattern}
            cache.clear()
            return {"cleared": "all"}
        except Exception as e:
            return {"error": str(e)}

    def cache_warmup(self, queries: list[str] | None = None) -> dict:
        """Warm the cache by pre-running common searches."""
        try:
            warmed = 0
            if queries:
                for q in queries:
                    self.search(q, limit=5)
                    warmed += 1
            return {"warmed": warmed}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Webhook operations (v2.1)
    # ------------------------------------------------------------------

    def _get_webhook_registry(self):
        """Return (or create) the webhook registry."""
        if not hasattr(self, "_webhook_registry"):
            from memoria.webhooks.registry import WebhookRegistry
            self._webhook_registry = WebhookRegistry(
                db_path=self._mem_dir / "webhooks.db"
            )
        return self._webhook_registry

    def _get_webhook_dispatcher(self):
        """Return (or create) the webhook dispatcher."""
        if not hasattr(self, "_webhook_dispatcher"):
            from memoria.webhooks.dispatcher import WebhookDispatcher
            self._webhook_dispatcher = WebhookDispatcher(self._get_webhook_registry())
        return self._webhook_dispatcher

    def _get_webhook_bridge(self):
        """Return (or create) the webhook bridge and start it."""
        if not hasattr(self, "_webhook_bridge"):
            from memoria.webhooks.bridge import WebhookBridge
            self._webhook_bridge = WebhookBridge(self._get_webhook_dispatcher())
            self._webhook_bridge.start()
        return self._webhook_bridge

    def webhook_register(
        self,
        url: str,
        *,
        events: list[str] | None = None,
        secret: str = "",
        description: str = "",
    ) -> dict:
        """Register a new webhook endpoint.

        Args:
            url: The HTTP(S) URL to receive POST notifications.
            events: List of event types to subscribe to (default: all).
            secret: Optional secret for HMAC-SHA256 signature verification.
            description: Human-readable label.

        Returns a dict with the created webhook details.
        """
        registry = self._get_webhook_registry()
        wh = registry.register(
            url, events=events, secret=secret, description=description
        )
        # Ensure bridge is running
        self._get_webhook_bridge()
        return {
            "webhook_id": wh.webhook_id,
            "url": wh.url,
            "events": wh.events,
            "active": wh.active,
            "description": wh.description,
            "created_at": wh.created_at,
        }

    def webhook_unregister(self, webhook_id: str) -> dict:
        """Remove a webhook registration."""
        registry = self._get_webhook_registry()
        removed = registry.unregister(webhook_id)
        return {"removed": removed, "webhook_id": webhook_id}

    def webhook_list(self, *, active_only: bool = False) -> list[dict]:
        """List all registered webhooks."""
        registry = self._get_webhook_registry()
        webhooks = registry.list_all(active_only=active_only)
        return [
            {
                "webhook_id": wh.webhook_id,
                "url": wh.url,
                "events": wh.events,
                "active": wh.active,
                "consecutive_failures": wh.consecutive_failures,
                "description": wh.description,
                "created_at": wh.created_at,
            }
            for wh in webhooks
        ]

    # ------------------------------------------------------------------
    # Summarization (v2.2)
    # ------------------------------------------------------------------

    def _get_summarizer(self):
        """Return (or create) the Summarizer."""
        if not hasattr(self, "_summarizer"):
            import os

            from memoria.intelligence.providers.base import create_provider
            from memoria.intelligence.summarizer import Summarizer

            provider = create_provider(
                provider=self._config.get("llm_provider"),
                model=self._config.get("llm_model"),
                api_key=self._config.get("llm_api_key"),
            )
            threshold = int(
                self._config.get(
                    "summarize_threshold",
                    os.environ.get("MEMORIA_SUMMARIZE_THRESHOLD", "500"),
                )
            )
            self._summarizer = Summarizer(provider, threshold=threshold)
        return self._summarizer

    def summarize(self, content: str, *, max_tokens: int = 200) -> dict:
        """Summarize text using the configured LLM provider.

        Returns a dict with summary, key_facts, compression_ratio, etc.
        """
        import asyncio
        summarizer = self._get_summarizer()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run, summarizer.summarize(content, max_tokens=max_tokens)
                ).result()
        else:
            result = asyncio.run(summarizer.summarize(content, max_tokens=max_tokens))

        return {
            "summary": result.summary,
            "key_facts": result.key_facts,
            "original_length": result.original_length,
            "summary_length": result.summary_length,
            "compression_ratio": round(result.compression_ratio, 3),
            "chunks_processed": result.chunks_processed,
            "provider": result.provider,
        }

    def summarize_memories(
        self, *, namespace: str | None = None, user_id: str | None = None, limit: int = 10
    ) -> dict:
        """Summarize stored memories matching the given filters.

        This fetches memories from the namespace store and summarizes
        those exceeding the configured character threshold.
        """
        import asyncio

        summarizer = self._get_summarizer()
        results: list[dict] = []
        skipped = 0

        try:
            store = self._get_namespace_store()
            query = "SELECT id, content FROM memories WHERE 1=1"
            params: list = []
            if namespace:
                query += " AND namespace = ?"
                params.append(namespace)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = store._conn.execute(query, params).fetchall()
            for row in rows:
                mid, content = row[0], row[1]
                if not summarizer.should_summarize(content):
                    skipped += 1
                    continue
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        sr = pool.submit(asyncio.run, summarizer.summarize(content)).result()
                else:
                    sr = asyncio.run(summarizer.summarize(content))

                results.append({
                    "memory_id": mid,
                    "original_length": sr.original_length,
                    "summary_length": sr.summary_length,
                    "compression_ratio": round(sr.compression_ratio, 3),
                    "summary": sr.summary,
                })
        except Exception as e:
            return {"error": str(e), "summarized": 0}

        return {
            "summarized": len(results),
            "skipped": skipped,
            "provider": summarizer.provider_name,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _get_embedder(self):
        """Return (or create) the embedding provider."""
        if not hasattr(self, "_embedder_instance"):
            emb = self._config.get("embedder")
            if emb is None:
                from memoria.vector.embeddings import TFIDFEmbedder
                emb = TFIDFEmbedder()
            self._embedder_instance = emb
        return self._embedder_instance

    def _get_dedup_detector(self):
        """Return (or create) the duplicate detector."""
        if not hasattr(self, "_dedup_detector"):
            import os

            from memoria.dedup.detector import DuplicateDetector
            threshold = float(
                self._config.get("dedup_threshold")
                or os.environ.get("MEMORIA_DEDUP_THRESHOLD", "0.92")
            )
            self._dedup_detector = DuplicateDetector(
                embedder=self._get_embedder(),
                vector_client=self._get_vector_client(),
                threshold=threshold,
            )
        return self._dedup_detector

    def _get_dedup_merger(self):
        """Return (or create) the memory merger."""
        if not hasattr(self, "_dedup_merger"):
            import os

            from memoria.dedup.merger import MemoryMerger
            strategy = (
                self._config.get("dedup_merge_strategy")
                or os.environ.get("MEMORIA_DEDUP_MERGE_STRATEGY", "longer")
            )
            self._dedup_merger = MemoryMerger(strategy=strategy)
        return self._dedup_merger

    @property
    def _dedup_enabled(self) -> bool:
        """Check if dedup is enabled via config or env."""
        import os
        val = (
            self._config.get("dedup_enabled")
            or os.environ.get("MEMORIA_DEDUP_ENABLED", "false")
        )
        return str(val).lower() in ("true", "1", "yes")

    @property
    def _dedup_mode(self) -> str:
        """Get dedup mode: reject, merge, or warn."""
        import os
        return (
            self._config.get("dedup_mode")
            or os.environ.get("MEMORIA_DEDUP_MODE", "warn")
        )

    def find_duplicates(
        self,
        content: str,
        *,
        limit: int = 10,
        user_id: str | None = None,
        threshold: float | None = None,
    ) -> list[dict]:
        """Find memories similar to *content*.

        Returns a list of duplicate candidates with similarity scores.
        """
        detector = self._get_dedup_detector()
        if threshold is not None:
            old = detector.threshold
            detector.threshold = threshold

        matches = detector.find_duplicates(content, limit=limit, user_id=user_id)

        if threshold is not None:
            detector.threshold = old

        return [
            {
                "memory_id": m.memory_id,
                "content": m.content,
                "similarity": m.similarity,
                "metadata": m.metadata,
            }
            for m in matches
        ]

    def merge_duplicates(
        self,
        memory_id: str,
        new_content: str,
        *,
        namespace: str = "default",
        new_metadata: dict | None = None,
    ) -> dict:
        """Merge *new_content* into an existing memory by *memory_id*.

        Uses the configured merge strategy (longer, combine, newer).
        """
        store = self._get_namespace_store()
        row = store._conn.execute(
            "SELECT content, metadata FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return {"error": f"Memory {memory_id} not found"}

        import json
        existing_content = row[0]
        existing_meta = json.loads(row[1]) if row[1] else {}

        merger = self._get_dedup_merger()
        result = merger.merge(
            existing_id=memory_id,
            existing_content=existing_content,
            existing_metadata=existing_meta,
            new_content=new_content,
            new_metadata=new_metadata,
        )

        meta_json = json.dumps(result.merged_metadata)
        store._conn.execute(
            "UPDATE memories SET content = ?, metadata = ?, updated_at = ? WHERE id = ?",
            (result.merged_content, meta_json, store._now_iso(), memory_id),
        )
        store._conn.commit()

        return {
            "status": "merged",
            "memory_id": memory_id,
            "strategy": result.strategy,
            "content_length": len(result.merged_content),
            "source_ids": result.source_ids,
        }

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def _get_template_registry(self):
        """Return (or create) the template registry."""
        if not hasattr(self, "_template_registry"):
            from memoria.templates.registry import TemplateRegistry
            self._template_registry = TemplateRegistry()
        return self._template_registry

    def template_list(self, *, category: str | None = None) -> list[dict]:
        """List available memory templates."""
        return self._get_template_registry().list(category=category)

    def template_apply(
        self,
        template_name: str,
        data: dict,
        *,
        namespace: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        """Apply a template to create a new memory.

        Validates the data against the template schema, renders the
        content, and stores it via :meth:`add`.
        """
        registry = self._get_template_registry()
        tmpl = registry.get(template_name)
        if tmpl is None:
            return {"error": f"Template '{template_name}' not found"}

        errors = tmpl.validate(data)
        if errors:
            return {"error": "Validation failed", "details": errors}

        content = tmpl.render(data)
        memory_type = tmpl.default_tier
        result = self.add(
            content,
            namespace=namespace or "default",
            user_id=user_id,
            agent_id=agent_id,
            memory_type=memory_type,
        )

        if isinstance(result, dict):
            result["template"] = template_name
            return result
        return {
            "status": "created",
            "id": result,
            "template": template_name,
            "content_length": len(content),
        }

    def template_create(
        self,
        name: str,
        description: str,
        fields: list[dict],
        content_template: str,
        *,
        category: str = "custom",
        tags: list[str] | None = None,
        default_tier: str = "working",
        default_importance: float = 0.5,
    ) -> dict:
        """Create and register a custom template."""
        from memoria.templates.schema import FieldSpec, MemoryTemplate

        field_specs = [
            FieldSpec(
                name=f["name"],
                type=f.get("type", "string"),
                required=f.get("required", False),
                description=f.get("description", ""),
                default=f.get("default"),
            )
            for f in fields
        ]
        tmpl = MemoryTemplate(
            name=name,
            description=description,
            category=category,
            fields=field_specs,
            content_template=content_template,
            tags=tags or [],
            default_tier=default_tier,
            default_importance=default_importance,
            builtin=False,
        )
        self._get_template_registry().register(tmpl)
        return {
            "status": "created",
            "name": name,
            "fields": len(field_specs),
            "category": category,
        }
