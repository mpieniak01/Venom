"""Frozen pilot recipes, separate from Gemma4 and its update budget."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

from venom_core.services.granite_operator.contract import digest

MODEL = "google/functiongemma-270m-it"
REVISION = "39eccb091651513a5dfb56892d3714c1b5b8276c"
LOCK = "requirements/locks/granite-operator-training-linux-py314.txt"
INITIAL_WEIGHT_FILES = frozenset(
    {"model.safetensors", "config.json", "generation_config.json"}
)
INITIAL_WEIGHTS_DIRECTORY = "warm-start"


@dataclass(frozen=True)
class Recipe:
    """Matched F1/L1 exposure; no quantization or silent precision fallback."""

    method: str = "full"
    model: str = MODEL
    revision: str = REVISION
    context: int = 1024
    epochs: int = 3
    batch_size: int = 4
    accumulation: int = 4
    learning_rate: float = 5e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.05
    seed: int = 42
    rank: int = 8
    alpha: int = 16
    dropout: float = 0.05
    max_new_tokens: int = 256
    initial_weights: dict[str, str] | None = None
    checkpoint_interval: int | None = None
    parameter_dtype: str | None = None
    retention_weight: float | None = None

    def validate(self) -> None:
        if self.model != MODEL or self.revision != REVISION:
            raise ValueError("functiongemma_base_mismatch")
        if (
            self.method not in {"full", "lora"}
            or type(self.context) is not int
            or self.context not in {1024, 2048}
        ):
            raise ValueError("functiongemma_recipe_unsupported")
        for key, upper in {
            "epochs": 3,
            "batch_size": 64,
            "accumulation": 64,
            "seed": 2**31 - 1,
            "rank": 64,
            "alpha": 256,
            "max_new_tokens": 512,
        }.items():
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError("functiongemma_integer_invalid:" + key)
        for key, upper in {
            "learning_rate": 0.001,
            "weight_decay": 1,
            "warmup_ratio": 0.5,
            "dropout": 0.5,
        }.items():
            value = getattr(self, key)
            if (
                type(value) not in {int, float}
                or not math.isfinite(value)
                or not 0 <= value <= upper
            ):
                raise ValueError("functiongemma_number_invalid:" + key)
        if self.learning_rate == 0:
            raise ValueError("functiongemma_learning_rate_zero")

        if self.parameter_dtype is not None and (
            self.parameter_dtype != "fp32" or self.method != "full"
        ):
            raise ValueError("functiongemma_parameter_dtype_unsupported")

        if self.initial_weights is not None:
            if (
                self.method != "full"
                or not isinstance(self.initial_weights, dict)
                or self.initial_weights.keys() != INITIAL_WEIGHT_FILES
                or any(
                    not isinstance(value, str)
                    or re.fullmatch(r"[a-f0-9]{64}", value) is None
                    for value in self.initial_weights.values()
                )
            ):
                raise ValueError("functiongemma_initial_weights_invalid")
        if self.retention_weight is not None and (
            type(self.retention_weight) not in {int, float}
            or not 0 < self.retention_weight <= 1
            or self.initial_weights is None
            or self.parameter_dtype != "fp32"
        ):
            raise ValueError("functiongemma_retention_weight_invalid")
        if self.checkpoint_interval is not None and (
            type(self.checkpoint_interval) is not int or self.checkpoint_interval < 1
        ):
            raise ValueError("functiongemma_checkpoint_interval_invalid")

    def identity(self) -> dict[str, Any]:
        self.validate()
        return {key: value for key, value in asdict(self).items() if value is not None}

    def budget(self, samples: int) -> dict[str, int]:
        self.validate()
        if type(samples) is not int or samples < 1:
            raise ValueError("functiongemma_empty_training_split")
        batches = math.ceil(samples / self.batch_size)
        updates = math.ceil(batches / self.accumulation)
        total = updates * self.epochs
        if self.checkpoint_interval is not None and total % self.checkpoint_interval:
            raise ValueError("functiongemma_checkpoint_interval_budget_mismatch")
        return {
            "samples": samples,
            "batches_per_epoch": batches,
            "updates_per_epoch": updates,
            "total_updates": total,
            "effective_batch_size": self.batch_size * self.accumulation,
        }

    @property
    def fingerprint(self) -> str:
        return digest(self.identity())
