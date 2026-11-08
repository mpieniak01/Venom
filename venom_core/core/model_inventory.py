"""Read-only evidence of installed model payloads; never import inference engines."""

import json
import re
from pathlib import Path


def nonempty_file(path: Path) -> bool:
    """Return whether an accessible regular file has a nonzero payload."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def is_onnx_model_dir(path: Path) -> bool:
    """Require at least one nonempty ONNX payload in an existing directory."""
    return path.is_dir() and any(nonempty_file(p) for p in path.glob("*.onnx"))


def is_hf_model_dir(path: Path) -> bool:
    """Require valid model configuration, real weights and complete indexed or named shards."""
    if not path.is_dir() or not nonempty_file(path / "config.json"):
        return False
    try:
        if not isinstance(json.loads((path / "config.json").read_text()), dict):
            return False
    except (ValueError, OSError):
        return False
    if not all(_valid_weight_index(path, index) for index in path.glob("*.index.json")):
        return False
    weights = [
        *path.glob("*.safetensors"),
        *path.glob("pytorch_model*.bin"),
        *path.glob("model*.bin"),
    ]
    return (
        bool(weights)
        and all(nonempty_file(p) for p in weights)
        and _complete_shards(path, weights)
    )


def _valid_weight_index(path: Path, index: Path) -> bool:
    """Require a nonempty shard map referencing existing weights without path traversal."""
    try:
        weight_map = json.loads(index.read_text())["weight_map"]
        if not isinstance(weight_map, dict):
            return False
        names = set(weight_map.values())
        return bool(names) and all(
            isinstance(name, str)
            and not Path(name).is_absolute()
            and ".." not in Path(name).parts
            and nonempty_file(path / name)
            for name in names
        )
    except (ValueError, KeyError, TypeError, OSError):
        return False


def _complete_shards(path: Path, weights: list[Path]) -> bool:
    """Require every numbered shard declared by each sharded weight filename."""
    for weight in weights:
        shard = re.fullmatch(r"(.+)-(\d+)-of-(\d+)\.(safetensors|bin)", weight.name)
        if shard is None:
            continue
        prefix, number, count, extension = shard.groups()
        if not all(
            nonempty_file(
                path / f"{prefix}-{part:0{len(number)}d}-of-{count}.{extension}"
            )
            for part in range(1, int(count) + 1)
        ):
            return False
    return True


def manifest_size(manifest: Path) -> int:
    """Return the size of one complete installed Ollama variant."""
    root = next(
        parent
        for parent in manifest.parents
        if parent.name in {"manifests", "manifests-v2"}
    )
    blob_root = (root.parent / "blobs").resolve()
    if root.name == "manifests-v2" and manifest.is_symlink():
        target = manifest.resolve(strict=True)
        if target.parent != blob_root or not re.fullmatch(
            r"sha256-[0-9a-f]{64}", target.name
        ):
            return 0
    payload = json.loads(manifest.read_text())
    if payload.get("mediaType") != "application/vnd.ollama.manifest.list.v2+json":
        return _manifest_layer_size(payload, blob_root)

    for variant in payload.get("manifests", []):
        if not isinstance(variant, dict):
            continue
        digest = variant.get("digest", "")
        if not isinstance(digest, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", digest
        ):
            continue
        child = blob_root / digest.replace(":", "-")
        try:
            if (
                child.is_symlink()
                or not child.is_file()
                or child.stat().st_size > 8 * 1024**2
            ):
                continue
            size = _manifest_layer_size(json.loads(child.read_text()), blob_root)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if size:
            return size
    return 0


def _manifest_layer_size(payload: dict, blob_root: Path) -> int:
    layers = payload.get("layers", [])
    if not any(
        layer.get("mediaType") == "application/vnd.ollama.image.model"
        for layer in layers
    ):
        return 0
    total = 0
    for entry in [payload.get("config", {}), *layers]:
        digest, size = entry.get("digest", ""), entry.get("size")
        if (
            not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or not isinstance(size, int)
            or size < 0
        ):
            return 0
        blob = blob_root / digest.replace(":", "-")
        if not blob.is_file() or blob.stat().st_size != size:
            return 0
        total += size
    return total


def cached_model_paths(roots: list[Path]):
    """Only actual HF snapshots, with aliases/revisions deduplicated by resolved path."""
    seen = set()
    for root in roots:
        for snapshot in root.glob("models--*/snapshots/*"):
            if snapshot.resolve() in seen or not is_hf_model_dir(snapshot):
                continue
            seen.add(snapshot.resolve())
            name = snapshot.parent.parent.name.removeprefix("models--").replace(
                "--", "/", 1
            )
            yield name, snapshot
