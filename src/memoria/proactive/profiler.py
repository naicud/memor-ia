"""Client profiling — builds and maintains user profiles from interactions."""

from __future__ import annotations

import re
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoria.graph.knowledge import KnowledgeGraph

# ---------------------------------------------------------------------------
# Known vocabularies for detection
# ---------------------------------------------------------------------------

_LANGUAGES = {
    "python", "javascript", "typescript", "java", "go", "rust", "ruby",
    "swift", "kotlin", "c++", "c#", "php", "scala", "elixir", "haskell",
    "lua", "perl", "r", "dart", "zig", "sql", "html", "css", "bash", "shell",
}

_FRAMEWORKS = {
    "react", "vue", "angular", "svelte", "next.js", "nextjs", "nuxt",
    "django", "flask", "fastapi", "express", "nestjs", "spring",
    "rails", "laravel", "gin", "actix", "phoenix", "gatsby", "remix",
    "tailwind", "bootstrap", "pytorch", "tensorflow", "langchain",
}

_TOOLS = {
    "git", "docker", "kubernetes", "k8s", "npm", "yarn", "pnpm",
    "pip", "cargo", "gradle", "maven", "webpack", "vite", "esbuild",
    "postgres", "redis", "mongodb", "mysql", "sqlite", "neo4j",
    "aws", "gcp", "azure", "terraform", "ansible", "jenkins",
    "github", "gitlab", "jira", "figma", "vim", "neovim", "vscode",
}

_ADVANCED_TERMS = {
    "coroutine", "mutex", "semaphore", "monoid", "functor", "monad",
    "eigenvalue", "gradient descent", "backpropagation", "sharding",
    "microservices", "event sourcing", "cqrs", "saga pattern",
    "dependency injection", "inversion of control", "raft consensus",
    "distributed system", "cap theorem", "eventual consistency",
}

_BEGINNER_PATTERNS = [
    re.compile(r"\bwhat\s+is\s+(a\s+)?\w+", re.I),
    re.compile(r"\bhow\s+do\s+i\b", re.I),
    re.compile(r"\bwhat\s+does\s+\w+\s+mean\b", re.I),
    re.compile(r"\bcan\s+you\s+explain\b", re.I),
    re.compile(r"\bi\s+don'?t\s+understand\b", re.I),
]

_PREFERENCE_PATTERNS = [
    re.compile(r"\bi\s+prefer\s+(\w[\w\s.+-]*)", re.I),
    re.compile(r"\bi\s+like\s+(\w[\w\s.+-]*)", re.I),
    re.compile(r"\buse\s+(\w[\w.+-]+)\s+(?:instead|over|rather)", re.I),
    re.compile(r"\bmy\s+favorite\s+is\s+(\w[\w\s.+-]*)", re.I),
    re.compile(r"\balways\s+use\s+(\w[\w.+-]+)", re.I),
]


# ---------------------------------------------------------------------------
# ClientProfile
# ---------------------------------------------------------------------------

@dataclass
class ClientProfile:
    """Complete profile of a client/user."""

    user_id: str
    expertise_level: str = "intermediate"
    primary_languages: list[str] = field(default_factory=list)
    primary_frameworks: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    interaction_count: int = 0
    topics_of_interest: list[str] = field(default_factory=list)
    working_hours: dict[str, int] = field(default_factory=dict)
    average_session_length: float = 0.0
    last_seen: float = 0.0
    preferences: dict[str, str] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    areas_for_growth: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

_MAX_PROFILES = 10_000
_MAX_LIST_ITEMS = 200
_MAX_SESSION_DURATIONS = 500


class Profiler:
    """Builds and maintains client profiles from interactions."""

    def __init__(self, kg: KnowledgeGraph | None = None):
        self._lock = threading.RLock()
        self._profiles: dict[str, ClientProfile] = {}
        self._kg = kg
        self._beginner_signals: dict[str, int] = {}
        self._advanced_signals: dict[str, int] = {}
        self._session_durations: dict[str, list[float]] = {}

    def _ensure_profile(self, user_id: str) -> ClientProfile:
        if user_id not in self._profiles:
            if len(self._profiles) >= _MAX_PROFILES:
                oldest_uid = min(self._profiles, key=lambda u: self._profiles[u].last_seen)
                del self._profiles[oldest_uid]
                self._beginner_signals.pop(oldest_uid, None)
                self._advanced_signals.pop(oldest_uid, None)
                self._session_durations.pop(oldest_uid, None)
            self._profiles[user_id] = ClientProfile(user_id=user_id)
        return self._profiles[user_id]

    def update_from_message(self, user_id: str, message: str, role: str = "user") -> None:
        """Update profile based on a new message."""
        with self._lock:
            self._update_from_message_impl(user_id, message, role)

    def _update_from_message_impl(self, user_id: str, message: str, role: str = "user") -> None:
        profile = self._ensure_profile(user_id)
        profile.interaction_count += 1
        profile.last_seen = time.time()

        if role != "user":
            return

        lower = message.lower()
        tokens = set(re.findall(r"[a-z0-9#+.]+", lower))

        # Detect languages
        for lang in _LANGUAGES:
            if lang in tokens and lang not in profile.primary_languages:
                profile.primary_languages.append(lang)
                profile.primary_languages = profile.primary_languages[-_MAX_LIST_ITEMS:]

        # Detect frameworks
        for fw in _FRAMEWORKS:
            if fw in tokens and fw not in profile.primary_frameworks:
                profile.primary_frameworks.append(fw)
                profile.primary_frameworks = profile.primary_frameworks[-_MAX_LIST_ITEMS:]

        # Detect tools
        for tool in _TOOLS:
            if tool in tokens and tool not in profile.preferred_tools:
                profile.preferred_tools.append(tool)
                profile.preferred_tools = profile.preferred_tools[-_MAX_LIST_ITEMS:]

        # Topics of interest (any detected tech term)
        for term in tokens & (_LANGUAGES | _FRAMEWORKS | _TOOLS):
            if term not in profile.topics_of_interest:
                profile.topics_of_interest.append(term)
                profile.topics_of_interest = profile.topics_of_interest[-_MAX_LIST_ITEMS:]

        # Preference extraction
        for pat in _PREFERENCE_PATTERNS:
            m = pat.search(message)
            if m:
                pref = m.group(1).strip().rstrip(".,!?")
                if pref:
                    profile.preferences[pref.lower()] = pref

        # Expertise signals
        uid = user_id
        self._beginner_signals.setdefault(uid, 0)
        self._advanced_signals.setdefault(uid, 0)

        for pat in _BEGINNER_PATTERNS:
            if pat.search(message):
                self._beginner_signals[uid] += 1

        for term in _ADVANCED_TERMS:
            if term in lower:
                self._advanced_signals[uid] += 1

        profile.expertise_level = self._compute_expertise(uid)

        self._compute_strengths_and_gaps(user_id)

    def _compute_strengths_and_gaps(self, user_id: str) -> None:
        """Populate strengths and areas_for_growth from interaction data."""
        profile = self._profiles.get(user_id)
        if profile is None:
            return

        # Strengths: topics mentioned most frequently
        topic_counts: Counter = Counter(profile.topics_of_interest)
        profile.strengths = [
            topic for topic, count in topic_counts.most_common(5)
            if count >= 1  # At least mentioned once
        ]

        # Areas for growth: known concepts not in user's tool/language set
        all_known = set(profile.primary_languages) | set(profile.primary_frameworks) | set(profile.preferred_tools)
        _GROWTH_CANDIDATES = {
            "testing", "docker", "kubernetes", "ci/cd", "security",
            "monitoring", "typescript", "rust", "go",
        }
        profile.areas_for_growth = [
            area for area in _GROWTH_CANDIDATES
            if area not in all_known
        ][:3]  # Top 3 growth areas

    def update_from_session(self, user_id: str, session_data: dict) -> None:
        """Update profile from session summary."""
        with self._lock:
            profile = self._ensure_profile(user_id)

        # Working hours
        ts = session_data.get("timestamp", time.time())
        import datetime
        dt = datetime.datetime.fromtimestamp(ts)
        hour_key = str(dt.hour)
        profile.working_hours[hour_key] = profile.working_hours.get(hour_key, 0) + 1

        # Session duration
        duration = session_data.get("duration", 0.0)
        if duration > 0:
            self._session_durations.setdefault(user_id, []).append(duration)
            durations = self._session_durations[user_id]
            if len(durations) > _MAX_SESSION_DURATIONS:
                self._session_durations[user_id] = durations[-_MAX_SESSION_DURATIONS:]
                durations = self._session_durations[user_id]
            profile.average_session_length = sum(durations) / len(durations)

        # Topics
        for topic in session_data.get("topics", []):
            if topic not in profile.topics_of_interest:
                profile.topics_of_interest.append(topic)
                profile.topics_of_interest = profile.topics_of_interest[-_MAX_LIST_ITEMS:]

        profile.last_seen = ts

    def get_profile(self, user_id: str) -> ClientProfile:
        """Get current profile for user."""
        with self._lock:
            return self._ensure_profile(user_id)

    def detect_expertise(self, user_id: str) -> str:
        """Detect expertise level from interaction patterns."""
        with self._lock:
            return self._compute_expertise(user_id)

    def _compute_expertise(self, user_id: str) -> str:
        beg = self._beginner_signals.get(user_id, 0)
        adv = self._advanced_signals.get(user_id, 0)
        profile = self._profiles.get(user_id)

        tool_count = 0
        if profile:
            tool_count = len(profile.preferred_tools) + len(profile.primary_frameworks)

        if adv >= 2 or tool_count >= 6:  # Lowered from 3/8
            return "expert"
        if beg >= 3 and adv == 0:
            return "beginner"
        return "intermediate"

    def profile_confidence(self, user_id: str) -> float:
        """Return confidence score (0-1) for how well we know this user."""
        with self._lock:
            profile = self._ensure_profile(user_id)
        signals = 0
        if profile.primary_languages:
            signals += 1
        if profile.primary_frameworks:
            signals += 1
        if profile.preferred_tools:
            signals += 1
        if profile.preferences:
            signals += 1
        if profile.interaction_count >= 5:
            signals += 1
        if profile.interaction_count >= 20:
            signals += 1
        if profile.working_hours:
            signals += 1
        return min(1.0, signals / 7.0)

    def get_working_pattern(self, user_id: str) -> dict:
        """Get working pattern analysis."""
        with self._lock:
            profile = self._ensure_profile(user_id)
        hours = profile.working_hours

        if not hours:
            return {"peak_hours": [], "total_sessions": 0}

        sorted_hours = sorted(hours.items(), key=lambda x: x[1], reverse=True)
        peak = [int(h) for h, _ in sorted_hours[:3]]
        total = sum(hours.values())

        return {
            "peak_hours": peak,
            "total_sessions": total,
            "average_session_length": profile.average_session_length,
            "distribution": dict(hours),
        }

    def serialize(self, user_id: str) -> dict:
        """Serialize profile for storage."""
        with self._lock:
            profile = self._ensure_profile(user_id)
            return asdict(profile)

    def deserialize(self, data: dict) -> ClientProfile:
        """Deserialize profile from storage."""
        with self._lock:
            valid_fields = {f.name for f in fields(ClientProfile)}
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            if "user_id" not in filtered:
                raise ValueError("data must contain 'user_id'")
            profile = ClientProfile(**filtered)
            self._profiles[profile.user_id] = profile
            return profile
