"""Bibliothek: automatisches Speichern, Suche, Tags, Export, Löschen."""

from __future__ import annotations

import json

import pytest

from app.models.compose import ComposeResponse, PromptBundle, PromptCritique
from app.models.library import derive_title, normalise_tags
from app.services.images import cleanup_old, uploads_dir
from app.services.library import get_library

PAYLOAD = {
    "mode": "improve",
    "profile_id": "flux_image",
    "density": "balanced",
    "language": "en",
    "input_prompt": "girl in alley, neon",
}


def response_for(
    prompt: str = "eine praezise Fassung",
    *,
    mode: str = "improve",
    profile_id: str = "flux_image",
) -> ComposeResponse:
    return ComposeResponse(
        mode=mode,
        intent="reproduce",
        profile_id=profile_id,
        profile_label="FLUX / Krea — Bild",
        language="en",
        density="balanced",
        model="testmodell",
        critique=PromptCritique(summary="Zu vage."),
        bundles=[
            PromptBundle(
                variant=variant, profile_id=profile_id, main_prompt=f"{prompt} ({variant})"
            ).fill_meta(variant)
            for variant in ("precise", "cinematic", "experimental")
        ],
        duration_ms=1234,
    )


@pytest.fixture
def composed(client, monkeypatch):
    """Ein Lauf ueber die echte Route, aber ohne Modellserver."""

    def run(prompt: str = "eine praezise Fassung", **overrides) -> dict:
        async def fake_compose(request, settings, profile, provider, emit=None):
            return response_for(prompt, **overrides)

        monkeypatch.setattr("app.api.compose.compose", fake_compose)
        body = {**PAYLOAD, **{k: v for k, v in overrides.items() if k in PAYLOAD}}
        response = client.post("/api/compose", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    return run


# --- Automatisches Speichern ----------------------------------------------


def test_a_run_lands_in_the_library(client, composed):
    result = composed()
    assert result["library_id"] == 1
    assert result["library_error"] is None

    entry = client.get("/api/library/1").json()
    assert entry["mode"] == "improve"
    assert entry["variant_count"] == 3
    assert len(entry["bundles"]) == 3
    assert entry["critique"]["summary"] == "Zu vage."
    assert entry["input_prompt"] == "girl in alley, neon"
    assert entry["favorite"] is False


def test_one_entry_per_run_not_per_variant(client, composed):
    composed()
    composed("ein zweiter Lauf")
    page = client.get("/api/library").json()
    assert page["total"] == 2
    assert [item["variant_count"] for item in page["items"]] == [3, 3]


def test_disabled_library_stores_nothing(client, composed):
    current = client.get("/api/settings").json()
    current["library"]["enabled"] = False
    client.put("/api/settings", json=current)

    result = composed()
    assert result["library_id"] is None
    assert result["library_error"] is None
    assert client.get("/api/library").json()["total"] == 0


def test_storage_failure_does_not_destroy_the_result(client, composed, monkeypatch):
    """Ein Ergebnis, auf das der Nutzer gewartet hat, darf nicht an der Datenbank scheitern."""

    def boom(*args, **kwargs):
        raise OSError("Platte voll")

    monkeypatch.setattr("app.services.library.LibraryStore.remember", boom)
    result = composed()
    assert result["bundles"][0]["main_prompt"].startswith("eine praezise Fassung")
    assert result["library_id"] is None
    assert "Bibliothek" in result["library_error"]


def test_the_stream_route_saves_too(client, monkeypatch):
    async def fake_compose(request, settings, profile, provider, emit=None):
        return response_for("aus dem Strom")

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    body = client.post("/api/compose/stream", json=PAYLOAD).text
    assert '"library_id": 1' in body.replace("\n", " ") or '"library_id":1' in body
    assert client.get("/api/library/1").json()["title"] == "girl in alley, neon"


# --- Suche -----------------------------------------------------------------


def test_full_text_search_finds_the_prompt(client, composed):
    composed("ein Mann auf einem Dach bei Regen")
    composed("eine Frau im Sonnenlicht")

    hits = client.get("/api/library", params={"query": "dach bei regen"}).json()
    assert hits["total"] == 1
    assert "Dach" in hits["items"][0]["title"] or hits["items"][0]["id"] == 1


def test_search_covers_briefing_and_variants(client, composed):
    composed("Nachtaufnahme mit Neonreflexen")
    assert client.get("/api/library", params={"query": "NEONREFLEXEN"}).json()["total"] == 1
    assert client.get("/api/library", params={"query": "girl in alley"}).json()["total"] == 1
    assert client.get("/api/library", params={"query": "gibtsnicht"}).json()["total"] == 0


def test_filters_narrow_the_list(client, composed):
    composed("erster", profile_id="flux_image")
    composed("zweiter", profile_id="sdxl_tags")
    client.patch("/api/library/1", json={"favorite": True})

    assert client.get("/api/library", params={"favorite": True}).json()["total"] == 1
    assert client.get("/api/library", params={"profile_id": "sdxl_tags"}).json()["total"] == 1
    assert client.get("/api/library", params={"mode": "improve"}).json()["total"] == 2


def test_paging_reports_the_full_total(client, composed):
    for index in range(5):
        composed(f"lauf {index}")
    page = client.get("/api/library", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert [item["id"] for item in page["items"]] == [3, 2]


# --- Tags und Favorit ------------------------------------------------------


def test_tags_are_normalised(client, composed):
    composed()
    entry = client.patch(
        "/api/library/1", json={"tags": ["  Portrait ", "portrait", "NACHT", ""]}
    ).json()
    assert entry["tags"] == ["nacht", "portrait"]


def test_search_finds_a_tag(client, composed):
    composed()
    client.patch("/api/library/1", json={"tags": ["kundenprojekt"]})
    assert client.get("/api/library", params={"tag": "kundenprojekt"}).json()["total"] == 1
    assert client.get("/api/library", params={"query": "kundenproj"}).json()["total"] == 1


def test_empty_patch_is_rejected(client, composed):
    composed()
    response = client.patch("/api/library/1", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_patch_on_missing_entry_is_404(client):
    assert client.patch("/api/library/99", json={"favorite": True}).status_code == 404


def test_tag_helpers():
    assert normalise_tags(["A", "a", " b "]) == ["a", "b"]
    assert len(normalise_tags([str(index) for index in range(50)])) == 12
    assert derive_title("", "", []) == "ohne Text"
    assert derive_title("  mein   Briefing ", "x", []) == "mein Briefing"


# --- Löschen ---------------------------------------------------------------


def test_delete_single_entry(client, composed):
    composed()
    composed("zweiter")
    assert client.delete("/api/library/1").json() == {"deleted": 1}
    assert client.get("/api/library/1").status_code == 404
    assert client.get("/api/library").json()["total"] == 1


def test_clearing_needs_confirmation(client, composed):
    composed()
    assert client.delete("/api/library").status_code == 422
    assert client.get("/api/library").json()["total"] == 1
    assert client.delete("/api/library", params={"confirm": True}).json() == {"deleted": 1}
    assert client.get("/api/library").json()["total"] == 0


def test_pruning_keeps_favourites(client, composed):
    current = client.get("/api/settings").json()
    current["library"]["max_entries"] = 100
    client.put("/api/settings", json=current)

    composed("der wichtige")
    client.patch("/api/library/1", json={"favorite": True})
    for index in range(4):
        composed(f"weiterer {index}")

    library = get_library()
    library.prune(2)
    remaining = [item["id"] for item in client.get("/api/library").json()["items"]]
    assert 1 in remaining, "Favoriten dürfen nie weggeräumt werden"
    assert len(remaining) == 2


# --- Export ----------------------------------------------------------------


def test_text_export_is_readable(client, composed):
    composed("ein Mann auf einem Dach")
    client.patch("/api/library/1", json={"tags": ["nacht"], "favorite": True})

    response = client.post("/api/library/export", json={"ids": [1], "format": "txt"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert ".txt" in response.headers["content-disposition"]
    body = response.text
    assert "Hauptprompt" in body
    assert "ein Mann auf einem Dach (precise)" in body
    assert "Tags: nacht" in body
    assert "Favorit: ja" in body


def test_json_export_round_trips(client, composed):
    composed()
    composed("zweiter")
    body = client.post("/api/library/export", json={"format": "json"}).json()
    assert body["count"] == 2
    assert len(body["entries"][0]["bundles"]) == 3
    assert body["entries"][0]["id"] == 2


def test_csv_export_has_one_row_per_variant(client, composed):
    composed()
    text = client.post("/api/library/export", json={"ids": [1], "format": "csv"}).text
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[0].startswith("id;erstellt;modus")
    assert len(lines) == 4  # Kopfzeile plus drei Varianten


def test_export_without_entries_is_404(client):
    assert client.post("/api/library/export", json={"format": "txt"}).status_code == 404


# --- Referenz-Vorschaubilder ----------------------------------------------


def test_thumbnails_survive_the_upload_cleanup(client, monkeypatch, png_bytes):
    stored = client.post(
        "/api/images", files={"file": ("ref.png", png_bytes, "image/png")}
    ).json()

    async def fake_compose(request, settings, profile, provider, emit=None):
        return response_for("mit Referenz", mode="image")

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    result = client.post(
        "/api/compose",
        json={
            "mode": "image",
            "profile_id": "flux_image",
            "briefing": "eine Szene",
            "references": [{"id": stored["id"], "role": "subject"}],
        },
    ).json()
    assert result["library_id"] == 1

    entry = client.get("/api/library/1").json()
    assert entry["thumbs"] == [
        {"position": 0, "role": "subject", "url": "/api/library/1/thumb/0"}
    ]
    assert client.get("/api/library/1/thumb/0").status_code == 200

    # Die Uploads werden nach 24 Stunden aufgeraeumt - die Bibliothek nicht.
    for path in uploads_dir().glob("*.jpg"):
        path.unlink()
    cleanup_old(max_age_hours=0.0)
    assert client.get("/api/library/1/thumb/0").status_code == 200


def test_thumbnails_can_be_switched_off(client, monkeypatch, png_bytes):
    current = client.get("/api/settings").json()
    current["library"]["store_thumbnails"] = False
    client.put("/api/settings", json=current)

    stored = client.post(
        "/api/images", files={"file": ("ref.png", png_bytes, "image/png")}
    ).json()

    async def fake_compose(request, settings, profile, provider, emit=None):
        return response_for("ohne Vorschau", mode="image")

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    client.post(
        "/api/compose",
        json={
            "mode": "image",
            "profile_id": "flux_image",
            "briefing": "eine Szene",
            "references": [{"id": stored["id"], "role": "subject"}],
        },
    )
    assert client.get("/api/library/1").json()["thumbs"] == []
    assert client.get("/api/library/1/thumb/0").status_code == 404


def test_deleting_an_entry_removes_its_thumbnail_file(client, monkeypatch, png_bytes):
    from app.core.paths import thumbs_dir

    stored = client.post(
        "/api/images", files={"file": ("ref.png", png_bytes, "image/png")}
    ).json()

    async def fake_compose(request, settings, profile, provider, emit=None):
        return response_for("mit Referenz", mode="image")

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    client.post(
        "/api/compose",
        json={
            "mode": "image",
            "profile_id": "flux_image",
            "briefing": "eine Szene",
            "references": [{"id": stored["id"], "role": "subject"}],
        },
    )
    assert (thumbs_dir() / "1_0.jpg").is_file()
    client.delete("/api/library/1")
    assert not (thumbs_dir() / "1_0.jpg").is_file()


# --- Kennzahlen ------------------------------------------------------------


def test_stats_report_counts_and_tags(client, composed):
    composed()
    composed("zweiter")
    client.patch("/api/library/1", json={"favorite": True, "tags": ["nacht"]})
    stats = client.get("/api/library/stats").json()
    assert stats["count"] == 2
    assert stats["favorites"] == 1
    assert stats["tags"] == ["nacht"]
    assert stats["bytes_on_disk"] > 0


def test_payload_survives_a_restart(client, composed):
    """Der Store haelt nichts im Speicher - ein neuer Zugriff liest von der Platte."""
    composed("dauerhaft")
    get_library().invalidate()
    entry = client.get("/api/library/1").json()
    assert json.dumps(entry["bundles"])[:1] == "["
    assert entry["bundles"][2]["variant"] == "experimental"


# --- Import ----------------------------------------------------------------


def export_json(client) -> bytes:
    return client.post("/api/library/export", json={"format": "json"}).content


def test_export_and_import_round_trip(client, composed):
    composed("ein Mann auf einem Dach")
    client.patch("/api/library/1", json={"tags": ["nacht", "dach"], "favorite": True})
    backup = export_json(client)

    client.delete("/api/library", params={"confirm": True})
    assert client.get("/api/library").json()["total"] == 0

    result = client.post(
        "/api/library/import", files={"file": ("sicherung.json", backup, "application/json")}
    ).json()
    assert result["imported"] == 1
    assert result["skipped"] == 0
    assert "Vorschaubilder" in result["note"]

    entry = client.get("/api/library").json()["items"][0]
    assert entry["title"] == "girl in alley, neon"
    assert entry["favorite"] is True
    assert entry["tags"] == ["dach", "nacht"]

    full = client.get(f"/api/library/{entry['id']}").json()
    assert len(full["bundles"]) == 3
    assert full["bundles"][0]["main_prompt"].startswith("ein Mann auf einem Dach")
    assert full["critique"]["summary"] == "Zu vage."


def test_import_does_not_duplicate_what_is_already_there(client, composed):
    composed()
    backup = export_json(client)

    result = client.post(
        "/api/library/import", files={"file": ("sicherung.json", backup, "application/json")}
    ).json()
    assert result == {"imported": 0, "skipped": 1, "note": result["note"]}
    assert "schon vorhanden" in result["note"]
    assert client.get("/api/library").json()["total"] == 1


def test_imported_entries_are_searchable(client, composed):
    composed("Nachtaufnahme mit Neonreflexen")
    backup = export_json(client)
    client.delete("/api/library", params={"confirm": True})
    client.post("/api/library/import", files={"file": ("s.json", backup, "application/json")})

    assert client.get("/api/library", params={"query": "neonreflexen"}).json()["total"] == 1
    assert client.get("/api/library", params={"tag": "gibtsnicht"}).json()["total"] == 0


def test_import_rejects_something_that_is_not_a_backup(client):
    for payload in (b"kein json", b'{"was": "anderes"}', b"[]"):
        response = client.post(
            "/api/library/import", files={"file": ("x.json", payload, "application/json")}
        )
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "validation_error"


def test_import_keeps_the_readable_entries_and_counts_the_rest(client, composed):
    composed()
    backup = json.loads(export_json(client))
    backup["entries"].append({"id": 99, "kaputt": True})
    client.delete("/api/library", params={"confirm": True})

    result = client.post(
        "/api/library/import",
        files={"file": ("s.json", json.dumps(backup).encode(), "application/json")},
    ).json()
    assert result["imported"] == 1
    assert "nicht lesbar" in result["note"]


# --- Filter nach Videoquelle ----------------------------------------------


def video_run(client, monkeypatch, source: str, prompt: str) -> None:
    async def fake_compose(request, settings, profile, provider, emit=None):
        response = response_for(prompt, mode="video", profile_id="ltx23_i2v")
        response.video_source = source
        return response

    monkeypatch.setattr("app.api.compose.compose", fake_compose)
    assert (
        client.post(
            "/api/compose",
            json={
                "mode": "video",
                "video_source": source,
                "profile_id": "ltx23_i2v",
                "briefing": prompt,
            },
        ).status_code
        == 200
    )


def test_video_source_narrows_the_list(client, monkeypatch, composed):
    composed("ein Bildlauf")
    video_run(client, monkeypatch, "startframe", "sie dreht den Kopf")
    video_run(client, monkeypatch, "references", "sie laeuft durch den Regen")

    assert client.get("/api/library").json()["total"] == 3
    startframe = client.get("/api/library", params={"video_source": "startframe"}).json()
    assert startframe["total"] == 1
    assert startframe["items"][0]["title"] == "sie dreht den Kopf"

    references = client.get("/api/library", params={"video_source": "references"}).json()
    assert references["total"] == 1
    assert references["items"][0]["title"] == "sie laeuft durch den Regen"


def test_video_source_filter_never_shows_image_runs(client, monkeypatch, composed):
    """Bildlaeufe tragen den Standardwert der Spalte - der darf nicht mitgefiltert werden."""
    composed("nur ein Bildlauf")
    assert client.get("/api/library", params={"video_source": "startframe"}).json()["total"] == 0


def test_list_item_carries_the_video_source(client, monkeypatch):
    video_run(client, monkeypatch, "references", "eine Szene")
    entry = client.get("/api/library").json()["items"][0]
    assert entry["video_source"] == "references"
    assert entry["mode"] == "video"
