"""Federation Protocol for cross-instance memory sharing.

Enables multiple Memoria instances to selectively sync namespaces
with PKI-based trust, conflict resolution via CRDT vector clocks,
and bidirectional/push/pull sync modes.

Usage:
    from memoria import Memoria
    m = Memoria()
    m.federation_connect("https://peer.example.com/federation", shared_key="...")
    m.federation_sync(namespace="shared-knowledge")
"""

from memoria.federation.conflict import ConflictResolver, VectorClock
from memoria.federation.protocol import FederationPeer, FederationProtocol
from memoria.federation.sync import SyncEngine, SyncResult
from memoria.federation.trust import TrustEntry, TrustRegistry

__all__ = [
    "FederationProtocol",
    "FederationPeer",
    "TrustRegistry",
    "TrustEntry",
    "SyncEngine",
    "SyncResult",
    "ConflictResolver",
    "VectorClock",
]
