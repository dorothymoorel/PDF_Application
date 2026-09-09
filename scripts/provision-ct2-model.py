"""Explicitly provision the pinned local EN→ID pilot; never called by the runtime."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

from transloka_translation.providers.nmt_model import (
    CONVERTER_VERSIONS,
    MODEL_HASHES,
    SOURCE_HASHES,
    SOURCE_MODEL,
    SOURCE_REVISION,
    model_manifest,
    safe_model_path,
    verify_files,
    verify_model_directory,
)


class HTTPSRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Request | None:
        if not newurl.startswith("https://"):
            raise ValueError("Model downloads cannot redirect away from HTTPS.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_sources(destination: Path) -> None:
    opener = build_opener(HTTPSRedirectHandler())
    for name, expected in SOURCE_HASHES.items():
        url = f"https://huggingface.co/{SOURCE_MODEL}/resolve/{SOURCE_REVISION}/{name}"
        limit = 300_000_000 if name == "pytorch_model.bin" else 2_000_000
        with opener.open(url, timeout=120) as response, (destination / name).open("xb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise ValueError(f"Source download exceeds the approved size limit: {name}")
                output.write(chunk)
        verify_files(destination, {name: expected})


def check_converter_versions() -> None:
    for package, expected in CONVERTER_VERSIONS.items():
        installed = importlib.metadata.version(package).split("+", 1)[0]
        if installed != expected:
            raise ValueError(f"Conversion requires {package}=={expected}, found {installed}.")


def convert_sources(source: Path, destination: Path) -> None:
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        DO_NOT_TRACK="1",
        TORCH_FORCE_WEIGHTS_ONLY_LOAD="1",
    )
    check_converter_versions()
    transformers_converter: Any = importlib.import_module(
        "ctranslate2.converters"
    ).TransformersConverter

    class OfflineConverter(transformers_converter):  # type: ignore[misc]
        def load_model(self, model_class: Any, model_name_or_path: str, **kwargs: Any) -> Any:
            return model_class.from_pretrained(
                model_name_or_path,
                **kwargs,
                local_files_only=True,
                trust_remote_code=False,
                weights_only=True,
                use_safetensors=False,
            )

        def load_tokenizer(
            self, tokenizer_class: Any, model_name_or_path: str, **kwargs: Any
        ) -> Any:
            return tokenizer_class.from_pretrained(
                model_name_or_path, **kwargs, local_files_only=True, trust_remote_code=False
            )

    OfflineConverter(str(source), trust_remote_code=False).convert(
        str(destination), quantization="int8"
    )
    for name in MODEL_HASHES.keys() & SOURCE_HASHES.keys() - {"config.json"}:
        shutil.copyfile(source / name, destination / name)
    verify_files(destination, MODEL_HASHES)
    (destination / "manifest.json").write_text(
        json.dumps(model_manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def provision(model_dir: Path, source_dir: Path | None, *, download: bool) -> Path:
    destination = safe_model_path(model_dir)
    if source_dir is not None:
        source_dir = safe_model_path(source_dir)
    if download == (source_dir is not None):
        raise ValueError("Choose exactly one of --download or --source-dir.")
    if destination.exists():
        return verify_model_directory(destination)
    check_converter_versions()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".transloka-ct2-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        source = staging / "source"
        source.mkdir()
        if download:
            download_sources(source)
        else:
            assert source_dir is not None
            verify_files(source_dir, SOURCE_HASHES)
            # Stage only pinned files; never load extra code or alternate weights from a cache.
            for name in SOURCE_HASHES:
                shutil.copyfile(source_dir / name, source / name)
            verify_files(source, SOURCE_HASHES)
        converted = staging / "model"
        convert_sources(source, converted)
        verify_model_directory(converted)
        if destination.exists():
            raise ValueError("Model destination appeared during conversion; refusing replacement.")
        converted.rename(destination)
    return verify_model_directory(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument(
        "--download", action="store_true", help="Download pinned public artifacts."
    )
    operation.add_argument("--source-dir", type=Path, help="Use an existing pinned source offline.")
    operation.add_argument(
        "--verify", action="store_true", help="Verify only; no downloads or imports."
    )
    args = parser.parse_args()
    try:
        directory = (
            verify_model_directory(args.model_dir)
            if args.verify
            else provision(args.model_dir, args.source_dir, download=args.download)
        )
    except (OSError, ValueError, ImportError, RuntimeError) as error:
        print(f"Model provisioning failed: {error}", file=sys.stderr)
        return 1
    print(f"Verified {directory}")
    print("Set TRANSLOKA_CT2_MODEL_DIR to this absolute path. Runtime inference is offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
