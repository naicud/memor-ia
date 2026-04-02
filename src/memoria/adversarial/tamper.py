"""TamperProof — integrity hashing and audit trail."""

import dataclasses
import hashlib
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from .types import AnomalyReport, IntegrityRecord, IntegrityStatus

_MAX_RECORDS = 10000
_MAX_AUDIT = 50000


class TamperProof:
    """Integrity hashing, tamper detection, and anomaly analysis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, IntegrityRecord] = {}
        self._record_order: deque = deque(maxlen=_MAX_RECORDS)
        self._audit_trail: deque = deque(maxlen=_MAX_AUDIT)
        self._stats: Dict[str, int] = {
            "total_hashes": 0,
            "total_verifications": 0,
            "intact": 0,
            "tampered": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def hash_content(self, content: str, content_id: str) -> IntegrityRecord:
        """Create an integrity hash for *content* and store it under *content_id*."""
        content_hash = self._compute_hash(content)
        now = time.time()

        record = IntegrityRecord(
            content_hash=content_hash,
            content_id=content_id,
            status=IntegrityStatus.INTACT,
            created_at=now,
            last_verified=now,
            verification_count=0,
            metadata={"content_length": len(content)},
        )

        with self._lock:
            # FIFO rotation for records
            if content_id not in self._records and len(self._records) >= _MAX_RECORDS:
                oldest_id = self._record_order.popleft()
                self._records.pop(oldest_id, None)

            self._records[content_id] = record
            if content_id not in self._record_order:
                self._record_order.append(content_id)

            self._stats["total_hashes"] += 1

            self._audit_trail.append({
                "action": "hash",
                "content_id": content_id,
                "content_hash": content_hash,
                "timestamp": now,
            })

        return dataclasses.replace(record, metadata=dict(record.metadata))

    def verify_integrity(self, content: str, content_id: str) -> IntegrityStatus:
        """Verify that *content* matches the stored hash for *content_id*."""
        current_hash = self._compute_hash(content)

        with self._lock:
            self._stats["total_verifications"] += 1

            record = self._records.get(content_id)
            if record is None:
                self._audit_trail.append({
                    "action": "verify",
                    "content_id": content_id,
                    "result": IntegrityStatus.UNKNOWN.value,
                    "timestamp": time.time(),
                })
                return IntegrityStatus.UNKNOWN

            record.verification_count += 1
            record.last_verified = time.time()

            if current_hash == record.content_hash:
                record.status = IntegrityStatus.INTACT
                self._stats["intact"] += 1
                result = IntegrityStatus.INTACT
            else:
                record.status = IntegrityStatus.TAMPERED
                self._stats["tampered"] += 1
                result = IntegrityStatus.TAMPERED

            self._audit_trail.append({
                "action": "verify",
                "content_id": content_id,
                "result": result.value,
                "expected_hash": record.content_hash,
                "actual_hash": current_hash,
                "timestamp": time.time(),
            })

        return result

    def get_audit_trail(self, content_id: Optional[str] = None) -> List[Dict]:
        """Return the audit trail, optionally filtered by *content_id*."""
        with self._lock:
            if content_id is None:
                return [dict(e) for e in self._audit_trail]
            return [dict(e) for e in self._audit_trail if e.get("content_id") == content_id]

    def detect_anomalies(self, recent_operations: List[Dict]) -> AnomalyReport:
        """Detect anomalous patterns in *recent_operations*."""
        recent_operations = list(recent_operations)
        anomalies: List[Dict[str, Any]] = []
        anomaly_score = 0.0

        if not recent_operations:
            return AnomalyReport(
                is_anomalous=False,
                anomaly_score=0.0,
                anomalies=[],
                baseline_stats={},
            )

        timestamps = [
            op.get("timestamp", 0.0)
            for op in recent_operations
            if isinstance(op.get("timestamp"), (int, float))
        ]

        # --- rate anomaly: >3x average frequency ---
        if len(timestamps) >= 2:
            timestamps_sorted = sorted(timestamps)
            total_span = timestamps_sorted[-1] - timestamps_sorted[0]
            if total_span > 0:
                avg_interval = total_span / (len(timestamps_sorted) - 1)
                # Check for bursts: any window where ops come >3x the average rate
                for i in range(len(timestamps_sorted) - 1):
                    gap = timestamps_sorted[i + 1] - timestamps_sorted[i]
                    if gap > 0 and avg_interval / gap > 3.0:
                        anomalies.append({
                            "type": "rate",
                            "description": "Operation frequency spike detected",
                            "severity": "medium",
                        })
                        anomaly_score += 0.3
                        break

        # --- bulk anomaly: >50 modifications in 60 seconds ---
        if timestamps:
            ts_sorted = sorted(timestamps)
            window = 60.0
            for i in range(len(ts_sorted)):
                j = i
                while j < len(ts_sorted) and ts_sorted[j] - ts_sorted[i] <= window:
                    j += 1
                count_in_window = j - i
                if count_in_window > 50:
                    anomalies.append({
                        "type": "bulk",
                        "description": f"{count_in_window} operations in 60-second window",
                        "severity": "high",
                    })
                    anomaly_score += 0.4
                    break

        # --- pattern anomaly: all modifications target same content_id ---
        content_ids = [
            op.get("content_id")
            for op in recent_operations
            if op.get("content_id") is not None
        ]
        if len(content_ids) > 5:
            unique_ids = set(content_ids)
            if len(unique_ids) == 1:
                anomalies.append({
                    "type": "pattern",
                    "description": f"All operations target same content_id: {unique_ids.pop()}",
                    "severity": "medium",
                })
                anomaly_score += 0.3

        # --- size anomaly: content size changes >5x from baseline ---
        sizes = [
            op.get("content_length", op.get("size", 0))
            for op in recent_operations
            if isinstance(op.get("content_length", op.get("size")), (int, float))
        ]
        if len(sizes) >= 2:
            baseline = sum(sizes) / len(sizes)
            if baseline > 0:
                for s in sizes:
                    ratio = s / baseline if baseline > 0 else 0
                    if ratio > 5.0 or (ratio > 0 and ratio < 0.2):
                        anomalies.append({
                            "type": "size",
                            "description": f"Content size anomaly: {s} vs baseline {baseline:.1f}",
                            "severity": "medium",
                        })
                        anomaly_score += 0.3
                        break

        anomaly_score = min(1.0, anomaly_score)
        baseline_stats: Dict[str, float] = {
            "operation_count": float(len(recent_operations)),
            "unique_content_ids": float(len(set(content_ids))) if content_ids else 0.0,
        }

        return AnomalyReport(
            is_anomalous=len(anomalies) > 0,
            anomaly_score=anomaly_score,
            anomalies=anomalies,
            baseline_stats=baseline_stats,
        )

    def get_integrity_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_hashes": self._stats["total_hashes"],
                "total_verifications": self._stats["total_verifications"],
                "intact": self._stats["intact"],
                "tampered": self._stats["tampered"],
                "tracked_records": len(self._records),
                "audit_trail_size": len(self._audit_trail),
            }

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            records = {}
            for cid, rec in self._records.items():
                records[cid] = {
                    "content_hash": rec.content_hash,
                    "content_id": rec.content_id,
                    "status": rec.status.value,
                    "created_at": rec.created_at,
                    "last_verified": rec.last_verified,
                    "verification_count": rec.verification_count,
                    "metadata": dict(rec.metadata),
                }
            return {
                "records": records,
                "record_order": list(self._record_order),
                "audit_trail": [dict(e) for e in self._audit_trail],
                "stats": dict(self._stats),
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TamperProof":
        obj = cls()
        for cid, rdata in data.get("records", {}).items():
            rec = IntegrityRecord(
                content_hash=rdata["content_hash"],
                content_id=rdata["content_id"],
                status=IntegrityStatus(rdata.get("status", "intact")),
                created_at=rdata.get("created_at", 0.0),
                last_verified=rdata.get("last_verified", 0.0),
                verification_count=rdata.get("verification_count", 0),
                metadata=dict(rdata.get("metadata", {})),
            )
            obj._records[cid] = rec
        record_order = data.get("record_order", [])
        if record_order:
            for cid in record_order:
                obj._record_order.append(cid)
        else:
            for cid in obj._records:
                obj._record_order.append(cid)
        for entry in data.get("audit_trail", []):
            obj._audit_trail.append(dict(entry))
        s = data.get("stats", {})
        for k in obj._stats:
            if k in s:
                obj._stats[k] = s[k]
        return obj

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8", errors="surrogatepass")).hexdigest()
