"""Tipi di dati per il modulo Product Ecosystem Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ProductCategory(Enum):
    """Categorie di prodotti tracciati."""

    BILLING = "billing"
    CRM = "crm"
    IDE = "ide"
    PROJECT_MANAGEMENT = "project_management"
    COMMUNICATION = "communication"
    ANALYTICS = "analytics"
    STORAGE = "storage"
    SECURITY = "security"
    DEVELOPMENT = "development"
    MARKETING = "marketing"
    SUPPORT = "support"
    CUSTOM = "custom"


class UsageFrequency(Enum):
    """Frequenza d'uso di un prodotto."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    OCCASIONAL = "occasional"
    RARE = "rare"
    INACTIVE = "inactive"


class AdoptionStage(Enum):
    """Stadio di adozione di un prodotto."""

    DISCOVERY = "discovery"
    ONBOARDING = "onboarding"
    REGULAR = "regular"
    POWER_USER = "power_user"
    CHAMPION = "champion"
    DECLINING = "declining"
    CHURNED = "churned"


class FeatureStatus(Enum):
    """Stato di adozione di una funzionalità."""

    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    TRIED = "tried"
    ADOPTED = "adopted"
    MASTERED = "mastered"
    ABANDONED = "abandoned"


@dataclass
class ProductInfo:
    """Informazioni su un prodotto registrato nell'ecosistema."""

    product_id: str
    name: str
    category: ProductCategory
    version: str = ""
    description: str = ""
    features: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "description": self.description,
            "features": list(self.features),
            "metadata": dict(self.metadata),
            "registered_at": self.registered_at,
        }


@dataclass
class ProductUsageEvent:
    """Singolo evento d'uso di un prodotto."""

    product_id: str
    feature: str
    action: str
    timestamp: float
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "feature": self.feature,
            "action": self.action,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "metadata": dict(self.metadata),
            "session_id": self.session_id,
        }


@dataclass
class UsageProfile:
    """Profilo d'uso aggregato per un prodotto."""

    product_id: str
    total_events: int = 0
    total_duration_seconds: float = 0.0
    frequency: UsageFrequency = UsageFrequency.INACTIVE
    adoption_stage: AdoptionStage = AdoptionStage.DISCOVERY
    features_used: Dict[str, int] = field(default_factory=dict)
    peak_hours: List[int] = field(default_factory=list)
    last_used: float = 0.0
    first_used: float = 0.0
    avg_session_duration: float = 0.0
    feature_adoption: Dict[str, FeatureStatus] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "total_events": self.total_events,
            "total_duration_seconds": self.total_duration_seconds,
            "frequency": self.frequency.value,
            "adoption_stage": self.adoption_stage.value,
            "features_used": dict(self.features_used),
            "peak_hours": list(self.peak_hours),
            "last_used": self.last_used,
            "first_used": self.first_used,
            "avg_session_duration": self.avg_session_duration,
            "feature_adoption": {
                k: v.value for k, v in self.feature_adoption.items()
            },
        }


@dataclass
class ProductRelationship:
    """Relazione tra due prodotti nell'ecosistema."""

    source_product: str
    target_product: str
    relationship_type: str
    strength: float = 0.0
    evidence_count: int = 0
    common_features: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_product": self.source_product,
            "target_product": self.target_product,
            "relationship_type": self.relationship_type,
            "strength": self.strength,
            "evidence_count": self.evidence_count,
            "common_features": list(self.common_features),
        }


@dataclass
class AdoptionCurve:
    """Curva di adozione di una funzionalità specifica."""

    product_id: str
    feature: str
    stage: FeatureStatus
    discovery_date: float = 0.0
    adoption_date: float = 0.0
    mastery_date: float = 0.0
    usage_trend: str = "stable"
    total_uses: int = 0
    days_to_adopt: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "feature": self.feature,
            "stage": self.stage.value,
            "discovery_date": self.discovery_date,
            "adoption_date": self.adoption_date,
            "mastery_date": self.mastery_date,
            "usage_trend": self.usage_trend,
            "total_uses": self.total_uses,
            "days_to_adopt": self.days_to_adopt,
        }
