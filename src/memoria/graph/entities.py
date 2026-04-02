"""Entity and relation extraction from text using pattern matching (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import NodeType, RelationType

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    name: str
    entity_type: NodeType
    confidence: float = 1.0
    source_text: str = ""


@dataclass
class Relation:
    source: Entity
    target: Entity
    relation_type: RelationType
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Known vocabularies
# ---------------------------------------------------------------------------

_KNOWN_TOOLS: set[str] = {
    "git", "npm", "yarn", "pnpm", "docker", "kubernetes", "k8s",
    "pip", "poetry", "conda", "cargo", "rustup",
    "webpack", "vite", "eslint", "prettier", "jest", "pytest",
    "terraform", "ansible", "jenkins", "github", "gitlab",
    "redis", "postgres", "postgresql", "mysql", "mongodb", "sqlite",
    "nginx", "apache", "graphql", "grpc", "kafka", "rabbitmq",
    "vim", "neovim", "emacs", "vscode", "intellij",
    "make", "cmake", "bazel", "gradle", "maven",
    "bash", "zsh", "fish", "tmux", "screen",
    "linux", "macos", "windows", "ubuntu", "debian",
    "aws", "gcp", "azure", "vercel", "netlify", "heroku",
    "falkordb", "neo4j", "memcached",
}

_KNOWN_CONCEPTS: set[str] = {
    "api", "rest", "graphql", "microservices", "monolith",
    "authentication", "authorization", "oauth", "jwt",
    "testing", "tdd", "bdd", "ci/cd", "devops",
    "machine learning", "deep learning", "nlp", "llm",
    "typescript", "javascript", "python", "rust", "go", "java",
    "react", "vue", "angular", "svelte", "nextjs",
    "node", "deno", "bun", "fastapi", "flask", "django", "express",
    "database", "caching", "queue", "pubsub",
    "concurrency", "parallelism", "async", "multithreading",
    "refactoring", "code review", "pair programming",
    "agile", "scrum", "kanban",
    "security", "encryption", "hashing",
    "docker", "containerization", "orchestration",
    "observability", "logging", "monitoring", "tracing",
    "design patterns", "solid", "dry", "kiss",
}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Capitalized multi-word names (2+ words starting with uppercase)
_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

# @mentions
_MENTION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_-]{1,38})")

# File paths / project paths
_PATH_RE = re.compile(
    r"(?:^|\s)((?:/[a-zA-Z0-9._-]+){2,}|(?:[a-zA-Z0-9_-]+/){2,}[a-zA-Z0-9._-]+)"
)

# URLs
_URL_RE = re.compile(r"https?://[^\s,)\"'>]+")

# Package names (npm-style: @scope/name or name)
_PKG_RE = re.compile(r"\b(@[a-z0-9_-]+/[a-z0-9._-]+|[a-z][a-z0-9._-]{2,})\b")

# Preference patterns
_PREFER_RE = re.compile(
    r"(?:I\s+)?(?:prefer|like|love|enjoy|use|choose|recommend|suggest)\s+"
    r"([A-Za-z0-9_./ -]+?)(?:\s+(?:over|instead of|rather than)\s+"
    r"([A-Za-z0-9_./ -]+))?(?:\.|,|$)",
    re.IGNORECASE,
)

# Email addresses
_EMAIL_RE = re.compile(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b")

# ISO dates and common date formats
_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\b"
    r"|\b(\d{1,2}/\d{1,2}/\d{4})\b"
)

# Organization patterns (Inc, Corp, LLC, Ltd, etc.)
_ORG_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*"
    r"\s+(?:Inc\.?|Corp\.?|LLC|Ltd\.?|GmbH|SA|AG|Co\.?))\b"
)

# Negative entity patterns (what NOT to extract)
_NEGATIVE_RE = re.compile(
    r"\b(?:not?\s+(?:using|use|like|prefer)|"
    r"(?:don'?t|doesn'?t|didn'?t)\s+(?:use|like|prefer|want)|"
    r"(?:avoid|against|dislike|hate|drop(?:ped)?|remov(?:e|ed|ing)|"
    r"stop(?:ped)?)\s+(?:using\s+)?)"
    r"([A-Za-z0-9_./ -]+?)(?:\s|[.,;:!?]|$)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Relation patterns
# ---------------------------------------------------------------------------

_RELATION_PATTERNS: list[tuple[re.Pattern[str], RelationType]] = [
    (re.compile(r"(.+?)\s+works?\s+on\s+(.+)", re.I), RelationType.WORKS_ON),
    (re.compile(r"(.+?)\s+knows?\s+(.+)", re.I), RelationType.KNOWS),
    (re.compile(r"(.+?)\s+(?:prefers?|likes?)\s+(.+)", re.I), RelationType.PREFERS),
    (re.compile(r"(.+?)\s+uses?\s+(.+)", re.I), RelationType.USES),
    (
        re.compile(r"(.+?)\s+(?:is\s+)?related\s+to\s+(.+)", re.I),
        RelationType.RELATED_TO,
    ),
]


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------


def extract_entities(text: str) -> list[Entity]:
    """Extract entities from *text* using regex-based pattern matching."""
    if not text or not text.strip():
        return []

    entities: list[Entity] = []
    seen_names: set[str] = set()

    def _add(name: str, etype: NodeType, confidence: float, source: str = "") -> None:
        key = name.lower().strip()
        if key and key not in seen_names:
            seen_names.add(key)
            entities.append(
                Entity(
                    name=name.strip(),
                    entity_type=etype,
                    confidence=confidence,
                    source_text=source or text,
                )
            )

    # --- Names (capitalized multi-word) ---
    for m in _NAME_RE.finditer(text):
        _add(m.group(1), NodeType.PERSON, 0.7, m.group(0))

    # --- @mentions ---
    for m in _MENTION_RE.finditer(text):
        _add(m.group(1), NodeType.PERSON, 0.9, m.group(0))

    # --- Tools ---
    _text_lower = text.lower()
    for tool in _KNOWN_TOOLS:
        # Match whole-word only
        pattern = re.compile(rf"\b{re.escape(tool)}\b", re.IGNORECASE)
        if pattern.search(text):
            _add(tool, NodeType.TOOL, 0.9)

    # --- Concepts ---
    for concept in _KNOWN_CONCEPTS:
        pattern = re.compile(rf"\b{re.escape(concept)}\b", re.IGNORECASE)
        if pattern.search(text):
            _add(concept, NodeType.CONCEPT, 0.8)

    # --- Paths / Projects ---
    for m in _PATH_RE.finditer(text):
        _add(m.group(1).strip(), NodeType.PROJECT, 0.8, m.group(0))

    # --- URLs → Projects ---
    for m in _URL_RE.finditer(text):
        _add(m.group(0), NodeType.PROJECT, 0.7, m.group(0))

    # --- Preferences ---
    for m in _PREFER_RE.finditer(text):
        preferred = m.group(1).strip()
        _add(preferred, NodeType.PREFERENCE, 0.8, m.group(0))
        if m.group(2):
            _add(m.group(2).strip(), NodeType.PREFERENCE, 0.6, m.group(0))

    # --- Emails ---
    for m in _EMAIL_RE.finditer(text):
        _add(m.group(1), NodeType.EMAIL, 0.95, m.group(0))

    # --- Dates ---
    for m in _DATE_RE.finditer(text):
        date_str = m.group(1) or m.group(2)
        if date_str:
            _add(date_str, NodeType.DATE, 0.9, m.group(0))

    # --- Organizations ---
    for m in _ORG_RE.finditer(text):
        _add(m.group(1), NodeType.ORGANIZATION, 0.75, m.group(0))

    # --- Mark negated entities ---
    negated_names: set[str] = set()
    for m in _NEGATIVE_RE.finditer(text):
        negated_names.add(m.group(1).strip().lower())

    # Reduce confidence for negated entities
    for entity in entities:
        if entity.name.lower() in negated_names:
            entity.confidence *= 0.3  # Severely reduce confidence

    return entities


def extract_entities_batch(texts: list[str]) -> list[list[Entity]]:
    """Extract entities from multiple texts efficiently."""
    return [extract_entities(text) for text in texts]


def extract_relations(text: str, entities: list[Entity]) -> list[Relation]:
    """Extract relationships between *entities* found in *text*."""
    if not text or not entities:
        return []

    relations: list[Relation] = []
    entity_by_name: dict[str, Entity] = {e.name.lower(): e for e in entities}

    # Check each sentence against relation patterns
    sentences = re.split(r"[.!?\n]+", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        for pattern, rel_type in _RELATION_PATTERNS:
            m = pattern.search(sentence)
            if not m:
                continue
            src_text = m.group(1).strip().lower()
            tgt_text = m.group(2).strip().rstrip(".,;:!?").lower()
            src = entity_by_name.get(src_text)
            tgt = entity_by_name.get(tgt_text)
            if src and tgt:
                relations.append(
                    Relation(
                        source=src,
                        target=tgt,
                        relation_type=rel_type,
                        confidence=min(src.confidence, tgt.confidence),
                    )
                )

    return relations
