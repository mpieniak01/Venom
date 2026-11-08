"""Paired proposals are scored without running tools."""

import copy
import json
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


@pytest.mark.parametrize(
    "text,expects_tool,unexpected",
    [
        ("<start_function_call>bad", True, False),
        ("<start_function_call>bad", False, True),
        ("<end_function_call>", False, False),
        (None, False, False),
    ],
)
def test_invalid_output_does_not_inflate_unexpected_calls(
    text, expects_tool, unexpected
):
    expected = (
        [{"name": "FileSkill-read_file", "arguments": {"file_path": "x"}}]
        if expects_tool
        else []
    )
    assert evaluation.score(text, TOOLS, expected) == {
        "schema_valid": False,
        "exact": False,
        "unexpected_call": unexpected,
    }


def test_comparison():
    result = evaluation.compare(trials())
    assert result["arms"]["B0"]["exact_rate"] == 1
    assert result["activation_allowed"] is False
    with pytest.raises(ValueError):
        evaluation.compare([])
    trial_rows_1 = trials()
    trial_rows_2 = trials()
    with pytest.raises(ValueError, match="duplicate"):
        evaluation.compare(trial_rows_1 + [trial_rows_2[0]])
    trial_rows_3 = trials()
    with pytest.raises(ValueError, match="incomplete"):
        evaluation.compare(trial_rows_3[:-1])
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


@pytest.mark.parametrize("field", evaluation.TRIAL_HASH_FIELDS)
@pytest.mark.parametrize("value", [None, "", " ", 3, [], {}])
def test_comparison_rejects_invalid_hash_fields_even_when_all_arms_match(field, value):
    rows = trials()
    for row in rows:
        row[field] = value
    with pytest.raises(ValueError, match="^functiongemma_trial_identity_invalid$"):
        evaluation.compare(rows)


@pytest.mark.parametrize("field", evaluation.TRIAL_HASH_FIELDS)
@pytest.mark.parametrize("all_arms", [False, True])
def test_comparison_rejects_missing_hash_fields_with_stable_error(field, all_arms):
    rows = trials()
    affected = rows if all_arms else rows[:1]
    for row in affected:
        del row[field]
    with pytest.raises(ValueError, match="^functiongemma_trial_identity_invalid$"):
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
    path_text_4 = str(source)
    path_text_5 = str(source)
    path_text_6 = str(output)
    with pytest.raises(FileExistsError):
        cli.main(
            [
                "export",
                "--train",
                path_text_4,
                "--validation",
                path_text_5,
                "--output",
                path_text_6,
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
            return {"<start_function_response>": 5, "<end_of_turn>": 6}[token]

        def decode(self, *a, **k):
            return text[0]

    generation = []

    def generate(**kwargs):
        generation.append(kwargs)
        return [[1, 2, 3]]

    model = NS(device="cuda", eval=lambda: None, generate=generate)
    result = evaluation.propose(Tokenizer(), model, [], TOOLS)
    assert result["decision"] == "propose"
    assert generation[-1]["eos_token_id"] == [1, 5, 6]
    assert result["execution_authorized"] is False
    assert (
        evaluation.propose(Tokenizer(), model, [], TOOLS, context=1)["reason"]
        == "context_budget"
    )
    text[0] = "<start_function_call>broken"
    assert evaluation.propose(Tokenizer(), model, [], TOOLS)["decision"] == "escalate"
    text[0] = "Please clarify"
    assert evaluation.propose(Tokenizer(), model, [], TOOLS)["decision"] == "no_call"


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"read","action":"approval"}',
        '{"action":"write"}',
        '{"action":"read","path":"a"}',
        '["read"]',
    ],
)
def test_scale_decoder_accepts_only_one_allowlisted_action(raw):
    """Reject ambiguous or unrecognized model decisions."""
    from scripts.functiongemma_scale.score import decode_action

    assert decode_action('{"action":"read"}<end_of_turn>') == "read"
    with pytest.raises(ValueError):
        decode_action(raw)


@pytest.fixture
def pilot_read_case():
    """Use a synthetic read with one explicit verified path."""
    from scripts.functiongemma_scale.cases import CONTEXT

    context = {
        "paths": ["proof.txt"],
        "body": None,
        "active": None,
        "active_requested": False,
        "recursive": None,
        "max_depth": None,
    }
    return {
        "record": {
            "record_id": "one",
            "language": "en",
            "messages": [
                {"role": "system", "content": CONTEXT + json.dumps(context)},
                {"role": "user", "content": 'Read "proof.txt".'},
            ],
        },
        "oracle": {
            "family": "read",
            "fixture": {"files": {"proof.txt": "evidence"}},
            "expected_action": "read",
            "expected_calls": [
                {
                    "name": "FileSkill-read_file",
                    "arguments": {"file_path": "proof.txt"},
                }
            ],
            "expected_result": "call",
            "reference_text": None,
        },
    }


@pytest.mark.asyncio
async def test_read_only_pilot_is_shadow_by_default(monkeypatch, pilot_read_case):
    """A correct shadow proposal must not create a workspace."""
    from scripts.functiongemma_scale import pilot

    def unexpected_workspace(_files):
        pytest.fail("Shadow mode opened a workspace")

    monkeypatch.setattr(pilot, "fixture_skill", unexpected_workspace)
    row = await pilot.assess_case(
        pilot_read_case, {"stop_reason": "eos", "text": '{"action":"read"}'}
    )
    assert row["decision_ok"]
    assert row["fixture_authorized"]
    assert row["proposed_calls"] == pilot_read_case["oracle"]["expected_calls"]
    assert row["executed_calls"] == []
    assert row["observed_effects"] is None


@pytest.mark.asyncio
async def test_read_only_pilot_replays_only_the_expected_synthetic_read(
    pilot_read_case,
):
    """Record the real FileSkill result, separately from the proposed arguments."""
    from scripts.functiongemma_scale import pilot

    row = await pilot.assess_case(
        pilot_read_case,
        {"stop_reason": "eos", "text": '{"action":"read"}'},
        execute_fixtures=True,
    )
    assert row["fixture_authorized"]
    assert row["executed_calls"] == row["proposed_calls"]
    assert row["observed_effects"] == ["evidence"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prediction", "format_ok"),
    [
        ({"stop_reason": "timeout", "text": '{"action":"read"}'}, False),
        ({"stop_reason": "eos", "text": '{"action":"read","path":"other"}'}, False),
        ({"stop_reason": "eos", "text": '{"action":"exists"}'}, True),
    ],
)
async def test_read_only_pilot_blocks_unapproved_proposals(
    monkeypatch, pilot_read_case, prediction, format_ok
):
    """Even replay mode must leave the workspace untouched on a rejected proposal."""
    from scripts.functiongemma_scale import pilot

    def unexpected_workspace(_files):
        pytest.fail("A rejected proposal opened a workspace")

    monkeypatch.setattr(pilot, "fixture_skill", unexpected_workspace)
    row = await pilot.assess_case(pilot_read_case, prediction, execute_fixtures=True)
    assert row["format_ok"] is format_ok
    assert row["fallback"] == (None if format_ok else "clarify")
    assert not row["fixture_authorized"]
    assert row["executed_calls"] == []


@pytest.mark.asyncio
async def test_read_only_pilot_blocks_read_proposed_for_preview(pilot_read_case):
    """A bindable file path does not authorize executing a preview."""
    from scripts.functiongemma_scale import pilot

    pilot_read_case["oracle"].update(
        expected_action="preview", expected_calls=[], expected_result="preview"
    )
    row = await pilot.assess_case(
        pilot_read_case,
        {"stop_reason": "eos", "text": '{"action":"read"}'},
        execute_fixtures=True,
    )
    assert row["unexpected_proposal"]
    assert row["proposed_calls"]
    assert row["executed_calls"] == []


@pytest.mark.asyncio
async def test_read_only_pilot_rejects_incomplete_prediction_set(pilot_read_case):
    """Reject unpaired results before the execution stage."""
    from scripts.functiongemma_scale import pilot

    with pytest.raises(ValueError, match="prediction IDs must match"):
        await pilot.assess([pilot_read_case], {}, execute_fixtures=True)


def test_read_only_pilot_cli_records_shadow_result(
    monkeypatch, tmp_path, pilot_read_case
):
    """Load frozen inputs through the CLI and keep the replay opt-in."""
    from scripts.functiongemma_scale import pilot

    cases = tmp_path / "cases.json"
    raw = tmp_path / "raw.json"
    output = tmp_path / "shadow.json"
    cases.write_text(json.dumps([pilot_read_case]), encoding="utf-8")
    raw.write_text(
        json.dumps(
            {"raw": {"one": {"stop_reason": "eos", "text": '{"action":"read"}'}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "pilot",
            "--cases",
            str(cases),
            "--predictions",
            str(raw),
            "--output",
            str(output),
        ],
    )

    pilot.main()

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["mode"] == "shadow"
    assert data["rows"][0]["proposed_calls"]
    assert data["rows"][0]["executed_calls"] == []


def test_scale_route_keeps_empty_body_distinct_and_binds_active():
    """Bind a verified active file and distinguish an empty body from no body."""
    from scripts.functiongemma_scale.score import route

    record = {"language": "pl"}
    context = {
        "paths": ["d/a"],
        "body": "",
        "recursive": None,
        "max_depth": None,
        "active": None,
        "active_requested": False,
    }
    assert route("approval", context, record, None) == ([], "approval", None)
    context["body"] = None
    assert route("approval", context, record, None) == ([], "missing_body", None)
    context.update(active="d/a", active_requested=True)
    calls, result, _ = route(
        "read", context, record, '{"ARCHIVE":"d/old","ACTIVE":"d/a"}'
    )
    assert result == "call" and calls == [
        {"name": "FileSkill-read_file", "arguments": {"file_path": "d/a"}}
    ]
    assert route("read", context, record, '{"ACTIVE":"../escape"}') == (
        [],
        "blocked",
        None,
    )


def test_tool_order_variants_cover_reads_and_lists_in_both_languages():
    """Choose existing anchors from both families while keeping 24 paired cases."""
    from scripts.functiongemma_scale.cases import CONTEXT, counterfactuals, make_suite

    def source(profile):
        """Provide one minimal discovery record for the selected system profile."""
        return {
            "record_id": f"source:{profile}:discovery-en",
            "prompt_profile": profile,
            "tools": TOOLS
            + [{"type": "function", "function": {"name": "FileSkill-list_files"}}],
            "messages": [
                {"role": "system", "content": profile + CONTEXT + "{}"},
                {"role": "user", "content": "Read the inventory."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"arguments": {"file_path": "inventory.json"}}}
                    ],
                },
                {"role": "tool", "content": "{}"},
            ],
        }

    development = make_suite([source("first"), source("second")])
    originals = {case["record"]["record_id"]: case for case in development}
    variants = counterfactuals(development)
    assert len(variants) == 24
    tool_order = [case for case in variants if case["oracle"]["factor"] == "tool-order"]
    assert {
        (case["record"]["language"], case["oracle"]["family"]) for case in tool_order
    } == {("pl", "read"), ("en", "read"), ("pl", "list"), ("en", "list")}
    for case in tool_order:
        original = originals[case["oracle"]["paired_with"]]
        assert case["record"]["tools"] == original["record"]["tools"][::-1]


def test_comparison_gate_rejects_lost_correct_listing():
    """Count tool regressions using the sealed oracle, independent of case family."""
    from scripts.functiongemma_scale.compare import compare

    rows = [
        {"record_id": "listing", "family": "list", "tool_task": True},
        {"record_id": "preview", "family": "preview", "tool_task": False},
    ]
    for row in rows:
        row.update(group="fixture", language="pl", seconds=0.1, correct=True)
    total = {
        "tool_cases": 100,
        "text_cases": 100,
        "tool_correct": 99,
        "text_correct": 99,
        "invalid": 0,
        "unexpected_call": 0,
        "unexpected_execution": 0,
        "possible_write_claim": 0,
    }
    before = {"case_sha256": "sealed", "verdicts": rows, "total": total}
    after = copy.deepcopy(before)
    for row in after["verdicts"]:
        row["correct"] = False

    result = compare(before, after)
    assert result["lost_correct_reads"] == ["listing"]
    assert not result["candidate_passes_quality_thresholds"]
