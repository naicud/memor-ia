"""Federation protocol — peer discovery, connection, and message exchange."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FederationPeer:
    """Represents a connected federation peer."""
    instance_id: str
    endpoint: str
    public_key: str = ""
    shared_namespaces: list[str] = field(default_factory=list)
    direction: str = "bidirectional"  # bidirectional | push | pull
    connected_at: float = field(default_factory=time.time)
    last_sync: float | None = None
    status: str = "connected"  # connected | disconnected | error
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FederationMessage:
    """A message exchanged between federated instances."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_instance: str = ""
    target_instance: str = ""
    message_type: str = ""  # sync_request | sync_response | heartbeat | trust_verify
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    signature: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def compute_signature(self, secret: str) -> str:
        """Compute HMAC-like signature for message integrity."""
        content = json.dumps(
            {"source": self.source_instance, "target": self.target_instance,
             "type": self.message_type, "payload": self.payload,
             "timestamp": self.timestamp},
            sort_keys=True,
        )
        self.signature = hashlib.sha256(f"{content}{secret}".encode()).hexdigest()
        return self.signature

    def verify_signature(self, secret: str) -> bool:
        """Verify message signature."""
        expected = hashlib.sha256(
            f'{json.dumps({"source": self.source_instance, "target": self.target_instance, "type": self.message_type, "payload": self.payload, "timestamp": self.timestamp}, sort_keys=True)}{secret}'.encode()
        ).hexdigest()
        return self.signature == expected


class FederationProtocol:
    """Manages federation peer connections and message exchange."""

    def __init__(self, instance_id: str | None = None) -> None:
        self._instance_id = instance_id or f"memoria-{uuid.uuid4().hex[:8]}"
        self._peers: dict[str, FederationPeer] = {}
        self._message_log: list[FederationMessage] = []
        self._message_handlers: dict[str, list] = {}

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def peers(self) -> dict[str, FederationPeer]:
        return dict(self._peers)

    def connect(self, endpoint: str, instance_id: str | None = None,
                public_key: str = "", shared_namespaces: list[str] | None = None,
                direction: str = "bidirectional",
                metadata: dict[str, Any] | None = None) -> FederationPeer:
        """Register a federation peer."""
        peer_id = instance_id or hashlib.sha256(endpoint.encode()).hexdigest()[:16]

        if peer_id in self._peers:
            existing = self._peers[peer_id]
            existing.status = "connected"
            existing.shared_namespaces = shared_namespaces or existing.shared_namespaces
            return existing

        peer = FederationPeer(
            instance_id=peer_id,
            endpoint=endpoint,
            public_key=public_key,
            shared_namespaces=shared_namespaces or [],
            direction=direction,
            metadata=metadata or {},
        )
        self._peers[peer_id] = peer

        self._log_message(FederationMessage(
            source_instance=self._instance_id,
            target_instance=peer_id,
            message_type="connect",
            payload={"endpoint": endpoint},
        ))

        return peer

    def disconnect(self, peer_id: str) -> bool:
        """Disconnect from a federation peer."""
        if peer_id not in self._peers:
            return False

        self._peers[peer_id].status = "disconnected"
        self._log_message(FederationMessage(
            source_instance=self._instance_id,
            target_instance=peer_id,
            message_type="disconnect",
        ))
        return True

    def remove_peer(self, peer_id: str) -> bool:
        """Remove a peer entirely."""
        if peer_id not in self._peers:
            return False
        del self._peers[peer_id]
        return True

    def get_peer(self, peer_id: str) -> FederationPeer | None:
        return self._peers.get(peer_id)

    def list_peers(self) -> list[dict]:
        return [p.to_dict() for p in self._peers.values()]

    def send_message(self, peer_id: str, message_type: str,
                     payload: dict[str, Any], secret: str = "") -> FederationMessage:
        """Create and record a federation message."""
        peer = self._peers.get(peer_id)
        if not peer:
            raise ValueError(f"Unknown peer: {peer_id}")

        msg = FederationMessage(
            source_instance=self._instance_id,
            target_instance=peer_id,
            message_type=message_type,
            payload=payload,
        )
        if secret:
            msg.compute_signature(secret)

        self._log_message(msg)
        self._dispatch(message_type, msg)
        return msg

    def receive_message(self, message_data: dict, secret: str = "") -> FederationMessage:
        """Process an incoming federation message."""
        msg = FederationMessage(**{k: v for k, v in message_data.items()
                                   if k in FederationMessage.__dataclass_fields__})

        if secret and msg.signature:
            if not msg.verify_signature(secret):
                raise ValueError("Invalid message signature")

        self._log_message(msg)
        self._dispatch(msg.message_type, msg)
        return msg

    def on_message(self, message_type: str, handler: Any) -> None:
        """Register a handler for a message type."""
        self._message_handlers.setdefault(message_type, []).append(handler)

    def get_message_log(self, limit: int = 50) -> list[dict]:
        return [m.to_dict() for m in self._message_log[-limit:]]

    def status(self) -> dict:
        connected = sum(1 for p in self._peers.values() if p.status == "connected")
        return {
            "instance_id": self._instance_id,
            "total_peers": len(self._peers),
            "connected_peers": connected,
            "total_messages": len(self._message_log),
        }

    def _log_message(self, msg: FederationMessage) -> None:
        self._message_log.append(msg)

    def _dispatch(self, message_type: str, msg: FederationMessage) -> None:
        for handler in self._message_handlers.get(message_type, []):
            try:
                handler(msg)
            except Exception:
                pass
