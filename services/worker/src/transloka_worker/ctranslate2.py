from __future__ import annotations

import json
import os
from dataclasses import dataclass

from transloka_translation.providers.nmt_model import model_manifest
from transloka_translation.providers.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    validate_ollama_base_url,
)

FALLBACK_MODEL_ENV = "TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL"


class CTranslate2ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CTranslate2Settings:
    fallback_model_name: str | None = None
    fallback_base_url: str | None = None

    def __post_init__(self) -> None:
        if self.fallback_model_name is None:
            if self.fallback_base_url is not None:
                raise CTranslate2ConfigurationError("The local fallback settings are invalid.")
            return
        if (
            type(self.fallback_model_name) is not str
            or not self.fallback_model_name.strip()
            or self.fallback_model_name != self.fallback_model_name.strip()
            or not self.fallback_model_name.isprintable()
            or len(self.fallback_model_name) > 200
            or self.fallback_base_url is None
        ):
            raise CTranslate2ConfigurationError("The local fallback settings are invalid.")
        try:
            normalized = validate_ollama_base_url(self.fallback_base_url)
        except (TypeError, ValueError):
            raise CTranslate2ConfigurationError("The local fallback endpoint is invalid.") from None
        if normalized != self.fallback_base_url:
            raise CTranslate2ConfigurationError("The local fallback endpoint is invalid.")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "transloka.ctranslate2.settings.v1",
            "provenance": model_manifest(),
            "generation": {
                "device": "cpu",
                "compute_type": "int8",
                "inter_threads": 1,
                "intra_threads": 4,
                "beam_size": 1,
                "retry_beam_size": 4,
                "max_source_tokens": 384,
                "max_input_length": 0,
                "max_decoding_length": 512,
                "batch_type": "tokens",
                "max_batch_size": 2048,
                "max_segments": 64,
                "max_source_characters": 100_000,
                "protected_span_version": "protected_span_v1",
                "suppress_digit_tokens": True,
            },
            "fallback": (
                {
                    "provider_type": "OLLAMA",
                    "model_name": self.fallback_model_name,
                    "base_url": self.fallback_base_url,
                    "temperature": 0.1,
                    "translation_timeout_seconds": 600.0,
                }
                if self.fallback_model_name is not None
                else None
            ),
        }

    @classmethod
    def from_payload(cls, value: object) -> CTranslate2Settings:
        if not isinstance(value, dict):
            raise CTranslate2ConfigurationError("The CTranslate2 snapshot is invalid.")
        fallback = value.get("fallback")
        if fallback is None:
            settings = cls()
        elif (
            isinstance(fallback, dict)
            and isinstance(fallback.get("model_name"), str)
            and isinstance(fallback.get("base_url"), str)
        ):
            settings = cls(fallback["model_name"], fallback["base_url"])
        else:
            raise CTranslate2ConfigurationError("The local fallback snapshot is invalid.")
        if json.dumps(value, sort_keys=True) != json.dumps(settings.to_payload(), sort_keys=True):
            raise CTranslate2ConfigurationError("The CTranslate2 snapshot is unsupported.")
        return settings


def ctranslate2_settings_from_environment() -> CTranslate2Settings:
    model_name = os.environ.get(FALLBACK_MODEL_ENV, "").strip()
    if not model_name:
        return CTranslate2Settings()
    try:
        base_url = validate_ollama_base_url(
            os.environ.get("TRANSLOKA_OLLAMA_URL", DEFAULT_OLLAMA_BASE_URL)
        )
    except ValueError:
        raise CTranslate2ConfigurationError("The local fallback endpoint is invalid.") from None
    return CTranslate2Settings(model_name, base_url)
