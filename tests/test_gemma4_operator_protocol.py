"""CPU-only Gemma metadata, native calls and template delegation contracts."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator.profile import (
    E4B_LOADER,
    E4B_MODEL,
    E4B_REVISION,
    LOADER,
    MODEL,
    PINNED_REVISIONS,
    SNAPSHOT_FILES,
    GemmaProfile,
    loader_for_model,
)
from venom_core.services.gemma4_operator.protocol import (
    CALL_END,
    CALL_START,
    STRING,
    parse_response,
    render_messages,
    validate_tools,
)


@pytest.fixture(autouse=True)
def approved_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", str(tmp_path))


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
    catalog = tools()
    with pytest.raises(ValueError, match=error):
        parse_response(source, catalog)


@pytest.mark.parametrize(
    "source,error",
    [
        ("x" * 262145, "budget_exceeded"),
        (call("name:" + string("a")) * 17, "count_exceeded"),
        (
            call("name:" + string("a") + ",values:" + "[" * 18 + "0" + "]" * 18),
            "depth_exceeded",
        ),
    ],
)
def test_parser_budgets_depth_calls_and_size(source, error):
    catalog = tools()
    with pytest.raises(ValueError, match=error):
        parse_response(source, catalog)


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
    renderer, catalog = Renderer(), tools()
    with pytest.raises(ValueError, match="template_mismatch"):
        render_messages(renderer, messages, catalog, p)


def test_template_rejects_empty_conversation_and_nontext_output(tmp_path):
    p, snapshot = fixture_profile(tmp_path)

    class Renderer:
        chat_template = (snapshot / "chat_template.jinja").read_text()

        def apply_chat_template(self, *_args, **_kwargs):
            return [1, 2]

    renderer, catalog = Renderer(), tools()
    messages = [{"role": "user", "content": "x"}]
    with pytest.raises(ValueError, match="messages_invalid"):
        render_messages(renderer, [], catalog, p)
    with pytest.raises(ValueError, match="text_required"):
        render_messages(renderer, messages, catalog, p)


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
    source = call("name:" + string("x"))
    with pytest.raises(ValueError, match="schema_reference_invalid"):
        parse_response(source, catalog)


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

    renderer, catalog = Renderer(), tools()
    with pytest.raises(ValueError, match=error):
        render_messages(renderer, messages, catalog, p)


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


@pytest.mark.parametrize("name", ["názwa", "inspect_１"])
def test_tool_names_remain_ascii_after_regex_simplification(name):
    catalog = tools()
    catalog[0]["function"]["name"] = name
    with pytest.raises(ValueError, match="name_invalid"):
        validate_tools(catalog)


def test_numeric_arguments_reject_unicode_digits():
    source = call("name:" + string("x") + ",limit:１")
    catalog = tools()
    with pytest.raises(ValueError, match="value_invalid"):
        parse_response(source, catalog)


def test_local_schema_anchor_resolves_consistently():
    catalog = tools()
    schema = catalog[0]["function"]["parameters"]
    schema["$defs"] = {"service": {"$anchor": "service", "type": "string"}}
    schema["properties"]["name"] = {"$ref": "#service"}
    parsed = parse_response(call("name:" + string("web")), catalog)
    assert parsed[0].arguments["name"] == "web"


@pytest.mark.parametrize("status", ["needs_input", "success"])
def test_renderer_keeps_canonical_intermediate_finish_without_tool_result(
    tmp_path, status
):
    p, snapshot = fixture_profile(tmp_path)
    catalog = tools() + [
        {
            "type": "function",
            "function": {
                "name": "Finish",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["status", "summary"],
                },
            },
        }
    ]
    messages = [
        {"role": "user", "content": "Inspect the selected service"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "Finish",
                        "arguments": {"status": status, "summary": "Which service?"},
                    }
                }
            ],
        },
        {"role": "user", "content": "Use web"},
        {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "inspect", "arguments": {"name": "web"}}}
            ],
        },
        {"role": "tool", "name": "inspect", "content": "running"},
        {"role": "assistant", "content": "Web is running."},
    ]
    seen = {}

    class Renderer:
        chat_template = (snapshot / "chat_template.jinja").read_text()

        def apply_chat_template(self, history, **_kwargs):
            seen["history"] = history
            return "native rendered history"

    from venom_core.services.gemma4_operator.material import prepare_material

    messages[1]["tool_calls"][0]["id"] = "finish-clarification"
    messages[3]["tool_calls"][0]["id"] = "inspect-service"
    messages[4]["tool_call_id"] = "inspect-service"
    selected = [1, 3, 5] if status == "needs_input" else [3, 5]
    row = {
        "record_id": "finish-continuation",
        "problem_group": "finish-continuation",
        "language": "pl",
        "split": "train",
        "training_allowed": True,
        "messages": messages,
        "tools": catalog,
        "supervised_assistant_indices": selected,
        "context_only_assistant_indices": [] if status == "needs_input" else [1],
    }
    prepared = prepare_material({"train": [row]})["records"]["train"][0]
    rendered = render_messages(
        Renderer(),
        prepared["messages"],
        prepared["tools"],
        p,
        add_generation_prompt=False,
    )
    assert rendered == "native rendered history"
    assert seen["history"] == messages


def test_native_maf_tool_name_keeps_hyphen_without_relaxing_argument_keys():
    catalog = tools()
    catalog[0]["function"]["name"] = "FileSkill-read_file"
    parsed = parse_response(
        call("name:" + string("log"), "FileSkill-read_file"), catalog
    )
    assert parsed[0].name == "FileSkill-read_file"
    assert parsed[0].arguments == {"name": "log"}
    malformed_call = call("bad-key:" + string("log"), "FileSkill-read_file")
    with pytest.raises(ValueError, match="syntax_invalid"):
        parse_response(malformed_call, catalog)


def test_two_native_variants_have_separate_pinned_architectures():
    large = GemmaProfile.load(Path("config/gemma4_operator_profile.json"))
    small = GemmaProfile.load(Path("config/gemma4_operator_e4b_profile.json"))
    assert large.model == MODEL
    assert large.loader == LOADER
    assert small.model == E4B_MODEL
    assert small.loader == E4B_LOADER
    assert small.revision == E4B_REVISION
    assert PINNED_REVISIONS[large.model] == large.revision
    assert PINNED_REVISIONS[small.model] == small.revision
    assert small.files != large.files
    assert loader_for_model(small.model) == small.loader
    assert loader_for_model(large.model) == large.loader
    assert small.context == large.context == 4096


@pytest.mark.parametrize(
    "model,loader",
    [(MODEL, E4B_LOADER), (E4B_MODEL, LOADER), ("google/gemma-4-27B-it", LOADER)],
)
def test_native_variants_reject_crossed_or_unknown_model_loader_pairs(
    tmp_path, model, loader
):
    profile, _ = fixture_profile(tmp_path)
    with pytest.raises(ValueError, match="model_invalid"):
        replace(profile, model=model, loader=loader)
