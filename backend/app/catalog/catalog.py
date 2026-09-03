"""Product catalog: loaded from products.json, validated against config.

This is the merchant's ground truth. Anything derived from the catalog and
fed into an LLM prompt (product names/descriptions) is treated as trusted
*only because it passed this validation* — raw file contents are not trusted
until they clear these checks.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from backend.app.config import get_settings

CATALOG_PATH = Path(__file__).parent / "products.json"

_ID_RE = r"^[a-z0-9][a-z0-9-]{1,63}$"


class Product(BaseModel):
    id: str = Field(pattern=_ID_RE)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    price_paise: int = Field(gt=0, le=100_000_000)
    category: str
    related_ids: list[str] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def _no_control_chars(cls, v: str) -> str:
        if any(ord(c) < 0x20 and c not in ("\n", "\t") for c in v):
            raise ValueError("control characters are not allowed in catalog text fields")
        return v

    @field_validator("related_ids")
    @classmethod
    def _related_ids_well_formed(cls, v: list[str]) -> list[str]:
        import re

        for rid in v:
            if not re.match(_ID_RE, rid):
                raise ValueError(f"related_ids entry '{rid}' is not a valid product id")
        return v


class Catalog:
    def __init__(self, products: list[Product]) -> None:
        self._by_id = {p.id: p for p in products}

    def get(self, product_id: str) -> Product | None:
        return self._by_id.get(product_id)

    def all(self) -> list[Product]:
        return list(self._by_id.values())

    def related(self, product_id: str) -> list[Product]:
        """Explicit `related_ids` (curated upsell pairings) take priority;
        falls back to same-category products when a product has none set."""
        product = self.get(product_id)
        if product is None:
            return []
        if product.related_ids:
            return [self._by_id[rid] for rid in product.related_ids if rid in self._by_id]
        return [p for p in self._by_id.values() if p.category == product.category and p.id != product_id]


def _load_products() -> list[Product]:
    settings = get_settings()
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("products.json must contain a JSON array")

    products: list[Product] = []
    seen_ids: set[str] = set()
    for entry in raw:
        product = Product.model_validate(entry)
        if product.id in seen_ids:
            raise ValueError(f"duplicate product id in catalog: {product.id}")
        if product.category not in settings.allowed_categories:
            raise ValueError(
                f"product '{product.id}' has category '{product.category}' "
                f"not in allowed_categories {settings.allowed_categories}"
            )
        seen_ids.add(product.id)
        products.append(product)

    if not products:
        raise ValueError("catalog is empty")

    for product in products:
        for rid in product.related_ids:
            if rid not in seen_ids:
                raise ValueError(
                    f"product '{product.id}' has related_ids entry '{rid}' "
                    "which does not match any catalog product id"
                )

    return products


@lru_cache
def get_catalog() -> Catalog:
    return Catalog(_load_products())
