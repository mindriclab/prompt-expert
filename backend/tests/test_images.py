from __future__ import annotations

import io
import os
import time

import pytest
from PIL import Image

from app.core.errors import AppError
from app.models.settings import ImageSettings
from app.services import images


def make_image(
    width: int = 2400,
    height: int = 1600,
    fmt: str = "JPEG",
    mode: str = "RGB",
    with_exif: bool = False,
) -> bytes:
    image = Image.new(mode, (width, height), (120, 40, 80) if mode == "RGB" else (120, 40, 80, 255))
    buffer = io.BytesIO()
    if with_exif:
        exif = Image.Exif()
        exif[0x010F] = "TestKamera"  # Make
        exif[0x9286] = "geheimer Kommentar"  # UserComment
        image.save(buffer, format=fmt, exif=exif)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def settings(**overrides) -> ImageSettings:
    return ImageSettings(**{"max_edge": 1280, "jpeg_quality": 85, "max_upload_mb": 25, **overrides})


def test_oversized_image_is_scaled_down():
    stored = images.store_upload(make_image(2400, 1600), "gross.jpg", settings())
    assert (stored.width, stored.height) == (1280, 853)
    with Image.open(images.image_path(stored.id)) as saved:
        assert saved.size == (1280, 853)
        assert saved.format == "JPEG"


def test_small_image_is_not_upscaled():
    stored = images.store_upload(make_image(400, 300), "klein.jpg", settings())
    assert (stored.width, stored.height) == (400, 300)


def test_max_edge_setting_is_honoured():
    stored = images.store_upload(make_image(2000, 1000), "x.jpg", settings(max_edge=512))
    assert max(stored.width, stored.height) == 512


def test_exif_is_removed():
    raw = make_image(800, 600, with_exif=True)
    with Image.open(io.BytesIO(raw)) as original:
        assert original.getexif().get(0x010F) == "TestKamera"  # war vorher drin

    stored = images.store_upload(raw, "mit_exif.jpg", settings())
    with Image.open(images.image_path(stored.id)) as saved:
        assert dict(saved.getexif()) == {}


def test_png_with_alpha_is_flattened_to_jpeg():
    stored = images.store_upload(make_image(600, 600, fmt="PNG", mode="RGBA"), "a.png", settings())
    with Image.open(images.image_path(stored.id)) as saved:
        assert saved.mode == "RGB"
        assert saved.format == "JPEG"


def test_webp_is_accepted():
    stored = images.store_upload(make_image(500, 500, fmt="WEBP"), "a.webp", settings())
    assert stored.width == 500


def test_unsupported_format_is_rejected():
    with pytest.raises(AppError) as excinfo:
        images.store_upload(make_image(100, 100, fmt="BMP"), "a.bmp", settings())
    assert excinfo.value.code == "image_rejected"
    assert "JPEG, PNG und WebP" in excinfo.value.message


def test_non_image_is_rejected():
    with pytest.raises(AppError, match="als Bild lesen"):
        images.store_upload(b"das ist kein bild", "fake.jpg", settings())


def test_empty_file_is_rejected():
    with pytest.raises(AppError, match="leer"):
        images.store_upload(b"", "leer.jpg", settings())


def test_file_over_limit_is_rejected():
    # Das Groessenlimit greift vor dem Dekodieren, der Inhalt ist hier egal.
    too_big = b"x" * (1024 * 1024 + 1)
    with pytest.raises(AppError) as excinfo:
        images.store_upload(too_big, "x.jpg", settings(max_upload_mb=1))
    assert excinfo.value.code == "image_rejected"
    assert "1 MB" in excinfo.value.message


def test_thumbnail_is_created_and_smaller():
    stored = images.store_upload(make_image(2000, 2000), "x.jpg", settings())
    with Image.open(images.thumb_path(stored.id)) as thumb:
        assert max(thumb.size) == images.THUMB_EDGE
    assert images.thumb_path(stored.id).stat().st_size < images.image_path(stored.id).stat().st_size


def test_data_uri_round_trip():
    stored = images.store_upload(make_image(320, 240), "x.jpg", settings())
    uri = images.as_data_uri(stored.id)
    assert uri.startswith("data:image/jpeg;base64,")

    from app.providers.base import split_data_uri

    fmt, payload = split_data_uri(uri)
    assert fmt == "jpeg" and len(payload) > 100


def test_path_traversal_is_blocked():
    for evil in ("../../etc/passwd", "..", "x" * 31, "NICHT-HEX-0123456789abcdef0123"):
        with pytest.raises(AppError, match="Ungültige Bild-Kennung"):
            images.image_path(evil)


def test_delete_removes_both_files():
    stored = images.store_upload(make_image(300, 300), "x.jpg", settings())
    full = images.image_path(stored.id)
    thumb = images.thumb_path(stored.id)
    assert images.delete_image(stored.id) is True
    assert not full.exists() and not thumb.exists()
    assert images.delete_image(stored.id) is False


def test_cleanup_only_removes_old_files():
    fresh = images.store_upload(make_image(200, 200), "neu.jpg", settings())
    old = images.store_upload(make_image(200, 200), "alt.jpg", settings())
    stale = time.time() - 48 * 3600
    for path in (images.image_path(old.id), images.thumb_path(old.id)):
        os.utime(path, (stale, stale))

    removed = images.cleanup_old(max_age_hours=24)

    assert removed == 2  # Bild und Vorschaubild
    assert images.image_path(fresh.id).exists()
    with pytest.raises(AppError):
        images.image_path(old.id)


# --- API ---------------------------------------------------------------------


def test_upload_endpoint_returns_metadata(client):
    response = client.post(
        "/api/images", files={"file": ("foto.png", make_image(1800, 1200, fmt="PNG"), "image/png")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["original_name"] == "foto.png"
    assert body["width"] == 1280
    assert body["thumb_url"] == f"/api/images/{body['id']}/thumb"


def test_thumb_endpoint_serves_jpeg(client):
    image_id = client.post(
        "/api/images", files={"file": ("a.jpg", make_image(900, 900), "image/jpeg")}
    ).json()["id"]
    response = client.get(f"/api/images/{image_id}/thumb")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


def test_upload_rejects_rubbish(client):
    response = client.post("/api/images", files={"file": ("x.jpg", b"kein bild", "image/jpeg")})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "image_rejected"


def test_delete_endpoint(client):
    image_id = client.post(
        "/api/images", files={"file": ("a.jpg", make_image(300, 300), "image/jpeg")}
    ).json()["id"]
    assert client.delete(f"/api/images/{image_id}").json() == {"deleted": True}
    assert client.delete(f"/api/images/{image_id}").status_code == 404


def test_roles_endpoint_lists_all_roles(client):
    roles = client.get("/api/images/roles").json()
    assert [entry["id"] for entry in roles] == [
        "subject",
        "style",
        "composition",
        "wardrobe",
        "environment",
    ]
    assert roles[0]["label"] == "Subjekt"
