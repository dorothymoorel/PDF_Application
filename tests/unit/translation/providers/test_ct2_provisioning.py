from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from urllib.request import Request

import pytest
from transloka_translation.providers import nmt_model

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "provision-ct2-model.py"


@pytest.fixture
def provisioner() -> Any:
    spec = importlib.util.spec_from_file_location("provision_ct2_model", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def model_files(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    files = {name: f"test {name}".encode() for name in nmt_model.MODEL_HASHES}
    monkeypatch.setattr(
        nmt_model,
        "MODEL_HASHES",
        {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    )
    return files


def write_model(directory: Path, files: dict[str, bytes]) -> Path:
    directory.mkdir()
    for name, data in files.items():
        (directory / name).write_bytes(data)
    (directory / "manifest.json").write_text(json.dumps(nmt_model.model_manifest()))
    return directory


@pytest.mark.parametrize("path", [Path("relative/model"), Path("/tmp/../model"), Path("/")])
def test_model_path_rejects_unsafe_locations(path: Path) -> None:
    with pytest.raises(ValueError, match="Model paths|dedicated model directory"):
        nmt_model.safe_model_path(path)


def test_model_path_rejects_home_and_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dedicated model directory"):
        nmt_model.safe_model_path(Path.home())
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").write_text("gitdir: /some/worktree")
    with pytest.raises(ValueError, match="outside Git repositories"):
        nmt_model.safe_model_path(repository / "models" / "pilot")


def test_model_path_rejects_symlink_into_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="outside Git repositories"):
        nmt_model.safe_model_path(alias / "model")


def test_model_path_rejects_repository_symlink_to_external_cache(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    alias = repository / "alias"
    alias.symlink_to(cache, target_is_directory=True)
    with pytest.raises(ValueError, match="outside Git repositories"):
        nmt_model.safe_model_path(alias / "model")


def test_manifest_and_checksums_are_required(tmp_path: Path, model_files: dict[str, bytes]) -> None:
    model = write_model(tmp_path / "model", model_files)
    assert nmt_model.verify_model_directory(model) == model
    manifest = model / "manifest.json"
    original = manifest.read_text()
    altered: dict[str, Any] = json.loads(original)
    altered["source_revision"] = "unapproved"
    manifest.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="approved revision"):
        nmt_model.verify_model_directory(model)
    manifest.write_text(original)
    (model / "model.bin").write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum mismatch: model.bin"):
        nmt_model.verify_model_directory(model)


@pytest.mark.parametrize("content", [b"{not json", b"\xff", b" " * 16_385])
def test_manifest_must_be_bounded_json(
    tmp_path: Path, model_files: dict[str, bytes], content: bytes
) -> None:
    model = write_model(tmp_path / "model", model_files)
    (model / "manifest.json").write_bytes(content)
    with pytest.raises(ValueError, match="manifest.json"):
        nmt_model.verify_model_directory(model)


@pytest.mark.parametrize("name", ["manifest.json", "model.bin", "source.spm"])
def test_model_rejects_symlink_files(
    tmp_path: Path, model_files: dict[str, bytes], name: str
) -> None:
    model = write_model(tmp_path / "model", model_files)
    outside = tmp_path / "outside"
    (model / name).rename(outside)
    (model / name).symlink_to(outside)
    with pytest.raises(ValueError, match="regular"):
        nmt_model.verify_model_directory(model)


def test_existing_verified_model_needs_no_converter_or_download(
    tmp_path: Path, model_files: dict[str, bytes], provisioner: Any
) -> None:
    model = write_model(tmp_path / "model", model_files)
    provisioner.check_converter_versions = Mock(side_effect=AssertionError("unexpected converter"))
    provisioner.download_sources = Mock(side_effect=AssertionError("unexpected network"))
    assert provisioner.provision(model, None, download=True) == model


def test_invalid_existing_model_is_not_overwritten(tmp_path: Path, provisioner: Any) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "keep").write_text("do not replace")
    with pytest.raises(ValueError, match="manifest.json"):
        provisioner.provision(model, None, download=True)
    assert (model / "keep").read_text() == "do not replace"


def test_offline_provision_stages_only_verified_inputs(
    tmp_path: Path, provisioner: Any, model_files: dict[str, bytes]
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "weights.bin").write_bytes(b"approved")
    (source / "custom_code.py").write_text("raise RuntimeError('must not load')")
    provisioner.SOURCE_HASHES = {"weights.bin": hashlib.sha256(b"approved").hexdigest()}
    provisioner.check_converter_versions = Mock()
    provisioner.download_sources = Mock(side_effect=AssertionError("unexpected network"))

    def convert(staged_source: Path, output: Path) -> None:
        assert set(path.name for path in staged_source.iterdir()) == {"weights.bin"}
        assert staged_source != source
        write_model(output, model_files)

    provisioner.convert_sources = Mock(side_effect=convert)
    model = tmp_path / "model"
    assert provisioner.provision(model, source, download=False) == model
    assert set(path.name for path in tmp_path.iterdir()) == {"source", "model"}
    assert (source / "custom_code.py").is_file()


def test_conversion_failure_leaves_no_partial_model(tmp_path: Path, provisioner: Any) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "weights.bin").write_bytes(b"approved")
    provisioner.SOURCE_HASHES = {"weights.bin": hashlib.sha256(b"approved").hexdigest()}
    provisioner.check_converter_versions = Mock()
    provisioner.convert_sources = Mock(side_effect=RuntimeError("conversion failed"))
    with pytest.raises(RuntimeError, match="conversion failed"):
        provisioner.provision(tmp_path / "model", source, download=False)
    assert list(tmp_path.iterdir()) == [source]


def test_unverified_source_never_reaches_converter(tmp_path: Path, provisioner: Any) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "weights.bin").write_bytes(b"unapproved")
    provisioner.SOURCE_HASHES = {"weights.bin": hashlib.sha256(b"approved").hexdigest()}
    provisioner.check_converter_versions = Mock()
    provisioner.convert_sources = Mock(side_effect=AssertionError("unverified conversion"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        provisioner.provision(tmp_path / "model", source, download=False)
    assert list(tmp_path.iterdir()) == [source]


def test_downloads_use_pinned_https_and_check_each_file(tmp_path: Path, provisioner: Any) -> None:
    approved = b"approved"
    provisioner.SOURCE_HASHES = {"first": hashlib.sha256(approved).hexdigest(), "second": "wrong"}
    opener = Mock()
    opener.open.side_effect = [io.BytesIO(approved), io.BytesIO(b"tampered")]
    provisioner.build_opener = Mock(return_value=opener)
    with pytest.raises(ValueError, match="checksum mismatch: second"):
        provisioner.download_sources(tmp_path)
    assert opener.open.call_count == 2
    for call, name in zip(opener.open.call_args_list, provisioner.SOURCE_HASHES, strict=True):
        assert call.args == (
            f"https://huggingface.co/{nmt_model.SOURCE_MODEL}/resolve/"
            f"{nmt_model.SOURCE_REVISION}/{name}",
        )
        assert call.kwargs == {"timeout": 120}


def test_download_failure_stops_before_next_file(tmp_path: Path, provisioner: Any) -> None:
    provisioner.SOURCE_HASHES = {"first": "wrong", "second": "wrong"}
    opener = Mock()
    opener.open.return_value = io.BytesIO(b"tampered")
    provisioner.build_opener = Mock(return_value=opener)
    with pytest.raises(ValueError, match="checksum mismatch: first"):
        provisioner.download_sources(tmp_path)
    assert opener.open.call_count == 1


def test_download_size_is_bounded(tmp_path: Path, provisioner: Any) -> None:
    provisioner.SOURCE_HASHES = {"source.spm": "unused"}
    opener = Mock()
    opener.open.return_value = io.BytesIO(b"x" * 2_000_001)
    provisioner.build_opener = Mock(return_value=opener)
    with pytest.raises(ValueError, match="size limit"):
        provisioner.download_sources(tmp_path)


def test_redirect_cannot_downgrade_https(provisioner: Any) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        provisioner.HTTPSRedirectHandler().redirect_request(
            Request("https://huggingface.co/model"),
            None,
            302,
            "Found",
            {},
            "http://example.com/file",
        )


def test_converter_version_mismatch_fails_before_import(
    provisioner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provisioner.importlib.metadata, "version", lambda package: "0.0.0")
    with pytest.raises(ValueError, match="Conversion requires ctranslate2==4.6.0"):
        provisioner.check_converter_versions()


def test_converter_accepts_cpu_build_version(
    provisioner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def version(package: str) -> str:
        value: str = nmt_model.CONVERTER_VERSIONS[package]
        return value + "+cpu" if package == "torch" else value

    monkeypatch.setattr(provisioner.importlib.metadata, "version", version)
    provisioner.check_converter_versions()


def test_conversion_forces_offline_safe_loading(
    tmp_path: Path, provisioner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "TORCH_FORCE_WEIGHTS_ONLY_LOAD": "1",
    }
    for name in environment:
        monkeypatch.setenv(name, "0")
    source = tmp_path / "source"
    source.mkdir()
    (source / "source.spm").write_bytes(b"tokenizer")
    (source / "config.json").write_bytes(b"source config")
    destination = tmp_path / "model"
    model_class = Mock()
    tokenizer_class = Mock()

    class Converter:
        def __init__(self, path: str, *, trust_remote_code: bool) -> None:
            assert path == str(source)
            assert trust_remote_code is False

        def convert(self, path: str, *, quantization: str) -> None:
            assert {name: os.environ[name] for name in environment} == environment
            assert path == str(destination)
            assert quantization == "int8"
            self.load_model(model_class, str(source), torch_dtype="float32")  # type: ignore[attr-defined]
            self.load_tokenizer(tokenizer_class, str(source))  # type: ignore[attr-defined]
            destination.mkdir()
            (destination / "config.json").write_bytes(b"CT2 config")

    provisioner.check_converter_versions = Mock()
    provisioner.importlib = SimpleNamespace(
        import_module=Mock(return_value=SimpleNamespace(TransformersConverter=Converter))
    )
    provisioner.SOURCE_HASHES = {"source.spm": "unused", "config.json": "unused"}
    provisioner.MODEL_HASHES = {
        "source.spm": hashlib.sha256(b"tokenizer").hexdigest(),
        "config.json": hashlib.sha256(b"CT2 config").hexdigest(),
    }
    provisioner.convert_sources(source, destination)
    provisioner.importlib.import_module.assert_called_once_with("ctranslate2.converters")
    model_class.from_pretrained.assert_called_once_with(
        str(source),
        torch_dtype="float32",
        local_files_only=True,
        trust_remote_code=False,
        weights_only=True,
        use_safetensors=False,
    )
    tokenizer_class.from_pretrained.assert_called_once_with(
        str(source), local_files_only=True, trust_remote_code=False
    )
    assert (destination / "source.spm").read_bytes() == b"tokenizer"
    assert (destination / "config.json").read_bytes() == b"CT2 config"
    assert json.loads((destination / "manifest.json").read_text()) == nmt_model.model_manifest()


def test_verify_cli_needs_no_site_packages(tmp_path: Path) -> None:
    package_source = SCRIPT.parents[1] / "python" / "transloka-translation" / "src"
    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "--model-dir", str(tmp_path / "missing"), "--verify"],
        env={**os.environ, "PYTHONPATH": str(package_source)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "A bounded, regular model manifest.json is required." in result.stderr
    assert "Traceback" not in result.stderr
