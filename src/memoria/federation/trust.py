"""PKI-based trust registry for federation peers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TrustEntry:
    """A trust record for a federation peer."""
    instance_id: str
    public_key: str
    trust_level: str = "standard"  # untrusted | standard | elevated | full
    allowed_namespaces: list[str] = field(default_factory=list)
    granted_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    revoked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_valid(self) -> bool:
        if self.revoked:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True


TRUST_LEVELS = ["untrusted", "standard", "elevated", "full"]

TRUST_PERMISSIONS = {
    "untrusted": {"can_read": False, "can_write": False, "can_sync": False},
    "standard": {"can_read": True, "can_write": False, "can_sync": True},
    "elevated": {"can_read": True, "can_write": True, "can_sync": True},
    "full": {"can_read": True, "can_write": True, "can_sync": True},
}


class TrustRegistry:
    """Manages trust relationships between federation peers."""

    def __init__(self) -> None:
        self._entries: dict[str, TrustEntry] = {}
        self._shared_secrets: dict[str, str] = {}

    def add_trust(self, instance_id: str, public_key: str,
                  trust_level: str = "standard",
                  allowed_namespaces: list[str] | None = None,
                  expires_at: float | None = None,
                  metadata: dict[str, Any] | None = None) -> TrustEntry:
        """Add or update a trust entry for a peer."""
        if trust_level not in TRUST_LEVELS:
            raise ValueError(f"Invalid trust level: {trust_level}. Must be one of {TRUST_LEVELS}")

        entry = TrustEntry(
            instance_id=instance_id,
            public_key=public_key,
            trust_level=trust_level,
            allowed_namespaces=allowed_namespaces or [],
            expires_at=expires_at,
            metadata=metadata or {},
        )
        self._entries[instance_id] = entry
        return entry

    def revoke_trust(self, instance_id: str) -> bool:
        """Revoke trust for a peer."""
        entry = self._entries.get(instance_id)
        if not entry:
            return False
        entry.revoked = True
        return True

    def get_trust(self, instance_id: str) -> TrustEntry | None:
        return self._entries.get(instance_id)

    def is_trusted(self, instance_id: str) -> bool:
        entry = self._entries.get(instance_id)
        return entry is not None and entry.is_valid

    def get_permissions(self, instance_id: str) -> dict[str, bool]:
        """Get permissions for a peer based on trust level."""
        entry = self._entries.get(instance_id)
        if not entry or not entry.is_valid:
            return TRUST_PERMISSIONS["untrusted"]
        return TRUST_PERMISSIONS.get(entry.trust_level, TRUST_PERMISSIONS["untrusted"])

    def can_access_namespace(self, instance_id: str, namespace: str) -> bool:
        """Check if a peer can access a specific namespace."""
        entry = self._entries.get(instance_id)
        if not entry or not entry.is_valid:
            return False
        if not entry.allowed_namespaces:
            return True  # empty = all namespaces allowed
        return namespace in entry.allowed_namespaces

    def list_trusted(self) -> list[dict]:
        return [e.to_dict() for e in self._entries.values() if e.is_valid]

    def list_all(self) -> list[dict]:
        return [e.to_dict() for e in self._entries.values()]

    def set_shared_secret(self, instance_id: str, secret: str) -> None:
        """Set a shared secret for HMAC message signing with a peer."""
        self._shared_secrets[instance_id] = secret

    def get_shared_secret(self, instance_id: str) -> str | None:
        return self._shared_secrets.get(instance_id)

    def sign_payload(self, instance_id: str, payload: dict) -> str:
        """Sign a payload using the shared secret for a peer."""
        secret = self._shared_secrets.get(instance_id)
        if not secret:
            raise ValueError(f"No shared secret for peer: {instance_id}")
        canonical = json.dumps(payload, sort_keys=True).encode()
        return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()

    def verify_payload(self, instance_id: str, payload: dict, signature: str) -> bool:
        """Verify a payload signature from a peer."""
        try:
            expected = self.sign_payload(instance_id, payload)
            return hmac.compare_digest(expected, signature)
        except ValueError:
            return False

    def cleanup_expired(self) -> int:
        """Remove expired trust entries. Returns count removed."""
        expired = [k for k, v in self._entries.items()
                   if v.expires_at and time.time() > v.expires_at]
        for k in expired:
            del self._entries[k]
        return len(expired)

    def status(self) -> dict:
        total = len(self._entries)
        valid = sum(1 for e in self._entries.values() if e.is_valid)
        revoked = sum(1 for e in self._entries.values() if e.revoked)
        return {
            "total_entries": total,
            "valid": valid,
            "revoked": revoked,
            "expired": total - valid - revoked,
        }
