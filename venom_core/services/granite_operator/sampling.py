"""Versioned, proportional epoch ordering without consuming model RNG state."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from fractions import Fraction

from .contract import digest


class FamilyEpochOrder:
    """Visit each row once per epoch; interleave families without oversampling."""

    policy = "family_epoch_v1"

    def __init__(self, families: list[str], seed: int):
        if (
            not families
            or any(not isinstance(f, str) or not f.strip() for f in families)
            or type(seed) is not int
            or seed < 1
        ):
            raise ValueError("granite_sampling_input_invalid")
        self.families = tuple(families)
        self.seed = seed
        self.epoch = -1
        self.order: list[int] = []

    def identity(self, samples_seen: int) -> dict:
        """Bind row groups and absolute position to the resumable checkpoint."""
        if type(samples_seen) is not int or samples_seen < 0:
            raise ValueError("granite_sampling_position_invalid")
        return {
            "policy": self.policy,
            "seed": self.seed,
            "rows": len(self.families),
            "families_sha256": digest(self.families),
            "samples_seen": samples_seen,
        }

    def _key(self, epoch: int, value: str) -> bytes:
        return hashlib.sha256(f"{self.seed}:{epoch}:{value}".encode()).digest()

    def _epoch_order(self, epoch: int) -> list[int]:
        buckets: dict[str, list[int]] = defaultdict(list)
        for index, family in enumerate(self.families):
            buckets[family].append(index)
        ranked = []
        for family, indices in buckets.items():
            indices.sort(key=lambda i: self._key(epoch, f"row:{i}"))
            for ordinal, index in enumerate(indices):
                # Exact rational spacing keeps small families distributed too.
                ranked.append(
                    (
                        Fraction(2 * ordinal + 1, 2 * len(indices)),
                        self._key(epoch, "family:" + family),
                        index,
                    )
                )
        return [index for _, _, index in sorted(ranked)]

    def index(self, position: int) -> int:
        """Address a row directly from the global consumed-sample position."""
        if type(position) is not int or position < 0:
            raise ValueError("granite_sampling_position_invalid")
        epoch, offset = divmod(position, len(self.families))
        if epoch != self.epoch:
            self.order = self._epoch_order(epoch)
            self.epoch = epoch
        return self.order[offset]
