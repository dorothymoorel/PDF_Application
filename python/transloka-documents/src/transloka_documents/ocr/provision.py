from __future__ import annotations

import argparse
import importlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .paddle import (
    _DETECTION_MODEL_DIRECTORY,
    _RECOGNITION_MODEL_DIRECTORY,
    _controlled_cache_dir,
    _validate_language,
    _validate_model_name,
)


class PaddleOCRProvisionError(RuntimeError):
    """Raised when an explicit local PaddleOCR model setup cannot complete."""


def provision_local_models(
    *,
    model_cache_dir: str | Path,
    model_name: str = "official_models",
    language: str = "en",
) -> Path:
    """Download the CPU OCR model bundle after an explicit setup action.

    Normal OCR execution never calls this function. PaddleOCR receives a
    controlled cache directory so the downloaded weights remain outside the
    repository and can be reused when the application is offline.
    """

    cache_dir = _controlled_cache_dir(model_cache_dir)
    bundle_name = _validate_model_name(model_name)
    normalized_language = _validate_language(language)
    bundle_dir = cache_dir / bundle_name
    if _has_required_models(bundle_dir):
        return bundle_dir

    cache_dir.mkdir(parents=True, exist_ok=True)
    with (
        _temporary_environment("PADDLE_PDX_CACHE_HOME", str(cache_dir)),
        _temporary_environment("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True"),
    ):
        try:
            paddleocr = importlib.import_module("paddleocr")
        except ImportError as exc:
            raise PaddleOCRProvisionError("The local PaddleOCR runtime is not installed.") from exc
        paddle_class = getattr(paddleocr, "PaddleOCR", None)
        if not callable(paddle_class):
            raise PaddleOCRProvisionError("The local PaddleOCR runtime is invalid.")
        try:
            paddle_class(
                lang=normalized_language,
                device="cpu",
                text_detection_model_name=_DETECTION_MODEL_DIRECTORY,
                text_recognition_model_name=_RECOGNITION_MODEL_DIRECTORY,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as exc:
            raise PaddleOCRProvisionError("The local PaddleOCR model download failed.") from exc

    if not _has_required_models(bundle_dir):
        raise PaddleOCRProvisionError("The local PaddleOCR model bundle is incomplete.")
    return bundle_dir


def _has_required_models(bundle_dir: Path) -> bool:
    return all(
        (bundle_dir / model_directory).is_dir()
        for model_directory in (_DETECTION_MODEL_DIRECTORY, _RECOGNITION_MODEL_DIRECTORY)
    )


@contextmanager
def _temporary_environment(name: str, value: str) -> Iterator[None]:
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision TransLoka's local PaddleOCR model bundle."
    )
    parser.add_argument("--model-cache-dir", required=True, type=Path)
    args = parser.parse_args()
    bundle_dir = provision_local_models(model_cache_dir=args.model_cache_dir)
    print(f"PaddleOCR models are ready at: {bundle_dir}")


if __name__ == "__main__":
    main()
