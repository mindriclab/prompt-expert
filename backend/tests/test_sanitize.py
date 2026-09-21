from __future__ import annotations

from app.models.compose import VARIANT_LABELS
from app.models.profile import Profile
from app.services.composer import BundleDraft, _merge_negative_base, finalise_bundle
from app.services.profiles import ProfileRegistry
from app.services.sanitize import (
    enforce_max_chars,
    normalise_tags,
    strip_banned_phrases,
    strip_decoration,
)

LABELS = VARIANT_LABELS["default"]


def profile(profile_id: str) -> Profile:
    return ProfileRegistry().get(profile_id)


def test_strip_decoration_removes_model_habits():
    assert strip_decoration("**Prompt:** a wet street") == "a wet street"
    assert strip_decoration("Main prompt: a wet street") == "a wet street"
    assert strip_decoration("```json\na wet street\n```") == "a wet street"
    assert strip_decoration('"a wet street"') == "a wet street"
    assert strip_decoration("### Output:\na wet street") == "a wet street"


def test_strip_decoration_keeps_real_content():
    text = "A prompt engineer walks into a bar. The lighting is hard and low."
    assert strip_decoration(text) == text


def test_banned_phrases_are_removed_and_reported():
    text = "masterpiece, a wet neon alley, best quality, 85mm lens"
    cleaned, removed = strip_banned_phrases(text, ["masterpiece", "best quality", "8k"])
    assert "masterpiece" not in cleaned.lower()
    assert "best quality" not in cleaned.lower()
    assert removed == ["masterpiece", "best quality"]
    assert cleaned == "a wet neon alley, 85mm lens"


def test_banned_phrases_respect_word_boundaries():
    cleaned, removed = strip_banned_phrases("a masterpiece-level grip", ["masterpiece"])
    assert removed == []
    assert cleaned == "a masterpiece-level grip"


def test_max_chars_cuts_at_sentence_boundary():
    text = "One sentence here. Second sentence here. Third sentence that overflows badly."
    cut, trimmed = enforce_max_chars(text, 45, "prose")
    assert trimmed is True
    assert cut == "One sentence here. Second sentence here."
    assert len(cut) <= 45


def test_max_chars_leaves_short_text_alone():
    assert enforce_max_chars("short", 100, "prose") == ("short", False)


def test_tags_are_normalised():
    assert normalise_tags("1Girl, Solo , solo,\nwet skin") == "1girl, solo, wet skin"


def test_negative_base_is_merged_without_duplicates():
    merged = _merge_negative_base("blurry, extra fingers", ["lowres", "Blurry"])
    assert merged == "blurry, extra fingers, lowres"


def test_finalise_drops_fields_the_profile_does_not_use():
    draft = BundleDraft(
        main_prompt="a wet neon alley, 85mm lens",
        motion_prompt="camera pushes in",
        negative_prompt="blurry",
        rationale=["Licht konkretisiert"],
    )
    bundle = finalise_bundle(draft, profile("flux_image"), "precise", LABELS["precise"])
    assert bundle.motion_prompt is None  # flux_image ist ein Bildprofil
    assert bundle.negative_prompt is None  # FLUX nutzt keinen Negativprompt
    assert bundle.camera_notes is None
    assert bundle.rationale == ["Licht konkretisiert"]
    assert bundle.variant_label == "Präzise"
    assert bundle.char_count == len(bundle.main_prompt)


def test_finalise_enforces_negative_base_for_tag_profile():
    draft = BundleDraft(main_prompt="1girl, solo", negative_prompt="watermark")
    bundle = finalise_bundle(draft, profile("sdxl_tags"), "cinematic", LABELS["cinematic"])
    assert bundle.negative_prompt is not None
    assert "watermark" in bundle.negative_prompt
    assert "lowres" in bundle.negative_prompt
    assert bundle.negative_prompt.count("watermark") == 1


def test_finalise_warns_about_removed_filler():
    draft = BundleDraft(main_prompt="masterpiece, 1girl, solo, best quality")
    bundle = finalise_bundle(draft, profile("sdxl_tags"), "precise", LABELS["precise"])
    assert "masterpiece" not in bundle.main_prompt
    assert any("Füllphrasen entfernt" in w for w in bundle.warnings)


def test_finalise_warns_when_truncated():
    long_text = "a very long sentence about light. " * 200
    draft = BundleDraft(main_prompt=long_text)
    target = profile("flux_image")
    bundle = finalise_bundle(draft, target, "precise", LABELS["precise"])
    assert len(bundle.main_prompt) <= target.length.max_chars
    assert any("gekürzt" in w for w in bundle.warnings)


def test_finalise_warns_on_empty_main_prompt():
    bundle = finalise_bundle(
        BundleDraft(main_prompt="   "), profile("flux_image"), "precise", LABELS["precise"]
    )
    assert bundle.main_prompt == ""
    assert any("keinen Hauptprompt" in w for w in bundle.warnings)
