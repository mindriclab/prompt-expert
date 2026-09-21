from __future__ import annotations

import pytest

from app.models.aspect import aspect_phrase, contains_ratio, nearest_ratio, orientation_of
from app.models.compose import ComposeRequest
from app.models.reference import ReferenceInput
from app.prompts.composition import compose_messages, render_profile_block, render_reference_slots
from app.services.composer import BundleDraft, finalise_bundle
from app.services.profiles import ProfileRegistry

LABEL = "Präzise"


def profile(profile_id: str):
    return ProfileRegistry().get(profile_id)


def request_for(**overrides) -> ComposeRequest:
    base = {
        "mode": "image",
        "intent": "reproduce",
        "profile_id": "seedream_image",
        "briefing": "eine Gasse im Regen",
    }
    base.update(overrides)
    return ComposeRequest(**base)


# --- Seitenverhältnis --------------------------------------------------------


def test_orientation_and_phrase():
    assert orientation_of("4:5") == "portrait"
    assert orientation_of("16:9") == "landscape"
    assert orientation_of("1:1") == "square"
    assert aspect_phrase("4:5") == "portrait 4:5 aspect ratio"
    assert aspect_phrase("auto") == ""


def test_nearest_ratio_from_real_image_sizes():
    assert nearest_ratio(1024, 1280) == "4:5"
    assert nearest_ratio(1920, 1080) == "16:9"
    assert nearest_ratio(1000, 1000) == "1:1"
    assert nearest_ratio(1080, 1620) == "2:3"
    assert nearest_ratio(0, 100) == "auto"


def test_contains_ratio_tolerates_spacing():
    assert contains_ratio("portrait 4:5 aspect ratio", "4:5")
    assert contains_ratio("shot at 4 : 5", "4:5")
    assert not contains_ratio("a wet alley", "4:5")
    assert contains_ratio("anything", "auto")


def test_ratio_reaches_the_composer_when_the_target_uses_it():
    block = render_profile_block(profile("seedream_image"), "en", 420, "4:5")
    assert "portrait 4:5 aspect ratio" in block
    assert "Do not change it" in block


def test_ratio_is_marked_as_workflow_setting_otherwise():
    block = render_profile_block(profile("flux_image"), "en", 700, "4:5")
    assert "takes it from the workflow" in block
    assert "Do not write it into the prompt" in block


def test_no_ratio_line_when_auto():
    assert "aspect ratio" not in render_profile_block(profile("seedream_image"), "en", 420, "auto")


def test_missing_ratio_is_appended_not_merely_requested():
    draft = BundleDraft(main_prompt="A woman in a wet alley at night")
    bundle = finalise_bundle(draft, profile("seedream_image"), "precise", LABEL, "4:5")
    assert bundle.main_prompt.endswith("Portrait 4:5 aspect ratio.")
    assert bundle.main_prompt.count("4:5") == 1


def test_present_ratio_is_not_duplicated():
    draft = BundleDraft(main_prompt="A woman in a wet alley, portrait 4:5 aspect ratio.")
    bundle = finalise_bundle(draft, profile("seedream_image"), "precise", LABEL, "4:5")
    assert bundle.main_prompt.count("4:5") == 1


def test_ratio_is_not_forced_into_workflow_driven_targets():
    draft = BundleDraft(main_prompt="A woman in a wet alley at night")
    bundle = finalise_bundle(draft, profile("flux_image"), "precise", LABEL, "4:5")
    assert "4:5" not in bundle.main_prompt


def test_tag_profiles_get_the_ratio_as_a_tag_if_enabled():
    target = profile("sdxl_tags").model_copy(update={"aspect_ratio_in_prompt": True})
    bundle = finalise_bundle(
        BundleDraft(main_prompt="1girl, solo"), target, "precise", LABEL, "9:16"
    )
    assert bundle.main_prompt.endswith("portrait 9:16 aspect ratio")


def test_auto_leaves_the_prompt_untouched():
    draft = BundleDraft(main_prompt="A woman in a wet alley at night")
    bundle = finalise_bundle(draft, profile("seedream_image"), "precise", LABEL, "auto")
    assert bundle.main_prompt == "A woman in a wet alley at night"


def test_unknown_ratio_is_rejected():
    with pytest.raises(ValueError):
        request_for(aspect_ratio="7:13")


# --- Referenz-Slots ----------------------------------------------------------


def test_slot_block_lists_every_reference_with_its_role():
    references = [
        ReferenceInput(id="a" * 32, role="subject"),
        ReferenceInput(id="b" * 32, role="wardrobe"),
        ReferenceInput(id="c" * 32, role="environment"),
    ]
    block = render_reference_slots(references)
    assert "(Image 1) = subject" in block
    assert "(Image 2) = wardrobe" in block
    assert "(Image 3) = environment" in block
    assert "exclusively" in block
    assert "must appear at least once" in block


def test_slots_reach_the_composer_for_targets_that_understand_them():
    request = request_for(
        references=[
            ReferenceInput(id="a" * 32, role="subject"),
            ReferenceInput(id="b" * 32, role="wardrobe"),
        ]
    )
    user = compose_messages(request, profile("seedream_image"), "precise", 420)[1].content
    assert "REFERENCE SLOTS" in user
    assert "(Image 2) = wardrobe" in user


def test_slots_are_left_out_for_targets_that_do_not_use_them():
    request = request_for(
        profile_id="flux_image",
        references=[ReferenceInput(id="a" * 32, role="subject")],
    )
    user = compose_messages(request, profile("flux_image"), "precise", 700)[1].content
    assert "REFERENCE SLOTS" not in user


def test_no_slot_block_without_references():
    user = compose_messages(request_for(), profile("seedream_image"), "precise", 420)[1].content
    assert "REFERENCE SLOTS" not in user


def test_edit_and_gpt_image_also_carry_slots():
    for profile_id in ("edit_instruct", "gpt_image"):
        assert profile(profile_id).reference_slots is True


def test_only_reference_capable_video_profiles_carry_slots():
    # WAN 2.2 nimmt nur einen Startframe, die anderen beiden koennen Identitaets-Referenzen.
    assert profile("wan22_i2v").reference_slots is False
    for profile_id in ("ltx23_i2v", "minimax_video"):
        assert profile(profile_id).reference_slots is True


# --- Durchsetzung der Slots --------------------------------------------------


def two_references() -> list[ReferenceInput]:
    return [
        ReferenceInput(id="a" * 32, role="subject"),
        ReferenceInput(id="b" * 32, role="style"),
    ]


def test_missing_slots_are_appended_with_a_warning():
    draft = BundleDraft(main_prompt="A rowboat on calm water in a foggy forest")
    bundle = finalise_bundle(
        draft, profile("seedream_image"), "precise", LABEL, "auto", two_references()
    )
    assert "subject from (Image 1)" in bundle.main_prompt
    assert "style from (Image 2)" in bundle.main_prompt
    assert any("Referenz-Zuordnung fehlte" in w for w in bundle.warnings)


def test_present_slots_are_left_alone():
    draft = BundleDraft(
        main_prompt="A rowboat (Image 1) in the light of the forest (Image 2), early morning"
    )
    bundle = finalise_bundle(
        draft, profile("seedream_image"), "precise", LABEL, "auto", two_references()
    )
    assert "Reference use:" not in bundle.main_prompt
    assert bundle.warnings == []


def test_partial_slots_still_trigger_the_fallback():
    draft = BundleDraft(main_prompt="A rowboat (Image 1) in a foggy forest")
    bundle = finalise_bundle(
        draft, profile("seedream_image"), "precise", LABEL, "auto", two_references()
    )
    assert "style from (Image 2)" in bundle.main_prompt


def test_no_slot_fallback_for_targets_that_do_not_use_them():
    draft = BundleDraft(main_prompt="A rowboat on calm water")
    bundle = finalise_bundle(
        draft, profile("flux_image"), "precise", LABEL, "auto", two_references()
    )
    assert "Reference use:" not in bundle.main_prompt
    assert bundle.warnings == []


def test_closing_instruction_insists_on_markers():
    request = request_for(references=two_references())
    user = compose_messages(request, profile("seedream_image"), "precise", 420)[1].content
    assert "must carry its (Image N) marker" in user
    # Der Slot-Block steht am Ende, weil Modelle das Ende staerker gewichten.
    assert user.index("REFERENCE SLOTS") > user.index("TARGET PROFILE")


def test_seedream_no_longer_demands_scale_clauses_unconditionally():
    target = profile("seedream_image")
    assert not any("body scale tends to drift" in rule for rule in target.rules.must)
    assert any("no person is in the scene" in rule for rule in target.rules.avoid)
