from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

import ollama
from prettytable import PrettyTable
from tqdm import tqdm

CacheName = Literal["internal", "external"]
BLOB_PREFIX = "sha256-"


class OllamaUtilError(RuntimeError):
    """Raised for recoverable configuration or cache-operation errors."""


@dataclass(frozen=True)
class CacheRef:
    name: CacheName
    path: Path

    @property
    def manifests_dir(self) -> Path:
        return self.path / "manifests"

    @property
    def blobs_dir(self) -> Path:
        return self.path / "blobs"


@dataclass(frozen=True)
class OllamaUtilConfig:
    internal: CacheRef
    external: CacheRef
    file_ignore: tuple[str, ...] = (".DS_Store",)
    home_dir: Path = Path.home()

    @property
    def caches(self) -> tuple[CacheRef, CacheRef]:
        return (self.internal, self.external)

    @property
    def models_link(self) -> Path:
        return self.home_dir / ".ollama" / "models"

    def cache(self, name: CacheName) -> CacheRef:
        for cache in self.caches:
            if cache.name == name:
                return cache
        raise OllamaUtilError(f"Unknown cache: {name}")


@dataclass(frozen=True)
class ModelRef:
    registry: str
    namespace: str
    model: str
    tag: str

    @property
    def table_key(self) -> str:
        if self.registry == "registry.ollama.ai":
            return f"{self.namespace}/{self.model}"
        return f"{self.registry}/{self.namespace}/{self.model}"

    @property
    def api_name(self) -> str:
        if self.namespace == "library":
            return f"{self.model}:{self.tag}"
        return f"{self.namespace}/{self.model}:{self.tag}"

    @property
    def manifest_relpath(self) -> Path:
        return Path(self.registry) / self.namespace / self.model / self.tag


@dataclass(frozen=True)
class CopyItem:
    source: Path
    dest: Path
    expected_digest: str | None = None
    size: int = 0


@dataclass(frozen=True)
class CopyPlan:
    source_cache: CacheRef
    dest_cache: CacheRef
    models: tuple[ModelRef, ...]
    items: tuple[CopyItem, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.items)


def _parse_ignore(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return (".DS_Store",)
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return (".DS_Store",)
    if isinstance(parsed, str):
        return (parsed,)
    if isinstance(parsed, (list, tuple)) and all(isinstance(item, str) for item in parsed):
        return tuple(parsed)
    return (".DS_Store",)


def load_config(*, require_env: bool = True, validate: bool = True) -> OllamaUtilConfig:
    internal_raw = os.getenv("OLLAMAUTIL_INTERNAL_DIR")
    external_raw = os.getenv("OLLAMAUTIL_EXTERNAL_DIR")
    missing = [
        name
        for name, value in (
            ("OLLAMAUTIL_INTERNAL_DIR", internal_raw),
            ("OLLAMAUTIL_EXTERNAL_DIR", external_raw),
        )
        if not value
    ]
    if missing and require_env:
        raise OllamaUtilError(f"Missing required environment variable(s): {', '.join(missing)}")

    internal = Path(internal_raw or "").expanduser().resolve()
    external = Path(external_raw or "").expanduser().resolve()
    home = Path(os.getenv("OLLAMAUTIL_HOME", str(Path.home()))).expanduser().resolve()
    config = OllamaUtilConfig(
        internal=CacheRef("internal", internal),
        external=CacheRef("external", external),
        file_ignore=_parse_ignore(os.getenv("OLLAMAUTIL_FILE_IGNORE")),
        home_dir=home,
    )
    if validate:
        validate_config(config)
    return config


def validate_config(config: OllamaUtilConfig) -> None:
    for cache in config.caches:
        if not cache.path.exists():
            raise OllamaUtilError(f"{cache.name} cache does not exist: {cache.path}")
        if not cache.path.is_dir():
            raise OllamaUtilError(f"{cache.name} cache is not a directory: {cache.path}")
        for child in (cache.manifests_dir, cache.blobs_dir):
            if not child.exists():
                raise OllamaUtilError(f"{cache.name} cache missing required directory: {child}")
            if not child.is_dir():
                raise OllamaUtilError(f"{cache.name} cache child is not a directory: {child}")


def walk_dir(directory: str | Path, ignore: Iterable[str] | None = None) -> list[str]:
    root_path = Path(directory)
    ignored = set(ignore or load_config(validate=False).file_ignore)
    if not root_path.exists():
        return []

    files: list[str] = []
    for root, _, file_list in os.walk(root_path):
        for filename in file_list:
            if filename in ignored:
                continue
            file_path = Path(root) / filename
            if os.access(file_path, os.R_OK):
                files.append(str(file_path))
            else:
                print(f"User does not have access to {file_path}. Skipping...")
    return sorted(files)


def parse_model_ref(manifest_file: str | Path, manifests_root: str | Path) -> ModelRef:
    manifest_path = Path(manifest_file).resolve()
    root = Path(manifests_root).resolve()
    try:
        relative = manifest_path.relative_to(root)
    except ValueError as exc:
        raise OllamaUtilError(f"Manifest {manifest_path} is outside manifest root {root}") from exc

    parts = relative.parts
    if len(parts) < 4:
        raise OllamaUtilError(
            f"Manifest path must be registry/namespace/model/tag, got {relative}"
        )
    registry = parts[0]
    namespace = parts[1]
    model = "/".join(parts[2:-1])
    tag = parts[-1]
    if not all((registry, namespace, model, tag)):
        raise OllamaUtilError(f"Manifest path has empty component: {relative}")
    return ModelRef(registry=registry, namespace=namespace, model=model, tag=tag)


def _models_for_cache(cache: CacheRef, ignore: Iterable[str]) -> dict[str, list[str]]:
    models: dict[str, list[str]] = {}
    for manifest_file in walk_dir(cache.manifests_dir, ignore=ignore):
        try:
            ref = parse_model_ref(manifest_file, cache.manifests_dir)
        except OllamaUtilError as exc:
            print(f"Skipping malformed manifest path {manifest_file}: {exc}")
            continue
        models.setdefault(ref.table_key, []).append(ref.tag)
    return {key: sorted(set(tags)) for key, tags in sorted(models.items())}


def build_ext_int_comb_filelist(
    config: OllamaUtilConfig | None = None,
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[list[Any]]]:
    config = config or load_config()
    external_dict = _models_for_cache(config.external, config.file_ignore)
    internal_dict = _models_for_cache(config.internal, config.file_ignore)
    combined: list[list[Any]] = []
    for model_name in sorted(set(external_dict) | set(internal_dict)):
        combined.append(
            [
                model_name,
                external_dict.get(model_name, []),
                internal_dict.get(model_name, []),
            ]
        )
    return external_dict, internal_dict, combined


def _split_table_key(model_name: str) -> tuple[str, str]:
    parts = model_name.split("/")
    if len(parts) == 1:
        return "library", parts[0]
    return "/".join(parts[:-1]), parts[-1]


def get_models_table(combined: list[list[Any]], table: PrettyTable | None = None) -> PrettyTable:
    table = table or PrettyTable(
        ["Lib", "Model", "Tag", "External", "Internal"],
        title="Ollama GPTs Installed",
        left_padding_width=3,
        right_padding_width=2,
    )
    rows: list[list[str]] = []
    for model_name, external_tags, internal_tags in combined:
        lib, model = _split_table_key(model_name)
        for tag in sorted(set(external_tags + internal_tags)):
            rows.append(
                [
                    lib,
                    model,
                    tag,
                    "Yes" if tag in external_tags else "No",
                    "Yes" if tag in internal_tags else "No",
                ]
            )
    table.add_rows(sorted(rows, key=lambda row: (row[0], row[1], row[2])))
    table.add_autoindex("No.")
    return table


def get_curnow_cache(config: OllamaUtilConfig | None = None) -> CacheName | None:
    config = config or load_config()
    link = config.models_link
    if not link.exists() and not link.is_symlink():
        return None
    try:
        current_path = link.resolve(strict=True)
    except FileNotFoundError:
        return None
    for cache in config.caches:
        if current_path == cache.path:
            return cache.name
    return None


def display_models_table(
    combined: list[list[Any]],
    table: PrettyTable | None = None,
    config: OllamaUtilConfig | None = None,
) -> PrettyTable:
    table = get_models_table(combined, table=table) if table is None else table
    print(table)
    print(f"\nCurrent cache set to:    \033[4m{get_curnow_cache(config)}\033[0m")
    return table


def get_user_confirmation(prompt: str) -> bool:
    valid_responses = {"yes": True, "y": True, "no": False, "n": False}
    prompt = prompt.strip()
    while True:
        try:
            user_response = input(f"{prompt} (yes/no): ").lower()
        except EOFError:
            return False
        if user_response in valid_responses:
            return valid_responses[user_response]
        print("Invalid response. Please answer 'yes' or 'no'.")


def _atomic_symlink_replace(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temp_link = link.with_name(f".{link.name}.tmp-{os.getpid()}")
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
    os.symlink(target, temp_link)
    os.replace(temp_link, link)
    if link.resolve(strict=True) != target.resolve(strict=True):
        raise OllamaUtilError(f"Symlink verification failed: {link} -> {target}")


def _toggle_cache(
    toggle_target: CacheName | tuple[str, str] | CacheRef,
    *,
    config: OllamaUtilConfig | None = None,
    silent: bool = False,
) -> CacheName:
    config = config or load_config()
    target_name: CacheName
    if isinstance(toggle_target, CacheRef):
        target_name = toggle_target.name
    elif isinstance(toggle_target, tuple):
        target_name = toggle_target[0]  # type: ignore[assignment]
    else:
        target_name = toggle_target
    target = config.cache(target_name)
    validate_config(config)
    link = config.models_link
    if link.exists() and not link.is_symlink():
        raise OllamaUtilError(f"Refusing to replace non-symlink models path: {link}")
    _atomic_symlink_replace(link, target.path)
    if not silent:
        print(f"Changed .ollama/models symlink to {target.name.upper()} cache.")
    return target.name


def toggle_int_ext_cache(
    combined: list[list[Any]] | None = None,
    table: PrettyTable | None = None,
    *,
    config: OllamaUtilConfig | None = None,
) -> CacheName:
    config = config or load_config()
    current = get_curnow_cache(config)
    if current is None:
        raise OllamaUtilError(
            f"Current {config.models_link} target is not one of configured caches."
        )
    target: CacheName = "external" if current == "internal" else "internal"
    if combined is not None:
        display_models_table(combined, table=table, config=config)
    print(f"Current Ollama cache set to: {current.upper()}.")
    if get_user_confirmation(f"Swap symlink to {target.upper()} cache?"):
        return _toggle_cache(target, config=config)
    print(f"No changes made. Still using {current.upper()} cache.")
    return current


def _model_ref_from_table_selection(selection: list[str]) -> ModelRef:
    library, model, tag = selection[:3]
    if "/" in library:
        parts = library.split("/")
        registry = parts[0] if "." in parts[0] else "registry.ollama.ai"
        namespace = parts[-1] if registry != "registry.ollama.ai" else library
    else:
        registry = "registry.ollama.ai"
        namespace = library
    return ModelRef(registry=registry, namespace=namespace, model=model, tag=tag)


def select_models(
    table: PrettyTable,
    prompt: str | None = "",
    allow_multiples: bool = True,
    bypassGetAll: bool = False,
) -> list[list[str]]:
    print(table)
    base_prompt = (
        "Select model/tag items to act on using numbers (e.g. 1, 3, 12-15) or all"
        if prompt is None
        else prompt
    )
    while True:
        try:
            raw_input = "ALL" if bypassGetAll else input(f"{base_prompt}: ").strip()
        except EOFError:
            return []
        if raw_input == "":
            print("No model/tag option selected. Quitting...")
            return []
        if raw_input.upper() == "ALL":
            indexes = list(range(1, len(table._rows) + 1))
        else:
            indexes = _parse_selection_indexes(raw_input)
            if indexes is None:
                continue
        if not allow_multiples and len(indexes) > 1:
            print("Multiple selections are not allowed. Please select only one model.")
            continue
        selected: list[list[str]] = []
        for index in indexes:
            if index < 1 or index > len(table._rows):
                print(f"Selection out of range: {index}")
                selected = []
                break
            selected.append(list(table._rows[index - 1][1:-2]))
        if selected:
            return selected


def _parse_selection_indexes(raw_input: str) -> list[int] | None:
    indexes: list[int] = []
    for item in raw_input.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if "-" in item:
                start, end = [int(part.strip()) for part in item.split("-", 1)]
                if start > end:
                    raise ValueError
                indexes.extend(range(start, end + 1))
            else:
                indexes.append(int(item))
        except ValueError:
            print(f"Invalid selection: {raw_input}")
            return None
    return sorted(set(indexes))


def model_api_name_from_selection(selection: list[str]) -> str:
    library, model, tag = selection[:3]
    if library == "library":
        return f"{model}:{tag}"
    return f"{library}/{model}:{tag}"


def _iter_ollama_stream(result: Any) -> Iterator[dict[str, Any]]:
    if result is None:
        return
    if isinstance(result, dict):
        yield result
        return
    if isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
        for item in result:
            if isinstance(item, dict):
                yield item


def _run_ollama_transfer(action: Literal["pull", "push"], model_names: list[str]) -> None:
    api_func = ollama.pull if action == "pull" else ollama.push
    for model_name in model_names:
        print(f"{action.title()}ing {model_name}...")
        try:
            result = api_func(model_name, stream=True)
            for event in _iter_ollama_stream(result):
                status = event.get("status")
                completed = event.get("completed")
                total = event.get("total")
                if status:
                    if completed is not None and total:
                        print(f"{model_name}: {status} {completed}/{total}")
                    else:
                        print(f"{model_name}: {status}")
        except Exception as exc:  # noqa: BLE001 - keep CLI failure bounded.
            raise OllamaUtilError(f"{action} failed for {model_name}: {exc}") from exc


def pull_models(
    combined: list[list[Any]],
    table: PrettyTable | None = None,
    prompt: str | None = None,
    allow_multiples: bool = True,
) -> None:
    table = table or display_models_table(combined)
    selections = select_models(table, prompt=prompt, allow_multiples=allow_multiples)
    if not selections:
        return
    model_names = [model_api_name_from_selection(selection) for selection in selections]
    _run_ollama_transfer("pull", model_names)


def push_models(combined: list[list[Any]], table: PrettyTable | None = None) -> None:
    table = table or display_models_table(combined)
    selections = select_models(table)
    if not selections:
        return
    model_names = [model_api_name_from_selection(selection) for selection in selections]
    personal_models = [name for name in model_names if "/" in name.split(":", 1)[0]]
    skipped = sorted(set(model_names) - set(personal_models))
    for name in skipped:
        print(f"Skipping {name}: push requires a personal namespace.")
    if personal_models:
        _run_ollama_transfer("push", personal_models)


def _digest_to_blob_name(digest: str) -> str:
    return digest.replace(":", "-")


def _load_manifest(manifest_file: Path) -> dict[str, Any]:
    try:
        with manifest_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise OllamaUtilError(f"Invalid manifest JSON: {manifest_file}") from exc
    if not isinstance(data.get("config"), dict) or not isinstance(data.get("layers"), list):
        raise OllamaUtilError(f"Manifest missing config/layers: {manifest_file}")
    return data


def _manifest_digests(manifest_file: Path) -> list[str]:
    data = _load_manifest(manifest_file)
    digests = [data["config"].get("digest")]
    digests.extend(layer.get("digest") for layer in data["layers"] if isinstance(layer, dict))
    clean = [digest for digest in digests if isinstance(digest, str) and digest.startswith("sha256:")]
    if not clean:
        raise OllamaUtilError(f"Manifest has no sha256 digests: {manifest_file}")
    return clean


def build_copy_plan(
    model_refs: Iterable[ModelRef],
    source_cache: CacheRef,
    dest_cache: CacheRef,
    *,
    overwrite: bool = False,
) -> CopyPlan:
    items: list[CopyItem] = []
    refs = tuple(model_refs)
    for ref in refs:
        source_manifest = source_cache.manifests_dir / ref.manifest_relpath
        dest_manifest = dest_cache.manifests_dir / ref.manifest_relpath
        if not source_manifest.exists():
            raise OllamaUtilError(f"Source manifest missing: {source_manifest}")
        if overwrite or not dest_manifest.exists():
            items.append(CopyItem(source_manifest, dest_manifest, size=source_manifest.stat().st_size))
        for digest in _manifest_digests(source_manifest):
            blob_name = _digest_to_blob_name(digest)
            source_blob = source_cache.blobs_dir / blob_name
            dest_blob = dest_cache.blobs_dir / blob_name
            if not source_blob.exists():
                raise OllamaUtilError(f"Source blob missing: {source_blob}")
            if overwrite or not dest_blob.exists():
                items.append(
                    CopyItem(
                        source_blob,
                        dest_blob,
                        expected_digest=blob_name,
                        size=source_blob.stat().st_size,
                    )
                )
    return CopyPlan(source_cache=source_cache, dest_cache=dest_cache, models=refs, items=tuple(items))


def _sha256_blob_name(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{BLOB_PREFIX}{digest.hexdigest()}"


def _copy_one_atomic(item: CopyItem) -> None:
    item.dest.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = item.dest.with_name(f".{item.dest.name}.partial-{os.getpid()}")
    if temp_dest.exists():
        temp_dest.unlink()
    try:
        with item.source.open("rb") as src, temp_dest.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if item.expected_digest:
            actual = _sha256_blob_name(temp_dest)
            if actual != item.expected_digest:
                temp_dest.unlink(missing_ok=True)
                raise OllamaUtilError(
                    f"Digest mismatch for {item.source}: expected {item.expected_digest}, got {actual}"
                )
        shutil.copystat(item.source, temp_dest)
        os.replace(temp_dest, item.dest)
    finally:
        if temp_dest.exists():
            temp_dest.unlink()


def copy_plan(plan: CopyPlan, *, dry_run: bool = False) -> None:
    if dry_run:
        print(
            f"Would copy {len(plan.items)} files "
            f"({plan.total_bytes} bytes) from {plan.source_cache.name} to {plan.dest_cache.name}."
        )
        return
    with tqdm(
        total=plan.total_bytes,
        unit="B",
        unit_scale=True,
        desc="Copying cache files",
        dynamic_ncols=True,
    ) as progress:
        for item in plan.items:
            _copy_one_atomic(item)
            progress.update(item.size)


def migrate_cache(
    table: PrettyTable | None = None,
    combined: list[list[Any]] | None = None,
    selected_files: list[list[str]] | None = None,
    which_direction: str | None = None,
    bypassGetAll: bool = False,
    overwrite: bool = False,
    *,
    config: OllamaUtilConfig | None = None,
    dry_run: bool = False,
) -> None:
    config = config or load_config()
    if table is None:
        _, _, combined = build_ext_int_comb_filelist(config)
        table = display_models_table(combined, config=config)
    if selected_files is None or not selected_files:
        selected_files = select_models(table, None, True, bypassGetAll=bypassGetAll)
    if not selected_files:
        return
    if which_direction not in {"1", "2"}:
        raise OllamaUtilError("Copy direction must be '1' external->internal or '2' internal->external.")
    source = config.external if which_direction == "1" else config.internal
    dest = config.internal if which_direction == "1" else config.external
    refs = [_model_ref_from_table_selection(selection) for selection in selected_files]
    plan = build_copy_plan(refs, source, dest, overwrite=overwrite)
    copy_plan(plan, dry_run=dry_run)


def migrate_cache_user(table: PrettyTable | None, combined: list[list[Any]]) -> None:
    selected = select_models(table or get_models_table(combined), None, True, bypassGetAll=False)
    if not selected:
        print("No models selected. Quitting...")
        return
    try:
        which_direction = input("Move from:\n(1) external to internal\n(2) internal to external\n(1 or 2): ")
        overwrite = input("If the model already exists, should it be overwritten? (y/N): ").lower() in (
            "y",
            "yes",
        )
    except EOFError:
        return
    migrate_cache(
        table=table,
        combined=combined,
        selected_files=selected,
        overwrite=overwrite,
        which_direction=which_direction,
    )


def build_remove_plan(
    selections: Iterable[list[str]],
    cache_names: Iterable[CacheName],
    *,
    config: OllamaUtilConfig | None = None,
) -> list[tuple[CacheRef, ModelRef, Path]]:
    config = config or load_config()
    plan: list[tuple[CacheRef, ModelRef, Path]] = []
    for cache_name in cache_names:
        cache = config.cache(cache_name)
        for selection in selections:
            ref = _model_ref_from_table_selection(selection)
            manifest = cache.manifests_dir / ref.manifest_relpath
            if manifest.exists():
                plan.append((cache, ref, manifest))
    return plan


def _build_remove_paths(plan: list[tuple[CacheRef, ModelRef, Path]]) -> list[Path]:
    planned_manifests = {manifest.resolve() for _, _, manifest in plan}
    referenced_by_cache: dict[Path, set[str]] = {}
    planned_blobs: list[Path] = []
    planned_manifest_paths = [manifest for _, _, manifest in plan]

    for cache, _, manifest in plan:
        cache_key = cache.path.resolve()
        if cache_key not in referenced_by_cache:
            referenced: set[str] = set()
            for other_manifest in cache.manifests_dir.rglob("*"):
                if not other_manifest.is_file() or other_manifest.resolve() in planned_manifests:
                    continue
                try:
                    referenced.update(_digest_to_blob_name(digest) for digest in _manifest_digests(other_manifest))
                except OllamaUtilError:
                    continue
            referenced_by_cache[cache_key] = referenced
        for digest in _manifest_digests(manifest):
            blob_name = _digest_to_blob_name(digest)
            if blob_name not in referenced_by_cache[cache_key]:
                planned_blobs.append(cache.blobs_dir / blob_name)

    seen: set[Path] = set()
    remove_paths: list[Path] = []
    for path in planned_manifest_paths + planned_blobs:
        resolved = path.resolve() if path.exists() else path
        if resolved not in seen:
            seen.add(resolved)
            remove_paths.append(path)
    return remove_paths


def remove_from_cache(
    combined: list[list[Any]],
    table: PrettyTable | None,
    *,
    config: OllamaUtilConfig | None = None,
    dry_run: bool = False,
) -> None:
    config = config or load_config()
    table = table or get_models_table(combined)
    try:
        cache_choice = input(
            "Remove models from which cache? (q) exit, (1) internal, (2) external, (3) both? "
        ).strip()
    except EOFError:
        return
    cache_map: dict[str, tuple[CacheName, ...]] = {
        "1": ("internal",),
        "2": ("external",),
        "3": ("internal", "external"),
    }
    if cache_choice.lower() == "q":
        return
    if cache_choice not in cache_map:
        print("Invalid choice. Please try again.")
        return
    selected = select_models(table, "Select model/tag items to remove")
    if not selected:
        return
    plan = build_remove_plan(selected, cache_map[cache_choice], config=config)
    if not plan:
        print("No selected manifests exist in chosen cache(s).")
        return
    print("Remove plan:")
    for cache, ref, manifest in plan:
        print(f"  {cache.name}: {ref.api_name} ({manifest})")
    remove_paths = _build_remove_paths(plan)
    print(f"  files to remove: {len(remove_paths)}")
    if dry_run:
        return
    if not get_user_confirmation("This operation cannot be undone. Remove the above manifests?"):
        print("Removal canceled.")
        return
    for path in tqdm(remove_paths, desc="Removing cache files", unit="file"):
        path.unlink(missing_ok=True)
    print(f"Removed {len(remove_paths)} cache file(s).")


def validate_blob_sha256(dest_blob: str, blob_hash_prefix: str = BLOB_PREFIX, expected_digest: str = "") -> None:
    actual = _sha256_blob_name(Path(dest_blob))
    expected = expected_digest or actual
    if not expected.startswith(blob_hash_prefix):
        expected = f"{blob_hash_prefix}{expected}"
    if actual != expected:
        raise OllamaUtilError(f"Digest does not match for {dest_blob}. Expected {expected}, got {actual}.")
    print(f"Checksum verified: {dest_blob}")


def copy_metadata(src: str | Path, dst: str | Path) -> None:
    shutil.copystat(src, dst)


def copy_blob_files(
    source_file: str | Path,
    dest_file: str | Path,
    source_dir: str | Path,
    dest_dir: str | Path,
    overwrite: bool,
) -> None:
    manifest = Path(source_file)
    digests = _manifest_digests(manifest)
    items = [
        CopyItem(
            Path(source_dir) / "blobs" / _digest_to_blob_name(digest),
            Path(dest_dir) / "blobs" / _digest_to_blob_name(digest),
            expected_digest=_digest_to_blob_name(digest),
            size=(Path(source_dir) / "blobs" / _digest_to_blob_name(digest)).stat().st_size,
        )
        for digest in digests
        if overwrite or not (Path(dest_dir) / "blobs" / _digest_to_blob_name(digest)).exists()
    ]
    copy_plan(
        CopyPlan(
            source_cache=CacheRef("internal", Path(source_dir)),
            dest_cache=CacheRef("external", Path(dest_dir)),
            models=(),
            items=tuple(items),
        )
    )


def display_welcome() -> None:
    print("OllamaUtil")
