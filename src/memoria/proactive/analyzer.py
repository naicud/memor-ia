"""Pattern detection in user interactions."""

from __future__ import annotations

import threading
import time
from collections import Counter
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Pattern dataclass
# ---------------------------------------------------------------------------

@dataclass
class Pattern:
    """A detected behavioral pattern."""

    name: str
    description: str
    pattern_type: str  # "repetition", "sequence", "preference", "temporal"
    frequency: int
    confidence: float
    examples: list[str] = field(default_factory=list)
    last_seen: float = 0.0


# ---------------------------------------------------------------------------
# PatternAnalyzer
# ---------------------------------------------------------------------------

_MAX_HISTORY = 5000
_MAX_PATTERNS = 1000


class PatternAnalyzer:
    """Detects patterns in user interactions."""

    def __init__(self, max_history: int = _MAX_HISTORY) -> None:
        self._lock = threading.RLock()
        self._patterns: dict[str, Pattern] = {}
        self._query_history: list[tuple[float, str]] = []
        self._action_history: list[tuple[float, str, str]] = []
        self._max_history = max_history

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_query(self, query: str, timestamp: float | None = None) -> None:
        """Record a user query for pattern analysis."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._query_history.append((ts, query))
            if len(self._query_history) > self._max_history:
                self._query_history = self._query_history[-self._max_history:]

    def record_action(self, action: str, context: str = "",
                      timestamp: float | None = None) -> None:
        """Record a user action (tool use, file edit, etc.)."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._action_history.append((ts, action, context))
            if len(self._action_history) > self._max_history:
                self._action_history = self._action_history[-self._max_history:]

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def detect_repetitions(self, min_count: int = 3) -> list[Pattern]:
        """Find repeated queries/actions."""
        with self._lock:
            return self._detect_repetitions_impl(min_count)

    def _detect_repetitions_impl(self, min_count: int = 3) -> list[Pattern]:
        """Find repeated queries/actions (lock must be held)."""
        patterns: list[Pattern] = []

        # Query repetitions
        query_counts: Counter[str] = Counter()
        query_times: dict[str, float] = {}
        for ts, q in self._query_history:
            normalised = q.strip().lower()
            query_counts[normalised] += 1
            query_times[normalised] = max(query_times.get(normalised, 0.0), ts)

        for q_text, count in query_counts.items():
            if count >= min_count:
                name = f"repeated_query_{hash(q_text) & 0xFFFF:04x}"
                p = Pattern(
                    name=name,
                    description=f"Query repeated {count} times: '{q_text[:60]}'",
                    pattern_type="repetition",
                    frequency=count,
                    confidence=min(1.0, count / (min_count * 2)),
                    examples=[q_text],
                    last_seen=query_times[q_text],
                )
                patterns.append(p)
                self._patterns[name] = p

        # Action repetitions
        action_counts: Counter[str] = Counter()
        action_times: dict[str, float] = {}
        for ts, act, _ctx in self._action_history:
            action_counts[act] += 1
            action_times[act] = max(action_times.get(act, 0.0), ts)

        for act, count in action_counts.items():
            if count >= min_count:
                name = f"repeated_action_{hash(act) & 0xFFFF:04x}"
                p = Pattern(
                    name=name,
                    description=f"Action repeated {count} times: '{act[:60]}'",
                    pattern_type="repetition",
                    frequency=count,
                    confidence=min(1.0, count / (min_count * 2)),
                    examples=[act],
                    last_seen=action_times[act],
                )
                patterns.append(p)
                self._patterns[name] = p

        self._cap_patterns()
        return patterns

    def detect_sequences(self, min_length: int = 2) -> list[Pattern]:
        """Find action sequences that repeat."""
        with self._lock:
            return self._detect_sequences_impl(min_length)

    def _detect_sequences_impl(self, min_length: int = 2) -> list[Pattern]:
        """Find action sequences that repeat (lock must be held).

        Looks for pairs (and longer runs) of consecutive actions that
        recur multiple times.
        """
        patterns: list[Pattern] = []
        if len(self._action_history) < min_length * 2:
            return patterns

        actions = [act for _, act, _ in self._action_history]

        # Build bigrams
        bigram_counts: Counter[tuple[str, str]] = Counter()
        for i in range(len(actions) - 1):
            bigram_counts[(actions[i], actions[i + 1])] += 1

        for bigram, count in bigram_counts.items():
            if count >= 2:
                name = f"sequence_{'_'.join(bigram)}"[:64]
                desc = f"Sequence '{bigram[0]} → {bigram[1]}' seen {count} times"
                p = Pattern(
                    name=name,
                    description=desc,
                    pattern_type="sequence",
                    frequency=count,
                    confidence=min(1.0, count / 4),
                    examples=[f"{bigram[0]} → {bigram[1]}"],
                    last_seen=self._action_history[-1][0],
                )
                patterns.append(p)
                self._patterns[name] = p

        # Build trigrams
        if len(actions) >= 3:
            trigram_counts: Counter[tuple[str, str, str]] = Counter()
            for i in range(len(actions) - 2):
                trigram_counts[(actions[i], actions[i + 1], actions[i + 2])] += 1

            for trigram, count in trigram_counts.items():
                if count >= 2:
                    name = f"sequence_{'_'.join(trigram)}"[:64]
                    desc = f"Sequence '{' → '.join(trigram)}' seen {count} times"
                    p = Pattern(
                        name=name,
                        description=desc,
                        pattern_type="sequence",
                        frequency=count,
                        confidence=min(1.0, count / 3),
                        examples=[" → ".join(trigram)],
                        last_seen=self._action_history[-1][0],
                    )
                    patterns.append(p)
                    self._patterns[name] = p

        self._cap_patterns()
        return patterns

    def detect_temporal_patterns(self) -> list[Pattern]:
        """Find time-based patterns (e.g. user works on X in the morning)."""
        with self._lock:
            return self._detect_temporal_patterns_impl()

    def _detect_temporal_patterns_impl(self) -> list[Pattern]:
        """Find time-based patterns (lock must be held)."""
        patterns: list[Pattern] = []
        if not self._action_history:
            return patterns

        import datetime

        # Bucket actions by hour-of-day
        hour_actions: dict[int, Counter[str]] = {}
        for ts, act, ctx in self._action_history:
            dt = datetime.datetime.fromtimestamp(ts)
            hour = dt.hour
            hour_actions.setdefault(hour, Counter())[act] += 1

        # Find concentrated activity
        for hour, counts in hour_actions.items():
            top_action, top_count = counts.most_common(1)[0]
            if top_count >= 3:
                period = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
                name = f"temporal_{period}_{top_action}"[:64]
                p = Pattern(
                    name=name,
                    description=f"User performs '{top_action}' frequently in the {period}",
                    pattern_type="temporal",
                    frequency=top_count,
                    confidence=min(1.0, top_count / 5),
                    last_seen=self._action_history[-1][0],
                )
                patterns.append(p)
                self._patterns[name] = p

        # Bucket queries by context keywords for temporal grouping
        hour_contexts: dict[int, Counter[str]] = {}
        for ts, act, ctx in self._action_history:
            if ctx:
                dt = datetime.datetime.fromtimestamp(ts)
                hour_contexts.setdefault(dt.hour, Counter())[ctx] += 1

        for hour, counts in hour_contexts.items():
            top_ctx, top_count = counts.most_common(1)[0]
            if top_count >= 3:
                period = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
                name = f"temporal_context_{period}_{top_ctx}"[:64]
                p = Pattern(
                    name=name,
                    description=f"User works on '{top_ctx}' in the {period}",
                    pattern_type="temporal",
                    frequency=top_count,
                    confidence=min(1.0, top_count / 5),
                    last_seen=self._action_history[-1][0],
                )
                patterns.append(p)
                self._patterns[name] = p

        # Day-of-week patterns
        day_actions: dict[int, Counter[str]] = {}
        for ts, act, ctx in self._action_history:
            dt = datetime.datetime.fromtimestamp(ts)
            day_actions.setdefault(dt.weekday(), Counter())[act] += 1

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for weekday, counts in day_actions.items():
            top_action, top_count = counts.most_common(1)[0]
            if top_count >= 3:
                day_name = day_names[weekday]
                name = f"temporal_day_{day_name}_{top_action}"[:64]
                p = Pattern(
                    name=name,
                    description=f"User performs '{top_action}' frequently on {day_name}s",
                    pattern_type="temporal",
                    frequency=top_count,
                    confidence=min(1.0, top_count / 5),
                    last_seen=self._action_history[-1][0],
                )
                patterns.append(p)
                self._patterns[name] = p

        self._cap_patterns()
        return patterns

    # ------------------------------------------------------------------
    # Cap helper
    # ------------------------------------------------------------------

    def _cap_patterns(self) -> None:
        """Evict oldest patterns if over capacity (lock must be held)."""
        if len(self._patterns) > _MAX_PATTERNS:
            sorted_pats = sorted(
                self._patterns.items(),
                key=lambda kv: kv[1].last_seen,
            )
            for key, _ in sorted_pats[: len(self._patterns) - _MAX_PATTERNS]:
                del self._patterns[key]

    # ------------------------------------------------------------------
    # Combined
    # ------------------------------------------------------------------

    def detect_all(self) -> list[Pattern]:
        """Run all pattern detectors and return combined results."""
        with self._lock:
            all_patterns: list[Pattern] = []
            all_patterns.extend(self._detect_repetitions_impl())
            all_patterns.extend(self._detect_sequences_impl())
            all_patterns.extend(self._detect_temporal_patterns_impl())
            # Deduplicate by name
            seen: set[str] = set()
            unique: list[Pattern] = []
            for p in all_patterns:
                if p.name not in seen:
                    seen.add(p.name)
                    unique.append(p)
            return unique

    def get_patterns(self, min_confidence: float = 0.5) -> list[Pattern]:
        """Get all detected patterns above confidence threshold."""
        with self._lock:
            return [
                p for p in self._patterns.values()
                if p.confidence >= min_confidence
            ]
