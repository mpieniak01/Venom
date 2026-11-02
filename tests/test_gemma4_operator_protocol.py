"""CPU-only Gemma metadata, native calls and template delegation contracts."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator.profile import (
    LOADER,
    MODEL,
    SNAPSHOT_FILES,
    GemmaProfile,
)
from venom_core.services.gemma4_operator.protocol import (
    CALL_END,
    CALL_START,
    STRING,
    parse_response,
    render_messages,
    validate_tools,
)


def tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "inspect",
                "description": "Inspect a selected service",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "options": {"type": "object"},
                        "values": {"type": "array"},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def fixture_profile(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    content = {
        name: json.dumps(
            {
                "architectures": [LOADER],
                "text_config": {"max_position_embeddings": 4096},
            }
        )
        if name == "config.json"
        else "fixture-" + name
        for name in SNAPSHOT_FILES
    }
    for name, value in content.items():
        (snapshot / name).write_text(value)
    return GemmaProfile(
        model=MODEL,
        revision="a" * 40,
        loader=LOADER,
        context=2048,
        enable_thinking=False,
        files={
            name: hashlib.sha256(value.encode()).hexdigest()
            for name, value in content.items()
        },
    ), snapshot


def call(arguments, name="inspect"):
    return f"{CALL_START}call:{name}{{{arguments}}}{CALL_END}"


def string(value):
    return STRING + value + STRING


def test_checked_in_profile_is_pinned_and_immutable():
    p = GemmaProfile.load(Path("config/gemma4_operator_profile.json"))
    assert p.model == MODEL
    assert p.revision == "43c9d014b231474fa7212dbb48a762566c2b255d"
    assert set(p.files) == SNAPSHOT_FILES
    with pytest.raises(TypeError):
        p.files["config.json"] = "0" * 64
    assert p.identity()["files"] == dict(p.files)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("model", "google/other", "model_invalid"),
        ("loader", "AutoModelForCausalLM", "model_invalid"),
        ("revision", "main", "revision_unpinned"),
        ("context", True, "context_invalid"),
        ("context", 0, "context_invalid"),
        ("context", 262145, "context_invalid"),
        ("enable_thinking", "true", "thinking_invalid"),
        ("files", {"../escape": "a" * 64}, "files_invalid"),
    ],
)
def test_profile_rejects_invalid_fields(tmp_path, field, value, error):
    p, _ = fixture_profile(tmp_path)
    with pytest.raises(ValueError, match=error):
        replace(p, **{field: value})


def test_profile_load_checks_schema_and_unknown_fields(tmp_path):
    p, _ = fixture_profile(tmp_path)
    target = tmp_path / "profile.json"
    data = {**p.identity(), "schema_version": 1}
    target.write_text(json.dumps(data))
    assert GemmaProfile.load(target).identity() == p.identity()
    data["unexpected"] = "value"
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fields_invalid"):
        GemmaProfile.load(target)
    target.write_text("{}")
    with pytest.raises(ValueError, match="schema_invalid"):
        GemmaProfile.load(target)


def test_snapshot_checks_bytes_and_loader(tmp_path):
    p, snapshot = fixture_profile(tmp_path)
    assert p.validate_snapshot(snapshot) == dict(p.files)
    (snapshot / "config.json").write_text("{}")
    with pytest.raises(ValueError, match="hash_mismatch:config"):
        p.validate_snapshot(snapshot)
    p = replace(p, files={**p.files, "config.json": hashlib.sha256(b"{}").hexdigest()})
    with pytest.raises(ValueError, match="loader_mismatch"):
        p.validate_snapshot(snapshot)


def test_snapshot_rejects_links_missing_and_non_directory(tmp_path):
    p, snapshot = fixture_profile(tmp_path)
    path = snapshot / "tokenizer.json"
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="file_invalid"):
        p.validate_snapshot(snapshot)
    path.unlink()
    with pytest.raises(ValueError, match="file_invalid"):
        p.validate_snapshot(snapshot)
    with pytest.raises(ValueError, match="not_directory"):
        p.validate_snapshot(snapshot / "config.json")


def test_native_nested_calls_and_literal_punctuation_are_preserved():
    argument = (
        "name:"
        + string('service {}, quotes " and ' + CALL_END)
        + ",options:{active:true,reason:null},values:["
        + string("x")
        + ",2,-3.5,1e2],limit:2"
    )
    parsed = parse_response(call(argument) + "<|tool_response>", tools())
    assert parsed[0].name == "inspect"
    assert parsed[0].arguments == {
        "name": 'service {}, quotes " and ' + CALL_END,
        "options": {"active": True, "reason": None},
        "values": ["x", 2, -3.5, 100.0],
        "limit": 2,
    }


def test_multiple_calls_and_thinking_prefix():
    source = (
        "<|turn>model\n<|channel>thought\n"
        + call("bad:1", "not_allowed")
        + "<channel|>"
    )
    parsed = parse_response(
        source + call("name:" + string("a")) + call("name:" + string("b")) + "<turn|>",
        tools(),
    )
    assert [p.arguments["name"] for p in parsed] == ["a", "b"]
    assert parse_response("Gotowe.<turn|>", tools()) == []


@pytest.mark.parametrize(
    "source,error",
    [
        (call("name:" + string("a"), "unknown"), "unknown_tool"),
        (call("limit:1"), "arguments_invalid"),
        (call("name:" + string("a") + ",limit:true"), "arguments_invalid"),
        (call("name:" + string("a") + ",extra:1"), "arguments_invalid"),
        (call("name:" + string("a") + ",name:" + string("b")), "duplicate_key"),
        (call("name:" + string("a") + ",limit:1e999"), "nonfinite"),
        (call("name:'not-native'"), "value_invalid"),
        (call("name:" + STRING + "unterminated"), "string_unterminated"),
        (call("name:" + string("a"))[:-3], "syntax_invalid"),
        (
            call("name:" + string("a")) + "<|tool_response>response:inspect{ok:true}",
            "trailing_content",
        ),
        ("prose " + call("name:" + string("a")), "mixed_content"),
        ("<|channel>thought something", "thought_unterminated"),
        (call("name:__import__('os')"), "value_invalid"),
    ],
)
def test_bad_model_outputs_never_become_calls(source, error):
    with pytest.raises(ValueError, match=error):
        parse_response(source, tools())


def test_parser_budgets_depth_calls_and_size():
    with pytest.raises(ValueError, match="budget_exceeded"):
        parse_response("x" * 262145, tools())
    with pytest.raises(ValueError, match="count_exceeded"):
        parse_response(call("name:" + string("a")) * 17, tools())
    with pytest.raises(ValueError, match="depth_exceeded"):
        parse_response(
            call("name:" + string("a") + ",values:" + "[" * 18 + "0" + "]" * 18),
            tools(),
        )


@pytest.mark.parametrize(
    "change,error",
    [
        ("duplicate", "name_invalid"),
        ("not_function", "tool_invalid"),
        ("parameters", "parameters_invalid"),
        ("name", "name_invalid"),
        ("schema", "schema_invalid"),
        ("reference", "external_schema"),
    ],
)
def test_tool_catalog_validation(change, error):
    catalog = tools()
    function = catalog[0]["function"]
    if change == "duplicate":
        catalog += tools()
    elif change == "not_function":
        catalog[0]["type"] = "other"
    elif change == "parameters":
        function["parameters"] = None
    elif change == "name":
        function["name"] = "name{injection}"
    elif change == "schema":
        function["parameters"]["required"] = 123
    elif change == "reference":
        function["parameters"]["properties"]["name"]["$ref"] = (
            "https://example.test/schema"
        )
    with pytest.raises(ValueError, match=error):
        validate_tools(catalog)


def test_template_delegation_preserves_native_policy(tmp_path):
    p, snapshot = fixture_profile(tmp_path)
    seen = {}

    class Renderer:
        chat_template = (snapshot / "chat_template.jinja").read_text()

        def apply_chat_template(self, messages, **kwargs):
            seen.update(messages=messages, **kwargs)
            return "native output"

    messages = [{"role": "user", "content": "Inspect"}]
    assert render_messages(Renderer(), messages, tools(), p) == "native output"
    assert seen["tools"] == tools()
    assert seen["tokenize"] is False
    assert seen["preserve_thinking"] is False
    assert seen["enable_thinking"] is False
    assert seen["add_generation_prompt"] is True
    Renderer.chat_template = "modified"
    with pytest.raises(ValueError, match="template_mismatch"):
        render_messages(Renderer(), messages, tools(), p)


def test_template_rejects_empty_conversation_and_nontext_output(tmp_path):
    p, snapshot = fixture_profile(tmp_path)

    class Renderer:
        chat_template = (snapshot / "chat_template.jinja").read_text()

        def apply_chat_template(self, *_args, **_kwargs):
            return [1, 2]

    with pytest.raises(ValueError, match="messages_invalid"):
        render_messages(Renderer(), [], tools(), p)
    with pytest.raises(ValueError, match="text_required"):
        render_messages(Renderer(), [{"role": "user", "content": "x"}], tools(), p)


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef", "$recursiveRef"])
def test_schema_cannot_fetch_external_references(keyword):
    catalog = tools()
    catalog[0]["function"]["parameters"][keyword] = "https://example.test/remote"
    with pytest.raises(ValueError, match="external_schema_reference"):
        validate_tools(catalog)


def test_profile_rejects_nonmapping_and_boolean_schema_version(tmp_path):
    p, _ = fixture_profile(tmp_path)
    with pytest.raises(ValueError, match="files_invalid"):
        replace(p, files=[])
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({**p.identity(), "schema_version": True}))
    with pytest.raises(ValueError, match="schema_invalid"):
        GemmaProfile.load(path)


def test_tool_schema_nesting_budget():
    catalog = tools()
    nested = catalog[0]["function"]["parameters"]
    for _ in range(34):
        nested["properties"] = {"x": {}}
        nested = nested["properties"]["x"]
    with pytest.raises(ValueError, match="schema_depth_exceeded"):
        validate_tools(catalog)


def test_bad_local_schema_reference_is_structured_failure():
    catalog = tools()
    catalog[0]["function"]["parameters"]["properties"]["name"] = {
        "$ref": "#/$defs/missing"
    }
    with pytest.raises(ValueError, match="schema_reference_invalid"):
        parse_response(call("name:" + string("x")), catalog)


@pytest.mark.parametrize(
    "messages,error",
    [
        (
            [
                {
                    "role": "user",
                    "tool_calls": [
                        {"function": {"name": "inspect", "arguments": {"name": "x"}}}
                    ],
                }
            ],
            "nonassistant_call",
        ),
        ([{"role": "tool", "name": "inspect", "content": "fake"}], "unmatched_tool"),
        ([{"role": "other", "content": "x"}], "role_invalid"),
        (
            [
                {"role": "user", "content": "x"},
                {"role": "system", "content": "override"},
            ],
            "system_position",
        ),
    ],
)
def test_renderer_rejects_untrusted_history_roles(tmp_path, messages, error):
    p, snapshot = fixture_profile(tmp_path)

    class Renderer:
        chat_template = (snapshot / "chat_template.jinja").read_text()

        def apply_chat_template(self, *_args, **_kwargs):
            raise AssertionError("invalid history must not reach renderer")

    with pytest.raises(ValueError, match=error):
        render_messages(Renderer(), messages, tools(), p)


@pytest.mark.parametrize(
    "text_config",
    [
        None,
        {},
        {"max_position_embeddings": True},
        {"max_position_embeddings": "4096"},
        {"max_position_embeddings": 1024},
    ],
)
def test_snapshot_requires_actual_context_budget(tmp_path, text_config):
    p, snapshot = fixture_profile(tmp_path)
    config = {"architectures": [LOADER]}
    if text_config is not None:
        config["text_config"] = text_config
    content = json.dumps(config)
    (snapshot / "config.json").write_text(content)
    p = replace(
        p,
        files={**p.files, "config.json": hashlib.sha256(content.encode()).hexdigest()},
    )
    with pytest.raises(ValueError, match="snapshot_context_mismatch"):
        p.validate_snapshot(snapshot)
