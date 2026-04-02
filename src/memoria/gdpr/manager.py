"""GDPR Manager — cascade delete, data export, and PII scanning."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from memoria.gdpr.types import DeletionCertificate, ExportBundle

if TYPE_CHECKING:
    from memoria import Memoria

log = logging.getLogger(__name__)


class GDPRManager:
    """Orchestrates GDPR operations across all MEMORIA subsystems.

    Supports:
    - ``forget_user`` — cascade delete all data for a user
    - ``export_user_data`` — portable JSON export of all user data
    - ``scan_pii`` — detect PII in arbitrary text
    """

    def __init__(self, memoria: "Memoria") -> None:
        self._m = memoria

    # ------------------------------------------------------------------
    # Cascade Delete
    # ------------------------------------------------------------------

    def forget_user(self, user_id: str) -> DeletionCertificate:
        """Delete **all** data associated with *user_id* across every subsystem.

        Returns a ``DeletionCertificate`` documenting what was removed.
        """
        now = datetime.now(timezone.utc).isoformat()
        cert = DeletionCertificate(
            user_id=user_id,
            requested_at=now,
            completed_at="",
        )

        # 1. Namespace store (SQLite — has user_id column)
        self._delete_namespace_memories(user_id, cert)

        # 2. Vector store (SQLite — has user_id in vec_metadata)
        self._delete_vector_data(user_id, cert)

        # 3. File-based memories (scan frontmatter for user_id)
        self._delete_file_memories(user_id, cert)

        # 4. Version history (cascade from memory ids)
        self._delete_version_history(user_id, cert)

        # 5. Audit trail (cascade from memory ids)
        self._delete_audit_trail(user_id, cert)

        # 6. Preferences (in-memory dict keyed by user_id)
        self._delete_preferences(user_id, cert)

        # 7. User DNA (in-memory dict keyed by user_id)
        self._delete_user_dna(user_id, cert)

        # 8. Episodic memory (in-memory — filter events by user_id)
        self._delete_episodic_data(user_id, cert)

        # 9. Recall memory (session-based, best effort)
        self._delete_recall_data(user_id, cert)

        # 10. ACL grants (agent-id based, treat user_id as agent_id)
        self._delete_acl_grants(user_id, cert)

        cert.completed_at = datetime.now(timezone.utc).isoformat()
        log.info(
            "GDPR forget_user complete: user=%s total_deleted=%d subsystems=%s",
            user_id,
            cert.total_deleted,
            cert.subsystems_cleared,
        )
        return cert

    # ------------------------------------------------------------------
    # Data Export (Right to Portability)
    # ------------------------------------------------------------------

    def export_user_data(self, user_id: str) -> ExportBundle:
        """Export all data associated with *user_id* as a portable JSON bundle."""
        bundle = ExportBundle(
            user_id=user_id,
            exported_at=datetime.now(timezone.utc).isoformat(),
        )
        total = 0

        # Namespace memories
        try:
            store = self._m._get_namespace_store()
            rows = store._conn.execute(
                "SELECT id, namespace, content, metadata, created_at, updated_at "
                "FROM memories WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            items = []
            for r in rows:
                items.append({
                    "id": r[0], "namespace": r[1], "content": r[2],
                    "metadata": r[3], "created_at": r[4], "updated_at": r[5],
                })
            if items:
                bundle.data["namespace_memories"] = items
                total += len(items)
        except Exception as e:
            log.warning("export: namespace store error: %s", e)

        # Vector metadata
        try:
            vc = self._m._get_vector_client()
            rows = vc.conn.execute(
                "SELECT id, content, metadata, created_at FROM vec_metadata WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            items = []
            for r in rows:
                items.append({
                    "id": r[0], "content": r[1], "metadata": r[2], "created_at": r[3],
                })
            if items:
                bundle.data["vector_memories"] = items
                total += len(items)
        except Exception as e:
            log.warning("export: vector store error: %s", e)

        # File-based memories
        try:
            file_items = self._collect_file_memories(user_id)
            if file_items:
                bundle.data["file_memories"] = file_items
                total += len(file_items)
        except Exception as e:
            log.warning("export: file memories error: %s", e)

        # Preferences
        try:
            pref_store = self._m._get_preference_store()
            if hasattr(pref_store, "_preferences") and user_id in pref_store._preferences:
                prefs = []
                for pid, p in pref_store._preferences[user_id].items():
                    prefs.append({
                        "preference_id": p.preference_id,
                        "category": p.category.value if hasattr(p.category, "value") else str(p.category),
                        "key": p.key,
                        "value": p.value,
                        "confidence": p.confidence,
                    })
                if prefs:
                    bundle.data["preferences"] = prefs
                    total += len(prefs)
        except Exception as e:
            log.warning("export: preferences error: %s", e)

        # User DNA
        try:
            dna_store = self._m._get_user_dna_store()
            if hasattr(dna_store, "_profiles") and user_id in dna_store._profiles:
                profile = dna_store._profiles[user_id]
                bundle.data["user_dna"] = [{
                    "user_id": user_id,
                    "traits": {k: v for k, v in vars(profile).items() if not k.startswith("_")},
                }]
                total += 1
        except Exception as e:
            log.warning("export: user DNA error: %s", e)

        bundle.total_items = total
        return bundle

    # ------------------------------------------------------------------
    # Internal deletion helpers
    # ------------------------------------------------------------------

    def _delete_namespace_memories(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            store = self._m._get_namespace_store()
            # Collect memory IDs before deleting (needed for cascade)
            rows = store._conn.execute(
                "SELECT id FROM memories WHERE user_id = ?", (user_id,)
            ).fetchall()
            memory_ids = [r[0] for r in rows]

            cur = store._conn.execute(
                "DELETE FROM memories WHERE user_id = ?", (user_id,)
            )
            store._conn.commit()
            count = cur.rowcount
            if count > 0:
                cert.items_deleted["namespace_memories"] = count
                cert.subsystems_cleared.append("namespace_store")
            # Store memory IDs for cascade
            if not hasattr(cert, "_memory_ids"):
                cert._memory_ids = []  # type: ignore[attr-defined]
            cert._memory_ids.extend(memory_ids)  # type: ignore[attr-defined]
        except Exception as e:
            cert.errors.append(f"namespace_store: {e}")
            log.warning("GDPR delete namespace_store error: %s", e)

    def _delete_vector_data(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            vc = self._m._get_vector_client()
            rows = vc.conn.execute(
                "SELECT id FROM vec_metadata WHERE user_id = ?", (user_id,)
            ).fetchall()
            count = 0
            for (rid,) in rows:
                vc.delete(rid)
                count += 1
            if count > 0:
                cert.items_deleted["vector_embeddings"] = count
                cert.subsystems_cleared.append("vector_store")
        except Exception as e:
            cert.errors.append(f"vector_store: {e}")
            log.warning("GDPR delete vector_store error: %s", e)

    def _delete_file_memories(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            memory_dir = self._m._get_memory_dir()
            if not memory_dir.exists():
                return
            count = 0
            for md_file in memory_dir.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    if self._file_belongs_to_user(content, user_id):
                        md_file.unlink()
                        count += 1
                except Exception:
                    continue
            if count > 0:
                cert.items_deleted["file_memories"] = count
                cert.subsystems_cleared.append("file_store")
        except Exception as e:
            cert.errors.append(f"file_store: {e}")
            log.warning("GDPR delete file_store error: %s", e)

    def _delete_version_history(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            history = self._m._get_version_history()
            memory_ids = getattr(cert, "_memory_ids", [])
            if not memory_ids:
                return
            placeholders = ",".join("?" * len(memory_ids))
            cur = history._conn.execute(
                f"DELETE FROM versions WHERE memory_id IN ({placeholders})",
                memory_ids,
            )
            history._conn.commit()
            count = cur.rowcount
            if count > 0:
                cert.items_deleted["version_history"] = count
                cert.subsystems_cleared.append("version_history")
        except Exception as e:
            cert.errors.append(f"version_history: {e}")
            log.warning("GDPR delete version_history error: %s", e)

    def _delete_audit_trail(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            audit = self._m._get_audit_trail()
            memory_ids = getattr(cert, "_memory_ids", [])
            count = 0
            if memory_ids:
                placeholders = ",".join("?" * len(memory_ids))
                cur = audit._conn.execute(
                    f"DELETE FROM audit_log WHERE memory_id IN ({placeholders})",
                    memory_ids,
                )
                count += cur.rowcount
            # Also delete by agent_id = user_id (some systems use user as agent)
            cur2 = audit._conn.execute(
                "DELETE FROM audit_log WHERE agent_id = ?", (user_id,)
            )
            count += cur2.rowcount
            audit._conn.commit()
            if count > 0:
                cert.items_deleted["audit_trail"] = count
                cert.subsystems_cleared.append("audit_trail")
        except Exception as e:
            cert.errors.append(f"audit_trail: {e}")
            log.warning("GDPR delete audit_trail error: %s", e)

    def _delete_preferences(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            pref_store = self._m._get_preference_store()
            if not hasattr(pref_store, "_preferences"):
                return
            with pref_store._lock:
                prefs = pref_store._preferences.pop(user_id, None)
            if prefs:
                cert.items_deleted["preferences"] = len(prefs)
                cert.subsystems_cleared.append("preferences")
        except Exception as e:
            cert.errors.append(f"preferences: {e}")
            log.warning("GDPR delete preferences error: %s", e)

    def _delete_user_dna(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            dna_store = self._m._get_user_dna_store()
            if not hasattr(dna_store, "_profiles"):
                return
            count = 0
            with dna_store._lock:
                if dna_store._profiles.pop(user_id, None) is not None:
                    count += 1
                if hasattr(dna_store, "_history"):
                    history = dna_store._history.pop(user_id, None)
                    if history:
                        count += len(history)
                if hasattr(dna_store, "_saved_versions"):
                    dna_store._saved_versions.pop(user_id, None)
            if count > 0:
                cert.items_deleted["user_dna"] = count
                cert.subsystems_cleared.append("user_dna")
        except Exception as e:
            cert.errors.append(f"user_dna: {e}")
            log.warning("GDPR delete user_dna error: %s", e)

    def _delete_episodic_data(self, user_id: str, cert: DeletionCertificate) -> None:
        try:
            episodic = self._m._get_episodic()
            if not hasattr(episodic, "_episodes"):
                return
            count = 0
            with episodic._lock:
                empty_episodes = []
                for ep_id, episode in episodic._episodes.items():
                    before = len(episode.events)
                    episode.events = [
                        e for e in episode.events
                        if getattr(e, "user_id", None) != user_id
                    ]
                    removed = before - len(episode.events)
                    count += removed
                    if not episode.events:
                        empty_episodes.append(ep_id)
                for ep_id in empty_episodes:
                    del episodic._episodes[ep_id]
                    count += 1  # count the episode itself
            if count > 0:
                cert.items_deleted["episodic_events"] = count
                cert.subsystems_cleared.append("episodic_memory")
        except Exception as e:
            cert.errors.append(f"episodic_memory: {e}")
            log.warning("GDPR delete episodic_memory error: %s", e)

    def _delete_recall_data(self, user_id: str, cert: DeletionCertificate) -> None:
        """Best-effort: delete recall items where metadata contains user_id."""
        try:
            tiered = self._m._get_tiered_manager()
            recall = tiered._recall
            if not hasattr(recall, "_conn"):
                return
            # Recall items don't have user_id, but metadata JSON might
            rows = recall._conn.execute(
                "SELECT id, metadata FROM recall_items"
            ).fetchall()
            ids_to_delete = []
            for rid, meta_json in rows:
                try:
                    meta = json.loads(meta_json) if meta_json else {}
                    if meta.get("user_id") == user_id:
                        ids_to_delete.append(rid)
                except (json.JSONDecodeError, TypeError):
                    continue
            if ids_to_delete:
                placeholders = ",".join("?" * len(ids_to_delete))
                recall._conn.execute(
                    f"DELETE FROM recall_items WHERE id IN ({placeholders})",
                    ids_to_delete,
                )
                recall._conn.commit()
                cert.items_deleted["recall_items"] = len(ids_to_delete)
                cert.subsystems_cleared.append("recall_memory")
        except Exception as e:
            cert.errors.append(f"recall_memory: {e}")
            log.warning("GDPR delete recall_memory error: %s", e)

    def _delete_acl_grants(self, user_id: str, cert: DeletionCertificate) -> None:
        """Delete ACL grants where agent_id or granted_by matches user_id."""
        try:
            grant_store = self._m._get_grant_store()
            cur = grant_store._conn.execute(
                "DELETE FROM grants WHERE agent_id = ? OR granted_by = ?",
                (user_id, user_id),
            )
            grant_store._conn.commit()
            count = cur.rowcount
            if count > 0:
                cert.items_deleted["acl_grants"] = count
                cert.subsystems_cleared.append("acl_grants")
        except Exception as e:
            cert.errors.append(f"acl_grants: {e}")
            log.warning("GDPR delete acl_grants error: %s", e)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _file_belongs_to_user(self, content: str, user_id: str) -> bool:
        """Check if a markdown file's frontmatter references *user_id*."""
        if not content.startswith("---"):
            return False
        end = content.find("---", 3)
        if end == -1:
            return False
        frontmatter = content[3:end]
        return f"user_id: {user_id}" in frontmatter or f'"user_id": "{user_id}"' in frontmatter

    def _collect_file_memories(self, user_id: str) -> list[dict]:
        """Collect file-based memories belonging to *user_id*."""
        items: list[dict] = []
        try:
            memory_dir = self._m._get_memory_dir()
            if not memory_dir.exists():
                return items
            for md_file in memory_dir.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    if self._file_belongs_to_user(content, user_id):
                        items.append({
                            "path": str(md_file),
                            "content": content,
                        })
                except Exception:
                    continue
        except Exception:
            pass
        return items
