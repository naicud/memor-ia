"""DNA analyzer — mines behavioral patterns from collected signals."""

from __future__ import annotations

import datetime
import time
from collections import Counter

from memoria.user_dna.types import (
    CodingStyle,
    CommunicationProfile,
    ExpertiseSnapshot,
    InteractionFingerprint,
    SessionRhythm,
    UserDNA,
)


_MAX_EXPERTISE_DOMAINS = 50


class DNAAnalyzer:
    """Mines behavioral patterns from collected signals to build the UserDNA."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, dna: UserDNA, signals: list[dict]) -> UserDNA:
        """Update UserDNA from new signals. Returns updated DNA (mutates in place too)."""
        if not signals:
            return dna

        msg_signals = [s for s in signals if s.get("type") == "message"]
        code_signals = [s for s in signals if s.get("type") == "code"]
        session_signals = [s for s in signals if s.get("type") == "session"]

        if msg_signals:
            self._update_communication(dna.communication, msg_signals)
        if code_signals:
            self._update_coding_style(dna.coding_style, code_signals)
        if session_signals:
            self._update_rhythm(dna.rhythm, session_signals)

        dna.expertise = self._update_expertise(dna.expertise, signals)
        self._update_fingerprint(dna.fingerprint, signals)

        # Manage raw signals (keep last N)
        max_raw = 200
        dna.raw_signals = (dna.raw_signals + signals)[-max_raw:]

        dna.tags = self.generate_tags(dna)
        dna.version += 1
        dna.updated_at = time.time()
        if dna.created_at == 0.0:
            dna.created_at = dna.updated_at

        return dna

    # ------------------------------------------------------------------
    # Communication
    # ------------------------------------------------------------------

    def _update_communication(
        self, comm: CommunicationProfile, msg_signals: list[dict]
    ) -> None:
        """Update communication profile from message signals using running averages."""
        if not msg_signals:
            return

        lengths = [s.get("length", 0) for s in msg_signals]
        avg_len = sum(lengths) / len(lengths)
        # Verbosity: map average length to 1-10 scale (0→1, 500+→10)
        new_verbosity = min(10.0, max(1.0, avg_len / 50.0))
        comm.verbosity = _running_avg(comm.verbosity, new_verbosity, 0.3)

        formality_scores = [s.get("formality_score", 5.0) for s in msg_signals]
        new_formality = sum(formality_scores) / len(formality_scores)
        comm.formality = _running_avg(comm.formality, new_formality, 0.3)

        questions = sum(1 for s in msg_signals if s.get("is_question"))
        batch_size = len(msg_signals)
        q_per_10 = (questions / batch_size) * 10.0
        comm.question_frequency = _running_avg(comm.question_frequency, q_per_10, 0.3)

        # Explanation depth from average length
        if avg_len < 50:
            depth = "brief"
        elif avg_len < 200:
            depth = "medium"
        else:
            depth = "detailed"
        comm.explanation_depth = depth

        frustration = sum(s.get("frustration_signals", 0) for s in msg_signals)
        comm.frustration_indicators += frustration
        if frustration > 0:
            comm.patience_level = max(1.0, comm.patience_level - 0.5 * frustration)

        emoji_msgs = sum(1 for s in msg_signals if s.get("has_emoji"))
        if emoji_msgs > batch_size * 0.3:
            comm.uses_emoji = True

    # ------------------------------------------------------------------
    # Coding style
    # ------------------------------------------------------------------

    def _update_coding_style(
        self, style: CodingStyle, code_signals: list[dict]
    ) -> None:
        """Update coding style from code signals using majority voting."""
        if not code_signals:
            return

        # Naming convention — majority vote
        naming_votes: Counter[str] = Counter()
        for s in code_signals:
            nc = s.get("naming_convention", "unknown")
            if nc != "unknown":
                naming_votes[nc] += 1
        if naming_votes:
            style.naming_convention = naming_votes.most_common(1)[0][0]

        # Docstring style — majority vote
        doc_votes: Counter[str] = Counter()
        for s in code_signals:
            ds = s.get("docstring_style", "none")
            if ds not in ("none", "unknown"):
                doc_votes[ds] += 1
        if doc_votes:
            style.docstring_style = doc_votes.most_common(1)[0][0]

        # Import style — majority vote
        imp_votes: Counter[str] = Counter()
        for s in code_signals:
            ist = s.get("import_style", "unknown")
            if ist != "unknown":
                imp_votes[ist] += 1
        if imp_votes:
            style.import_style = imp_votes.most_common(1)[0][0]

        # Error handling — majority vote
        err_votes: Counter[str] = Counter()
        for s in code_signals:
            eh = s.get("error_handling", "unknown")
            if eh != "unknown":
                err_votes[eh] += 1
        if err_votes:
            style.error_handling = err_votes.most_common(1)[0][0]

        # Averages
        func_lens = [s.get("avg_function_length", 0.0) for s in code_signals if s.get("avg_function_length", 0) > 0]
        if func_lens:
            style.avg_function_length = _running_avg(
                style.avg_function_length, sum(func_lens) / len(func_lens), 0.3
            )

        densities = [s.get("comment_density", 0.0) for s in code_signals]
        if densities:
            style.comment_density = _running_avg(
                style.comment_density, sum(densities) / len(densities), 0.3
            )

        hints = [s.get("type_hint_ratio", 0.0) for s in code_signals]
        if hints:
            style.type_annotation_usage = _running_avg(
                style.type_annotation_usage, sum(hints) / len(hints), 0.3
            )

    # ------------------------------------------------------------------
    # Session rhythm
    # ------------------------------------------------------------------

    def _update_rhythm(
        self, rhythm: SessionRhythm, session_signals: list[dict]
    ) -> None:
        """Update session rhythm from session signals."""
        if not session_signals:
            return

        durations = [s.get("duration_minutes", 0.0) for s in session_signals if s.get("duration_minutes", 0) > 0]
        if durations:
            rhythm.avg_session_minutes = _running_avg(
                rhythm.avg_session_minutes, sum(durations) / len(durations), 0.3
            )

        msg_counts = [s.get("message_count", 0) for s in session_signals if s.get("message_count", 0) > 0]
        if msg_counts:
            rhythm.avg_messages_per_session = _running_avg(
                rhythm.avg_messages_per_session, sum(msg_counts) / len(msg_counts), 0.3
            )

        switches = [s.get("context_switches", 0) for s in session_signals]
        if switches:
            rhythm.context_switch_frequency = _running_avg(
                rhythm.context_switch_frequency, sum(switches) / len(switches), 0.3
            )

        # Peak hours from timestamps
        for s in session_signals:
            ts = s.get("timestamp", 0.0)
            if ts > 0:
                hour = datetime.datetime.fromtimestamp(ts).hour
                if hour not in rhythm.peak_hours:
                    rhythm.peak_hours.append(hour)
                    # Keep only top hours
                    if len(rhythm.peak_hours) > 8:
                        rhythm.peak_hours = rhythm.peak_hours[-8:]

        # Focus duration heuristic
        if durations and msg_counts:
            switches_total = sum(switches)
            if switches_total > 0:
                avg_dur = sum(durations) / len(durations)
                rhythm.focus_duration_minutes = avg_dur / (switches_total / len(session_signals) + 1)
            elif durations:
                rhythm.focus_duration_minutes = sum(durations) / len(durations)

    # ------------------------------------------------------------------
    # Expertise
    # ------------------------------------------------------------------

    def _update_expertise(
        self,
        expertise: list[ExpertiseSnapshot],
        signals: list[dict],
    ) -> list[ExpertiseSnapshot]:
        """Update expertise map from all signals. Add new domains, update existing."""
        domain_map: dict[str, ExpertiseSnapshot] = {e.domain: e for e in expertise}

        # Gather language evidence
        lang_evidence: Counter[str] = Counter()
        for s in signals:
            # From code signals
            lang = s.get("language", "")
            if lang:
                lang_evidence[lang] += 1
            # From language hints
            for hint in s.get("language_hints", []):
                lang_evidence[hint] += 1
            # From topics
            for topic in s.get("topics", []):
                lang_evidence[topic] += 1

        now = time.time()
        for domain, count in lang_evidence.items():
            if not domain:
                continue
            if domain in domain_map:
                snap = domain_map[domain]
                old_level = snap.level
                snap.evidence_count += count
                # Level grows with evidence, capped at 1.0
                snap.level = min(1.0, snap.level + count * 0.05)
                snap.last_seen = now
                snap.confidence = min(1.0, snap.evidence_count / 20.0)
                snap.growth_rate = snap.level - old_level
            else:
                snap = ExpertiseSnapshot(
                    domain=domain,
                    level=min(1.0, count * 0.05),
                    confidence=min(1.0, count / 20.0),
                    evidence_count=count,
                    first_seen=now,
                    last_seen=now,
                    growth_rate=min(1.0, count * 0.05),
                )
                domain_map[domain] = snap

        # Cap expertise domains to prevent unbounded growth
        if len(domain_map) > _MAX_EXPERTISE_DOMAINS:
            sorted_domains = sorted(domain_map.values(), key=lambda e: e.evidence_count, reverse=True)
            domain_map = {e.domain: e for e in sorted_domains[:_MAX_EXPERTISE_DOMAINS]}

        return list(domain_map.values())

    # ------------------------------------------------------------------
    # Fingerprint
    # ------------------------------------------------------------------

    def _update_fingerprint(
        self,
        fp: InteractionFingerprint,
        all_signals: list[dict],
    ) -> None:
        """Update interaction fingerprint totals."""
        msg_signals = [s for s in all_signals if s.get("type") == "message"]
        session_signals = [s for s in all_signals if s.get("type") == "session"]
        code_signals = [s for s in all_signals if s.get("type") == "code"]

        fp.total_interactions += len(msg_signals)
        fp.total_sessions += len(session_signals)

        timestamps = [s.get("timestamp", 0.0) for s in all_signals if s.get("timestamp", 0) > 0]
        if timestamps:
            if fp.first_interaction == 0.0:
                fp.first_interaction = min(timestamps)
            fp.last_interaction = max(timestamps)

        # Average message length (running average)
        lengths = [s.get("length", 0) for s in msg_signals if s.get("length", 0) > 0]
        if lengths:
            new_avg = sum(lengths) / len(lengths)
            fp.avg_message_length = _running_avg(fp.avg_message_length, new_avg, 0.3)

        # Code to text ratio
        if msg_signals:
            code_msgs = sum(1 for s in msg_signals if s.get("has_code"))
            ratio = code_msgs / len(msg_signals)
            fp.code_to_text_ratio = _running_avg(fp.code_to_text_ratio, ratio, 0.3)

        # Common intents — accumulate language domains as intents
        intent_counter: Counter[str] = Counter()
        for s in all_signals:
            for hint in s.get("language_hints", []):
                intent_counter[hint] += 1
            if s.get("has_code"):
                intent_counter["code"] += 1
            if s.get("is_question"):
                intent_counter["learn"] += 1

        if intent_counter:
            top_intents = [k for k, _ in intent_counter.most_common(5)]
            existing = set(fp.common_intents)
            for intent in top_intents:
                if intent not in existing:
                    fp.common_intents.append(intent)
            # Keep manageable
            fp.common_intents = fp.common_intents[-10:]

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def generate_tags(self, dna: UserDNA) -> list[str]:
        """Generate descriptive tags from DNA state."""
        tags: list[str] = []

        # Expertise tags
        for exp in dna.expertise:
            if exp.level >= 0.7:
                tags.append(f"{exp.domain}-expert")
            elif exp.level >= 0.3:
                tags.append(f"{exp.domain}-intermediate")

        # Communication tags
        if dna.communication.verbosity >= 7.0:
            tags.append("verbose")
        elif dna.communication.verbosity <= 3.0:
            tags.append("concise")

        if dna.communication.formality >= 7.0:
            tags.append("formal")
        elif dna.communication.formality <= 3.0:
            tags.append("casual")

        if dna.communication.frustration_indicators >= 5:
            tags.append("frustrated-user")

        if dna.communication.uses_emoji:
            tags.append("emoji-user")

        # Coding style tags
        if dna.coding_style.naming_convention != "unknown":
            tags.append(f"style-{dna.coding_style.naming_convention}")

        if dna.coding_style.testing_approach == "tdd":
            tags.append("tdd-practitioner")

        if dna.coding_style.type_annotation_usage >= 0.7:
            tags.append("type-annotator")

        # Rhythm tags
        if dna.rhythm.peak_hours:
            night_hours = {22, 23, 0, 1, 2, 3, 4}
            if any(h in night_hours for h in dna.rhythm.peak_hours):
                tags.append("night-owl")
            morning_hours = {5, 6, 7, 8}
            if any(h in morning_hours for h in dna.rhythm.peak_hours):
                tags.append("early-bird")

        return tags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _running_avg(old: float, new: float, alpha: float = 0.3) -> float:
    """Exponential moving average. alpha controls how much weight new data gets."""
    if abs(old) < 1e-12:
        return new
    return old * (1 - alpha) + new * alpha
