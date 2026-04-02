"""User DNA store — persistent storage with versioned snapshots."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import asdict

from memoria.user_dna.types import UserDNA


class UserDNAStore:
    """Persistent storage for UserDNA with versioned snapshots."""

    def __init__(self, max_snapshots: int = 50) -> None:
        self._lock = threading.RLock()
        self._max_profiles: int = 10_000
        self._profiles: dict[str, UserDNA] = {}
        self._history: dict[str, list[UserDNA]] = {}
        self._saved_versions: dict[str, int] = {}  # track last saved version
        self._max_snapshots = max_snapshots

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, user_id: str) -> UserDNA:
        """Get or create UserDNA for user."""
        with self._lock:
            if user_id not in self._profiles:
                if len(self._profiles) >= self._max_profiles:
                    oldest_uid = min(
                        self._profiles,
                        key=lambda u: self._profiles[u].updated_at,
                    )
                    del self._profiles[oldest_uid]
                    self._history.pop(oldest_uid, None)
                    self._saved_versions.pop(oldest_uid, None)
                dna = UserDNA(user_id=user_id, created_at=time.time())
                self._profiles[user_id] = dna
                self._history[user_id] = []
                self._saved_versions[user_id] = dna.version
            return self._profiles[user_id]

    def save(self, dna: UserDNA) -> None:
        """Save updated DNA, create snapshot if version changed."""
        with self._lock:
            last_ver = self._saved_versions.get(dna.user_id)

            # Snapshot previous state if version changed
            if last_ver is not None and last_ver != dna.version:
                history = self._history.setdefault(dna.user_id, [])
                # Find or build snapshot of previous version
                prev = self._find_version(dna.user_id, last_ver)
                if prev is not None and prev is not dna:
                    history.append(copy.deepcopy(prev))
                else:
                    # Same object mutated in place — store snapshot with old version
                    snap = copy.deepcopy(dna)
                    snap.version = last_ver
                    history.append(snap)
                if len(history) > self._max_snapshots:
                    self._history[dna.user_id] = history[-self._max_snapshots :]

            self._profiles[dna.user_id] = dna
            self._saved_versions[dna.user_id] = dna.version

    def get_history(self, user_id: str, limit: int = 10) -> list[UserDNA]:
        """Get version history for user."""
        with self._lock:
            history = self._history.get(user_id, [])
            return list(history[-limit:])

    def get_evolution(self, user_id: str, domain: str) -> list[dict]:
        """Track expertise evolution over time for a specific domain."""
        with self._lock:
            results: list[dict] = []
            history = self._history.get(user_id, [])

            for snap in history:
                for exp in snap.expertise:
                    if exp.domain == domain:
                        results.append(
                            {
                                "version": snap.version,
                                "level": exp.level,
                                "confidence": exp.confidence,
                                "timestamp": snap.updated_at,
                            }
                        )
                        break

            # Also include current version
            current = self._profiles.get(user_id)
            if current:
                for exp in current.expertise:
                    if exp.domain == domain:
                        results.append(
                            {
                                "version": current.version,
                                "level": exp.level,
                                "confidence": exp.confidence,
                                "timestamp": current.updated_at,
                            }
                        )
                        break

            return results

    def compare(self, user_id: str, version_a: int, version_b: int) -> dict:
        """Compare two DNA versions, showing what changed."""
        with self._lock:
            snap_a = self._find_version(user_id, version_a)
            snap_b = self._find_version(user_id, version_b)

            if snap_a is None or snap_b is None:
                return {
                    "error": "version not found",
                    "version_a": version_a,
                    "version_b": version_b,
                    "found_a": snap_a is not None,
                    "found_b": snap_b is not None,
                }

            dict_a = asdict(snap_a)
            dict_b = asdict(snap_b)

            changes: dict[str, dict] = {}
            all_keys = set(dict_a.keys()) | set(dict_b.keys())
            for key in all_keys:
                val_a = dict_a.get(key)
                val_b = dict_b.get(key)
                if val_a != val_b:
                    changes[key] = {"from": val_a, "to": val_b}

            return {
                "version_a": version_a,
                "version_b": version_b,
                "changes": changes,
            }

    def export(self, user_id: str) -> dict:
        """Export DNA as serializable dict."""
        with self._lock:
            dna = self._profiles.get(user_id)
            if dna is None:
                return {}
            return asdict(dna)

    def stats(self) -> dict:
        """Return store statistics."""
        with self._lock:
            total_users = len(self._profiles)
            total_snapshots = sum(len(h) for h in self._history.values())
            return {
                "total_users": total_users,
                "total_snapshots": total_snapshots,
                "max_snapshots_per_user": self._max_snapshots,
                "users": list(self._profiles.keys()),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_version(self, user_id: str, version: int) -> UserDNA | None:
        """Find a specific version in history or current."""
        current = self._profiles.get(user_id)
        if current is not None and current.version == version:
            return current

        for snap in self._history.get(user_id, []):
            if snap.version == version:
                return snap

        return None
