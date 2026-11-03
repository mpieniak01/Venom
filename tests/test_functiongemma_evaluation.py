"""Paired proposals are scored without running tools."""

import copy
from types import SimpleNamespace as NS

import pytest

from venom_core.services.functiongemma import cli, evaluation

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "FileSkill-read_file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
                "additionalProperties": False,
            },
        },
    }
]


def trials():
    return [
        {
            "arm": arm,
            "case_id": "case",
            "problem_group": "group",
            "benchmark_sha256": "benchmark",
            "tools_sha256": "tools",
            "generation_sha256": "generation",
            "seconds": i + 1,
            "exact": True,
            "schema_valid": True,
            "unexpected_call": False,
        }
        for i, arm in enumerate(sorted(evaluation.ARMS))
    ]


def test_score():
    expected = [{"name": "FileSkill-read_file", "arguments": {"file_path": "x"}}]
    text = "<start_function_call>call:FileSkill-read_file{file_path:<escape>x<escape>}<end_function_call>"
    assert evaluation.score(text, TOOLS, expected)["exact"]
    assert not evaluation.score("<start_function_call>bad", TOOLS, expected)[
        "schema_valid"
    ]
    assert evaluation.score("Need more details", TOOLS, [])["exact"]


def test_comparison():
    result = evaluation.compare(trials())
    assert result["arms"]["B0"]["exact_rate"] == 1
    assert result["activation_allowed"] is False
    with pytest.raises(ValueError):
        evaluation.compare([])
    with pytest.raises(ValueError, match="duplicate"):
        evaluation.compare(trials() + [trials()[0]])
    with pytest.raises(ValueError, match="incomplete"):
        evaluation.compare(trials()[:-1])
    for options in (
        {"arm": "X"},
        {"seconds": float("inf")},
        {"exact": 1},
        {"problem_group": "other"},
        {"tools_sha256": "other"},
    ):
        rows = copy.deepcopy(trials())
        rows[0].update(options)
        with pytest.raises(ValueError):
            evaluation.compare(rows)


def test_cli_plan(capsys):
    assert cli.main(["plan", "--samples", "832"]) == 0
    assert '"total_updates": 156' in capsys.readouterr().out


def test_cli_dispatch(tmp_path, monkeypatch):
    import json

    from venom_core.services.functiongemma import worker

    path = tmp_path / "input.json"
    path.write_text(json.dumps(trials()))
    assert cli.main(["compare", str(path)]) == 0
    monkeypatch.setattr(worker, "run", lambda value: {"prepared": True})
    assert cli.main(["run", str(path)]) == 0
    monkeypatch.setattr(cli, "prepare", lambda args: {"prepared": True})
    assert (
        cli.main(
            [
                "prepare",
                "--train",
                "a",
                "--validation",
                "b",
                "--snapshot",
                "s",
                "--output",
                "o",
            ]
        )
        == 0
    )


def test_prepare(tmp_path, monkeypatch):
    import sys

    from venom_core.services.functiongemma import dataset, encoding
    from venom_core.services.functiongemma.profile import Recipe

    snapshot = tmp_path / Recipe().revision
    snapshot.mkdir()
    train = tmp_path / "train.jsonl"
    train.write_text("{}")
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        NS(AutoTokenizer=NS(from_pretrained=lambda *a, **k: object())),
    )
    monkeypatch.setattr(dataset, "export_decisions", lambda value: {"records": value})
    monkeypatch.setattr(encoding, "encode_release", lambda *a, **k: {"encoded": True})
    monkeypatch.setattr(
        encoding, "validate_encoded_release", lambda *a, **k: {"train": [{}]}
    )
    args = NS(
        snapshot=str(snapshot),
        output=str(tmp_path / "out"),
        train=str(train),
        validation=str(train),
    )
    assert cli.prepare(args)["training_qualified"] is False
    with pytest.raises(FileExistsError):
        cli.prepare(args)
    args.snapshot = str(tmp_path)
    with pytest.raises(ValueError):
        cli.prepare(args)


def test_cpu_export(tmp_path, monkeypatch):
    from venom_core.services.functiongemma import dataset

    source = tmp_path / "source.jsonl"
    source.write_text("{}")
    output = tmp_path / "export.json"
    monkeypatch.setattr(
        dataset,
        "export_decisions",
        lambda rows: {"manifest": {"counts": {"train": 1}}, "release_sha256": "hash"},
    )
    assert (
        cli.main(
            [
                "export",
                "--train",
                str(source),
                "--validation",
                str(source),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.exists()
    with pytest.raises(FileExistsError):
        cli.main(
            [
                "export",
                "--train",
                str(source),
                "--validation",
                str(source),
                "--output",
                str(output),
            ]
        )


def test_proposal_has_no_execution(monkeypatch):
    import sys
    from contextlib import nullcontext

    from venom_core.services.functiongemma import protocol

    class Tensor:
        shape = (1, 2)

        def to(self, device):
            return self

    monkeypatch.setitem(sys.modules, "torch", NS(inference_mode=nullcontext))
    monkeypatch.setattr(protocol, "render_messages", lambda *a, **k: "prompt")
    text = [
        "<start_function_call>call:FileSkill-read_file{file_path:<escape>x<escape>}<end_function_call>"
    ]

    class Tokenizer:
        eos_token_id = 1
        unk_token_id = 99

        def __call__(self, *a, **k):
            return {"input_ids": Tensor()}

        def convert_tokens_to_ids(self, token):
            return 5

        def decode(self, *a, **k):
            return text[0]

    model = NS(device="cuda", eval=lambda: None, generate=lambda **k: [[1, 2, 3]])
    result = evaluation.propose(Tokenizer(), model, [], TOOLS)
    assert result["decision"] == "propose"
    assert result["execution_authorized"] is False
    assert (
        evaluation.propose(Tokenizer(), model, [], TOOLS, context=1)["reason"]
        == "context_budget"
    )
    text[0] = "<start_function_call>broken"
    assert evaluation.propose(Tokenizer(), model, [], TOOLS)["decision"] == "escalate"
    text[0] = "Please clarify"
    assert evaluation.propose(Tokenizer(), model, [], TOOLS)["decision"] == "no_call"
