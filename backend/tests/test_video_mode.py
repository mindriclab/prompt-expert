from __future__ import annotations

import io
import json

import httpx
import pytest
import respx
from PIL import Image

from app.models.compose import ComposeRequest, variant_label
from app.models.reference import ReferenceInput
from app.models.settings import AppSettings, ModelSettings, ProviderSettings
from app.prompts.composition import compose_messages, render_profile_block
from app.prompts.vision import vision_messages
from app.providers.ollama import OllamaProvider
from app.services import images
from app.services.composer import BundleDraft, brief_set_for, compose, finalise_bundle
from app.services.motion_check import (
    check_camera,
    check_motion,
    check_subject_motion,
    check_timeline,
    parse_brackets,
    split_segments,
)
from app.services.profiles import ProfileRegistry

OLLAMA_URL = "http://127.0.0.1:11434"


def settings_for() -> AppSettings:
    return AppSettings(
        provider=ProviderSettings(base_url=OLLAMA_URL, connect_timeout_s=1.0),
        models=ModelSettings(text_model="textmodell", vision_model="visionmodell"),
    )


def provider() -> OllamaProvider:
    return OllamaProvider(settings_for().provider)


def profile(profile_id: str):
    return ProfileRegistry().get(profile_id)


def answer(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={"model": "m", "message": {"content": json.dumps(payload)}})


def upload() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 360), (40, 60, 90)).save(buffer, format="JPEG")
    return images.store_upload(buffer.getvalue(), "frame.jpg", settings_for().images).id


# --- Zeitfenster -------------------------------------------------------------


def test_brackets_are_parsed_including_open_end():
    text = "start [0-4 sec] a [4-6 sec] b [6-11 sec] c [11+ sec] d"
    assert parse_brackets(text) == [(0, 4), (4, 6), (6, 11), (11, None)]


def test_segments_split_at_the_brackets():
    segments = split_segments("intro [0-4 sec] erstes [4-6 sec] zweites")
    assert len(segments) == 2
    assert "erstes" in segments[0]
    assert "zweites" in segments[1]


def test_text_without_brackets_is_one_segment():
    assert split_segments("kein zeitfenster hier") == ["kein zeitfenster hier"]


def test_clean_timeline_produces_no_warning():
    text = "opening [0-4 sec] a [4-6 sec] b [6-11 sec] c [11+ sec] d"
    assert check_timeline(text, 12) == []


def test_gap_in_the_timeline_is_reported():
    warnings = check_timeline("[0-4 sec] a [6-11 sec] b", 12)
    assert any("Lücke" in w for w in warnings)


def test_overlapping_windows_are_reported():
    warnings = check_timeline("[0-6 sec] a [4-9 sec] b", 12)
    assert any("überlappen" in w for w in warnings)


def test_timeline_must_start_at_zero():
    assert any("beginnt bei 2 s" in w for w in check_timeline("[2-6 sec] a", 12))


def test_timeline_longer_than_the_clip_is_reported():
    warnings = check_timeline("[0-4 sec] a [4-18 sec] b", 5)
    assert any("Cliplänge" in w for w in warnings)


def test_clip_length_is_fine_when_it_fits():
    assert check_timeline("[0-3 sec] a [3-5 sec] b", 5) == []


# --- Kamerawidersprüche ------------------------------------------------------


def test_opposite_camera_moves_in_one_window_are_reported():
    warnings = check_camera("[0-5 sec] the camera pushes in while it also pulls back")
    assert any("Gegenläufige Kamerabewegung" in w for w in warnings)


def test_opposite_camera_moves_across_windows_are_fine():
    # Erst heranfahren, dann zurueckziehen ist voellig normal - kein Widerspruch.
    text = "[0-5 sec] the camera pushes in slowly [5-10 sec] the camera pulls back again"
    assert check_camera(text) == []


def test_pan_left_and_right_in_one_window_are_reported():
    assert any("Gegenläufige" in w for w in check_camera("the camera pans left and pans right"))


def test_static_and_moving_camera_in_one_window_are_reported():
    warnings = check_camera("[0-4 sec] a locked-off shot while the camera dollies in")
    assert any("feste und bewegte Kamera" in w for w in warnings)


def test_a_single_camera_move_is_not_flagged():
    assert check_camera("the camera pushes in slowly across the whole clip") == []


# --- Subjektbewegung ---------------------------------------------------------


def test_still_and_running_in_one_window_is_reported():
    warnings = check_subject_motion("[0-5 sec] she stands still while running across the lawn")
    assert any("Stillstand und Fortbewegung" in w for w in warnings)


def test_still_then_running_across_windows_is_fine():
    text = "[0-3 sec] she stands still [3-8 sec] she is running across the lawn"
    assert check_subject_motion(text) == []


def test_combined_check_deduplicates():
    text = "[0-5 sec] locked off but the camera pushes in and pulls back"
    warnings = check_motion(text, 12)
    assert len(warnings) == len(set(warnings))
    assert len(warnings) >= 2


# --- Verträge und Auftrag ----------------------------------------------------


def test_video_mode_needs_reference_or_briefing():
    with pytest.raises(ValueError, match="Referenzbild oder eine Beschreibung"):
        ComposeRequest(mode="video", profile_id="wan22_i2v")


def test_video_labels_follow_the_source_not_the_intent():
    assert variant_label("cinematic", "video", "reproduce", "startframe") == "Kompakt"
    assert variant_label("cinematic", "video", "reproduce", "references") == "Cinematic"
    # Die Absicht spielt im Videomodus keine Rolle mehr.
    assert variant_label("cinematic", "video", "inspire", "startframe") == "Kompakt"


def test_brief_set_follows_the_source():
    request = ComposeRequest(mode="video", profile_id="wan22_i2v", briefing="etwas")
    assert brief_set_for(request) == "video_startframe"
    with_refs = ComposeRequest(
        mode="video", profile_id="minimax_video", video_source="references", briefing="etwas"
    )
    assert brief_set_for(with_refs) == "video_reproduce"


def test_startframe_takes_at_most_one_image():
    with pytest.raises(ValueError, match="genau ein Bild"):
        ComposeRequest(
            mode="video",
            profile_id="wan22_i2v",
            references=[
                ReferenceInput(id="a" * 32, role="subject"),
                ReferenceInput(id="b" * 32, role="subject"),
            ],
        )


def test_reference_source_takes_several_images():
    request = ComposeRequest(
        mode="video",
        profile_id="minimax_video",
        video_source="references",
        references=[
            ReferenceInput(id="a" * 32, role="subject"),
            ReferenceInput(id="b" * 32, role="subject"),
        ],
    )
    assert len(request.references) == 2
    assert request.uses_startframe is False


def test_clip_length_is_a_user_setting_and_never_written_into_the_prompt():
    with_length = render_profile_block(profile("wan22_i2v"), "en", 900, "auto", True, 7)
    assert "about 7 seconds" in with_length
    assert "NEVER write the duration into the prompt text" in with_length

    without = render_profile_block(profile("wan22_i2v"), "en", 900, "auto", True, None)
    assert "not specified" in without
    assert "Do not mention any duration" in without


def test_shot_structure_is_carried_into_the_prompt():
    request = ComposeRequest(
        mode="video",
        profile_id="wan22_i2v",
        briefing="Shot 1: sie sitzt. Shot 2: er kommt herein. Shot 3: sie umarmen sich.",
    )
    user = compose_messages(request, profile("wan22_i2v"), "precise", 900)[1].content
    assert "SHOT STRUCTURE GIVEN BY THE USER" in user
    assert "split into 3 shots: Shot 1, Shot 2, Shot 3" in user
    assert "all 3 shots in the given order" in user


def test_no_shot_block_without_a_structure():
    request = ComposeRequest(
        mode="video", profile_id="wan22_i2v", briefing="sie kuesst ihn, Kamera faehrt heran"
    )
    user = compose_messages(request, profile("wan22_i2v"), "precise", 900)[1].content
    assert "SHOT STRUCTURE" not in user


def test_missing_shots_are_reported():
    draft = BundleDraft(
        main_prompt="Shot 1: she sits on the sofa. Shot 2: he walks in.",
        negative_prompt="blurry",
    )
    bundle = finalise_bundle(
        draft, profile("wan22_i2v"), "precise", "Detailliert", "auto", None, None,
        ["Shot 1", "Shot 2", "Shot 3"],
    )
    assert any("Shot 3" in w for w in bundle.warnings)


def test_camera_conflicts_across_shots_are_not_flagged():
    from app.services.motion_check import check_camera

    text = "Shot 1: the camera pushes in. Shot 2: the camera pulls back."
    assert check_camera(text) == []


def test_startframe_forbids_describing_the_image():
    from app.models.scene import SceneSpec

    request = ComposeRequest(
        mode="video",
        profile_id="wan22_i2v",
        references=[ReferenceInput(id="a" * 32, role="subject")],
    )
    user = compose_messages(
        request, profile("wan22_i2v"), "precise", 900, None, SceneSpec()
    )[1].content
    assert "FIRST FRAME IS ALREADY GIVEN" in user
    assert "Do NOT describe what is in it" in user
    assert "re-render the scene instead of animating it" in user
    assert "camera PATH only" in user
    assert "VARIANT: full motion" in user
    assert "no subject that is still and travelling at the same moment" in user
    # Die Schlussanweisung wiederholt das Verbot, weil Modelle das Ende staerker gewichten.
    assert "must contain no description of the first frame" in user


def test_startframe_explains_how_to_anchor_subjects():
    from app.models.scene import SceneSpec

    request = ComposeRequest(
        mode="video",
        profile_id="wan22_i2v",
        references=[ReferenceInput(id="a" * 32, role="subject")],
    )
    user = compose_messages(
        request, profile("wan22_i2v"), "precise", 900, None, SceneSpec()
    )[1].content
    assert "the blonde woman" in user
    assert "never a full description" in user


def test_reference_video_builds_the_scene_instead():
    from app.models.scene import SceneSpec

    request = ComposeRequest(
        mode="video",
        profile_id="minimax_video",
        video_source="references",
        references=[
            ReferenceInput(id="a" * 32, role="subject"),
            ReferenceInput(id="b" * 32, role="subject"),
        ],
        briefing="die beiden kuscheln auf einem Sofa",
    )
    user = compose_messages(
        request, profile("minimax_video"), "precise", 500, None, SceneSpec()
    )[1].content
    assert "FIRST FRAME IS ALREADY GIVEN" not in user
    assert "Build the scene from them" in user
    assert "REFERENCE SLOTS" in user
    assert "(Image 2) = subject" in user


def test_startframe_never_gets_reference_slots():
    from app.models.scene import SceneSpec

    request = ComposeRequest(
        mode="video",
        profile_id="minimax_video",
        references=[ReferenceInput(id="a" * 32, role="subject")],
    )
    user = compose_messages(
        request, profile("minimax_video"), "precise", 500, None, SceneSpec()
    )[1].content
    assert "REFERENCE SLOTS" not in user


def test_vision_for_startframe_asks_for_anchors_not_prose():
    messages = vision_messages(
        [ReferenceInput(id="a" * 32)], ["data:image/jpeg;base64,AAA"], "", "startframe", True
    )
    user = messages[1].content
    assert "first frame of a video and the generator already has it" in user
    assert "shortest distinguishing traits" in user
    assert "Do not invent what happens next" in user


def test_vision_for_reference_video_asks_for_a_full_description():
    messages = vision_messages(
        [ReferenceInput(id="a" * 32)], ["data:image/jpeg;base64,AAA"], "", "references", True
    )
    user = messages[1].content
    assert "There is no start frame" in user
    assert "rebuild them in a new scene" in user


def test_image_vision_call_has_no_frame_note():
    messages = vision_messages(
        [ReferenceInput(id="a" * 32)], ["data:image/jpeg;base64,AAA"], "", "reproduce", False
    )
    assert "first frame of a video" not in messages[1].content


# --- Warnungen im Ergebnis ---------------------------------------------------


def test_contradictions_surface_as_warnings_on_the_bundle():
    draft = BundleDraft(
        main_prompt=(
            "[0-4 sec] a locked-off shot while the camera pushes in and pulls back, "
            "she stands still while running toward the door"
        ),
        negative_prompt="blurry",
    )
    bundle = finalise_bundle(draft, profile("wan22_i2v"), "precise", "Detailliert")
    assert any("Gegenläufige Kamerabewegung" in w for w in bundle.warnings)
    assert any("feste und bewegte Kamera" in w for w in bundle.warnings)
    assert any("Stillstand und Fortbewegung" in w for w in bundle.warnings)


def test_clean_video_prompt_has_no_motion_warnings():
    draft = BundleDraft(
        main_prompt=(
            "A woman stands on a lawn, her hair lifts in the wind. "
            "The camera pushes in slowly."
        ),
    )
    bundle = finalise_bundle(draft, profile("wan22_i2v"), "precise", "Detailliert")
    assert bundle.warnings == []


def test_image_profiles_are_not_motion_checked():
    draft = BundleDraft(main_prompt="she stands still while running across the lawn")
    bundle = finalise_bundle(draft, profile("flux_image"), "precise", "Präzise")
    assert bundle.warnings == []


# --- Gesamtdurchlauf ---------------------------------------------------------


SCENE_WITH_MOTION = {
    "subjects": [
        {
            "role": "subject",
            "appearance": "woman in a red coat",
            "build": "",
            "hair": "dark, shoulder length",
            "face": "",
            "wardrobe": "red wool coat",
            "pose": "standing, facing camera",
            "expression": "calm",
            "explicit_detail": "",
            "continuity_features": ["red coat", "silver earrings"],
        }
    ],
    "scene": {"setting": "empty street", "time_of_day": "dusk", "atmosphere": "cold", "props": []},
    "visual": {
        "style": "documentary",
        "composition": "centred",
        "lighting": "soft overcast",
        "palette": ["grey", "red"],
        "materials": ["wet asphalt"],
    },
    "camera": {
        "shot": "medium",
        "lens": "35mm",
        "angle": "eye level",
        "focus": "on the face",
        "depth_of_field": "shallow",
    },
    "motion": {
        "subject_motion": "coat hem lifted by wind",
        "camera_motion": "",
        "beats": [],
        "physics_notes": "",
    },
    "uncertainties": [],
    "age_gate": {"clearly_adult": True, "reason": ""},
}

VIDEO_BUNDLE = {
    "main_prompt": "A woman in a red coat on an empty street. The camera pushes in slowly.",
    "negative_prompt": "blurry",
    "motion_prompt": "Her coat hem lifts in the wind, she turns her head toward the camera.",
    "camera_notes": "medium shot, 35mm, eye level",
    "rationale": ["Windbewegung aus der Referenz übernommen"],
    "warnings": [],
}


@respx.mock
async def test_video_run_requests_motion_and_composes():
    route = respx.post(f"{OLLAMA_URL}/api/chat").mock(
        side_effect=[
            answer(SCENE_WITH_MOTION),
            answer(VIDEO_BUNDLE),
            answer(VIDEO_BUNDLE),
            answer(VIDEO_BUNDLE),
        ]
    )
    request = ComposeRequest(
        mode="video",
        intent="reproduce",
        profile_id="wan22_i2v",
        references=[ReferenceInput(id=upload(), role="subject")],
        briefing="Sie dreht den Kopf zur Kamera, leichter Wind.",
    )

    result = await compose(request, settings_for(), profile("wan22_i2v"), provider())

    assert route.call_count == 4
    assert result.scene is not None
    assert result.scene.motion is not None
    assert result.scene.motion.subject_motion == "coat hem lifted by wind"
    assert [b.variant_label for b in result.bundles] == [
        "Detailliert",
        "Kompakt",
        "Anders formuliert",
    ]
    # Alles steckt im Hauptprompt, es gibt keine Einzelfelder mehr.
    assert result.bundles[0].motion_prompt is None
    assert result.bundles[0].camera_notes is None

    vision_call = httpx.Response(200, content=route.calls[0].request.content).json()
    assert "motion" in vision_call["format"]["properties"]
    assert vision_call["model"] == "visionmodell"


@respx.mock
async def test_image_run_does_not_request_motion():
    route = respx.post(f"{OLLAMA_URL}/api/chat").mock(
        side_effect=[answer(SCENE_WITH_MOTION), answer({"main_prompt": "x", "camera_notes": "y",
                                                        "rationale": [], "warnings": []})]
    )
    request = ComposeRequest(
        mode="image",
        profile_id="flux_image",
        references=[ReferenceInput(id=upload(), role="subject")],
        variants=["precise"],
    )
    await compose(request, settings_for(), profile("flux_image"), provider())
    vision_call = httpx.Response(200, content=route.calls[0].request.content).json()
    assert "motion" not in vision_call["format"]["properties"]


def test_startframe_never_gets_the_slot_fallback():
    """Der Marker (Image 1) darf im Startframe-Prompt nicht auftauchen."""
    draft = BundleDraft(main_prompt="The boat rocks gently. Slow push in.")
    bundle = finalise_bundle(
        draft, profile("minimax_video"), "precise", "Detailliert", "auto", None
    )
    assert "Reference use" not in bundle.main_prompt
    assert "(Image 1)" not in bundle.main_prompt


def test_video_main_prompt_is_declared_as_one_block():
    block = render_profile_block(profile("minimax_video"), "en", 500, "auto", False)
    assert "one block, ready to paste" in block
    assert "single prompt field" in block


def test_startframe_forbids_describing_the_frame_in_the_field_hint():
    block = render_profile_block(profile("minimax_video"), "en", 500, "auto", True)
    assert "No description of the frame itself" in block
    assert "camera path, sound, dialogue" in block
