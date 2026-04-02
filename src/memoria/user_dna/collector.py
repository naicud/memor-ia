"""Passive signal collector — extracts behavioral signals from interactions."""

from __future__ import annotations

import re
import threading
import time

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CAMEL_RE = re.compile(r"\b[a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+\b")
_PASCAL_RE = re.compile(r"\b(?:[A-Z][a-z0-9]+){2,}\b")

_CODE_MARKERS = re.compile(
    r"(?:^|\n)\s*(?:def |class |function |import |from |const |let |var |return |if |for |while )"
    r"|[{};]\s*$"
    r"|^\s{4,}\S",
    re.MULTILINE,
)

_CONTRACTION_RE = re.compile(
    r"\b(?:don'?t|can'?t|won'?t|isn'?t|aren'?t|wouldn'?t|shouldn'?t|couldn'?t|haven'?t|hasn'?t|wasn'?t|weren'?t|it'?s|i'?m|i'?ll|you'?re|they'?re|we'?re|he'?s|she'?s|that'?s|there'?s|let'?s)\b",
    re.IGNORECASE,
)

_FRUSTRATION_WORDS = re.compile(
    r"!!!|\?\?\?"
    r"|(?:why\s+doesn'?t|why\s+isn'?t|why\s+won'?t|why\s+can'?t)"
    r"|still\s+not\s+working"
    r"|(?:broken|bug|frustrat|ugh|wtf|damn|crap|horrible|terrible|awful)",
    re.IGNORECASE,
)

_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F900-\U0001F9FF"
    r"\U00002702-\U000027B0"
    r"\U0001FA00-\U0001FA6F"
    r"\U0001FA70-\U0001FAFF"
    r"]+",
)

_GREETING_RE = re.compile(
    r"\b(?:hi|hello|hey|greetings|good\s+morning|good\s+afternoon|good\s+evening|dear|sir|madam)\b",
    re.IGNORECASE,
)

_DOCSTRING_GOOGLE_RE = re.compile(r"^\s+(?:Args|Returns|Raises|Yields|Note|Example):", re.MULTILINE)
_DOCSTRING_NUMPY_RE = re.compile(r"^\s+(?:Parameters|Returns|Raises)\s*\n\s+-{3,}", re.MULTILINE)
_DOCSTRING_SPHINX_RE = re.compile(r"^\s*:(?:param|type|returns|rtype|raises)\s", re.MULTILINE)
_DOCSTRING_TRIPLE_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')

_TYPE_HINT_RE = re.compile(r"(?::\s*\w[\w\[\], |]*\s*(?:=|$|\)))|(?:->\s*\w[\w\[\], |]*)", re.MULTILINE)

_LANG_HINTS: dict[str, list[re.Pattern[str]]] = {
    "python": [re.compile(r"\bdef \w+\("), re.compile(r"\bimport \w+"), re.compile(r"\bself\.")],
    "javascript": [re.compile(r"\bconst \w+"), re.compile(r"\bfunction \w+"), re.compile(r"=>")],
    "typescript": [re.compile(r":\s*\w+\[\]"), re.compile(r"\binterface \w+"), re.compile(r"\btype \w+\s*=")],
    "rust": [re.compile(r"\bfn \w+"), re.compile(r"\blet mut\b"), re.compile(r"\bimpl \w+")],
    "go": [re.compile(r"\bfunc \w+"), re.compile(r"\bpackage \w+"), re.compile(r":=")],
    "java": [re.compile(r"\bpublic\s+class\b"), re.compile(r"\bSystem\.out"), re.compile(r"\bprivate\s+\w+")],
}


class PassiveCollector:
    """Extracts behavioral signals from raw interaction data without user effort."""

    def __init__(self, max_raw_signals: int = 500) -> None:
        self._lock = threading.RLock()
        self._signals: list[dict] = []
        self._max_signals = max_raw_signals

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_from_message(
        self,
        message: str,
        role: str = "user",
        timestamp: float = 0.0,
    ) -> dict:
        """Extract signals from a single message. Returns signal dict."""
        if not message:
            message = ""
        ts = timestamp or time.time()

        has_code = bool(_CODE_MARKERS.search(message))
        is_question = "?" in message
        emoji_found = bool(_EMOJI_RE.search(message))

        # Formality: 0 = very casual, 10 = very formal
        contractions = len(_CONTRACTION_RE.findall(message))
        greetings = len(_GREETING_RE.findall(message))
        word_count = max(len(message.split()), 1)
        formality = max(0.0, min(10.0, 5.0 - contractions * 1.5 + greetings * 1.0 + (0.5 if message[0:1].isupper() else 0.0)))

        frustration = len(_FRUSTRATION_WORDS.findall(message))

        lang_hints: list[str] = []
        for lang, patterns in _LANG_HINTS.items():
            if any(p.search(message) for p in patterns):
                lang_hints.append(lang)

        signal: dict = {
            "type": "message",
            "role": role,
            "timestamp": ts,
            "length": len(message),
            "has_code": has_code,
            "is_question": is_question,
            "language_hints": lang_hints,
            "formality_score": round(formality, 2),
            "frustration_signals": frustration,
            "has_emoji": emoji_found,
            "word_count": word_count,
        }
        with self._lock:
            self._append(signal)
        return signal

    def collect_from_code(
        self,
        code: str,
        language: str = "",
        timestamp: float = 0.0,
    ) -> dict:
        """Extract coding style signals from a code snippet."""
        if not code:
            code = ""
        ts = timestamp or time.time()

        # Naming convention detection
        snake_count = len(_SNAKE_RE.findall(code))
        camel_count = len(_CAMEL_RE.findall(code))
        pascal_count = len(_PASCAL_RE.findall(code))

        counts = {"snake_case": snake_count, "camelCase": camel_count, "PascalCase": pascal_count}
        naming = max(counts, key=counts.get) if any(counts.values()) else "unknown"  # type: ignore[arg-type]

        # Docstring style
        has_docstrings = bool(_DOCSTRING_TRIPLE_RE.search(code))
        docstring_style = "none"
        if has_docstrings:
            if _DOCSTRING_GOOGLE_RE.search(code):
                docstring_style = "google"
            elif _DOCSTRING_NUMPY_RE.search(code):
                docstring_style = "numpy"
            elif _DOCSTRING_SPHINX_RE.search(code):
                docstring_style = "sphinx"
            else:
                docstring_style = "plain"

        # Type hints
        lines = code.split("\n")
        total_lines = max(len(lines), 1)
        func_defs = [line for line in lines if re.match(r"\s*def ", line)]
        type_hint_count = len(_TYPE_HINT_RE.findall(code))
        func_count = len(func_defs)
        type_hint_ratio = min(1.0, type_hint_count / max(func_count * 2, 1))

        # Function length
        func_lengths: list[int] = []
        in_func = False
        func_indent = 0
        func_line_count = 0
        for line in lines:
            stripped = line.rstrip()
            if re.match(r"\s*def ", stripped):
                if in_func and func_line_count > 0:
                    func_lengths.append(func_line_count)
                in_func = True
                func_indent = len(stripped) - len(stripped.lstrip())
                func_line_count = 0
            elif in_func:
                if stripped and (len(stripped) - len(stripped.lstrip())) <= func_indent and not stripped.startswith("#"):
                    if not stripped.startswith("@") and not stripped.startswith(")"):
                        func_lengths.append(func_line_count)
                        in_func = False
                        func_line_count = 0
                        continue
                func_line_count += 1
        if in_func and func_line_count > 0:
            func_lengths.append(func_line_count)

        avg_func_len = sum(func_lengths) / max(len(func_lengths), 1) if func_lengths else 0.0

        # Comment density (comments per 100 LOC)
        comment_lines = sum(1 for line in lines if line.strip().startswith("#") or line.strip().startswith("//"))
        comment_density = (comment_lines / total_lines) * 100.0

        # Import style
        import_lines = [line.strip() for line in lines if line.strip().startswith("import ") or line.strip().startswith("from ")]
        import_style = "unknown"
        if import_lines:
            import_indices = [i for i, line in enumerate(lines)
                              if line.strip().startswith("import ") or line.strip().startswith("from ")]
            has_gap = any(
                import_indices[j + 1] - import_indices[j] > 1
                for j in range(len(import_indices) - 1)
            ) if len(import_indices) > 1 else False
            if has_gap:
                import_style = "grouped"
            elif len(import_lines) > 1:
                sorted_imports = sorted(import_lines)
                import_style = "alphabetical" if import_lines == sorted_imports else "mixed"

        # Error handling
        has_try = "try:" in code or "try {" in code
        has_assert = "assert " in code
        error_handling = "unknown"
        if has_try and has_assert:
            error_handling = "mixed"
        elif has_try:
            error_handling = "try-except"
        elif has_assert:
            error_handling = "assertions"

        # Language detection if not provided
        if not language:
            for lang, patterns in _LANG_HINTS.items():
                if any(p.search(code) for p in patterns):
                    language = lang
                    break

        signal: dict = {
            "type": "code",
            "timestamp": ts,
            "language": language,
            "naming_convention": naming,
            "docstring_style": docstring_style,
            "type_hint_ratio": round(type_hint_ratio, 3),
            "avg_function_length": round(avg_func_len, 1),
            "comment_density": round(comment_density, 2),
            "import_style": import_style,
            "error_handling": error_handling,
            "total_lines": total_lines,
            "function_count": func_count,
        }
        with self._lock:
            self._append(signal)
        return signal

    def collect_from_session(
        self,
        messages: list[dict],
        duration_minutes: float = 0.0,
        timestamp: float = 0.0,
    ) -> dict:
        """Extract session-level signals."""
        if not messages:
            messages = []
        ts = timestamp or time.time()

        msg_count = len(messages)

        # Detect context switches: a rough heuristic — topic change when
        # consecutive messages share few words
        context_switches = 0
        prev_words: set[str] = set()
        for msg in messages:
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            words = set(content.lower().split())
            if prev_words and len(words & prev_words) < max(len(words) // 3, 1):
                context_switches += 1
            prev_words = words

        # Topic coverage
        topics: list[str] = []
        for msg in messages:
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            for lang in _LANG_HINTS:
                if lang not in topics:
                    for p in _LANG_HINTS[lang]:
                        if p.search(content):
                            topics.append(lang)
                            break

        signal: dict = {
            "type": "session",
            "timestamp": ts,
            "message_count": msg_count,
            "duration_minutes": duration_minutes,
            "context_switches": context_switches,
            "topics": topics,
        }
        with self._lock:
            self._append(signal)
        return signal

    def get_signals(self, since: float = 0.0) -> list[dict]:
        """Get all collected signals since timestamp."""
        with self._lock:
            if since <= 0:
                return list(self._signals)
            return [s for s in self._signals if s.get("timestamp", 0) >= since]

    def clear_old(self, before: float = 0.0) -> int:
        """Remove signals older than timestamp. Returns count removed."""
        with self._lock:
            if before <= 0:
                return 0
            original_len = len(self._signals)
            self._signals = [s for s in self._signals if s.get("timestamp", 0) >= before]
            return original_len - len(self._signals)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, signal: dict) -> None:
        self._signals.append(signal)
        if len(self._signals) > self._max_signals:
            self._signals = self._signals[-self._max_signals :]
