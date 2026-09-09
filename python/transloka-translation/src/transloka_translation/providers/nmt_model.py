"""Pinned, dependency-free integrity checks for the opt-in OPUS-MT pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MODEL_ID = "opus-mt-en-id-ct2-int8"
SOURCE_MODEL = "Helsinki-NLP/opus-mt-en-id"
SOURCE_REVISION = "6e4c52d61a6b16fe3509b0267cbfec65011b860b"
CONVERTER_VERSIONS = {
    "ctranslate2": "4.6.0",
    "sentencepiece": "0.2.1",
    "torch": "2.8.0",
    "transformers": "4.56.2",
}
SOURCE_HASHES = {
    "config.json": "4d7c70eec8e533308818fdbe89db9c56a3163261aa0c07ccc8d1dca4c1e5bd9d",
    "generation_config.json": "d8826c233032ab2e70d024a30ba4de3af907f72d67ba79204f953b7f2e74ada5",
    "source.spm": "e88300911c2c573ec5526777a1e84bae698d20925b82dcef9c7248bb0e537ed0",
    "target.spm": "2a8fefe71c7f26cb0c6aa1b9f0cc0f8d18006b20fe41c547af7f25b9c8333465",
    "vocab.json": "efb902a7e49901c3dcdd4b2e079419a0b6ccead3fa2cabfc90820ce1ba66e157",
    "tokenizer_config.json": "1e1ea5d4fd5b329d2f4c9bec15f6c1e34cfbe7383b10f88fdff1db3508bd1e1f",
    "README.md": "b22576651af4091e2b7460f1a0a59b96ce24e2bbfeb4886941e7805d51db4a15",
    "pytorch_model.bin": "55cf1d883321cfd3bcfc43ce37fa842fc01690c7cb05afaff0fc9ca2df15f859",
}
MODEL_HASHES = {
    "config.json": "8f6496adfc930cbfecbe8281112197705c488fab47d34b4829b06d7f478909af",
    "shared_vocabulary.json": "847ee565009741a6334e25486f5d17606505d387ab8f631a2c3752e165433c96",
    "model.bin": "2b9dc8ce6b00b40a9f1b08457fe0c8abe83b116eb88be5049d26242a41624a1b",
    **{
        name: SOURCE_HASHES[name]
        for name in ("source.spm", "target.spm", "vocab.json", "tokenizer_config.json", "README.md")
    },
}


def safe_model_path(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts or path.anchor.startswith("\\\\"):
        raise ValueError("Model paths must be absolute local paths without traversal.")
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise ValueError("Use a dedicated model directory, not a filesystem or home root.")
    # Check both spellings: an in-repository symlink must not become a cache location.
    for candidate in (path, resolved):
        if any((parent / ".git").exists() for parent in (candidate, *candidate.parents)):
            raise ValueError("Model paths must be outside Git repositories.")
    return resolved


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_files(directory: Path, hashes: dict[str, str]) -> None:
    for name, expected in hashes.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Required regular model file is missing: {name}")
        if file_sha256(path) != expected:
            raise ValueError(f"Model checksum mismatch: {name}")


def model_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "source_model": SOURCE_MODEL,
        "source_revision": SOURCE_REVISION,
        "license": "Apache-2.0",
        "quantization": "int8",
        "converter_versions": CONVERTER_VERSIONS.copy(),
        "source_sha256": SOURCE_HASHES.copy(),
        "files": MODEL_HASHES.copy(),
    }


def verify_model_directory(path: Path) -> Path:
    directory = safe_model_path(path)
    manifest = directory / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 16_384:
        raise ValueError("A bounded, regular model manifest.json is required.")
    try:
        actual = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid model manifest.json.") from error
    if actual != model_manifest():
        raise ValueError("Model manifest does not match the approved revision and checksums.")
    verify_files(directory, MODEL_HASHES)
    return directory
