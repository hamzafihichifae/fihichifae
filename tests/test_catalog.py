"""Catalog rules. Every row created here is deleted afterwards (see conftest.py)."""

import base64

import pytest

from app import catalog, config, storage
from app import db as database
from app.catalog import StoreError

PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4d60000000049454e44ae426082"
    )
).decode()


def test_grouped_catalog_shape():
    data = catalog.grouped_catalog()
    assert isinstance(data["categories"], list) and isinstance(data["featured"], list)
    for cat in data["categories"]:
        assert {"id", "title_ar", "title_fr", "title_en", "img", "products"} <= set(cat)


def test_default_sizes_follow_price(product):
    assert product["sizes"] == [
        {"size": "1", "unit": "kg", "price": 100.0},
        {"size": "0.5", "unit": "kg", "price": 50.0},
    ]
    assert product["sizes_custom"] is False


def test_price_edit_takes_effect_without_custom_sizes(product):
    updated = catalog.update_product(product["id"], price=150, sizes=[])
    assert updated["min"] == 150
    assert updated["sizes"][0]["price"] == 150


def test_custom_sizes_drive_the_price(product):
    updated = catalog.update_product(
        product["id"], sizes=[{"size": "2", "unit": "kg", "price": 180}], price=""
    )
    assert updated["sizes_custom"] is True
    assert (updated["min"], updated["max"]) == (180, 180)


def test_description_is_saved(product):
    updated = catalog.update_product(product["id"], description="عسل جبلي")
    assert updated["description"] == "عسل جبلي"


def test_delete_archives_and_restore_brings_back(product):
    old_id = catalog.archive_product(product["id"], "pytest")
    with database.live_db() as conn:
        assert not conn.execute("SELECT 1 FROM products WHERE id=?", (product["id"],)).fetchone()
    archived = [p for p in catalog.list_archive()["products"] if p["id"] == old_id]
    assert archived and archived[0]["name"] == product["name"]

    restored = catalog.restore_product(old_id)
    assert restored["restored"] == product["id"]
    with database.live_db() as conn:
        assert conn.execute("SELECT 1 FROM products WHERE id=?", (product["id"],)).fetchone()


def test_category_with_products_cannot_be_deleted(product):
    with pytest.raises(StoreError) as err:
        catalog.delete_category(product["cat"])
    assert err.value.code == "category_has_products"


def test_empty_category_is_archived(category):
    catalog.delete_category(category["slug"], "pytest")
    assert category["slug"] in {c["slug"] for c in catalog.list_archive()["categories"]}
    assert catalog.category_names()[category["slug"]] == category["title_ar"]


def test_image_upload_is_stored_and_svg_rejected(category):
    p = catalog.add_product(
        "pytest-img", category["slug"], 10.0, "data:image/png;base64," + PNG_1PX
    )
    assert p["img"].startswith(config.MEDIA_BASE_URL + "/prod_")
    name = catalog.uploaded_name(p["img"])
    assert name and storage.get(name)[1:4] == b"PNG"
    svg = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>").decode()
    with pytest.raises(StoreError):
        catalog.store_image_source("data:image/svg+xml;base64," + svg)


def test_image_path_traversal_is_rejected():
    with pytest.raises(StoreError):
        catalog.store_image_source("assets/../fihi-chifae.db")
    assert catalog.uploaded_name("assets/uploads/../../x") is None
