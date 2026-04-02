"""Tests for GDPR module: PII scanning, cascade delete, data export."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memoria.gdpr.manager import GDPRManager
from memoria.gdpr.pii import PIIScanner
from memoria.gdpr.types import (
    DeletionCertificate,
    ExportBundle,
    PIIMatch,
    PIIType,
)

# ===================================================================
# PIIType enum
# ===================================================================

class TestPIIType:
    def test_values(self):
        assert PIIType.EMAIL.value == "email"
        assert PIIType.PHONE.value == "phone"
        assert PIIType.SSN.value == "ssn"
        assert PIIType.CREDIT_CARD.value == "credit_card"
        assert PIIType.IP_ADDRESS.value == "ip_address"

    def test_all_types_count(self):
        assert len(PIIType) == 5


# ===================================================================
# PIIMatch
# ===================================================================

class TestPIIMatch:
    def test_basic_creation(self):
        m = PIIMatch(pii_type=PIIType.EMAIL, value="test@example.com", start=0, end=16)
        assert m.pii_type == PIIType.EMAIL
        assert m.value == "test@example.com"
        assert m.start == 0
        assert m.end == 16
        assert m.context == ""

    def test_redacted_short_value(self):
        m = PIIMatch(pii_type=PIIType.SSN, value="abc", start=0, end=3)
        assert m.redacted() == "****"

    def test_redacted_long_value(self):
        m = PIIMatch(pii_type=PIIType.EMAIL, value="test@example.com", start=0, end=16)
        r = m.redacted()
        assert r.startswith("te")
        assert r.endswith("om")
        assert "*" in r


# ===================================================================
# DeletionCertificate
# ===================================================================

class TestDeletionCertificate:
    def test_defaults(self):
        cert = DeletionCertificate(
            user_id="u1",
            requested_at="2024-01-01T00:00:00",
            completed_at="",
        )
        assert cert.user_id == "u1"
        assert cert.certificate_id  # auto-generated UUID
        assert cert.items_deleted == {}
        assert cert.subsystems_cleared == []
        assert cert.errors == []

    def test_total_deleted(self):
        cert = DeletionCertificate(
            user_id="u1",
            requested_at="now",
            completed_at="now",
            items_deleted={"a": 3, "b": 7},
        )
        assert cert.total_deleted == 10

    def test_success_no_errors(self):
        cert = DeletionCertificate(user_id="u1", requested_at="", completed_at="")
        assert cert.success is True

    def test_success_with_errors(self):
        cert = DeletionCertificate(
            user_id="u1", requested_at="", completed_at="",
            errors=["namespace_store: connection failed"],
        )
        assert cert.success is False

    def test_to_dict(self):
        cert = DeletionCertificate(
            user_id="u1", requested_at="t1", completed_at="t2",
            items_deleted={"x": 5},
        )
        d = cert.to_dict()
        assert d["user_id"] == "u1"
        assert d["total_deleted"] == 5
        assert d["success"] is True
        assert "certificate_id" in d


# ===================================================================
# ExportBundle
# ===================================================================

class TestExportBundle:
    def test_defaults(self):
        b = ExportBundle(user_id="u1", exported_at="now")
        assert b.data == {}
        assert b.total_items == 0

    def test_to_dict(self):
        b = ExportBundle(
            user_id="u1",
            exported_at="now",
            data={"memories": [{"id": "m1"}]},
            total_items=1,
        )
        d = b.to_dict()
        assert d["total_items"] == 1
        assert "memories" in d["data"]


# ===================================================================
# PIIScanner
# ===================================================================

class TestPIIScanner:
    def setup_method(self):
        self.scanner = PIIScanner()

    # -- email --

    def test_detect_email(self):
        matches = self.scanner.scan("Contact me at john@example.com please")
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.EMAIL
        assert matches[0].value == "john@example.com"

    def test_detect_multiple_emails(self):
        text = "alice@test.org and bob@company.co.uk"
        matches = [m for m in self.scanner.scan(text) if m.pii_type == PIIType.EMAIL]
        assert len(matches) == 2

    # -- phone --

    def test_detect_phone_us(self):
        matches = self.scanner.scan("Call +1-555-012-3456")
        phone_matches = [m for m in matches if m.pii_type == PIIType.PHONE]
        assert len(phone_matches) >= 1

    def test_detect_phone_international(self):
        matches = self.scanner.scan("Phone: +44 20 7946 0958")
        phone_matches = [m for m in matches if m.pii_type == PIIType.PHONE]
        assert len(phone_matches) >= 1

    # -- SSN --

    def test_detect_ssn(self):
        matches = self.scanner.scan("SSN is 123-45-6789")
        ssn = [m for m in matches if m.pii_type == PIIType.SSN]
        assert len(ssn) == 1
        assert ssn[0].value == "123-45-6789"

    def test_no_false_ssn(self):
        matches = self.scanner.scan("version 1.2.3")
        ssn = [m for m in matches if m.pii_type == PIIType.SSN]
        assert len(ssn) == 0

    # -- credit card --

    def test_detect_credit_card_spaces(self):
        matches = self.scanner.scan("Card: 4532 0151 2345 6789")
        cc = [m for m in matches if m.pii_type == PIIType.CREDIT_CARD]
        assert len(cc) == 1

    def test_detect_credit_card_dashes(self):
        matches = self.scanner.scan("Card: 4532-0151-2345-6789")
        cc = [m for m in matches if m.pii_type == PIIType.CREDIT_CARD]
        assert len(cc) == 1

    def test_detect_credit_card_continuous(self):
        matches = self.scanner.scan("Card: 4532015123456789")
        cc = [m for m in matches if m.pii_type == PIIType.CREDIT_CARD]
        assert len(cc) == 1

    # -- IP address --

    def test_detect_ip_address(self):
        matches = self.scanner.scan("Server at 192.168.1.100")
        ip = [m for m in matches if m.pii_type == PIIType.IP_ADDRESS]
        assert len(ip) == 1
        assert ip[0].value == "192.168.1.100"

    def test_no_false_ip(self):
        matches = self.scanner.scan("version 999.999.999.999")
        ip = [m for m in matches if m.pii_type == PIIType.IP_ADDRESS]
        assert len(ip) == 0  # > 255 in octets

    # -- no PII --

    def test_clean_text_no_pii(self):
        matches = self.scanner.scan("The quick brown fox jumps over the lazy dog")
        assert len(matches) == 0

    def test_has_pii_true(self):
        assert self.scanner.has_pii("email: test@test.com") is True

    def test_has_pii_false(self):
        assert self.scanner.has_pii("nothing here") is False

    # -- redaction --

    def test_redact_single(self):
        result = self.scanner.redact("Email me at test@example.com")
        assert "[EMAIL_REDACTED]" in result
        assert "test@example.com" not in result

    def test_redact_multiple(self):
        text = "Email test@test.com, SSN 123-45-6789"
        result = self.scanner.redact(text)
        assert "[EMAIL_REDACTED]" in result
        assert "[SSN_REDACTED]" in result
        assert "test@test.com" not in result
        assert "123-45-6789" not in result

    def test_redact_no_pii_returns_original(self):
        text = "Hello world"
        assert self.scanner.redact(text) == text

    # -- context window --

    def test_match_has_context(self):
        text = " " * 50 + "test@test.com" + " " * 50
        matches = self.scanner.scan(text)
        assert len(matches) == 1
        assert len(matches[0].context) > len(matches[0].value)

    # -- custom types filter --

    def test_filter_types(self):
        scanner = PIIScanner(types=[PIIType.EMAIL])
        text = "email: a@b.com SSN: 123-45-6789"
        matches = scanner.scan(text)
        assert all(m.pii_type == PIIType.EMAIL for m in matches)

    # -- extra patterns --

    def test_extra_pattern(self):
        scanner = PIIScanner(extra_patterns={"passport": r"[A-Z]{2}\d{7}"})
        matches = scanner.scan("Passport: AB1234567")
        assert len(matches) >= 1
        assert any("passport" in m.context.lower() or m.value == "AB1234567" for m in matches)


# ===================================================================
# GDPRManager — unit tests with mocked Memoria
# ===================================================================

class TestGDPRManagerForget:
    """Test cascade delete across subsystems using mocked Memoria."""

    def _make_mock_memoria(self, *, with_memories=True, with_vector=True):
        """Create a mocked Memoria with controllable subsystems."""
        m = MagicMock()

        # Namespace store
        ns_conn = sqlite3.connect(":memory:")
        ns_conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                namespace TEXT,
                content TEXT,
                metadata TEXT,
                user_id TEXT,
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )
        """)
        if with_memories:
            ns_conn.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, '', '')",
                ("m1", "ns1", "hello", "{}", "user-42"),
            )
            ns_conn.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, '', '')",
                ("m2", "ns1", "world", "{}", "user-42"),
            )
            ns_conn.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, '', '')",
                ("m3", "ns2", "other", "{}", "user-99"),
            )
            ns_conn.commit()
        ns_store = MagicMock()
        ns_store._conn = ns_conn
        m._get_namespace_store.return_value = ns_store

        # Vector client
        vc_conn = sqlite3.connect(":memory:")
        vc_conn.execute("""
            CREATE TABLE IF NOT EXISTS vec_metadata (
                id TEXT PRIMARY KEY,
                content TEXT,
                metadata TEXT,
                user_id TEXT,
                created_at TEXT DEFAULT ''
            )
        """)
        if with_vector:
            vc_conn.execute(
                "INSERT INTO vec_metadata VALUES (?, ?, ?, ?, '')",
                ("v1", "vec content", "{}", "user-42"),
            )
            vc_conn.commit()
        vc = MagicMock()
        vc.conn = vc_conn
        m._get_vector_client.return_value = vc

        # Memory dir (empty — no file-based memories for simplicity)
        fake_dir = MagicMock()
        fake_dir.exists.return_value = False
        m._get_memory_dir.return_value = fake_dir

        # Version history
        vh_conn = sqlite3.connect(":memory:")
        vh_conn.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY,
                memory_id TEXT,
                content TEXT,
                created_at TEXT DEFAULT ''
            )
        """)
        if with_memories:
            vh_conn.execute(
                "INSERT INTO versions VALUES (?, ?, ?, '')",
                ("vh1", "m1", "old content"),
            )
            vh_conn.commit()
        vh = MagicMock()
        vh._conn = vh_conn
        m._get_version_history.return_value = vh

        # Audit trail
        at_conn = sqlite3.connect(":memory:")
        at_conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                memory_id TEXT,
                action TEXT,
                agent_id TEXT,
                namespace TEXT,
                timestamp TEXT,
                details TEXT
            )
        """)
        if with_memories:
            at_conn.execute(
                "INSERT INTO audit_log (event_id, memory_id, action, agent_id) VALUES (?, ?, ?, ?)",
                ("e1", "m1", "create", "user-42"),
            )
            at_conn.execute(
                "INSERT INTO audit_log (event_id, memory_id, action, agent_id) VALUES (?, ?, ?, ?)",
                ("e2", "m3", "create", "user-99"),
            )
            at_conn.commit()
        audit = MagicMock()
        audit._conn = at_conn
        m._get_audit_trail.return_value = audit

        # Preference store (in-memory)
        from types import SimpleNamespace
        pref_store = MagicMock()
        pref_store._lock = threading.Lock()
        pref_item = SimpleNamespace(
            preference_id="p1", category=SimpleNamespace(value="ui"),
            key="theme", value="dark", confidence=0.9,
        )
        pref_store._preferences = {
            "user-42": {"p1": pref_item},
        }
        m._get_preference_store.return_value = pref_store

        # User DNA store (in-memory)
        dna_store = MagicMock()
        dna_store._lock = threading.Lock()
        dna_store._profiles = {"user-42": SimpleNamespace(trait="curious")}
        dna_store._history = {"user-42": ["h1", "h2"]}
        dna_store._saved_versions = {"user-42": {"v1": "data"}}
        m._get_user_dna_store.return_value = dna_store

        # Episodic (in-memory)
        episodic = MagicMock()
        episodic._lock = threading.Lock()
        event1 = SimpleNamespace(user_id="user-42")
        event2 = SimpleNamespace(user_id="user-99")
        episode = SimpleNamespace(events=[event1, event2])
        episodic._episodes = {"ep1": episode}
        m._get_episodic.return_value = episodic

        # Tiered manager + recall
        recall_conn = sqlite3.connect(":memory:")
        recall_conn.execute("""
            CREATE TABLE IF NOT EXISTS recall_items (
                id TEXT PRIMARY KEY,
                metadata TEXT
            )
        """)
        recall_conn.execute(
            "INSERT INTO recall_items VALUES (?, ?)",
            ("r1", json.dumps({"user_id": "user-42"})),
        )
        recall_conn.execute(
            "INSERT INTO recall_items VALUES (?, ?)",
            ("r2", json.dumps({"user_id": "user-99"})),
        )
        recall_conn.commit()
        recall = MagicMock()
        recall._conn = recall_conn
        tiered = MagicMock()
        tiered._recall = recall
        m._get_tiered_manager.return_value = tiered

        # Grant store
        gs_conn = sqlite3.connect(":memory:")
        gs_conn.execute("""
            CREATE TABLE IF NOT EXISTS grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                granted_by TEXT,
                permission TEXT
            )
        """)
        gs_conn.execute(
            "INSERT INTO grants (agent_id, granted_by, permission) VALUES (?, ?, ?)",
            ("user-42", "admin", "read"),
        )
        gs_conn.execute(
            "INSERT INTO grants (agent_id, granted_by, permission) VALUES (?, ?, ?)",
            ("other", "user-42", "write"),
        )
        gs_conn.commit()
        gs = MagicMock()
        gs._conn = gs_conn
        m._get_grant_store.return_value = gs

        return m

    def test_full_cascade_delete(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")

        assert cert.user_id == "user-42"
        assert cert.completed_at != ""
        assert cert.success is True
        assert cert.total_deleted > 0

        # Namespace: should have deleted 2 memories for user-42
        assert cert.items_deleted.get("namespace_memories") == 2
        # Verify user-99's memory is untouched
        ns_store = m._get_namespace_store()
        remaining = ns_store._conn.execute("SELECT id FROM memories").fetchall()
        assert len(remaining) == 1
        assert remaining[0][0] == "m3"

    def test_vector_deleted(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("vector_embeddings") == 1
        assert "vector_store" in cert.subsystems_cleared

    def test_version_history_cascade(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("version_history") == 1
        assert "version_history" in cert.subsystems_cleared

    def test_audit_trail_cascade(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("audit_trail", 0) >= 1
        assert "audit_trail" in cert.subsystems_cleared

    def test_preferences_deleted(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("preferences") == 1
        assert "preferences" in cert.subsystems_cleared
        # Verify deleted from store
        pref_store = m._get_preference_store()
        assert "user-42" not in pref_store._preferences

    def test_user_dna_deleted(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("user_dna", 0) >= 1
        assert "user_dna" in cert.subsystems_cleared
        dna = m._get_user_dna_store()
        assert "user-42" not in dna._profiles

    def test_episodic_events_filtered(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("episodic_events", 0) >= 1
        assert "episodic_memory" in cert.subsystems_cleared
        # user-99 event should remain
        ep = m._get_episodic()
        assert len(ep._episodes["ep1"].events) == 1

    def test_recall_items_deleted(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("recall_items") == 1
        assert "recall_memory" in cert.subsystems_cleared
        # user-99's recall item should remain
        recall = m._get_tiered_manager()._recall
        remaining = recall._conn.execute("SELECT id FROM recall_items").fetchall()
        assert len(remaining) == 1
        assert remaining[0][0] == "r2"

    def test_acl_grants_deleted(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        assert cert.items_deleted.get("acl_grants") == 2  # agent_id + granted_by
        assert "acl_grants" in cert.subsystems_cleared

    def test_certificate_has_uuid(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        uuid.UUID(cert.certificate_id)  # should not raise

    def test_delete_nonexistent_user(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("nonexistent-user")
        assert cert.total_deleted == 0
        assert cert.success is True

    def test_error_handling_partial_failure(self):
        m = self._make_mock_memoria()
        # Make vector client raise
        m._get_vector_client.side_effect = RuntimeError("DB locked")
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        # Should still succeed on other subsystems
        assert cert.items_deleted.get("namespace_memories") == 2
        assert len(cert.errors) >= 1
        assert "vector_store" in cert.errors[0]

    def test_subsystems_cleared_list(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")
        # Should have at least these subsystems
        expected = {"namespace_store", "vector_store", "version_history",
                    "audit_trail", "preferences", "user_dna",
                    "episodic_memory", "recall_memory", "acl_grants"}
        assert expected.issubset(set(cert.subsystems_cleared))


# ===================================================================
# GDPRManager — data export
# ===================================================================

class TestGDPRManagerExport:

    def _make_mock_memoria(self):
        m = MagicMock()

        # Namespace store
        ns_conn = sqlite3.connect(":memory:")
        ns_conn.execute("""
            CREATE TABLE memories (
                id TEXT, namespace TEXT, content TEXT,
                metadata TEXT, user_id TEXT,
                created_at TEXT DEFAULT '', updated_at TEXT DEFAULT ''
            )
        """)
        ns_conn.execute(
            "INSERT INTO memories VALUES ('m1', 'ns1', 'hello', '{}', 'user-42', '', '')"
        )
        ns_conn.commit()
        ns_store = MagicMock()
        ns_store._conn = ns_conn
        m._get_namespace_store.return_value = ns_store

        # Vector client
        vc_conn = sqlite3.connect(":memory:")
        vc_conn.execute("""
            CREATE TABLE vec_metadata (
                id TEXT, content TEXT, metadata TEXT,
                user_id TEXT, created_at TEXT DEFAULT ''
            )
        """)
        vc_conn.execute(
            "INSERT INTO vec_metadata VALUES ('v1', 'vec text', '{}', 'user-42', '')"
        )
        vc_conn.commit()
        vc = MagicMock()
        vc.conn = vc_conn
        m._get_vector_client.return_value = vc

        # Memory dir — no files
        fake_dir = MagicMock()
        fake_dir.exists.return_value = False
        m._get_memory_dir.return_value = fake_dir

        # Preference store
        from types import SimpleNamespace
        pref_store = MagicMock()
        pref_store._preferences = {
            "user-42": {
                "p1": SimpleNamespace(
                    preference_id="p1",
                    category=SimpleNamespace(value="ui"),
                    key="theme", value="dark", confidence=0.9,
                ),
            },
        }
        m._get_preference_store.return_value = pref_store

        # User DNA store
        dna_store = MagicMock()
        dna_store._profiles = {
            "user-42": SimpleNamespace(trait="curious", _internal="skip"),
        }
        m._get_user_dna_store.return_value = dna_store

        return m

    def test_export_returns_bundle(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        bundle = mgr.export_user_data("user-42")
        assert isinstance(bundle, ExportBundle)
        assert bundle.user_id == "user-42"
        assert bundle.total_items > 0

    def test_export_namespace_memories(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        bundle = mgr.export_user_data("user-42")
        assert "namespace_memories" in bundle.data
        assert len(bundle.data["namespace_memories"]) == 1
        assert bundle.data["namespace_memories"][0]["content"] == "hello"

    def test_export_vector_memories(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        bundle = mgr.export_user_data("user-42")
        assert "vector_memories" in bundle.data
        assert len(bundle.data["vector_memories"]) == 1

    def test_export_preferences(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        bundle = mgr.export_user_data("user-42")
        assert "preferences" in bundle.data
        assert bundle.data["preferences"][0]["key"] == "theme"

    def test_export_user_dna(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        bundle = mgr.export_user_data("user-42")
        assert "user_dna" in bundle.data

    def test_export_nonexistent_user_empty(self):
        m = self._make_mock_memoria()
        mgr = GDPRManager(m)
        bundle = mgr.export_user_data("nonexistent")
        assert bundle.total_items == 0
        assert bundle.data == {} or all(len(v) == 0 for v in bundle.data.values())


# ===================================================================
# GDPRManager — file-based memory delete
# ===================================================================

class TestGDPRManagerFileMemories:
    def test_file_belongs_to_user_yaml(self):
        mgr = GDPRManager(MagicMock())
        content = "---\nuser_id: user-42\ntitle: Test\n---\nBody"
        assert mgr._file_belongs_to_user(content, "user-42") is True
        assert mgr._file_belongs_to_user(content, "user-99") is False

    def test_file_belongs_to_user_json(self):
        mgr = GDPRManager(MagicMock())
        content = '---\n"user_id": "user-42"\n---\nBody'
        assert mgr._file_belongs_to_user(content, "user-42") is True

    def test_file_no_frontmatter(self):
        mgr = GDPRManager(MagicMock())
        assert mgr._file_belongs_to_user("No frontmatter here", "user-42") is False

    def test_delete_file_memories(self, tmp_path):
        """Integration test: create real files and delete user's files."""
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()

        # User-42's file
        f1 = mem_dir / "user42_mem.md"
        f1.write_text("---\nuser_id: user-42\n---\nMemory content")

        # Other user's file
        f2 = mem_dir / "other_mem.md"
        f2.write_text("---\nuser_id: user-99\n---\nOther content")

        m = MagicMock()
        m._get_memory_dir.return_value = mem_dir

        # Create minimal mocks for other subsystems to avoid errors
        m._get_namespace_store.side_effect = RuntimeError("not needed")
        m._get_vector_client.side_effect = RuntimeError("not needed")
        m._get_version_history.side_effect = RuntimeError("not needed")
        m._get_audit_trail.side_effect = RuntimeError("not needed")
        m._get_preference_store.side_effect = RuntimeError("not needed")
        m._get_user_dna_store.side_effect = RuntimeError("not needed")
        m._get_episodic.side_effect = RuntimeError("not needed")
        m._get_tiered_manager.side_effect = RuntimeError("not needed")
        m._get_grant_store.side_effect = RuntimeError("not needed")

        mgr = GDPRManager(m)
        cert = mgr.forget_user("user-42")

        assert cert.items_deleted.get("file_memories") == 1
        assert not f1.exists()
        assert f2.exists()  # other user's file untouched


# ===================================================================
# Integration via Memoria class
# ===================================================================

class TestMemoriaGDPRIntegration:
    def test_gdpr_scan_pii(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.gdpr_scan_pii("Email me at test@example.com")
        assert result["has_pii"] is True
        assert len(result["matches"]) >= 1
        assert result["matches"][0]["type"] == "email"
        assert "[EMAIL_REDACTED]" in result["redacted"]

    def test_gdpr_scan_pii_clean(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.gdpr_scan_pii("Hello world")
        assert result["has_pii"] is False
        assert result["matches"] == []

    def test_gdpr_forget_returns_certificate(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.gdpr_forget("test-user")
        assert "certificate_id" in result
        assert result["user_id"] == "test-user"
        assert isinstance(result["items_deleted"], dict)

    def test_gdpr_export_returns_bundle(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.gdpr_export("test-user")
        assert result["user_id"] == "test-user"
        assert "data" in result

    def test_gdpr_manager_lazy_init(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        mgr1 = m._get_gdpr_manager()
        mgr2 = m._get_gdpr_manager()
        assert mgr1 is mgr2  # same instance (lazy init)


# ===================================================================
# Edge cases and robustness
# ===================================================================

class TestGDPREdgeCases:
    def test_empty_text_scan(self):
        scanner = PIIScanner()
        assert scanner.scan("") == []
        assert scanner.has_pii("") is False
        assert scanner.redact("") == ""

    def test_unicode_text_scan(self):
        scanner = PIIScanner()
        # Use ASCII-compatible email in unicode context
        matches = scanner.scan("Ünïcödé text with email: test@example.com")
        emails = [m for m in matches if m.pii_type == PIIType.EMAIL]
        assert len(emails) >= 1

    def test_overlapping_pii_in_redaction(self):
        scanner = PIIScanner()
        text = "Contact: test@192.168.1.100"
        # This may match as email and/or IP — redaction should not crash
        result = scanner.redact(text)
        assert isinstance(result, str)

    def test_deletion_certificate_serializable(self):
        cert = DeletionCertificate(
            user_id="u1", requested_at="t1", completed_at="t2",
            items_deleted={"a": 1}, subsystems_cleared=["a"],
        )
        serialized = json.dumps(cert.to_dict())
        assert "u1" in serialized

    def test_export_bundle_serializable(self):
        bundle = ExportBundle(
            user_id="u1", exported_at="now",
            data={"items": [{"id": "1"}]}, total_items=1,
        )
        serialized = json.dumps(bundle.to_dict())
        assert "u1" in serialized
