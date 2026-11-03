"""Native prefix matching and last-assistant-only loss with a CPU double."""

import json

import pytest

from venom_core.services.functiongemma.encoding import (
    encode_decision,
    encode_release,
    validate_encoded_release,
)
from venom_core.services.gemma4_operator.material import digest


class Tokenizer:
    chat_template = "native-test-template"

    def __len__(self):
        return 1000000

    def apply_chat_template(self, messages, **kwargs):
        result = ""
        for message in messages:
            body = message.get("content", "") or ""
            if message.get("tool_calls"):
                body = json.dumps(message["tool_calls"], sort_keys=True)
            if not isinstance(body, str):
                body = json.dumps(body, sort_keys=True)
            result += (
                "<start_of_turn>" + message["role"] + "\n" + body + "<end_of_turn>"
            )
        if kwargs["add_generation_prompt"]:
            result += "<start_of_turn>assistant\n"
        return result

    def __call__(self, text, **kwargs):
        assert kwargs == {
            "add_special_tokens": False,
            "return_offsets_mapping": True,
            "truncation": False,
        }
        return {
            "input_ids": [ord(c) for c in text],
            "offset_mapping": [(i, i + 1) for i in range(len(text))],
        }

    def decode(self, ids, **kwargs):
        return "".join(chr(i) for i in ids)


def decision(split="train"):
    return {
        "record_id": split + "-decision",
        "problem_group": split + "-group",
        "language": "en",
        "split": split,
        "training_allowed": split == "train",
        "tools": [],
        "messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "excluded bad response"},
            {"role": "user", "content": "corrected observation"},
            {"role": "assistant", "content": "correct final"},
        ],
        "supervised_assistant_indices": [3],
        "context_only_assistant_indices": [1],
    }


def release():
    rows = {"train": [decision()], "validation": [decision("validation")]}
    result = {
        "schema_version": 1,
        "kind": "functiongemma_decision_release",
        "records": rows,
        "records_sha256": digest(rows),
    }
    result["release_sha256"] = digest(result)
    return result


def test_labels_only_final_target_including_native_end():
    encoded = encode_decision(decision(), Tokenizer())
    target = [value for value in encoded["labels"] if value != -100]
    assert Tokenizer().decode(target) == "correct final<end_of_turn>"
    assert encoded["labels"][0] == -100
    assert "excluded" not in Tokenizer().decode(target)


def test_encoded_seal_and_span_reload():
    encoded = encode_release(release(), Tokenizer())
    assert len(validate_encoded_release(encoded)["train"]) == 1
    encoded["records"]["train"][0]["labels"][0] = 1
    with pytest.raises(ValueError, match="hash_mismatch"):
        validate_encoded_release(encoded)


def test_oversize_never_truncated():
    row = decision()
    row["messages"][0]["content"] = "x" * 2048
    tokenizer_1 = Tokenizer()
    with pytest.raises(ValueError, match="sequence_exceeds_context"):
        encode_decision(row, tokenizer_1)


def test_unstable_native_prefix_fails_closed():
    class Unstable(Tokenizer):
        def apply_chat_template(self, messages, **kwargs):
            result = super().apply_chat_template(messages, **kwargs)
            return "unstable" + result if kwargs["add_generation_prompt"] else result

    record_2 = decision()
    tokenizer_3 = Unstable()
    with pytest.raises(ValueError, match="native_prefix_unstable"):
        encode_decision(record_2, tokenizer_3)


def test_resealed_mask_corruption_still_rejected():
    encoded = encode_release(release(), Tokenizer())
    row = encoded["records"]["train"][0]
    row["labels"][0] = 1
    row["sequence_sha256"] = digest(
        {k: v for k, v in row.items() if k != "sequence_sha256"}
    )
    encoded["encoded_release_sha256"] = digest(
        {k: v for k, v in encoded.items() if k != "encoded_release_sha256"}
    )
    with pytest.raises(ValueError, match="mask_invalid"):
        validate_encoded_release(encoded)


def test_bad_target_and_context_rejected():
    row = decision()
    row["supervised_assistant_indices"] = [1]
    tokenizer_4 = Tokenizer()
    with pytest.raises(ValueError, match="target_invalid"):
        encode_decision(row, tokenizer_4)
    record_5 = decision()
    tokenizer_6 = Tokenizer()
    with pytest.raises(ValueError, match="context_invalid"):
        encode_decision(record_5, tokenizer_6, 512)


def reseal(document):
    for rows in document["records"].values():
        for row in rows:
            row["sequence_sha256"] = digest(
                {k: v for k, v in row.items() if k != "sequence_sha256"}
            )
    document["encoded_release_sha256"] = digest(
        {k: v for k, v in document.items() if k != "encoded_release_sha256"}
    )
    return document


@pytest.mark.parametrize(
    "change",
    ["base", "context", "empty_train", "bad_id", "bad_span", "group", "mask", "ids"],
)
def test_resealed_invalid_vectors_rejected(change):
    encoded = encode_release(release(), Tokenizer())
    row = encoded["records"]["train"][0]
    if change == "base":
        encoded["model"] = "other"
    elif change == "context":
        encoded["context"] = 2048
    elif change == "empty_train":
        encoded["records"]["train"] = []
    elif change == "bad_id":
        row["record_id"] = ""
    elif change == "bad_span":
        row["assistant_token_spans"][0]["start"] = 0
    elif change == "group":
        encoded["records"]["validation"][0]["problem_group"] = row["problem_group"]
    elif change == "mask":
        row["attention_mask"] = []
    else:
        row["input_ids"][0] = -1
    sealed_document_7 = reseal(encoded)
    with pytest.raises(ValueError):
        validate_encoded_release(sealed_document_7)


def test_native_call_stops_at_function_response_boundary():
    from venom_core.services.functiongemma.protocol import CALL_END

    row = decision()
    row["tools"] = [
        {
            "type": "function",
            "function": {
                "name": "FileSkill-read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                    "required": ["file_path"],
                },
            },
        }
    ]
    row["messages"][-1] = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "one",
                "type": "function",
                "function": {
                    "name": "FileSkill-read_file",
                    "arguments": {"file_path": "x"},
                },
            }
        ],
    }

    class Native(Tokenizer):
        def apply_chat_template(self, messages, **kwargs):
            if kwargs["add_generation_prompt"]:
                return super().apply_chat_template(messages, **kwargs)
            prefix = super().apply_chat_template(
                messages[:-1], **{**kwargs, "add_generation_prompt": True}
            )
            return (
                prefix
                + "<start_function_call>call:FileSkill-read_file{file_path:<escape>x<escape>}"
                + CALL_END
                + "<start_function_response>"
            )

    encoded = encode_decision(row, Native())
    supervised = Native().decode(
        [value for value in encoded["labels"] if value != -100]
    )
    assert supervised.endswith(CALL_END + "<start_function_response>")


@pytest.mark.parametrize(
    ("context", "characters", "expected_context"),
    [(None, 50, 1024), (1024, 1100, None), (2048, 1100, 2048)],
)
def test_cli_prepare_context_contract(
    tmp_path, monkeypatch, context, characters, expected_context
):
    import sys
    from types import SimpleNamespace

    from venom_core.services.functiongemma.cli import main
    from venom_core.services.functiongemma.profile import Recipe

    snapshot = tmp_path / Recipe().revision
    snapshot.mkdir()
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: Tokenizer())
        ),
    )
    arguments = ["prepare", "--snapshot", str(snapshot)]
    for split in ("train", "validation"):
        source = decision(split)
        source["messages"][0]["content"] = "x" * characters
        source["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "FileSkill-read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"file_path": {"type": "string"}},
                        "required": ["file_path"],
                    },
                },
            }
        ]
        path = tmp_path / (split + ".jsonl")
        path.write_text(json.dumps(source) + "\n")
        arguments.extend(("--" + split, str(path)))
    output = tmp_path / "prepared"
    arguments.extend(("--output", str(output)))
    if context is not None:
        arguments.extend(("--context", str(context)))
    if expected_context is None:
        with pytest.raises(ValueError, match="sequence_exceeds_context"):
            main(arguments)
        assert not output.exists()
    else:
        assert main(arguments) == 0
        document = json.loads((output / "encoded.json").read_text())
        records = validate_encoded_release(document, context=expected_context)
        assert len(records["train"]) == len(records["validation"]) == 1
        for method in ("full", "lora"):
            recipe = json.loads((output / (method + "-recipe.json")).read_text())
            assert recipe["context"] == expected_context


def test_cli_prepare_rejects_unsupported_context_before_io(tmp_path):
    from venom_core.services.functiongemma.cli import main

    path_text_8 = str(tmp_path / "prepared")
    with pytest.raises(SystemExit) as error:
        main(
            [
                "prepare",
                "--train",
                "missing",
                "--validation",
                "missing",
                "--snapshot",
                "missing",
                "--output",
                path_text_8,
                "--context",
                "512",
            ]
        )
    assert error.value.code == 2
    assert not (tmp_path / "prepared").exists()
