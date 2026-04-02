"""Tracciamento dei prodotti nell'ecosistema utente."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from .types import ProductCategory, ProductInfo


class ProductTracker:
    """Tracks which products/services the user uses and their metadata.

    Maintains a bounded registry of :class:`ProductInfo` objects keyed by
    *product_id*.  Thread-safe via :class:`threading.RLock`.
    """

    def __init__(self, max_products: int = 100) -> None:
        self._lock = threading.RLock()
        self._products: Dict[str, ProductInfo] = {}
        self._max_products = max(1, max_products)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_product(
        self,
        product_id: str,
        name: str,
        category: ProductCategory,
        version: str = "",
        features: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProductInfo:
        """Register or update a product in the ecosystem."""
        with self._lock:
            if product_id in self._products:
                info = self._products[product_id]
                info.name = name
                info.category = category
                info.version = version
                info.features = list(features) if features else info.features
                if metadata:
                    info.metadata.update(metadata)
                return info

            # Evict oldest if at capacity
            if len(self._products) >= self._max_products:
                oldest_id = min(
                    self._products,
                    key=lambda pid: self._products[pid].registered_at,
                )
                del self._products[oldest_id]

            info = ProductInfo(
                product_id=product_id,
                name=name,
                category=category,
                version=version,
                features=list(features) if features else [],
                metadata=dict(metadata) if metadata else {},
                registered_at=time.time(),
            )
            self._products[product_id] = info
            return info

    def unregister_product(self, product_id: str) -> bool:
        """Remove a product from tracking.  Returns *True* if found."""
        with self._lock:
            if product_id in self._products:
                del self._products[product_id]
                return True
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_product(self, product_id: str) -> Optional[ProductInfo]:
        """Get product info by ID."""
        with self._lock:
            return self._products.get(product_id)

    def list_products(
        self, category: Optional[ProductCategory] = None
    ) -> List[ProductInfo]:
        """List tracked products, optionally filtered by *category*."""
        with self._lock:
            if category is None:
                return list(self._products.values())
            return [
                p for p in self._products.values() if p.category == category
            ]

    def get_ecosystem_summary(self) -> Dict[str, Any]:
        """Return summary: total products, categories breakdown, timeline."""
        with self._lock:
            categories: Dict[str, int] = {}
            timeline: List[Dict[str, Any]] = []
            for p in self._products.values():
                cat = p.category.value
                categories[cat] = categories.get(cat, 0) + 1
                timeline.append(
                    {
                        "product_id": p.product_id,
                        "name": p.name,
                        "registered_at": p.registered_at,
                    }
                )
            timeline.sort(key=lambda x: x["registered_at"])
            return {
                "total_products": len(self._products),
                "categories": categories,
                "timeline": timeline,
            }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise tracker state to a plain dict."""
        with self._lock:
            return {
                "max_products": self._max_products,
                "products": {
                    pid: info.to_dict()
                    for pid, info in self._products.items()
                },
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProductTracker:
        """Restore a tracker from a dict produced by :pymeth:`to_dict`."""
        tracker = cls(max_products=data.get("max_products", 100))
        for pid, pdata in data.get("products", {}).items():
            info = ProductInfo(
                product_id=pdata["product_id"],
                name=pdata["name"],
                category=ProductCategory(pdata["category"]),
                version=pdata.get("version", ""),
                description=pdata.get("description", ""),
                features=list(pdata.get("features", [])),
                metadata=dict(pdata.get("metadata", {})),
                registered_at=pdata.get("registered_at", 0.0),
            )
            tracker._products[pid] = info
        return tracker
