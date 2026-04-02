"""REST API layer bridging HTTP requests to Memoria methods."""

from __future__ import annotations

import re
import time
from typing import Any


class DashboardAPI:
    """Routes HTTP requests to Memoria methods and returns JSON responses."""

    def __init__(self, memoria: Any) -> None:
        self._memoria = memoria
        self._start_time = time.time()

    def route(self, method: str, path: str, body: dict | None = None,
              query: dict | None = None) -> tuple[int, dict]:
        """Route an API request. Returns (status_code, response_dict)."""
        query = query or {}

        routes = [
            ("GET", r"^/api/v1/health$", self._health),
            ("GET", r"^/api/v1/memories$", self._list_memories),
            ("GET", r"^/api/v1/memories/(?P<memory_id>[^/]+)$", self._get_memory),
            ("POST", r"^/api/v1/memories$", self._add_memory),
            ("DELETE", r"^/api/v1/memories/(?P<memory_id>[^/]+)$", self._delete_memory),
            ("GET", r"^/api/v1/search$", self._search),
            ("GET", r"^/api/v1/namespaces$", self._list_namespaces),
            ("GET", r"^/api/v1/stats$", self._stats),
            ("GET", r"^/api/v1/graph$", self._graph_data),
            ("GET", r"^/api/v1/audit$", self._audit_log),
            ("GET", r"^/api/v1/plugins$", self._list_plugins),
            ("GET", r"^/api/v1/streams$", self._list_streams),
        ]

        for route_method, pattern, handler in routes:
            if method != route_method:
                continue
            match = re.match(pattern, path)
            if match:
                try:
                    kwargs = match.groupdict()
                    return handler(body=body, query=query, **kwargs)
                except Exception as e:
                    return 500, {"error": str(e)}

        return 404, {"error": f"Not found: {method} {path}"}

    def _health(self, **_: Any) -> tuple[int, dict]:
        uptime = time.time() - self._start_time
        return 200, {
            "status": "ok",
            "version": self._get_version(),
            "uptime_seconds": round(uptime, 1),
        }

    def _get_version(self) -> str:
        try:
            from importlib.metadata import version
            return version("memor-ia")
        except Exception:
            return "unknown"

    def _list_memories(self, query: dict, **_: Any) -> tuple[int, dict]:
        namespace = query.get("namespace", "general")
        limit = int(query.get("limit", "50"))
        try:
            memories = self._memoria.list_memories(namespace)
            items = []
            for mem in memories[:limit]:
                if isinstance(mem, dict):
                    items.append(mem)
                elif isinstance(mem, str):
                    items.append({"id": mem, "content": mem})
                else:
                    items.append({"id": str(mem), "content": str(mem)})
            return 200, {"memories": items, "total": len(memories)}
        except Exception as e:
            return 200, {"memories": [], "total": 0, "note": str(e)}

    def _get_memory(self, memory_id: str, **_: Any) -> tuple[int, dict]:
        try:
            memory = self._memoria.get(memory_id)
            if memory is None:
                return 404, {"error": f"Memory {memory_id} not found"}
            if isinstance(memory, dict):
                return 200, memory
            return 200, {"id": memory_id, "content": str(memory)}
        except Exception as e:
            return 404, {"error": str(e)}

    def _add_memory(self, body: dict | None = None, **_: Any) -> tuple[int, dict]:
        if not body:
            return 400, {"error": "Request body required"}
        namespace = body.get("namespace", "general")
        content = body.get("content", "")
        metadata = body.get("metadata", {})
        if not content:
            return 400, {"error": "content field required"}
        try:
            result = self._memoria.add(namespace, content, metadata=metadata)
            return 201, {"created": True, "result": result}
        except Exception as e:
            return 500, {"error": str(e)}

    def _delete_memory(self, memory_id: str, **_: Any) -> tuple[int, dict]:
        try:
            result = self._memoria.delete(memory_id)
            return 200, {"deleted": True, "result": result}
        except Exception as e:
            return 500, {"error": str(e)}

    def _search(self, query: dict, **_: Any) -> tuple[int, dict]:
        q = query.get("q", "")
        limit = int(query.get("limit", "10"))
        if not q:
            return 400, {"error": "q parameter required"}
        try:
            results = self._memoria.search(q, top_k=limit)
            items = []
            for r in results:
                if isinstance(r, dict):
                    items.append(r)
                else:
                    items.append({"content": str(r)})
            return 200, {"results": items, "query": q}
        except Exception as e:
            return 200, {"results": [], "query": q, "note": str(e)}

    def _list_namespaces(self, **_: Any) -> tuple[int, dict]:
        try:
            ns = self._memoria.list_namespaces()
            return 200, {"namespaces": ns}
        except Exception as e:
            return 200, {"namespaces": [], "note": str(e)}

    def _stats(self, **_: Any) -> tuple[int, dict]:
        stats: dict[str, Any] = {}
        try:
            ns = self._memoria.list_namespaces()
            stats["namespace_count"] = len(ns)
        except Exception:
            stats["namespace_count"] = 0

        total = 0
        try:
            for ns_name in (ns if isinstance(ns, list) else []):
                name = ns_name if isinstance(ns_name, str) else ns_name.get("name", "")
                if name:
                    try:
                        mems = self._memoria.list_memories(name)
                        total += len(mems)
                    except Exception:
                        pass
        except Exception:
            pass
        stats["total_memories"] = total

        try:
            att_stats = self._memoria.attachment_stats()
            stats["attachments"] = att_stats
        except Exception:
            stats["attachments"] = {"total_attachments": 0}

        try:
            plugins = self._memoria.list_plugins()
            stats["plugin_count"] = len(plugins)
        except Exception:
            stats["plugin_count"] = 0

        return 200, stats

    def _graph_data(self, query: dict, **_: Any) -> tuple[int, dict]:
        """Return graph nodes and edges for D3 visualization."""
        nodes: list[dict] = []
        edges: list[dict] = []
        try:
            namespaces = self._memoria.list_namespaces()
            node_id = 0
            ns_nodes: dict[str, int] = {}
            for ns in (namespaces if isinstance(namespaces, list) else []):
                name = ns if isinstance(ns, str) else ns.get("name", "")
                if not name:
                    continue
                ns_nodes[name] = node_id
                nodes.append({"id": node_id, "label": name, "type": "namespace", "size": 20})
                node_id += 1
                try:
                    mems = self._memoria.list_memories(name)
                    for mem in mems[:20]:
                        mem_label = mem if isinstance(mem, str) else mem.get("id", str(mem))
                        mem_content = mem if isinstance(mem, str) else mem.get("content", "")
                        nodes.append({
                            "id": node_id,
                            "label": str(mem_label)[:40],
                            "type": "memory",
                            "size": 8,
                            "content": str(mem_content)[:200],
                        })
                        edges.append({"source": ns_nodes[name], "target": node_id})
                        node_id += 1
                except Exception:
                    pass
        except Exception:
            pass

        return 200, {"nodes": nodes, "edges": edges}

    def _audit_log(self, query: dict, **_: Any) -> tuple[int, dict]:
        limit = int(query.get("limit", "50"))
        try:
            trail = self._memoria._get_audit_trail()
            entries = trail.get_entries(limit=limit)
            items = [e if isinstance(e, dict) else {"entry": str(e)} for e in entries]
            return 200, {"entries": items, "total": len(items)}
        except Exception as e:
            return 200, {"entries": [], "total": 0, "note": str(e)}

    def _list_plugins(self, **_: Any) -> tuple[int, dict]:
        try:
            plugins = self._memoria.list_plugins()
            return 200, {"plugins": plugins}
        except Exception as e:
            return 200, {"plugins": [], "note": str(e)}

    def _list_streams(self, **_: Any) -> tuple[int, dict]:
        try:
            streams = self._memoria.stream_stats()
            return 200, {"streams": streams}
        except Exception as e:
            return 200, {"streams": {}, "note": str(e)}
