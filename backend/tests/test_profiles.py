from __future__ import annotations

import json

import pytest

from app.core.errors import AppError
from app.models.profile import LengthSpec, Profile
from app.services.profiles import ProfileRegistry

EXPECTED = {
    "flux_image",
    "sdxl_tags",
    "seedream_image",
    "gpt_image",
    "wan22_i2v",
    "ltx23_i2v",
    "minimax_video",
    "edit_instruct",
}


def test_all_shipped_profiles_load(client):
    body = client.get("/api/profiles").json()
    assert {p["id"] for p in body["profiles"]} == EXPECTED
    assert body["invalid"] == []


def test_ltx_profile_carries_audio_and_dialogue(client):
    profile = client.get("/api/profiles/ltx23_i2v").json()
    assert profile["kind"] == "video"
    # Ton und Dialog stehen im Block, nicht in eigenen Feldern.
    assert profile["fields"] == ["main_prompt", "negative_prompt"]
    assert any("one continuous block" in rule for rule in profile["rules"]["must"])
    assert any("Dialogue goes in quotation marks" in rule for rule in profile["rules"]["must"])
    # Zeitmarken sind auf diesem Setup belegt das funktionierende Format.
    assert any("[0-4 sec]" in rule for rule in profile["rules"]["must"])
    assert any("out-of-order time brackets" in rule for rule in profile["rules"]["avoid"])
    assert "[0-4 sec]" in profile["preferred_terms"]
    # main_prompt bleibt der vollstaendige Block, die Einzelfelder sind nur Auszuege.
    assert any("no separate motion, audio or camera fields" in r for r in profile["rules"]["must"])
    # Der Negativprompt unterdrueckt hier vor allem ungewollte Tonspuren.
    assert profile["negative_prompt"]["used"] is True
    assert {"music", "podcast", "non-english"} <= set(profile["negative_prompt"]["base"])


def test_tag_profile_uses_negative_prompt(client):
    profile = client.get("/api/profiles/sdxl_tags").json()
    assert profile["grammar"] == "tags"
    assert profile["negative_prompt"]["used"] is True
    assert "lowres" in profile["negative_prompt"]["base"]


def test_every_profile_bans_filler_phrases(client):
    for profile in client.get("/api/profiles").json()["profiles"]:
        banned = {phrase.lower() for phrase in profile["banned_phrases"]}
        assert "masterpiece" in banned, profile["id"]


def test_unknown_profile_returns_error_envelope(client):
    response = client.get("/api/profiles/gibtsnicht")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "profile_not_found"


def test_broken_profile_is_reported_not_swallowed(tmp_path):
    (tmp_path / "kaputt.json").write_text("{nope", encoding="utf-8")
    (tmp_path / "leer.json").write_text(json.dumps({"id": "leer"}), encoding="utf-8")
    registry = ProfileRegistry(tmp_path)
    assert registry.all() == []
    reported = {entry.file for entry in registry.invalid()}
    assert reported == {"kaputt.json", "leer.json"}


def test_id_must_match_filename(tmp_path):
    payload = json.loads((_profiles_path() / "flux_image.json").read_text(encoding="utf-8"))
    (tmp_path / "anderer_name.json").write_text(json.dumps(payload), encoding="utf-8")
    registry = ProfileRegistry(tmp_path)
    assert registry.all() == []
    assert "passt nicht zum Dateinamen" in registry.invalid()[0].error


def test_registry_get_raises_app_error(tmp_path):
    with pytest.raises(AppError) as excinfo:
        ProfileRegistry(tmp_path).get("flux_image")
    assert excinfo.value.code == "profile_not_found"


def test_reload_picks_up_changes(client):
    assert client.post("/api/profiles/reload").json()["invalid"] == []


def test_density_scales_length():
    spec = LengthSpec(target_chars=1000, max_chars=1400)
    assert spec.for_density("sparse") == 550
    assert spec.for_density("balanced") == 1000
    assert spec.for_density("detailed") == 1400  # durch max_chars gedeckelt


def test_image_profile_may_not_carry_motion():
    payload = json.loads((_profiles_path() / "flux_image.json").read_text(encoding="utf-8"))
    payload["fields"] = ["main_prompt", "motion_prompt"]
    with pytest.raises(ValueError, match="Motion"):
        Profile.model_validate(payload)


def test_negative_prompt_flag_and_field_must_agree():
    payload = json.loads((_profiles_path() / "sdxl_tags.json").read_text(encoding="utf-8"))
    payload["negative_prompt"]["used"] = False
    with pytest.raises(ValueError, match="negative_prompt"):
        Profile.model_validate(payload)


def _profiles_path():
    from app.core.paths import profiles_dir

    return profiles_dir()
