"""Decision-level retention for the optional protected SFT objective."""

from __future__ import annotations

import math
from typing import Any

ACTIONS = ("read", "exists", "list", "clarify_read", "preview", "approval")


def targets_for(document: dict, recipe: Any) -> dict:
    """Validate qualified decision anchors against the encoded release and teacher weights."""
    if recipe.retention_weight is None:
        return {}
    data = document.get("retention")
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or data.get("actions") != list(ACTIONS)
        or data.get("teacher_weights") != recipe.initial_weights
        or not isinstance(data.get("targets"), dict)
        or not data["targets"]
    ):
        raise ValueError("functiongemma_retention_targets_invalid")
    targets = data["targets"]
    train = {row["record_id"]: row for row in document["records"]["train"]}
    for ident, target in targets.items():
        row = train.get(ident)
        if row is None or not isinstance(target, dict):
            raise ValueError("functiongemma_retention_anchor_invalid")
        suffixes = target.get("suffixes")
        scores = target.get("scores")
        start = row["assistant_token_spans"][0]["start"]
        if (
            target.get("sequence_sha256") != row["sequence_sha256"]
            or not isinstance(suffixes, list)
            or len(suffixes) != len(ACTIONS)
            or any(
                not isinstance(tokens, list)
                or not tokens
                or start + len(tokens) > recipe.context
                or any(
                    type(token) is not int or not 0 <= token < 262144
                    for token in tokens
                )
                for tokens in suffixes
            )
            or len({tuple(tokens) for tokens in suffixes}) != len(ACTIONS)
            or target.get("expected") not in {"read", "list"}
            or suffixes[ACTIONS.index(target["expected"])] != row["input_ids"][start:]
            or not isinstance(scores, list)
            or len(scores) != len(ACTIONS)
            or any(
                type(score) not in {int, float} or not math.isfinite(score)
                for score in scores
            )
        ):
            raise ValueError("functiongemma_retention_anchor_invalid")
    return targets


def smoke_rows(rows: list[dict], targets: dict | None) -> list[dict]:
    """Ensure the protected smoke and resume actually exercise the penalty."""
    return [row for row in rows if row["record_id"] in targets] if targets else rows


def action_scores(
    model: Any,
    prefix: list[int],
    suffixes: list[list[int]],
    *,
    pad_id: int,
    device: Any,
) -> Any:
    """Score six complete continuations from one prefix with one forward pass."""
    import torch

    width = max(map(len, suffixes))
    inputs = torch.tensor(
        [prefix + tokens + [pad_id] * (width - len(tokens)) for tokens in suffixes],
        device=device,
    )
    positions = torch.arange(width, device=device)
    lengths = torch.tensor(list(map(len, suffixes)), device=device)
    valid = positions.unsqueeze(0) < lengths.unsqueeze(1)
    mask = torch.cat(
        (
            torch.ones((len(suffixes), len(prefix)), dtype=torch.bool, device=device),
            valid,
        ),
        dim=1,
    )
    # The logits immediately before and within the answer predict its tokens.
    offsets = positions + len(prefix) - 1
    logits = model(
        input_ids=inputs, attention_mask=mask, use_cache=False, logits_to_keep=offsets
    ).logits
    log_probs = logits.float().log_softmax(dim=-1)
    selected = log_probs.gather(-1, inputs[:, len(prefix) :].unsqueeze(-1)).squeeze(-1)
    return selected.masked_fill(~valid, 0).sum(dim=-1) / lengths


def protected_trainer(
    trainer_cls: type, targets: dict, weight: float, pad_id: int
) -> type:
    """Extend the stock Trainer loss only for explicitly qualified anchors."""
    import torch
    from torch.nn.functional import kl_div

    class ProtectedTrainer(trainer_cls):  # type: ignore[misc, valid-type]
        def compute_loss(
            self, model, inputs, return_outputs=False, num_items_in_batch=None
        ):
            """Combine SFT loss with the teacher penalty for qualified training anchors."""
            anchors = inputs.pop("retention_anchors")
            loss, outputs = super().compute_loss(
                model,
                inputs,
                return_outputs=True,
                num_items_in_batch=num_items_in_batch,
            )
            if model.training and anchors:
                penalties = []
                for ident, prefix in anchors:
                    target = targets[ident]
                    scores = action_scores(
                        model,
                        prefix,
                        target["suffixes"],
                        pad_id=pad_id,
                        device=inputs["input_ids"].device,
                    )
                    teacher = torch.tensor(
                        target["scores"], dtype=torch.float32, device=scores.device
                    )
                    penalties.append(
                        kl_div(
                            scores.log_softmax(-1), teacher.softmax(-1), reduction="sum"
                        )
                    )
                penalty = torch.stack(penalties).mean()
                # The stock Trainer only divides microbatch losses in the unnormalized path.
                if self.model_accepts_loss_kwargs and num_items_in_batch is not None:
                    penalty = penalty / self.current_gradient_accumulation_steps
                loss = loss + weight * penalty
            return (loss, outputs) if return_outputs else loss

    return ProtectedTrainer
