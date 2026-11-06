"""Derive and seal the 299M warm start from the verified 268M checkpoint."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from venom_core.services.functiongemma.profile import INITIAL_WEIGHT_FILES
from venom_core.services.granite_operator.contract import file_digest

ORIGINAL_PARAMS = 268_098_176
EXPANDED_PARAMS = 299_063_936
OLD_WIDTH = 2048
NEW_WIDTH = 2944


def hashes(weights: Path) -> dict[str, str]:
    files = {name: weights / name for name in sorted(INITIAL_WEIGHT_FILES)}
    if any(path.is_symlink() or not path.is_file() for path in files.values()):
        raise ValueError("missing or linked FunctionGemma weight file")
    return {name: file_digest(path) for name, path in files.items()}


def widen_channels(gate, up, down, width, initializer_range, generator):
    """Leave existing channels intact and zero the new output columns."""
    import torch

    old, hidden = gate.shape
    if up.shape != (old, hidden) or down.shape != (hidden, old) or width <= old:
        raise ValueError("incompatible MLP projection shapes")
    new = width - old

    def extend(matrix):
        extra = matrix.new_empty(new, hidden)
        extra.normal_(std=initializer_range, generator=generator)
        return torch.cat((matrix, extra), dim=0)

    return (
        extend(gate),
        extend(up),
        torch.cat((down, down.new_zeros(hidden, new)), dim=1),
    )


def expand(source: Path, receipt: Path, destination: Path) -> dict:
    """Write a fresh three-file warm start and return its source and output hashes."""
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    expected = json.loads(receipt.read_text())["files"]
    original = hashes(source)
    if original != expected:
        raise ValueError("source differs from checkpoint export receipt")
    config = json.loads((source / "config.json").read_text())
    shape = (
        config.get("architectures"),
        config.get("hidden_size"),
        config.get("num_hidden_layers"),
        config.get("intermediate_size"),
        config.get("tie_word_embeddings"),
    )
    if shape != (["Gemma3ForCausalLM"], 640, 18, OLD_WIDTH, True):
        raise ValueError("unexpected FunctionGemma source architecture")
    sigma = config["initializer_range"]
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("invalid initialization range")
    seed = 42
    generator = torch.Generator(device="cpu").manual_seed(seed)
    with safe_open(source / "model.safetensors", framework="pt") as reader:
        tensors = {name: reader.get_tensor(name) for name in reader.keys()}
        metadata = reader.metadata()
    if sum(tensor.numel() for tensor in tensors.values()) != ORIGINAL_PARAMS or {
        tensor.dtype for tensor in tensors.values()
    } != {torch.float32}:
        raise ValueError("unexpected source weights or precision")
    for layer in range(18):
        names = [
            f"model.layers.{layer}.mlp.{part}_proj.weight"
            for part in ("gate", "up", "down")
        ]
        values = widen_channels(
            *(tensors[name] for name in names), NEW_WIDTH, sigma, generator
        )
        tensors.update(zip(names, values, strict=True))
    if sum(tensor.numel() for tensor in tensors.values()) != EXPANDED_PARAMS:
        raise ValueError("unexpected parameter count after expansion")

    config["intermediate_size"] = NEW_WIDTH
    with TemporaryDirectory(
        dir=destination.parent, prefix="functiongemma-widen-"
    ) as temp:
        staging = Path(temp)
        save_file(tensors, staging / "model.safetensors", metadata=metadata)
        (staging / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        shutil.copyfile(
            source / "generation_config.json", staging / "generation_config.json"
        )
        expanded = hashes(staging)
        destination.mkdir()
        for name in expanded:
            (staging / name).replace(destination / name)

    return {
        "original": original,
        "expanded": expanded,
        "original_params": ORIGINAL_PARAMS,
        "expanded_params": EXPANDED_PARAMS,
        "width_before": OLD_WIDTH,
        "width_after": NEW_WIDTH,
        "expansion_seed": seed,
    }
