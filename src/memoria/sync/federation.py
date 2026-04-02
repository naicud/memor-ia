"""Multi-instance federation for coordinating sync across peers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from memoria.namespace.store import SharedMemoryStore

from .protocol import SyncProtocol, SyncResult
from .transport import SyncTransport

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PeerInfo:
    """Metadata about a federation peer."""

    peer_id: str
    name: str
    endpoint: str
    transport: SyncTransport
    last_seen: str  # ISO-8601
    status: str  # "active" | "inactive" | "error"


# ---------------------------------------------------------------------------
# FederationManager
# ---------------------------------------------------------------------------


class FederationManager:
    """Coordinates sync across multiple MEMORIA instances (peers)."""

    def __init__(
        self,
        instance_id: str | None = None,
        local_store: SharedMemoryStore | None = None,
    ) -> None:
        self._instance_id = instance_id or str(uuid.uuid4())
        self._store = local_store or SharedMemoryStore()
        self._peers: dict[str, PeerInfo] = {}

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- peer management ---------------------------------------------------

    def register_peer(
        self,
        name: str,
        transport: SyncTransport,
        endpoint: str = "",
    ) -> str:
        """Register a new peer and return its peer_id."""
        peer_id = str(uuid.uuid4())
        self._peers[peer_id] = PeerInfo(
            peer_id=peer_id,
            name=name,
            endpoint=endpoint,
            transport=transport,
            last_seen=self._now_iso(),
            status="active",
        )
        return peer_id

    def remove_peer(self, peer_id: str) -> bool:
        """Remove a peer. Returns ``True`` if it existed."""
        return self._peers.pop(peer_id, None) is not None

    def list_peers(self) -> list[PeerInfo]:
        """Return all registered peers."""
        return list(self._peers.values())

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Return a single peer, or ``None``."""
        return self._peers.get(peer_id)

    def peer_count(self) -> int:
        """Number of registered peers."""
        return len(self._peers)

    # -- sync operations ---------------------------------------------------

    def sync_with_peer(
        self,
        peer_id: str,
        namespace: str | None = None,
    ) -> SyncResult:
        """Sync with a specific peer using its transport."""
        peer = self._peers.get(peer_id)
        if peer is None:
            return SyncResult(pushed=0, pulled=0, conflicts=0, resolved=0,
                              errors=[f"unknown peer: {peer_id}"])

        proto = SyncProtocol(self._store, peer.transport)
        result = proto.sync(namespace)

        peer.last_seen = self._now_iso()
        if result.errors:
            peer.status = "error"
        else:
            peer.status = "active"

        return result

    def sync_all(self, namespace: str | None = None) -> dict[str, SyncResult]:
        """Sync with every active peer. Returns ``{peer_id: SyncResult}``."""
        results: dict[str, SyncResult] = {}
        for peer_id, peer in self._peers.items():
            if peer.status == "inactive":
                continue
            results[peer_id] = self.sync_with_peer(peer_id, namespace)
        return results

    # -- health ------------------------------------------------------------

    def health_check(self) -> dict[str, bool]:
        """Ping all peers, update their status, and return reachability map."""
        status: dict[str, bool] = {}
        for peer_id, peer in self._peers.items():
            try:
                reachable = peer.transport.ping()
            except Exception:  # noqa: BLE001
                reachable = False

            status[peer_id] = reachable
            peer.last_seen = self._now_iso()
            peer.status = "active" if reachable else "error"
        return status
