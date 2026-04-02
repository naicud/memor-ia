#!/usr/bin/env python3
"""MEMORIA — Example 3: Semantic Search

Shows vector indexing, embedding, and similarity search.
"""

from memoria.vector import (
    VectorClient,
    VectorRecord,
    TFIDFEmbedder,
    VectorIndex,
    SemanticSearch,
    chunk_markdown,
)


# ── Formattazione output ──────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def section(title: str) -> None:
    print(f"\n--- {title} {'-' * (55 - len(title))}")


def main() -> None:
    header("MEMORIA — Semantic Search")

    # Creiamo l'embedder TF-IDF (puro Python, nessuna dipendenza)
    embedder = TFIDFEmbedder(dimension=384)
    print(f"  Embedder: TFIDFEmbedder (pure Python, no ML deps)")
    print(f"  Dimension: {embedder.dimension}")

    # Client vettoriale in memoria
    client = VectorClient(db_path=None, dimension=embedder.dimension)
    print(f"  VectorClient: in-memory SQLite")

    # ── 1. Indicizzazione di snippet ──────────────────────────────────
    section("1. Indexing programming topic snippets")

    # Snippet su diversi argomenti di programmazione
    snippets = [
        ("s01", "React is a JavaScript library for building user interfaces with components"),
        ("s02", "Django is a Python web framework with batteries included and ORM support"),
        ("s03", "Docker containers package applications with their dependencies for deployment"),
        ("s04", "PostgreSQL is a powerful relational database with JSONB and full-text search"),
        ("s05", "FastAPI is a modern Python web framework for building APIs with type hints"),
        ("s06", "Kubernetes orchestrates container workloads across multiple nodes in a cluster"),
        ("s07", "Redis is an in-memory data store used for caching and message queues"),
        ("s08", "TypeScript adds static types to JavaScript for better developer experience"),
        ("s09", "GraphQL is a query language for APIs that lets clients request specific data"),
        ("s10", "Next.js is a React framework for server-side rendering and static sites"),
        ("s11", "SQLAlchemy is a Python ORM that provides SQL toolkit and object-relational mapping"),
        ("s12", "Vue.js is a progressive JavaScript framework for building web interfaces"),
        ("s13", "Nginx is a high-performance web server and reverse proxy for load balancing"),
        ("s14", "Git is a distributed version control system for tracking code changes"),
        ("s15", "Tailwind CSS is a utility-first CSS framework for rapid UI development"),
    ]

    # Indicizziamo usando VectorIndex per comodità
    index = VectorIndex(client, embedder)
    for sid, text in snippets:
        index.index_text(sid, text)
    print(f"  Indexed {len(snippets)} snippets")
    print(f"  Index stats: {index.stats()}")

    # ── 2. Ricerca semantica ──────────────────────────────────────────
    section("2. Semantic search")

    # Creiamo il motore di ricerca semantica
    search = SemanticSearch(client, embedder)

    # Query semantiche: dovrebbero trovare risultati correlati, non solo keyword match
    queries = [
        "web framework for building APIs",
        "database and data storage",
        "frontend JavaScript framework",
        "container orchestration and deployment",
        "CSS styling and design",
    ]

    for query in queries:
        print(f"\n  Query: \"{query}\"")
        results = search.search(query, limit=3)
        for i, r in enumerate(results, 1):
            print(f"    {i}. [{r.score:.3f}] ({r.id}) {r.content[:55]}...")

    # ── 3. Confronto keyword vs semantico ─────────────────────────────
    section("3. Keyword vs semantic comparison")

    # Una query senza keyword esatte ma con significato correlato
    test_queries = [
        ("Python backend development", "Nessuno snippet contiene esattamente queste parole"),
        ("user interface components", "Dovrebbe trovare React, Vue, etc."),
        ("server infrastructure", "Dovrebbe trovare Nginx, Docker, K8s"),
    ]

    for query, note in test_queries:
        print(f"\n  Query: \"{query}\"")
        print(f"  Note: {note}")

        # Ricerca semantica
        sem_results = search.search(query, limit=3)
        print(f"  Semantic results:")
        for r in sem_results:
            print(f"    [{r.score:.3f}] {r.content[:55]}...")

        # Confronto con keyword semplice (solo matching esatto)
        query_lower = query.lower()
        keyword_matches = [
            (sid, text) for sid, text in snippets
            if any(w in text.lower() for w in query_lower.split())
        ]
        print(f"  Keyword matches (exact word overlap): {len(keyword_matches)}")
        for sid, text in keyword_matches[:3]:
            print(f"    ({sid}) {text[:55]}...")

    # ── 4. Embedding: analisi di similarità ───────────────────────────
    section("4. Embedding similarity analysis")

    # Confrontiamo direttamente le distanze tra embedding
    # Usiamo frasi brevi perché TF-IDF funziona meglio con più contesto
    pairs = [
        ("React frontend JavaScript framework", "Vue.js progressive JavaScript framework"),
        ("React frontend JavaScript library", "PostgreSQL relational database server"),
        ("Docker container orchestration deployment", "Kubernetes container cluster management"),
        ("Python backend development scripting", "TypeScript frontend static typing"),
    ]

    for term_a, term_b in pairs:
        emb_a = embedder.embed(term_a)
        emb_b = embedder.embed(term_b)
        # Similarità coseno manuale
        dot = sum(a * b for a, b in zip(emb_a, emb_b))
        norm_a = sum(a * a for a in emb_a) ** 0.5
        norm_b = sum(b * b for b in emb_b) ** 0.5
        similarity = dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
        bar = "█" * int(similarity * 20)
        label_a = term_a.split()[0]
        label_b = term_b.split()[0]
        print(f"  {label_a:12s} ↔ {label_b:12s}  sim={similarity:.3f}  {bar}")

    # ── 5. Chunking di markdown ───────────────────────────────────────
    section("5. Markdown chunking")

    # Dimostriamo la suddivisione di un documento markdown
    markdown_doc = """\
# FastAPI Guide

FastAPI is a modern, fast web framework for building APIs with Python 3.7+
based on standard Python type hints. It's one of the fastest Python
frameworks available, on par with NodeJS and Go.

## Installation

Install FastAPI with pip:

```bash
pip install fastapi uvicorn
```

## Quick Start

Create a simple API endpoint:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
```

## Features

- Automatic API documentation with Swagger UI
- Data validation using Pydantic models
- Async support with async/await
- Dependency injection system
- OAuth2 and JWT authentication support

## Performance

FastAPI is built on top of Starlette and Pydantic.
It achieves high performance through async I/O
and efficient data serialization.
"""

    chunks = chunk_markdown(markdown_doc, max_chars=200)
    print(f"  Document length: {len(markdown_doc)} chars")
    print(f"  Chunks created: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        preview = chunk.text[:60].replace("\n", " ")
        print(f"    Chunk {i + 1}: [{chunk.start}-{chunk.end}] \"{preview}...\"")

    # Indicizziamo i chunk e cerchiamo
    for i, chunk in enumerate(chunks):
        index.index_text(f"chunk_{i}", chunk.text)

    print(f"\n  Searching chunks for 'async performance':")
    chunk_results = search.search("async performance", limit=3)
    for r in chunk_results:
        preview = r.content[:60].replace("\n", " ")
        print(f"    [{r.score:.3f}] ({r.id}) {preview}...")

    # ── 6. Statistiche finali ─────────────────────────────────────────
    section("6. Final statistics")

    final_stats = index.stats()
    print(f"  Total indexed records: {final_stats.get('count', client.count())}")
    print(f"  Embedding dimension:  {embedder.dimension}")

    client.close()

    print(f"\n{'=' * 60}")
    print("  Semantic search demo complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
