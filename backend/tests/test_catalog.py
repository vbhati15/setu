import pytest
from pydantic import ValidationError

from backend.app.catalog.catalog import Product, get_catalog


def test_catalog_loads_and_validates():
    catalog = get_catalog()
    products = catalog.all()
    assert len(products) >= 5
    ids = [p.id for p in products]
    assert len(ids) == len(set(ids)), "catalog ids must be unique"


def test_catalog_get_known_product():
    catalog = get_catalog()
    product = catalog.get("mechanical-keyboard-65")
    assert product is not None
    assert product.price_paise > 0


def test_catalog_get_unknown_product_returns_none():
    catalog = get_catalog()
    assert catalog.get("does-not-exist") is None


def test_related_uses_explicit_related_ids_when_present():
    catalog = get_catalog()
    related = catalog.related("mechanical-keyboard-65")
    assert [r.id for r in related] == ["keycap-set-pbt-129"]


def test_related_can_cross_categories_via_explicit_pairing():
    # monitor (displays) is explicitly paired with monitor-arm (accessories) —
    # a curated pairing, not a same-category fallback.
    catalog = get_catalog()
    monitor = catalog.get("monitor-27-1440p-144hz")
    related = catalog.related("monitor-27-1440p-144hz")
    assert len(related) == 1
    assert related[0].id == "monitor-arm-single"
    assert related[0].category != monitor.category


def test_related_falls_back_to_category_when_no_explicit_ids():
    catalog = get_catalog()
    product = catalog.get("mouse-pad-xl")
    assert product.related_ids == []
    related = catalog.related("mouse-pad-xl")
    for r in related:
        assert r.id != product.id
        assert r.category == product.category


@pytest.mark.parametrize(
    "bad_id",
    ["Has Spaces", "UPPERCASE", "-leading-dash", "a", "x" * 100],
)
def test_product_id_validation_rejects_bad_ids(bad_id):
    with pytest.raises(ValidationError):
        Product(id=bad_id, name="x", description="x", price_paise=100, category="peripherals")


def test_product_rejects_control_characters_in_text_fields():
    with pytest.raises(ValidationError):
        Product(
            id="valid-id",
            name="bad\x00name",
            description="fine",
            price_paise=100,
            category="peripherals",
        )


def test_product_rejects_malformed_related_id():
    with pytest.raises(ValidationError):
        Product(
            id="valid-id",
            name="fine",
            description="fine",
            price_paise=100,
            category="peripherals",
            related_ids=["Not A Valid Id"],
        )
