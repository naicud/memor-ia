"""MEMORIA sync protocol — local ↔ remote synchronisation, conflict resolution, and federation."""

from .conflicts import ConflictStrategy, SyncConflict, SyncConflictResolver, SyncResolution
from .federation import FederationManager, PeerInfo
from .protocol import SyncProtocol, SyncResult, SyncState
from .transport import FileTransport, InMemoryTransport, SyncTransport

__all__ = [
    "ConflictStrategy",
    "SyncConflict",
    "SyncConflictResolver",
    "SyncResolution",
    "FederationManager",
    "PeerInfo",
    "SyncProtocol",
    "SyncResult",
    "SyncState",
    "FileTransport",
    "InMemoryTransport",
    "SyncTransport",
]
