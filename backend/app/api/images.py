"""Referenzbilder hochladen, ansehen, löschen.

Bilder bleiben im Datenverzeichnis der App. Es werden nie Bilddaten protokolliert.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.core.settings_store import get_store
from app.models.reference import ROLE_LABELS, StoredImage
from app.services import images

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/roles")
async def list_roles() -> list[dict[str, str]]:
    """Die verfügbaren Rollen für die UI."""
    return [{"id": role, "label": label} for role, label in ROLE_LABELS.items()]


@router.post("", response_model=StoredImage)
async def upload_image(file: UploadFile) -> StoredImage:
    settings = get_store().load()
    raw = await file.read()
    # Pillow arbeitet synchron. Im Event-Loop wuerde ein grosses Bild den ganzen
    # Server anhalten - auch einen laufenden Kompositionsstrom.
    return await asyncio.to_thread(
        images.store_upload, raw, file.filename or "bild", settings.images
    )


@router.get("/{image_id}/thumb")
async def read_thumb(image_id: str) -> FileResponse:
    return FileResponse(
        images.thumb_path(image_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{image_id}")
async def remove_image(image_id: str) -> dict[str, bool]:
    if not images.delete_image(image_id):
        raise AppError("image_rejected", "Dieses Referenzbild gibt es nicht.", status_code=404)
    return {"deleted": True}
