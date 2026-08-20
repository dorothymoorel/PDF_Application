import pytest
from transloka_reconstruction.settings import (
    ReconstructionMode,
    ReconstructionProfile,
    ReconstructionSettings,
)


def test_defaults_use_hybrid_and_documented_safe_values() -> None:
    settings = ReconstructionSettings()

    assert settings.mode is ReconstructionMode.HYBRID
    assert settings.profile is ReconstructionProfile.BALANCED
    assert settings.minimum_body_font_pt == 8.0
    assert settings.maximum_font_reduction_percent == 10.0
    assert settings.allow_page_addition is True
    assert settings.allow_single_column_fallback is False
    assert settings.allow_column_change is False
    assert settings.block_export_on_critical_errors is True
    assert settings.preserves_protected_content is True


def test_defaults_round_trip_through_json_mapping() -> None:
    settings = ReconstructionSettings()

    assert ReconstructionSettings.from_dict(settings.to_dict()) == settings


@pytest.mark.parametrize("minimum_font", [0, 5.99, 72.01])
def test_invalid_minimum_font_is_rejected(minimum_font: float) -> None:
    with pytest.raises(ValueError, match="minimum_body_font_pt"):
        ReconstructionSettings(minimum_body_font_pt=minimum_font)


def test_invalid_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="profile"):
        ReconstructionSettings.from_dict({"profile": "INVALID"})


def test_unsafe_overlay_settings_are_rejected() -> None:
    with pytest.raises(ValueError, match="OVERLAY"):
        ReconstructionSettings(mode=ReconstructionMode.OVERLAY, allow_column_change=True)

    with pytest.raises(ValueError, match="OVERLAY"):
        ReconstructionSettings(mode=ReconstructionMode.OVERLAY, allow_single_column_fallback=True)

    with pytest.raises(ValueError, match="PRESERVE_LAYOUT"):
        ReconstructionSettings(
            profile=ReconstructionProfile.PRESERVE_LAYOUT,
            allow_column_change=True,
        )


def test_profiles_cannot_disable_protected_content() -> None:
    for profile in ReconstructionProfile:
        settings = ReconstructionSettings(profile=profile)
        assert settings.preserves_protected_content is True


def test_unknown_setting_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown reconstruction setting"):
        ReconstructionSettings.from_dict({"profil": "BALANCED"})
