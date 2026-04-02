"""Cross-database insight generation — graph, vector, and file memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoria.graph.knowledge import KnowledgeGraph
    from memoria.vector.search import SemanticSearch


# ---------------------------------------------------------------------------
# Insight dataclass
# ---------------------------------------------------------------------------

@dataclass
class Insight:
    """An insight derived from cross-referencing graph, vector, and file memory."""

    title: str
    description: str
    insight_type: str  # "connection", "trend", "gap", "expertise"
    confidence: float
    supporting_data: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# InsightGenerator
# ---------------------------------------------------------------------------

class InsightGenerator:
    """Generates insights by cross-referencing graph, vector, and file data."""

    def __init__(
        self,
        kg: KnowledgeGraph | None = None,
        search: SemanticSearch | None = None,
    ) -> None:
        self._kg = kg
        self._search = search

    # ------------------------------------------------------------------
    # Hidden connections
    # ------------------------------------------------------------------

    def find_hidden_connections(self, user_id: str) -> list[Insight]:
        """Find connections between concepts the user works with separately."""
        insights: list[Insight] = []
        if not self._kg:
            return insights

        try:
            _stats = self._kg.stats()
        except Exception:
            return insights

        # Get all entities the user has interacted with
        try:
            entities = self._kg.find_entity("")  # broad search
        except Exception:
            entities = []

        if len(entities) < 2:
            return insights

        # Look for pairs that are not directly connected but share neighbours
        entity_names = [e.get("name", "") for e in entities[:30]]

        checked: set[tuple[str, str]] = set()
        for i, name_a in enumerate(entity_names):
            for name_b in entity_names[i + 1:]:
                pair = (name_a, name_b) if name_a < name_b else (name_b, name_a)
                if pair in checked:
                    continue
                checked.add(pair)

                try:
                    related_a = {
                        r.get("name", "")
                        for r in self._kg.get_related(name_a, depth=1)
                    }
                    related_b = {
                        r.get("name", "")
                        for r in self._kg.get_related(name_b, depth=1)
                    }
                except Exception:
                    continue

                # If they share neighbours but are not directly connected
                shared = related_a & related_b - {name_a, name_b}
                direct = name_b in related_a or name_a in related_b
                if shared and not direct:
                    insights.append(Insight(
                        title=f"Hidden connection: {name_a} ↔ {name_b}",
                        description=(
                            f"'{name_a}' and '{name_b}' are not directly linked "
                            f"but share connections via: {', '.join(list(shared)[:3])}. "
                            "They may integrate well together."
                        ),
                        insight_type="connection",
                        confidence=min(1.0, len(shared) * 0.3),
                        supporting_data=[
                            {"entity_a": name_a, "entity_b": name_b,
                             "shared": list(shared)[:5]},
                        ],
                    ))

        return insights

    # ------------------------------------------------------------------
    # Knowledge gaps
    # ------------------------------------------------------------------

    def identify_knowledge_gaps(self, user_id: str) -> list[Insight]:
        """Find areas where user has partial knowledge."""
        insights: list[Insight] = []
        if not self._kg:
            return insights

        try:
            entities = self._kg.find_entity("")
        except Exception:
            return insights

        for ent in entities[:20]:
            name = ent.get("name", "")
            if not name:
                continue

            try:
                profile = self._kg.get_entity_profile(name)
            except Exception:
                continue

            related_count = profile.get("related_count", 0)
            outgoing = profile.get("outgoing_relations", [])

            # Low connectivity = potential gap
            if 0 < related_count <= 2 and len(outgoing) <= 1:
                insights.append(Insight(
                    title=f"Knowledge gap: {name}",
                    description=(
                        f"You've mentioned '{name}' but have limited related knowledge. "
                        "Exploring related concepts could deepen your understanding."
                    ),
                    insight_type="gap",
                    confidence=0.5,
                    supporting_data=[{"entity": name, "related_count": related_count}],
                ))

        return insights

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def detect_trends(self, days: int = 30) -> list[Insight]:
        """Detect trending topics and shifts in user interests."""
        insights: list[Insight] = []
        if not self._kg:
            return insights

        try:
            from memoria.graph.temporal import get_trending_concepts
            trending = get_trending_concepts(self._kg, days=days)
        except Exception:
            return insights

        if trending:
            top = trending[:5]
            names = [t.get("name", "unknown") for t in top]
            insights.append(Insight(
                title="Trending topics",
                description=f"Your most active topics recently: {', '.join(names)}",
                insight_type="trend",
                confidence=0.8,
                supporting_data=top,
            ))

        return insights

    # ------------------------------------------------------------------
    # Expertise map
    # ------------------------------------------------------------------

    def generate_expertise_map(self, user_id: str) -> dict[str, float]:
        """Generate expertise levels across topics. Returns {topic: score 0–1}."""
        expertise: dict[str, float] = {}
        if not self._kg:
            return expertise

        try:
            entities = self._kg.find_entity("")
        except Exception:
            return expertise

        max_count = 1
        for ent in entities:
            count = ent.get("interaction_count", ent.get("properties", {}).get("interaction_count", 1))
            if isinstance(count, (int, float)) and count > max_count:
                max_count = count

        for ent in entities:
            name = ent.get("name", "")
            count = ent.get("interaction_count", ent.get("properties", {}).get("interaction_count", 1))
            if isinstance(count, (int, float)):
                expertise[name] = min(1.0, count / max(max_count, 1))
            else:
                expertise[name] = 0.1

        return expertise

    # ------------------------------------------------------------------
    # Combined
    # ------------------------------------------------------------------

    def generate_all(self, user_id: str) -> list[Insight]:
        """Generate all available insights."""
        all_insights: list[Insight] = []
        all_insights.extend(self.find_hidden_connections(user_id))
        all_insights.extend(self.identify_knowledge_gaps(user_id))
        all_insights.extend(self.detect_trends())
        return all_insights
