"""Local data-preparation analysis, not a production trainer. Never executes HF content."""

import ast
import copy
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(os.environ["GRANITE_DATA_ROOT"]).resolve()
OUT = ROOT / "hf"
OUT.mkdir(exist_ok=True)
REVS = {
    "when2call": "0582f7749df63a96fdc3070932e83e72396ace53",
    "toolace": "6bda777c88d21e5a204703c1ee45597a8fa4f734",
}
REPOS = {"when2call": "nvidia/When2Call", "toolace": "Team-ACE/ToolACE"}


def digest(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def canonical(name):
    if name.isidentifier() and len(name) <= 64:
        return name
    stem = re.sub(r"\W", "_", name).strip("_")[:42]
    if not stem or stem[0].isdigit():
        stem = "fn_" + stem
    return stem + "_" + hashlib.sha256(name.encode()).hexdigest()[:8]


def normalize_schema(s):
    if not isinstance(s, dict):
        raise ValueError("schema_not_object")
    out = copy.deepcopy(s)
    aliases = {
        "dict": "object",
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
    }
    if isinstance(out.get("type"), str):
        out["type"] = aliases.get(out["type"], out["type"])
    if out.get("required") is None:
        out.pop("required", None)
    if "properties" in out:
        if not isinstance(out["properties"], dict):
            raise ValueError("properties_not_object")
        if any(not k.isidentifier() for k in out["properties"]):
            raise ValueError("invalid_parameter_name")
        out["properties"] = {
            k: normalize_schema(v) for k, v in out["properties"].items()
        }
    if "items" in out:
        out["items"] = normalize_schema(out["items"])
    for key in ("allOf", "anyOf", "oneOf"):
        if key in out:
            out[key] = [normalize_schema(v) for v in out[key]]
    if "default" in out:
        # Empty default is a missing-value sentinel in these sources, not a real fallback.
        if out["default"] == "":
            out.pop("default")
        elif not Draft202012Validator(
            {k: v for k, v in out.items() if k != "default"}
        ).is_valid(out["default"]):
            raise ValueError("invalid_default_annotation")
    Draft202012Validator.check_schema(out)
    return out


def normalize_tools(raw):
    tools = []
    mapping = {}
    schemas = {}
    for t in raw:
        if isinstance(t, str):
            t = json.loads(t)
        if not isinstance(t, dict):
            raise ValueError("invalid_tool")
        t = t.get("function", t)
        name = t["name"]
        if not isinstance(name, str) or name in mapping:
            raise ValueError("duplicate_tool_name")
        p = copy.deepcopy(t["parameters"])
        outer = t.get("required")
        if outer is not None:
            if p.get("required") is not None and p["required"] != outer:
                raise ValueError("conflicting_required")
            p["required"] = outer
        p = normalize_schema(p)
        if p.get("type") != "object":
            raise ValueError("tool_parameters_not_object")
        if not set(p.get("required", [])) <= set(p.get("properties", {})):
            raise ValueError("unknown_required_field")
        new = canonical(name)
        if new in mapping.values():
            raise ValueError("name_collision")
        mapping[name] = new
        schemas[name] = p
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": new,
                    "description": t.get("description", ""),
                    "parameters": p,
                },
            }
        )
    return tools, mapping, schemas


def split_top(text):
    chunks = []
    start = 0
    depth = 0
    quote = None
    escaped = False
    for i, c in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced_call")
        elif c == "," and depth == 0:
            chunks.append(text[start:i].strip())
            start = i + 1
    if depth or quote:
        raise ValueError("unbalanced_call")
    chunks.append(text[start:].strip())
    return [x for x in chunks if x]


def parse_calls(text):
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError("not_call_list")
    calls = []
    for part in split_top(text[1:-1]):
        name, sep, tail = part.partition("(")
        if not sep or not tail.endswith(")"):
            raise ValueError("unsupported_call_syntax")
        node = ast.parse("_fn(" + tail, mode="eval").body
        if not isinstance(node, ast.Call) or node.args:
            raise ValueError("positional_or_invalid_call")
        arguments = {}
        for kw in node.keywords:
            if kw.arg is None or kw.arg in arguments:
                raise ValueError("expanded_or_duplicate_argument")
            arguments[kw.arg] = ast.literal_eval(kw.value)
        calls.append((name.strip(), arguments))
    if not calls:
        raise ValueError("empty_calls")
    return calls


def normalize_when(row):
    tools, mapping, schemas = normalize_tools(row["tools"])
    messages = row["messages"]
    if len(messages) != 2 or [m["role"] for m in messages] != ["user", "assistant"]:
        raise ValueError("unexpected_dialogue")
    user = messages[0]["content"]
    reply = messages[1]["content"]
    if len(tools) != 1:
        raise ValueError("pilot_requires_single_tool")
    if not (20 < len(user) < 700 and 20 < len(reply) < 400):
        raise ValueError("pilot_length")
    if re.search(
        r"apolog|sorry|unable|cannot|can't|don't have|do not have", reply, re.I
    ):
        raise ValueError("refusal_excluded")
    if not re.search(
        r"could you|please (?:provide|specify|tell)|i.*need|can you (?:provide|specify)",
        reply,
        re.I,
    ):
        raise ValueError("not_explicit_clarification")
    required = next(iter(schemas.values())).get("required", [])
    mentioned = []
    for name in required:
        words = [w for w in re.split(r"[_\W]+", name.lower()) if len(w) >= 3]
        if words and any(
            re.search(r"\b" + re.escape(w) + r"\b", reply.lower()) for w in words
        ):
            mentioned.append(name)
    if not mentioned:
        raise ValueError("clarification_not_tied_to_required_field")
    return (
        tools,
        copy.deepcopy(messages),
        mapping,
        "clarification",
        {"required_fields_mentioned": mentioned},
    )


def normalize_toolace(row):
    system = row["system"]
    i = system.find("[")
    original_length = len(row["conversations"])
    # Extract only an already complete first round, without creating missing observations.
    if (
        len(row["conversations"]) >= 4
        and [m["from"] for m in row["conversations"][:4]]
        == ["user", "assistant", "tool", "assistant"]
        and not row["conversations"][3]["value"].lstrip().startswith("[")
    ):
        row = {**row, "conversations": row["conversations"][:4]}
    else:
        raise ValueError("pilot_requires_complete_first_round")
    if i < 0:
        raise ValueError("no_tool_list")
    raw, _ = json.JSONDecoder().raw_decode(system[i:])
    tools, mapping, schemas = normalize_tools(raw)
    messages = []
    pending = {}
    next_id = 0
    call_count = 0
    for m in row["conversations"]:
        role = m["from"]
        value = m["value"]
        if not isinstance(value, str):
            raise ValueError("non_text_message")
        if role == "user":
            if pending:
                raise ValueError("missing_tool_response")
            messages.append({"role": "user", "content": value})
        elif role == "assistant":
            if pending:
                raise ValueError("missing_tool_response")
            if value.lstrip().startswith("["):
                calls = parse_calls(value.strip())
                normalized = []
                for name, args in calls:
                    if name not in mapping:
                        raise ValueError("unknown_tool")
                    Draft202012Validator(schemas[name]).validate(args)
                    if name in pending:
                        raise ValueError("ambiguous_same_tool_pending")
                    ident = f"call_{next_id}"
                    next_id += 1
                    pending[name] = ident
                    call_count += 1
                    normalized.append(
                        {
                            "id": ident,
                            "type": "function",
                            "function": {"name": mapping[name], "arguments": args},
                        }
                    )
                messages.append(
                    {"role": "assistant", "content": "", "tool_calls": normalized}
                )
            else:
                messages.append({"role": "assistant", "content": value})
        elif role == "tool":
            if not pending:
                raise ValueError("orphan_tool_response")
            observations = json.loads(value)
            if not isinstance(observations, list):
                raise ValueError("response_not_named_list")
            for observation in observations:
                name = observation["name"]
                if name not in pending or "results" not in observation:
                    raise ValueError("unmatched_observation")
                messages.append(
                    {
                        "role": "tool",
                        "name": mapping[name],
                        "tool_call_id": pending.pop(name),
                        "content": json.dumps(
                            observation["results"], ensure_ascii=False, sort_keys=True
                        ),
                    }
                )
        else:
            raise ValueError("unknown_role")
    if pending:
        raise ValueError("missing_tool_response")
    if (
        not messages
        or messages[-1]["role"] != "assistant"
        or messages[-1].get("tool_calls")
    ):
        raise ValueError("incomplete_dialogue")
    if (
        len(messages) != 4
        or [m["role"] for m in messages] != ["user", "assistant", "tool", "assistant"]
        or call_count != 1
    ):
        raise ValueError("pilot_requires_single_complete_round")
    if (
        len(messages[0]["content"]) > 600
        or len(messages[-1]["content"]) > 700
        or len(messages[2]["content"]) > 1800
    ):
        raise ValueError("pilot_length")
    call = messages[1]["tool_calls"][0]["function"]
    rawname = next(k for k, v in mapping.items() if v == call["name"])
    desc = next(
        t["function"]["description"]
        for t in tools
        if t["function"]["name"] == call["name"]
    )
    if re.search(
        r"password|cryptocurr|bitcoin|ethereum|invest|cancer|diabetes|diagnos|stock market|credit.?card",
        rawname + " " + desc,
        re.I,
    ):
        raise ValueError("out_of_operator_pilot_scope")
    if not re.search(
        r"search|find|list|get|fetch|convert|calculat|format|time|text|file|weather|temperature|information",
        rawname + " " + desc,
        re.I,
    ):
        raise ValueError("out_of_operator_pilot_scope")
    return (
        tools,
        messages,
        mapping,
        "single_tool_round",
        {
            "source_message_range": [0, 4],
            "source_conversation_messages": original_length,
            "extraction": "complete_first_round_prefix; later source turns not imported",
        },
    )


def main():
    raw = {
        "when2call": [
            json.loads(line)
            for line in (
                ROOT / "raw/nvidia/When2Call/train/when2call_train_sft.jsonl"
            ).open()
        ],
        "toolace": json.loads((ROOT / "raw/Team-ACE/ToolACE/data.json").read_text()),
    }
    profile = {}
    candidates = []
    for source, rows in raw.items():
        reasons = Counter()
        accepted = []
        seen = set()
        normalizer = normalize_when if source == "when2call" else normalize_toolace
        for idx, row in enumerate(rows):
            try:
                tools, messages, mapping, kind, extra = normalizer(row)
                key = digest({"tools": tools, "messages": messages})
                if key in seen:
                    raise ValueError("duplicate_normalized_conversation")
                seen.add(key)
                rec = {
                    "record_id": f"hf-{source}-{idx:05d}",
                    "source_id": REPOS[source],
                    "source_revision": REVS[source],
                    "source_row": idx,
                    "source_split": "train",
                    "license": "cc-by-4.0" if source == "when2call" else "apache-2.0",
                    "raw_record_sha256": digest(row),
                    "normalized_sha256": key,
                    "problem_group": f"hf:{source}:"
                    + digest(
                        {
                            "tools": tools,
                            "user": re.sub(
                                r"\d+", "<NUM>", messages[0]["content"].lower()
                            ),
                        }
                    )[:20],
                    "language": "en",
                    "tools": tools,
                    "messages": messages,
                    "name_mapping": mapping,
                    "kind": kind,
                    "verification_kind": "source_label_plus_schema_checks_not_execution",
                    "execution_verified": False,
                    "quality_review": "pending",
                    "training_allowed": False,
                    "normalization_notes": [
                        "source type aliases normalized",
                        "empty default annotations omitted",
                        "source system formatting instructions not copied",
                    ],
                    **extra,
                }
                accepted.append(rec)
            except Exception as exc:
                reason = (
                    str(exc).splitlines()[0][:130]
                    if isinstance(exc, ValueError)
                    else type(exc).__name__
                )
                reasons[reason] += 1
        accepted.sort(key=lambda r: hashlib.sha256(r["record_id"].encode()).hexdigest())
        selected = accepted[:100]
        profile[source] = {
            "raw_rows": len(rows),
            "structurally_eligible": len(accepted),
            "excluded": sum(reasons.values()),
            "exclusion_reasons": dict(reasons),
            "audit_candidate_rows": len(selected),
        }
        candidates += selected
    (OUT / "structural-profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    )
    with (OUT / "audit-candidates.jsonl").open("w") as f:
        for row in candidates:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # Compact source-label review packets; no network or imported code execution.
    packets = []
    for r in candidates:
        first = r["messages"][0]["content"]
        assistant = r["messages"][-1]["content"]
        calls = [c["function"] for m in r["messages"] for c in m.get("tool_calls", [])]
        packets.append(
            {
                "id": r["record_id"],
                "user": first,
                "assistant": assistant,
                "calls": calls,
                "required": {
                    t["function"]["name"]: t["function"]["parameters"].get(
                        "required", []
                    )
                    for t in r["tools"]
                },
                "observation": [
                    m["content"] for m in r["messages"] if m["role"] == "tool"
                ],
            }
        )
    (OUT / "audit-review-packets.json").write_text(
        json.dumps(packets, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(profile, ensure_ascii=False))


if __name__ == "__main__":
    main()
