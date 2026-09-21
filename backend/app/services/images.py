"""Referenzbilder: prüfen, verkleinern, EXIF entfernen, lokal ablegen.

Die Bilder bleiben ausschließlich im Datenverzeichnis der App. Es werden nie
Bilddaten protokolliert und nie Bilddaten an etwas anderes als den konfigurierten
lokalen Modellserver gegeben.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import secrets
import time
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.errors import AppError
from app.core.paths import data_dir
from app.models.reference import StoredImage
from app.models.settings import ImageSettings

log = logging.getLogger(__name__)

ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
THUMB_EDGE = 280
ID_RE = re.compile(r"^[0-9a-f]{32}$")

#: Schutz gegen Dekompressionsbomben, unabhängig vom Dateigrößenlimit.
MAX_PIXELS = 50_000_000


def uploads_dir() -> Path:
    path = data_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _paths(image_id: str) -> tuple[Path, Path]:
    if not ID_RE.match(image_id):
        raise AppError("image_rejected", "Ungültige Bild-Kennung.", status_code=400)
    base = uploads_dir()
    return base / f"{image_id}.jpg", base / f"{image_id}_thumb.jpg"


def store_upload(raw: bytes, original_name: str, settings: ImageSettings) -> StoredImage:
    """Prüft, normalisiert und speichert ein hochgeladenes Bild."""
    limit = settings.max_upload_mb * 1024 * 1024
    if len(raw) > limit:
        raise AppError(
            "image_rejected",
            f"Die Datei ist größer als {settings.max_upload_mb} MB. "
            "Verkleinere sie oder erhöhe das Limit in den Einstellungen.",
        )
    if not raw:
        raise AppError("image_rejected", "Die Datei ist leer.")

    try:
        source = Image.open(io.BytesIO(raw))
        image_format = (source.format or "").upper()
        if image_format not in ACCEPTED_FORMATS:
            raise AppError(
                "image_rejected",
                f"Format {image_format or 'unbekannt'} wird nicht unterstützt. "
                "Erlaubt sind JPEG, PNG und WebP.",
            )
        if source.width * source.height > MAX_PIXELS:
            raise AppError("image_rejected", "Das Bild hat zu viele Pixel.")
        source.load()
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AppError(
            "image_rejected", "Die Datei liess sich nicht als Bild lesen."
        ) from exc

    # Neu kodieren entfernt EXIF, Farbprofile und exotische Container vollstaendig.
    flattened = _flatten(source)
    scaled = _fit(flattened, settings.max_edge)

    image_id = secrets.token_hex(16)
    full_path, thumb_path = _paths(image_id)
    scaled.save(full_path, format="JPEG", quality=settings.jpeg_quality, optimize=True)
    _fit(flattened, THUMB_EDGE).save(thumb_path, format="JPEG", quality=80, optimize=True)

    log.info(
        "Referenzbild abgelegt: %s (%dx%d, %d kB)",
        image_id,
        scaled.width,
        scaled.height,
        full_path.stat().st_size // 1024,
    )
    return StoredImage(
        id=image_id,
        original_name=Path(original_name).name[:120] or "bild",
        width=scaled.width,
        height=scaled.height,
        bytes=full_path.stat().st_size,
    ).with_urls()


def _flatten(image: Image.Image) -> Image.Image:
    """Transparenz auf Weiss legen und in RGB wandeln."""
    if image.mode in ("RGBA", "LA", "P"):
        converted = image.convert("RGBA")
        canvas = Image.new("RGB", converted.size, (255, 255, 255))
        canvas.paste(converted, mask=converted.split()[-1])
        return canvas
    return image.convert("RGB")


def _fit(image: Image.Image, max_edge: int) -> Image.Image:
    longest = max(image.width, image.height)
    if longest <= max_edge:
        return image.copy()
    scale = max_edge / longest
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def image_path(image_id: str) -> Path:
    full_path, _ = _paths(image_id)
    if not full_path.is_file():
        raise AppError(
            "image_rejected",
            "Dieses Referenzbild gibt es nicht mehr. Lade es erneut hoch.",
            status_code=404,
        )
    return full_path


def thumb_path(image_id: str) -> Path:
    _, thumb = _paths(image_id)
    if not thumb.is_file():
        raise AppError("image_rejected", "Vorschaubild nicht gefunden.", status_code=404)
    return thumb


def thumb_source_path(image_id: str) -> Path | None:
    """Vorschaubild zum Kopieren in die Bibliothek - None, wenn es nicht mehr da ist."""
    _, thumb = _paths(image_id)
    return thumb if thumb.is_file() else None


def as_data_uri(image_id: str) -> str:
    payload = base64.b64encode(image_path(image_id).read_bytes()).decode()
    return f"data:image/jpeg;base64,{payload}"


def delete_image(image_id: str) -> bool:
    full_path, thumb = _paths(image_id)
    existed = full_path.is_file()
    full_path.unlink(missing_ok=True)
    thumb.unlink(missing_ok=True)
    return existed


def cleanup_old(max_age_hours: float = 24.0) -> int:
    """Alte Uploads beim Start entfernen. Gibt die Anzahl gelöschter Dateien zurück."""
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for path in uploads_dir().glob("*.jpg"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        log.info("%d alte Referenzbilder entfernt", removed)
    return removed
