"""Regression tests for multi_runtime logits probe token decoding."""

from __future__ import annotations

import torch

from services.multi_runtime.main import _extract_logits_top


class _FakeTokenizer:
    def convert_ids_to_tokens(self, token_ids):
        return [f"TOK_{token_ids[0]}"]


def test_extract_logits_top_decodes_vocab_token_ids() -> None:
    logits = torch.tensor([0.1, 2.0, 1.5, -0.4], dtype=torch.float32)
    result = _extract_logits_top(
        logits_vector=logits,
        top_k=3,
        tokenizer=_FakeTokenizer(),
    )

    assert len(result) == 3
    assert result[0]["token_index"] == 1
    assert result[0]["token"] == "TOK_1"
    assert result[1]["token_index"] == 2
    assert result[1]["token"] == "TOK_2"
