"""Emotional Intelligence Layer — multi-signal emotion analyzer.

Performs lexical, punctuation, and contextual analysis to produce
EmotionReading and SentimentScore objects.  All keyword dictionaries
are self-contained (no imports from other MEMORIA modules).
"""

import re
import threading
from typing import Dict, List, Set

from .types import (
    EmotionReading,
    EmotionType,
    IntensityLevel,
    SentimentScore,
)

# ── expanded keyword dictionaries (one set per EmotionType) ──────────

_EMOTION_KEYWORDS: Dict[EmotionType, Set[str]] = {
    EmotionType.JOY: {
        "happy", "glad", "love", "wonderful", "yay", "woohoo",
        "delighted", "cheerful", "joyful", "elated", "thrilled",
        "overjoyed", "blissful", "ecstatic", "pleased",
    },
    EmotionType.SATISFACTION: {
        "perfect", "works", "great", "thanks", "solved", "done",
        "finally", "nailed", "solid", "smooth", "clean",
        "well done", "good job", "that's it", "exactly",
    },
    EmotionType.EXCITEMENT: {
        "excited", "can't wait", "amazing", "incredible", "awesome",
        "wow", "whoa", "fantastic", "mind-blowing", "epic",
        "unbelievable", "stunning", "brilliant", "phenomenal",
    },
    EmotionType.CONFIDENCE: {
        "sure", "definitely", "obviously", "of course", "easy",
        "no problem", "certain", "absolutely", "clearly", "trivial",
        "simple", "straightforward", "got this", "know how",
    },
    EmotionType.FRUSTRATION: {
        "frustrated", "annoying", "broken", "ugh", "hate",
        "terrible", "awful", "stupid", "ridiculous", "impossible",
        "doesn't work", "keeps failing", "still broken",
        "why won't", "not working", "give up", "waste of time",
    },
    EmotionType.ANGER: {
        "angry", "furious", "mad", "infuriating", "absurd",
        "outrageous", "unacceptable", "wtf", "damn", "hell",
        "pissed", "livid", "enraged", "irate", "fuming",
    },
    EmotionType.CONFUSION: {
        "confused", "unclear", "don't understand", "what",
        "how", "why does", "makes no sense", "lost", "huh",
        "baffled", "puzzled", "perplexed", "bewildered",
        "no idea", "don't get it", "what do you mean",
    },
    EmotionType.ANXIETY: {
        "worried", "nervous", "afraid", "scared", "unsure",
        "risky", "concern", "fear", "dread", "panic",
        "uncertain", "hesitant", "anxious", "tense", "uneasy",
    },
    EmotionType.BOREDOM: {
        "boring", "tedious", "repetitive", "dull", "same thing",
        "monotonous", "mundane", "tiresome", "uninteresting",
        "yawn", "meh", "whatever", "bland",
    },
    EmotionType.FATIGUE: {
        "tired", "exhausted", "done", "enough", "give up",
        "can't anymore", "burnt out", "drained", "worn out",
        "spent", "wiped", "fatigued", "depleted", "over it",
    },
    EmotionType.CURIOSITY: {
        "interesting", "wonder", "cool", "fascinating", "how does",
        "what if", "curious", "intriguing", "neat", "tell me more",
        "explore", "dig into", "investigate", "learn",
    },
}

# VAD profiles per emotion: (valence, arousal, dominance)
_EMOTION_VAD: Dict[EmotionType, tuple] = {
    EmotionType.JOY:          ( 0.9,  0.7, 0.7),
    EmotionType.SATISFACTION:  ( 0.7,  0.3, 0.6),
    EmotionType.EXCITEMENT:    ( 0.8,  0.9, 0.7),
    EmotionType.CONFIDENCE:    ( 0.6,  0.4, 0.9),
    EmotionType.FRUSTRATION:   (-0.7,  0.7, 0.3),
    EmotionType.ANGER:         (-0.8,  0.9, 0.6),
    EmotionType.CONFUSION:     (-0.4,  0.5, 0.2),
    EmotionType.ANXIETY:       (-0.6,  0.7, 0.2),
    EmotionType.BOREDOM:       (-0.3,  0.1, 0.4),
    EmotionType.FATIGUE:       (-0.5,  0.2, 0.2),
    EmotionType.CURIOSITY:     ( 0.5,  0.6, 0.5),
    EmotionType.NEUTRAL:       ( 0.0,  0.3, 0.5),
}


class EmotionAnalyzer:
    """Multi-signal sentiment and emotion analyzer."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ── public API ───────────────────────────────────────────────────

    def analyze(self, text: str, context: str = "") -> EmotionReading:
        """Analyse *text* and return the dominant EmotionReading."""
        with self._lock:
            return self._analyze_impl(text, context)

    def analyze_batch(self, texts: List[str]) -> List[EmotionReading]:
        """Analyse a list of texts."""
        if not texts:
            return []
        with self._lock:
            return [self._analyze_impl(t) for t in texts]

    def get_sentiment_score(self, text: str) -> SentimentScore:
        """Return a VAD SentimentScore for *text*."""
        with self._lock:
            reading = self._analyze_impl(text)
            vad = _EMOTION_VAD.get(reading.emotion, (0.0, 0.3, 0.5))
            intensity = reading.intensity
            return SentimentScore(
                valence=round(vad[0] * intensity, 4),
                arousal=round(vad[1] * intensity, 4),
                dominance=round(vad[2] * intensity, 4),
            )

    @staticmethod
    def get_intensity_level(intensity: float) -> IntensityLevel:
        """Map a 0–1 float to an IntensityLevel enum."""
        if intensity < 0.2:
            return IntensityLevel.MINIMAL
        if intensity < 0.4:
            return IntensityLevel.MILD
        if intensity < 0.6:
            return IntensityLevel.MODERATE
        if intensity < 0.8:
            return IntensityLevel.STRONG
        return IntensityLevel.INTENSE

    # ── internals ────────────────────────────────────────────────────

    def _analyze_impl(self, text: str, context: str = "") -> EmotionReading:
        if text is None:
            text = ""
        if not text or not text.strip():
            return EmotionReading(
                emotion=EmotionType.NEUTRAL,
                intensity=0.0,
                confidence=0.0,
                context=context,
            )

        text_lower = text.lower()
        words = text.split()
        total_words = len(words) if words else 1

        # 1. Lexical matching
        emotion_scores: Dict[EmotionType, float] = {}
        all_signals: Dict[EmotionType, List[str]] = {}

        for etype, keywords in _EMOTION_KEYWORDS.items():
            matched: List[str] = []
            for kw in keywords:
                if kw in text_lower:
                    matched.append(kw)
            if matched:
                base = len(matched) / (len(keywords) * 0.1 + 1)
                base = min(base, 1.0)
                emotion_scores[etype] = base
                all_signals[etype] = [f"keyword:{m}" for m in matched]

        # 2. Punctuation modifiers
        punct_signals: List[str] = []
        exclaim = len(re.findall(r"!{2,}", text))
        question = len(re.findall(r"\?{2,}", text))
        ellipsis = len(re.findall(r"\.{3,}", text))

        caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
        caps_ratio = caps_words / total_words if total_words else 0.0

        smiley_pos = len(re.findall(r"[:;][\-]?[)D]", text))
        smiley_neg = len(re.findall(r"[:;][\-]?[(]", text))

        if exclaim:
            punct_signals.append("punctuation:!!!")
        if question:
            punct_signals.append("punctuation:???")
        if ellipsis:
            punct_signals.append("punctuation:...")
        if caps_ratio > 0.3:
            punct_signals.append("punctuation:CAPS")
        if smiley_pos:
            punct_signals.append("punctuation:smiley_positive")
        if smiley_neg:
            punct_signals.append("punctuation:smiley_negative")

        # Apply punctuation boosts
        if exclaim:
            for et in (EmotionType.ANGER, EmotionType.FRUSTRATION,
                       EmotionType.EXCITEMENT, EmotionType.JOY):
                if et in emotion_scores:
                    emotion_scores[et] *= 1.3
        if question:
            for et in (EmotionType.CONFUSION, EmotionType.FRUSTRATION):
                if et in emotion_scores:
                    emotion_scores[et] *= 1.2
        if ellipsis:
            for et in (EmotionType.ANXIETY, EmotionType.CONFUSION):
                if et in emotion_scores:
                    emotion_scores[et] *= 1.15
        if caps_ratio > 0.3:
            for et in (EmotionType.ANGER, EmotionType.FRUSTRATION):
                if et in emotion_scores:
                    emotion_scores[et] *= (1.0 + caps_ratio)

        if smiley_pos:
            for et in (EmotionType.JOY, EmotionType.SATISFACTION):
                emotion_scores.setdefault(et, 0.0)
                emotion_scores[et] += 0.2
                all_signals.setdefault(et, []).append("smiley_positive")
        if smiley_neg:
            for et in (EmotionType.FRUSTRATION, EmotionType.ANXIETY):
                emotion_scores.setdefault(et, 0.0)
                emotion_scores[et] += 0.2
                all_signals.setdefault(et, []).append("smiley_negative")

        # 3. Contextual: message length modifier
        if total_words < 5 and emotion_scores:
            # Short angry/frustrated messages = higher intensity
            for et in (EmotionType.ANGER, EmotionType.FRUSTRATION):
                if et in emotion_scores:
                    emotion_scores[et] *= 1.2
        elif total_words > 30 and emotion_scores:
            for et in (EmotionType.ANGER, EmotionType.FRUSTRATION):
                if et in emotion_scores:
                    emotion_scores[et] *= 0.85

        if not emotion_scores:
            return EmotionReading(
                emotion=EmotionType.NEUTRAL,
                intensity=0.0,
                confidence=0.1,
                context=context,
            )

        # Pick dominant emotion
        best_emotion = max(emotion_scores, key=lambda e: emotion_scores[e])
        raw_intensity = emotion_scores[best_emotion]
        intensity = max(0.0, min(1.0, raw_intensity))

        signals = all_signals.get(best_emotion, []) + punct_signals
        signal_count = len(signals)
        confidence = min(1.0, signal_count / 3.0)

        return EmotionReading(
            emotion=best_emotion,
            intensity=round(intensity, 4),
            confidence=round(confidence, 4),
            signals=signals,
            context=context,
        )
