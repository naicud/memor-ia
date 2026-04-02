"""Business intelligence types for revenue signals, segmentation, lifecycle, and value scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RevenueSignalType(Enum):
    UPSELL_OPPORTUNITY = "upsell_opportunity"
    CROSS_SELL_OPPORTUNITY = "cross_sell_opportunity"
    CHURN_RISK = "churn_risk"
    EXPANSION_SIGNAL = "expansion_signal"
    CONTRACTION_SIGNAL = "contraction_signal"
    RENEWAL_RISK = "renewal_risk"
    ADVOCACY_SIGNAL = "advocacy_signal"


class SegmentType(Enum):
    POWER_USER = "power_user"
    REGULAR = "regular"
    CASUAL = "casual"
    AT_RISK = "at_risk"
    NEW_USER = "new_user"
    CHAMPION = "champion"
    DORMANT = "dormant"


class LifecycleStage(Enum):
    PROSPECT = "prospect"
    ONBOARDING = "onboarding"
    ADOPTION = "adoption"
    GROWTH = "growth"
    MATURITY = "maturity"
    SATURATION = "saturation"
    DECLINE = "decline"
    REACTIVATION = "reactivation"


class ValueTier(Enum):
    PLATINUM = "platinum"   # top 10%
    GOLD = "gold"           # top 25%
    SILVER = "silver"       # top 50%
    BRONZE = "bronze"       # bottom 50%


@dataclass
class RevenueSignal:
    signal_id: str
    signal_type: RevenueSignalType
    product_id: str
    description: str
    impact_score: float = 0.0       # 0.0-1.0 estimated revenue impact
    confidence: float = 0.0         # 0.0-1.0
    timestamp: float = 0.0
    evidence: list[str] = field(default_factory=list)
    recommended_action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserSegment:
    segment_type: SegmentType
    confidence: float = 0.0
    factors: list[str] = field(default_factory=list)
    since: float = 0.0
    products_considered: list[str] = field(default_factory=list)


@dataclass
class LifecyclePosition:
    stage: LifecycleStage
    product_id: str
    confidence: float = 0.0
    days_in_stage: int = 0
    progression_probability: float = 0.0
    regression_probability: float = 0.0
    stage_health: float = 0.0


@dataclass
class ValueScore:
    product_id: str
    engagement_score: float = 0.0
    adoption_score: float = 0.0
    retention_score: float = 0.0
    advocacy_score: float = 0.0
    overall_value: float = 0.0
    value_tier: ValueTier = ValueTier.BRONZE
    trend: str = "stable"
    last_computed: float = 0.0
