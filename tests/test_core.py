"""Comprehensive tests for the memdir memory layer."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest import mock

import pytest

from memoria.core.paths import (
    AUTO_MEM_DIRNAME,
    AUTO_MEM_ENTRYPOINT_NAME,
    _sanitize_path,
    ensure_memory_dir_exists,
    get_auto_mem_entrypoint,
    get_auto_mem_path,
    get_claude_config_home,
    get_daily_log_path,
    get_project_dir,
    get_session_dir,
    get_session_memory_path,
    get_transcript_path,
    is_auto_mem_path,
    is_auto_memory_enabled,
)
from memoria.core.types import (
    MEMORY_TYPE_DESCRIPTIONS,
    MemoryFrontmatter,
    MemoryType,
    format_frontmatter,
    parse_frontmatter,
    parse_memory_type,
)
from memoria.core.store import (
    EntrypointTruncation,
    create_memory_file,
    delete_memory_file,
    list_memory_files,
    read_entrypoint,
    read_memory_file,
    truncate_entrypoint,
    update_entrypoint,
    write_memory_file,
)
from memoria.core.scanner import (
    MAX_MEMORY_FILES,
    MemoryHeader,
    format_memory_manifest,
    scan_memory_files,
)
from memoria.core.recall import (
    RelevantMemory,
    find_relevant_memories,
)
from memoria.core.transcript import (
    SessionInfo,
    SessionTranscript,
    append_message,
    create_session,
    list_sessions,
    list_sessions_touched_since,
    read_head_and_tail,
    read_transcript,
)


# =========================================================================
# Path resolution tests
# =========================================================================


class TestGetClaudeConfigHome:
    def test_default_is_home_dot_claude(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLAUDE_CODE_CONFIG_DIR", None)
            result = get_claude_config_home()
            assert result == Path.home() / ".claude"

    def test_override_via_env(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            assert get_claude_config_home() == tmp_path


class TestGetProjectDir:
    def test_returns_projects_subdir(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_project_dir("/some/project")
            assert str(result).startswith(str(tmp_path / "projects"))

    def test_sanitized_name_is_deterministic(self):
        a = _sanitize_path("/my/project")
        b = _sanitize_path("/my/project")
        assert a == b

    def test_different_paths_produce_different_names(self):
        a = _sanitize_path("/my/project-a")
        b = _sanitize_path("/my/project-b")
        assert a != b


class TestAutoMemPaths:
    def test_get_auto_mem_path(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_auto_mem_path("/proj")
            assert result.name == AUTO_MEM_DIRNAME

    def test_get_auto_mem_entrypoint(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_auto_mem_entrypoint("/proj")
            assert result.name == AUTO_MEM_ENTRYPOINT_NAME

    def test_get_session_dir(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_session_dir("/proj")
            assert "projects" in str(result)

    def test_get_transcript_path(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_transcript_path("/proj", "sess-123")
            assert result.name == "sess-123.jsonl"

    def test_get_session_memory_path(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_session_memory_path("sess-456")
            assert result.name == "sess-456.md"
            assert ".session_memory" in str(result)

    def test_get_daily_log_path(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = get_daily_log_path("/proj")
            assert result.suffix == ".md"
            assert "logs" in str(result)


class TestIsAutoMemPath:
    def test_valid_subpath(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            cwd = "/proj"
            mem_dir = ensure_memory_dir_exists(cwd)
            test_file = mem_dir / "test.md"
            test_file.touch()
            assert is_auto_mem_path(str(test_file), cwd) is True

    def test_outside_path(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            assert is_auto_mem_path("/etc/passwd", "/proj") is False

    def test_traversal_attempt(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            cwd = "/proj"
            mem_dir = ensure_memory_dir_exists(cwd)
            bad_path = str(mem_dir / ".." / ".." / "etc" / "passwd")
            assert is_auto_mem_path(bad_path, cwd) is False


class TestIsAutoMemoryEnabled:
    def test_default_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLAUDE_CODE_DISABLE_AUTO_MEMORY", None)
            os.environ.pop("CLAUDE_CODE_SIMPLE", None)
            assert is_auto_memory_enabled() is True

    def test_disabled_with_env_true(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "true"}):
            assert is_auto_memory_enabled() is False

    def test_disabled_with_env_1(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}):
            assert is_auto_memory_enabled() is False

    def test_explicitly_enabled(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "false"}):
            assert is_auto_memory_enabled() is True

    def test_disabled_in_simple_mode(self):
        env = {"CLAUDE_CODE_SIMPLE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            os.environ.pop("CLAUDE_CODE_DISABLE_AUTO_MEMORY", None)
            assert is_auto_memory_enabled() is False


class TestEnsureMemoryDirExists:
    def test_creates_directory(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            result = ensure_memory_dir_exists("/proj")
            assert result.is_dir()

    def test_idempotent(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            a = ensure_memory_dir_exists("/proj")
            b = ensure_memory_dir_exists("/proj")
            assert a == b


# =========================================================================
# Memory types tests
# =========================================================================


class TestMemoryType:
    def test_enum_values(self):
        assert MemoryType.USER == "user"
        assert MemoryType.FEEDBACK == "feedback"
        assert MemoryType.PROJECT == "project"
        assert MemoryType.REFERENCE == "reference"

    def test_all_types_have_descriptions(self):
        for mt in MemoryType:
            assert mt in MEMORY_TYPE_DESCRIPTIONS


class TestParseMemoryType:
    def test_valid_types(self):
        assert parse_memory_type("user") == MemoryType.USER
        assert parse_memory_type("FEEDBACK") == MemoryType.FEEDBACK
        assert parse_memory_type("Project") == MemoryType.PROJECT

    def test_invalid_returns_none(self):
        assert parse_memory_type("invalid") is None
        assert parse_memory_type("") is None


class TestParseFrontmatter:
    def test_with_valid_frontmatter(self):
        content = '---\nname: "test"\ndescription: "A test memory"\ntype: "user"\n---\n\nBody text here.'
        fm, body = parse_frontmatter(content)
        assert fm.name == "test"
        assert fm.description == "A test memory"
        assert fm.type == MemoryType.USER
        assert "Body text here." in body

    def test_without_frontmatter(self):
        content = "Just plain text, no frontmatter."
        fm, body = parse_frontmatter(content)
        assert fm.name == ""
        assert fm.type is None
        assert body == content

    def test_partial_frontmatter(self):
        content = '---\nname: "partial"\n---\nSome body.'
        fm, body = parse_frontmatter(content)
        assert fm.name == "partial"
        assert fm.type is None
        assert "Some body." in body

    def test_unknown_type_ignored(self):
        content = '---\ntype: "bogus"\n---\nText.'
        fm, body = parse_frontmatter(content)
        assert fm.type is None


class TestFormatFrontmatter:
    def test_full_frontmatter(self):
        fm = MemoryFrontmatter(name="test", description="desc", type=MemoryType.USER)
        result = format_frontmatter(fm)
        assert '---' in result
        assert 'name: "test"' in result
        assert 'type: "user"' in result

    def test_empty_frontmatter(self):
        fm = MemoryFrontmatter()
        result = format_frontmatter(fm)
        assert result == "---\n---"

    def test_roundtrip(self):
        fm = MemoryFrontmatter(name="rt", description="roundtrip", type=MemoryType.FEEDBACK)
        text = format_frontmatter(fm) + "\n\nBody."
        fm2, body = parse_frontmatter(text)
        assert fm2.name == fm.name
        assert fm2.type == fm.type
        assert "Body." in body


# =========================================================================
# Memory store tests
# =========================================================================


class TestReadWriteMemoryFile:
    def test_write_and_read(self, tmp_path):
        path = tmp_path / "test.md"
        fm = MemoryFrontmatter(name="hello", type=MemoryType.PROJECT)
        write_memory_file(path, fm, "Some content.")
        fm2, body = read_memory_file(path)
        assert fm2.name == "hello"
        assert fm2.type == MemoryType.PROJECT
        assert "Some content." in body

    def test_write_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "test.md"
        fm = MemoryFrontmatter(name="nested")
        write_memory_file(path, fm, "body")
        assert path.exists()


class TestEntrypoint:
    def test_read_nonexistent(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            raw, trunc = read_entrypoint("/proj")
            assert raw == ""
            assert trunc.line_count == 0
            assert not trunc.was_line_truncated

    def test_write_and_read(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            update_entrypoint("/proj", "# Memory Index\n\n- item 1\n")
            raw, trunc = read_entrypoint("/proj")
            assert "Memory Index" in raw
            assert trunc.line_count == 3


class TestTruncateEntrypoint:
    def test_no_truncation(self):
        content = "line\n" * 10
        trunc = truncate_entrypoint(content)
        assert not trunc.was_line_truncated
        assert not trunc.was_byte_truncated

    def test_line_truncation(self):
        content = "line\n" * 300
        trunc = truncate_entrypoint(content, max_lines=200)
        assert trunc.was_line_truncated
        assert trunc.line_count == 200

    def test_byte_truncation(self):
        content = "x" * 30_000
        trunc = truncate_entrypoint(content, max_bytes=25_000)
        assert trunc.was_byte_truncated
        assert trunc.byte_count <= 25_000


class TestCreateDeleteMemoryFile:
    def test_create_and_delete(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            path = create_memory_file("/proj", "Test Note", MemoryType.USER, "A user note", "content")
            assert path.exists()
            assert path.suffix == ".md"

            fm, body = read_memory_file(path)
            assert fm.name == "Test Note"
            assert fm.type == MemoryType.USER

            assert delete_memory_file(path) is True
            assert not path.exists()
            assert delete_memory_file(path) is False

    def test_list_memory_files(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            create_memory_file("/proj", "one", MemoryType.USER)
            create_memory_file("/proj", "two", MemoryType.FEEDBACK)
            files = list_memory_files("/proj")
            assert len(files) == 2


# =========================================================================
# Scanner tests
# =========================================================================


class TestScanMemoryFiles:
    def test_scan_empty_dir(self, tmp_path):
        assert scan_memory_files(tmp_path) == []

    def test_scan_nonexistent_dir(self):
        assert scan_memory_files("/nonexistent/path") == []

    def test_scan_finds_md_files(self, tmp_path):
        # Create a memory file with frontmatter
        f1 = tmp_path / "note1.md"
        f1.write_text('---\nname: "note1"\ntype: "user"\ndescription: "first"\n---\nBody.', encoding="utf-8")
        f2 = tmp_path / "note2.md"
        f2.write_text('---\nname: "note2"\ntype: "feedback"\ndescription: "second"\n---\n', encoding="utf-8")
        # Non-md file should be ignored
        (tmp_path / "ignored.txt").write_text("nope")

        headers = scan_memory_files(tmp_path)
        assert len(headers) == 2
        names = {h.filename for h in headers}
        assert "note1.md" in names
        assert "note2.md" in names

    def test_excludes_entrypoint(self, tmp_path):
        (tmp_path / AUTO_MEM_ENTRYPOINT_NAME).write_text("# Index")
        (tmp_path / "keep.md").write_text("---\nname: \"keep\"\n---\n")
        headers = scan_memory_files(tmp_path)
        assert len(headers) == 1
        assert headers[0].filename == "keep.md"

    def test_sorted_newest_first(self, tmp_path):
        f1 = tmp_path / "old.md"
        f1.write_text("---\nname: \"old\"\n---\n")
        time.sleep(0.05)
        f2 = tmp_path / "new.md"
        f2.write_text("---\nname: \"new\"\n---\n")
        headers = scan_memory_files(tmp_path)
        assert headers[0].filename == "new.md"

    def test_max_files_cap(self, tmp_path):
        for i in range(MAX_MEMORY_FILES + 10):
            (tmp_path / f"file_{i:04d}.md").write_text(f'---\nname: "f{i}"\n---\n')
        headers = scan_memory_files(tmp_path)
        assert len(headers) == MAX_MEMORY_FILES


class TestFormatMemoryManifest:
    def test_empty_list(self):
        assert format_memory_manifest([]) == "(no memory files)"

    def test_format_output(self):
        headers = [
            MemoryHeader("a.md", "/path/a.md", 1000.0, "desc A", MemoryType.USER),
            MemoryHeader("b.md", "/path/b.md", 2000.0, None, None),
        ]
        result = format_memory_manifest(headers)
        assert "[user] a.md" in result
        assert "[unknown] b.md" in result
        assert "no description" in result


# =========================================================================
# Recall tests
# =========================================================================


class TestFindRelevantMemories:
    def test_empty_query(self, tmp_path):
        assert find_relevant_memories("", tmp_path) == []

    def test_no_match(self, tmp_path):
        (tmp_path / "note.md").write_text('---\ndescription: "cooking recipes"\n---\n')
        result = find_relevant_memories("quantum physics", tmp_path)
        assert len(result) == 0

    def test_keyword_match(self, tmp_path):
        (tmp_path / "auth.md").write_text('---\ndescription: "authentication setup"\n---\n')
        (tmp_path / "deploy.md").write_text('---\ndescription: "deployment pipeline"\n---\n')
        result = find_relevant_memories("authentication login", tmp_path)
        assert len(result) >= 1
        assert any("auth.md" in r.path for r in result)

    def test_excludes_entrypoint(self, tmp_path):
        (tmp_path / AUTO_MEM_ENTRYPOINT_NAME).write_text("---\ndescription: \"auth stuff\"\n---\n")
        (tmp_path / "auth.md").write_text('---\ndescription: "authentication"\n---\n')
        result = find_relevant_memories("authentication", tmp_path)
        assert all(AUTO_MEM_ENTRYPOINT_NAME not in r.path for r in result)

    def test_excludes_already_surfaced(self, tmp_path):
        f = tmp_path / "auth.md"
        f.write_text('---\ndescription: "authentication"\n---\n')
        surfaced = {str(f.resolve())}
        result = find_relevant_memories("authentication", tmp_path, already_surfaced=surfaced)
        assert len(result) == 0

    def test_score_ordering(self, tmp_path):
        (tmp_path / "auth_login.md").write_text('---\ndescription: "authentication login flow"\n---\n')
        (tmp_path / "deploy_auth.md").write_text('---\ndescription: "deployment authentication"\n---\n')
        result = find_relevant_memories("authentication login", tmp_path)
        if len(result) >= 2:
            assert result[0].score >= result[1].score


# =========================================================================
# Session transcript tests
# =========================================================================


class TestSessionTranscript:
    def test_create_session(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            session = create_session("/proj", "test-session")
            try:
                assert session.session_id == "test-session"
                assert session.path.exists()
            finally:
                session.close()

    def test_append_and_read(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            session = create_session("/proj", "test-rw")
            try:
                append_message(session, {"role": "user", "content": "hello"})
                append_message(session, {"role": "assistant", "content": "hi"})
            finally:
                session.close()

            msgs = read_transcript(session.path)
            assert len(msgs) == 2
            assert msgs[0]["role"] == "user"
            assert msgs[1]["content"] == "hi"

    def test_context_manager(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            with create_session("/proj", "ctx") as session:
                append_message(session, {"role": "user", "content": "test"})
            # File handle should be closed
            assert session._file is None or session._file.closed

    def test_read_nonexistent(self, tmp_path):
        assert read_transcript(tmp_path / "missing.jsonl") == []

    def test_read_head_and_tail(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            with create_session("/proj", "ht") as session:
                for i in range(50):
                    append_message(session, {"idx": i})

            head, tail = read_head_and_tail(session.path, head_n=5, tail_n=10)
            assert len(head) == 5
            assert len(tail) == 10
            assert head[0]["idx"] == 0
            assert tail[-1]["idx"] == 49

    def test_read_head_and_tail_short(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            with create_session("/proj", "short") as session:
                for i in range(3):
                    append_message(session, {"idx": i})

            head, tail = read_head_and_tail(session.path, head_n=10, tail_n=20)
            assert len(head) == 3
            assert len(tail) == 0


class TestListSessions:
    def test_list_empty(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            assert list_sessions("/proj") == []

    def test_list_sessions(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            with create_session("/proj", "s1") as s1:
                append_message(s1, {"m": 1})
            with create_session("/proj", "s2") as s2:
                append_message(s2, {"m": 2})

            sessions = list_sessions("/proj")
            assert len(sessions) == 2
            ids = {s.session_id for s in sessions}
            assert "s1" in ids
            assert "s2" in ids

    def test_list_sessions_touched_since(self, tmp_path):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_CONFIG_DIR": str(tmp_path)}):
            before = time.time()
            with create_session("/proj", "recent") as s:
                append_message(s, {"m": 1})

            result = list_sessions_touched_since("/proj", before - 1)
            assert "recent" in result

            result_future = list_sessions_touched_since("/proj", time.time() + 100)
            assert len(result_future) == 0


# =========================================================================
# Import test — verify __init__.py exports
# =========================================================================


class TestPackageExports:
    def test_top_level_import(self):
        import memoria.core as memdir
        assert hasattr(memdir, "MemoryType")
        assert hasattr(memdir, "get_auto_mem_path")
        assert hasattr(memdir, "scan_memory_files")
        assert hasattr(memdir, "find_relevant_memories")
        assert hasattr(memdir, "create_session")
        assert hasattr(memdir, "write_memory_file")
