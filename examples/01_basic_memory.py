#!/usr/bin/env python3
"""MEMORIA — Example 1: Basic Memory Operations

Shows add/search/get/delete operations with the Memoria class.
"""

import tempfile
from memoria import Memoria


# ── Formattazione output ──────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def section(title: str) -> None:
    print(f"\n--- {title} {'-' * (55 - len(title))}")


def main() -> None:
    header("MEMORIA — Basic Memory Operations")

    # Creiamo una directory temporanea per salvare le memorie
    with tempfile.TemporaryDirectory() as tmpdir:
        # Inizializziamo Memoria con la directory temporanea
        m = Memoria(project_dir=tmpdir)
        print(f"\nMemoria initialized in: {tmpdir}")

        # ── 1. Aggiungere memorie ─────────────────────────────────────
        section("1. Adding memories")

        # Definiamo le memorie di un developer fittizio
        memories_data = [
            ("Marco prefers Python over JavaScript for backend development",
             "preference"),
            ("Marco is building a REST API with FastAPI and PostgreSQL",
             "project"),
            ("Marco has 5 years of experience with Django and Flask",
             "skill"),
            ("Marco uses Docker and Kubernetes for deployment",
             "tool"),
            ("Marco's team follows trunk-based development with feature flags",
             "workflow"),
            ("Marco is learning Rust for systems programming",
             "learning"),
        ]

        # Salviamo le memorie e teniamo traccia degli ID
        memory_ids = []
        for content, mem_type in memories_data:
            mem_id = m.add(content, user_id="marco", memory_type="user")
            memory_ids.append(mem_id)
            print(f"  [+] Stored: {content[:50]}...")

        print(f"\n  Total memories stored: {len(memory_ids)}")

        # ── 2. Cercare memorie ────────────────────────────────────────
        section("2. Searching memories")

        # Cerchiamo memorie con query diverse
        queries = [
            "What programming languages does Marco use?",
            "deployment and infrastructure tools",
            "web framework experience",
        ]

        for query in queries:
            print(f"\n  Query: \"{query}\"")
            results = m.search(query, user_id="marco", limit=3)
            if results:
                for i, r in enumerate(results, 1):
                    score = r["score"]
                    content = r["memory"][:70]
                    sources = r["metadata"].get("sources", [])
                    print(f"    {i}. [{score:.2f}] {content}...")
                    if sources:
                        print(f"       Sources: {', '.join(sources)}")
            else:
                print("    (no results)")

        # ── 3. Recuperare una memoria specifica ───────────────────────
        section("3. Getting a specific memory by ID")

        # Prendiamo la prima memoria per ID
        target_id = memory_ids[0]
        memory = m.get(target_id)
        if memory:
            print(f"  ID:      {memory['id']}")
            print(f"  Content: {memory['memory']}")
            meta = memory["metadata"]
            print(f"  Name:    {meta.get('name', 'N/A')}")
            print(f"  Type:    {meta.get('type', 'N/A')}")
        else:
            print("  Memory not found!")

        # ── 4. Eliminare una memoria ──────────────────────────────────
        section("4. Deleting a memory")

        # Eliminiamo l'ultima memoria (learning)
        delete_id = memory_ids[-1]
        deleted_content = memories_data[-1][0]
        print(f"  Deleting: {deleted_content[:50]}...")
        success = m.delete(delete_id)
        print(f"  Deleted: {success}")

        # Verifichiamo che sia stata eliminata
        check = m.get(delete_id)
        print(f"  Verify (should be None): {check}")

        # ── 5. Riepilogo ─────────────────────────────────────────────
        section("5. Summary")

        # Contiamo quante memorie restano
        remaining = sum(1 for mid in memory_ids if m.get(mid) is not None)
        print(f"  Memories created:   {len(memory_ids)}")
        print(f"  Memories deleted:   1")
        print(f"  Memories remaining: {remaining}")

    # La directory temporanea viene rimossa automaticamente
    print(f"\n{'=' * 60}")
    print("  Cleanup complete — temp directory removed automatically")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
