from __future__ import annotations

import importlib
import math
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from .base import (
    OCRGeometry,
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRProvider,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
)


@runtime_checkable
class PaddleOCRProvider(OCRProvider, Protocol):
    """Contract for an OCR provider backed by a local PaddleOCR adapter.

    The protocol intentionally contains no Paddle import. M9-T02 can provide
    the local implementation without coupling pipeline code to Paddle types.
    """


@runtime_checkable
class PaddleOCRBackend(Protocol):
    def health_check(self) -> OCRHealth: ...

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings,
    ) -> OCRResult: ...


class PaddleOCRModelMissingError(OCRProviderError):
    def __init__(self) -> None:
        super().__init__(
            OCRProviderErrorCode.PROVIDER_UNAVAILABLE,
            "The local PaddleOCR model is missing from the controlled cache.",
        )


class PaddleOCRUnavailableError(OCRProviderError):
    def __init__(self, message: str = "The local PaddleOCR provider is unavailable.") -> None:
        super().__init__(
            OCRProviderErrorCode.PROVIDER_UNAVAILABLE,
            message,
            retryable=True,
        )


class PaddleOCRProviderAdapter:
    """Local-only PaddleOCR adapter that implements the M9-T01 provider protocol.

    PaddleOCR is imported lazily so the document package remains usable when
    the optional local OCR runtime is not installed. A caller may inject a
    backend for tests or for a pre-configured local runtime.
    """

    def __init__(
        self,
        *,
        model_cache_dir: str | Path | None = None,
        model_name: str = "paddleocr",
        language: str = "en",
        backend: PaddleOCRBackend | None = None,
    ) -> None:
        self._model_cache_dir = _controlled_cache_dir(model_cache_dir)
        self._model_name = _validate_model_name(model_name)
        self._language = _validate_language(language)
        self._backend = backend

    @property
    def model_cache_dir(self) -> Path:
        return self._model_cache_dir

    @property
    def model_path(self) -> Path:
        return self._model_cache_dir / self._model_name

    @property
    def device(self) -> str:
        return "cpu"

    def health_check(self) -> OCRHealth:
        try:
            backend = self._get_backend()
            health = backend.health_check()
        except PaddleOCRModelMissingError as exc:
            return OCRHealth(
                status=OCRHealthStatus.UNAVAILABLE,
                provider="paddleocr",
                detail=str(exc),
            )
        except OCRProviderError as exc:
            return OCRHealth(
                status=OCRHealthStatus.UNAVAILABLE,
                provider="paddleocr",
                detail=str(exc),
            )
        except Exception as exc:
            return OCRHealth(
                status=OCRHealthStatus.UNAVAILABLE,
                provider="paddleocr",
                detail=f"PaddleOCR health check failed: {type(exc).__name__}.",
            )
        return OCRHealth(
            status=health.status,
            provider="paddleocr",
            version=health.version,
            detail=health.detail,
        )

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult:
        effective_settings = settings or OCRSettings(language=self._language)
        if effective_settings.language.casefold() != self._language.casefold():
            raise OCRProviderError(
                OCRProviderErrorCode.INVALID_REQUEST,
                "The PaddleOCR provider was initialized for a different language.",
            )
        backend = self._get_backend()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transloka-ocr")
        future = executor.submit(backend.analyze_page, page, settings=effective_settings)
        try:
            result = future.result(timeout=effective_settings.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise OCRProviderError(
                OCRProviderErrorCode.TIMEOUT,
                "The local PaddleOCR provider timed out.",
                retryable=True,
            ) from exc
        except OCRProviderError:
            raise
        except Exception as exc:
            raise OCRProviderError(
                OCRProviderErrorCode.OCR_FAILED,
                "The local PaddleOCR provider failed to analyze the page.",
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        _validate_result(result, page)
        return result

    def _get_backend(self) -> PaddleOCRBackend:
        if self._backend is not None:
            return self._backend
        if not self.model_path.exists():
            raise PaddleOCRModelMissingError

        try:
            paddleocr = importlib.import_module("paddleocr")
        except ImportError as exc:
            raise PaddleOCRUnavailableError(
                "The local PaddleOCR runtime is not installed."
            ) from exc
        paddle_class = getattr(paddleocr, "PaddleOCR", None)
        if not callable(paddle_class):
            raise PaddleOCRUnavailableError("The local PaddleOCR runtime is invalid.")

        engine = _create_paddle_engine(paddle_class, self.model_path, self._language)
        self._backend = _RuntimePaddleOCRBackend(engine)
        return self._backend


LocalPaddleOCRProvider = PaddleOCRProviderAdapter


class _RuntimePaddleOCRBackend:
    def __init__(self, engine: object) -> None:
        self._engine = engine

    def health_check(self) -> OCRHealth:
        return OCRHealth(
            status=OCRHealthStatus.AVAILABLE,
            provider="paddleocr",
            version=_runtime_version(self._engine),
        )

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings,
    ) -> OCRResult:
        raw = _run_paddle_engine(self._engine, page.image)
        return _parse_paddle_result(raw, page, settings)


def _controlled_cache_dir(value: str | Path | None) -> Path:
    raw = str(value) if value is not None else os.environ.get("TRANSLOKA_OCR_MODEL_CACHE")
    if raw is None:
        data_root = os.environ.get("TRANSLOKA_DATA_DIR")
        raw = str(Path(data_root) if data_root else Path.home() / "transloka-data")
        raw = str(Path(raw) / "cache" / "paddleocr")
    if "://" in raw:
        raise ValueError("PaddleOCR model cache must be a local filesystem path.")
    path = Path(raw).expanduser().resolve()
    if not path.name:
        raise ValueError("PaddleOCR model cache must not be a filesystem root.")
    return path


def _validate_model_name(value: str) -> str:
    candidate = value.strip()
    if not candidate or candidate in {".", ".."} or Path(candidate).name != candidate:
        raise ValueError("PaddleOCR model name must be a single local path component.")
    return candidate


def _validate_language(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("PaddleOCR language must not be empty.")
    return candidate


def _create_paddle_engine(paddle_class: Any, model_path: Path, language: str) -> object:
    options = {
        "lang": language,
        "device": "cpu",
        "model_dir": str(model_path),
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    try:
        return paddle_class(**options)
    except TypeError:
        try:
            return paddle_class(
                lang=language,
                device="cpu",
                model_dir=str(model_path),
                use_angle_cls=False,
            )
        except Exception as exc:
            raise PaddleOCRUnavailableError(
                "The local PaddleOCR model could not be loaded."
            ) from exc
    except Exception as exc:
        raise PaddleOCRUnavailableError("The local PaddleOCR model could not be loaded.") from exc


def _run_paddle_engine(engine: object, image: bytes) -> object:
    predict = getattr(engine, "predict", None)
    if callable(predict):
        try:
            return predict(input=image)
        except TypeError:
            return predict(image)
    ocr = getattr(engine, "ocr", None)
    if callable(ocr):
        return ocr(image, cls=False)
    raise PaddleOCRUnavailableError("The local PaddleOCR runtime has no page analysis method.")


def _parse_paddle_result(raw: object, page: OCRPage, settings: OCRSettings) -> OCRResult:
    blocks: list[OCRTextBlock] = []
    for payload in _payloads(raw):
        if isinstance(payload, Mapping) and "rec_texts" in payload:
            blocks.extend(_parse_v3_payload(payload))
        else:
            blocks.extend(_parse_legacy_payload(payload))
    confidence = sum(block.confidence for block in blocks) / len(blocks) if blocks else 0.0
    return OCRResult(
        page_number=page.page_number,
        text="\n".join(block.text for block in blocks),
        blocks=tuple(blocks),
        confidence=confidence,
        settings=settings,
        provider="paddleocr",
    )


def _payloads(raw: object) -> tuple[object, ...]:
    if isinstance(raw, Mapping):
        return (raw,)
    values = _items(raw)
    return values if values else (raw,)


def _parse_v3_payload(payload: Mapping[object, object]) -> list[OCRTextBlock]:
    texts = _items(payload.get("rec_texts"))
    scores = _items(payload.get("rec_scores"))
    boxes = _items(payload.get("rec_boxes"))
    blocks: list[OCRTextBlock] = []
    for index, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip() or index >= len(boxes):
            continue
        score = scores[index] if index < len(scores) else 0.0
        blocks.append(_block(text, boxes[index], score))
    return blocks


def _parse_legacy_payload(payload: object) -> list[OCRTextBlock]:
    if _looks_like_legacy_detection(payload):
        box, text_score = cast(Sequence[object], payload)
        text, score = cast(Sequence[object], text_score)
        if isinstance(text, str) and text.strip():
            return [_block(text, box, score)]
    blocks: list[OCRTextBlock] = []
    for child in _items(payload):
        blocks.extend(_parse_legacy_payload(child))
    return blocks


def _looks_like_legacy_detection(value: object) -> bool:
    items = _items(value)
    if len(items) != 2:
        return False
    text_score = _items(items[1])
    return len(text_score) == 2 and isinstance(text_score[0], str)


def _block(text: str, raw_box: object, raw_score: object) -> OCRTextBlock:
    score = float(raw_score) if isinstance(raw_score, int | float) else 0.0
    if not math.isfinite(score):
        score = 0.0
    return OCRTextBlock(
        text=text.strip(),
        geometry=_box_geometry(raw_box),
        confidence=max(0.0, min(1.0, score)),
    )


def _box_geometry(raw_box: object) -> OCRGeometry:
    values = _items(raw_box)
    numeric_values = [value for value in values if isinstance(value, int | float)]
    if len(values) == 4 and len(numeric_values) == 4:
        x0, y0, x1, y1 = (float(value) for value in numeric_values)
        return OCRGeometry(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
    points = [_items(point) for point in values]
    if not points or any(len(point) < 2 for point in points):
        raise OCRProviderError(
            OCRProviderErrorCode.INVALID_RESPONSE,
            "The PaddleOCR response contained invalid geometry.",
        )
    coordinates = [
        (float(point[0]), float(point[1]))
        for point in points
        if isinstance(point[0], int | float) and isinstance(point[1], int | float)
    ]
    if len(coordinates) != len(points):
        raise OCRProviderError(
            OCRProviderErrorCode.INVALID_RESPONSE,
            "The PaddleOCR response contained invalid geometry.",
        )
    x0 = min(point[0] for point in coordinates)
    y0 = min(point[1] for point in coordinates)
    x1 = max(point[0] for point in coordinates)
    y1 = max(point[1] for point in coordinates)
    return OCRGeometry(x=x0, y=y0, width=x1 - x0, height=y1 - y0)


def _items(value: object) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray)) or value is None:
        return ()
    if isinstance(value, Sequence):
        return tuple(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        converted = tolist()
        return _items(converted)
    return ()


def _validate_result(result: OCRResult, page: OCRPage) -> None:
    if result.page_number != page.page_number:
        raise OCRProviderError(
            OCRProviderErrorCode.INVALID_RESPONSE,
            "The PaddleOCR result page number does not match the request.",
        )
    for block in result.blocks:
        geometry = block.geometry
        if (
            geometry.x + geometry.width > page.width_px
            or geometry.y + geometry.height > page.height_px
        ):
            raise OCRProviderError(
                OCRProviderErrorCode.INVALID_RESPONSE,
                "The PaddleOCR result geometry exceeds the page bounds.",
            )


def _runtime_version(engine: object) -> str | None:
    version = getattr(engine, "__version__", None)
    return version if isinstance(version, str) and version.strip() else None
