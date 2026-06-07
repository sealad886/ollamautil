from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from ollamautil.cli import main
from ollamautil.ollamautil import (
    CacheRef,
    ModelRef,
    OllamaUtilConfig,
    OllamaUtilError,
    _run_ollama_transfer,
    _build_remove_paths,
    _toggle_cache,
    build_copy_plan,
    build_ext_int_comb_filelist,
    build_remove_plan,
    copy_plan,
    get_curnow_cache,
    load_config,
    parse_model_ref,
    validate_blob_sha256,
)


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _blob_name(digest: str) -> str:
    return digest.replace(":", "-")


def _make_cache(root: Path) -> None:
    (root / "manifests").mkdir(parents=True)
    (root / "blobs").mkdir()


def _write_model(
    cache: Path,
    namespace: str = "library",
    model: str = "llama3",
    tag: str = "latest",
    config_blob: bytes = b"config",
    layer_blob: bytes = b"layer",
) -> ModelRef:
    config_digest = _digest(config_blob)
    layer_digest = _digest(layer_blob)
    for digest, content in ((config_digest, config_blob), (layer_digest, layer_blob)):
        (cache / "blobs" / _blob_name(digest)).write_bytes(content)
    manifest = {
        "config": {"digest": config_digest, "size": len(config_blob)},
        "layers": [{"digest": layer_digest, "size": len(layer_blob), "mediaType": "application/vnd.ollama.image"}],
    }
    manifest_path = cache / "manifests" / "registry.ollama.ai" / namespace / model / tag
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return ModelRef("registry.ollama.ai", namespace, model, tag)


@pytest.fixture()
def fake_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OllamaUtilConfig:
    internal = tmp_path / "internal"
    external = tmp_path / "external"
    home = tmp_path / "home"
    _make_cache(internal)
    _make_cache(external)
    (home / ".ollama").mkdir(parents=True)
    os.symlink(internal, home / ".ollama" / "models")
    monkeypatch.setenv("OLLAMAUTIL_INTERNAL_DIR", str(internal))
    monkeypatch.setenv("OLLAMAUTIL_EXTERNAL_DIR", str(external))
    monkeypatch.setenv("OLLAMAUTIL_HOME", str(home))
    monkeypatch.setenv("OLLAMAUTIL_FILE_IGNORE", '[".DS_Store"]')
    return load_config()


def test_load_config_uses_env_and_discovers_real_manifest(fake_config: OllamaUtilConfig) -> None:
    _write_model(fake_config.internal.path)
    external, internal, combined = build_ext_int_comb_filelist(fake_config)

    assert external == {}
    assert internal == {"library/llama3": ["latest"]}
    assert combined == [["library/llama3", [], ["latest"]]]
    assert get_curnow_cache(fake_config) == "internal"


def test_parse_model_ref_is_relative_to_manifest_root(fake_config: OllamaUtilConfig) -> None:
    ref = _write_model(fake_config.internal.path, namespace="sealad886", model="custom", tag="v1")
    manifest = fake_config.internal.manifests_dir / ref.manifest_relpath

    parsed = parse_model_ref(manifest, fake_config.internal.manifests_dir)

    assert parsed == ref
    assert parsed.table_key == "sealad886/custom"
    assert parsed.api_name == "sealad886/custom:v1"


def test_toggle_cache_replaces_symlink_atomically(fake_config: OllamaUtilConfig) -> None:
    result = _toggle_cache("external", config=fake_config, silent=True)

    assert result == "external"
    assert fake_config.models_link.is_symlink()
    assert fake_config.models_link.resolve(strict=True) == fake_config.external.path
    assert get_curnow_cache(fake_config) == "external"


def test_copy_plan_copies_manifest_and_blobs_with_checksum(fake_config: OllamaUtilConfig) -> None:
    ref = _write_model(fake_config.internal.path)
    plan = build_copy_plan([ref], fake_config.internal, fake_config.external)

    copy_plan(plan)

    assert (fake_config.external.manifests_dir / ref.manifest_relpath).exists()
    for item in plan.items:
        assert item.dest.exists()
        if item.expected_digest:
            validate_blob_sha256(str(item.dest), expected_digest=item.expected_digest)


def test_copy_plan_refuses_bad_blob_digest(fake_config: OllamaUtilConfig) -> None:
    ref = _write_model(fake_config.internal.path)
    bad_digest = _digest(b"wrong")
    manifest_path = fake_config.internal.manifests_dir / ref.manifest_relpath
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["layers"][0]["digest"] = bad_digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (fake_config.internal.blobs_dir / _blob_name(bad_digest)).write_bytes(b"not wrong")
    plan = build_copy_plan([ref], fake_config.internal, fake_config.external)

    with pytest.raises(OllamaUtilError, match="Digest mismatch"):
        copy_plan(plan)

    assert not (fake_config.external.blobs_dir / _blob_name(bad_digest)).exists()


def test_remove_plan_is_explicit_and_cache_scoped(fake_config: OllamaUtilConfig) -> None:
    ref = _write_model(fake_config.internal.path)
    selection = [["library", "llama3", "latest"]]

    plan = build_remove_plan(selection, ["internal", "external"], config=fake_config)

    assert plan == [(fake_config.internal, ref, fake_config.internal.manifests_dir / ref.manifest_relpath)]


def test_remove_paths_keep_blobs_referenced_by_other_manifests(fake_config: OllamaUtilConfig) -> None:
    ref = _write_model(fake_config.internal.path)
    shared_ref = _write_model(fake_config.internal.path, model="llama3-copy")
    plan = [(fake_config.internal, ref, fake_config.internal.manifests_dir / ref.manifest_relpath)]

    remove_paths = _build_remove_paths(plan)

    assert fake_config.internal.manifests_dir / ref.manifest_relpath in remove_paths
    assert fake_config.internal.manifests_dir / shared_ref.manifest_relpath not in remove_paths
    assert all(path.parent != fake_config.internal.blobs_dir for path in remove_paths)


def test_remove_paths_include_unreferenced_blobs(fake_config: OllamaUtilConfig) -> None:
    ref = _write_model(fake_config.internal.path, layer_blob=b"unique-layer")
    plan = [(fake_config.internal, ref, fake_config.internal.manifests_dir / ref.manifest_relpath)]

    remove_paths = _build_remove_paths(plan)

    assert fake_config.internal.manifests_dir / ref.manifest_relpath in remove_paths
    assert any(path.parent == fake_config.internal.blobs_dir for path in remove_paths)


def test_cli_list_json_uses_configured_dirs(fake_config: OllamaUtilConfig, capsys: pytest.CaptureFixture[str]) -> None:
    _write_model(fake_config.internal.path)

    assert main(["list", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["internal"] == {"library/llama3": ["latest"]}
    assert payload["external"] == {}
    assert payload["current_cache"] == "internal"


def test_ollama_transfer_consumes_streaming_progress(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    events = [
        {"status": "pulling manifest"},
        {"status": "downloading", "completed": 1, "total": 2},
        {"status": "success"},
    ]

    def fake_pull(model_name: str, stream: bool = False):
        assert model_name == "llama3:latest"
        assert stream is True
        return iter(events)

    monkeypatch.setattr("ollamautil.ollamautil.ollama.pull", fake_pull)

    _run_ollama_transfer("pull", ["llama3:latest"])

    out = capsys.readouterr().out
    assert "llama3:latest: pulling manifest" in out
    assert "llama3:latest: downloading 1/2" in out


def test_validate_config_rejects_missing_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    internal = tmp_path / "internal"
    external = tmp_path / "external"
    internal.mkdir()
    external.mkdir()
    monkeypatch.setenv("OLLAMAUTIL_INTERNAL_DIR", str(internal))
    monkeypatch.setenv("OLLAMAUTIL_EXTERNAL_DIR", str(external))

    with pytest.raises(OllamaUtilError, match="missing required directory"):
        load_config()
