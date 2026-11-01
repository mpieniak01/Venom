"""Apply recorded review decisions, split by tool family, validate and render datasets."""

import datetime
import hashlib
import importlib.util
import json
import os
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(os.environ["GRANITE_DATA_ROOT"]).resolve()
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from transformers import AutoTokenizer  # noqa: E402

from venom_core.services.maintenance_comparison.protocol import (  # noqa: E402
    granite_calls,
)


def sha(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def read_jsonl(path):
    return [
        json.loads(line) for line in path.open(encoding="utf-8-sig") if line.strip()
    ]


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def token_count(encoded):
    values = encoded["input_ids"] if hasattr(encoded, "keys") else encoded
    if values and isinstance(values[0], list):
        assert len(values) == 1
        values = values[0]
    assert values and all(isinstance(v, int) for v in values)
    return len(values)


def validate_record(row):
    schemas = {t["function"]["name"]: t["function"]["parameters"] for t in row["tools"]}
    assert len(schemas) == len(row["tools"])
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    pending = {}
    calls = 0
    for m in row["messages"]:
        assert m["role"] in ("system", "user", "assistant", "tool")
        if m["role"] == "tool":
            ident = m["tool_call_id"]
            assert ident in pending
            assert pending.pop(ident) == m["name"]
            assert isinstance(m["content"], str)
        else:
            assert not pending, "Unobserved intermediate call"
            if m.get("tool_calls"):
                assert m["role"] == "assistant"
                for call in m["tool_calls"]:
                    f = call["function"]
                    assert f["name"] in schemas
                    Draft202012Validator(schemas[f["name"]]).validate(f["arguments"])
                    calls += 1
                    if f["name"] != "Finish":
                        pending[call["id"]] = f["name"]
    assert not pending, "Unobserved final call"
    assert row["split"] in ("train", "validation")
    assert row["training_allowed"] == (row["split"] == "train")
    return calls


class ConverterChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "g01_prepare_hf", Path(__file__).with_name("prepare_hf.py")
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_nested_literal_arguments(self):
        name, args = self.mod.parse_calls(
            '[Lookup(keys=["a,b", "c"], options={"mode":"safe"})]'
        )[0]
        self.assertEqual(name, "Lookup")
        self.assertEqual(args, {"keys": ["a,b", "c"], "options": {"mode": "safe"}})

    def test_no_executable_values(self):
        with self.assertRaises((ValueError, SyntaxError)):
            self.mod.parse_calls("[Lookup(value=__import__('os').getcwd())]")

    def test_duplicate_argument(self):
        with self.assertRaises(ValueError):
            self.mod.parse_calls("[Lookup(x=1,x=2)]")

    def test_unbalanced_call(self):
        with self.assertRaises(ValueError):
            self.mod.parse_calls('[Lookup(x="unfinished)]')

    def test_invalid_default_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.normalize_schema({"type": "integer", "default": "not_a_number"})

    def test_known_type_alias(self):
        schema = self.mod.normalize_schema(
            {
                "type": "dict",
                "properties": {"count": {"type": "int"}},
                "required": ["count"],
            }
        )
        self.assertEqual(schema["properties"]["count"]["type"], "integer")

    def test_orphan_response_rejected(self):
        row = {
            "tools": [],
            "messages": [
                {"role": "tool", "tool_call_id": "absent", "name": "x", "content": "{}"}
            ],
            "split": "train",
            "training_allowed": True,
        }
        with self.assertRaises(AssertionError):
            validate_record(row)

    def test_token_count_encoding_mapping(self):
        self.assertEqual(
            token_count({"input_ids": [1, 2, 3], "attention_mask": [1, 1, 1]}), 3
        )
        self.assertEqual(
            token_count(
                {"input_ids": [[1, 2, 3, 4]], "attention_mask": [[1, 1, 1, 1]]}
            ),
            4,
        )

    def test_validation_cannot_train(self):
        row = {
            "tools": [],
            "messages": [],
            "split": "validation",
            "training_allowed": True,
        }
        with self.assertRaises(AssertionError):
            validate_record(row)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ConverterChecks)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful()
    candidates = read_jsonl(ROOT / "hf/audit-candidates.jsonl")
    decisions = json.loads(
        (ROOT / "hf/review-decisions.json").read_text(encoding="utf-8-sig")
    )
    reviewed = []
    hf = []
    for r in candidates:
        ident = r["record_id"].split("-")[-1]
        if r["source_id"] == "nvidia/When2Call":
            reason = decisions["whenRejected"].get(ident)
        else:
            reason = (
                None
                if ident in decisions["toolAccepted"]
                else decisions["toolRejectedReasons"].get(
                    ident, "outside_preferred_operator_pilot"
                )
            )
        reviewed.append(
            {
                "record_id": r["record_id"],
                "decision": "reject" if reason else "accept",
                "reason": reason
                or "clear_required_field_clarification_or_grounded_complete_round",
                "reviewer": "Codex agent; not human review",
                "scope": "100 questions/labels per source screened; all retained questions, calls, source observations and final responses inspected",
                "normalized_sha256": r["normalized_sha256"],
            }
        )
        if reason:
            continue
        functions = [
            c["function"]["name"]
            for m in r["messages"]
            for c in m.get("tool_calls", [])
        ]
        if not functions:
            functions = [t["function"]["name"] for t in r["tools"]]
        names = [
            next((k for k, v in r["name_mapping"].items() if v == name), name)
            for name in functions
        ]
        family = "|".join(sorted(re.sub(r"\W", "", x.lower()) for x in names))
        # All prompts/variants using the same tool family stay on the same side.
        r["problem_group"] = "hf-tool-family:" + family
        r["split"] = (
            "validation"
            if int(hashlib.sha256(family.encode()).hexdigest()[:8], 16) % 5 == 0
            else "train"
        )
        r["training_allowed"] = r["split"] == "train"
        r["quality_review"] = (
            "agent_reviewed_for_small_pilot; source_observations_not_execution_verified"
        )
        hf.append(r)
    write_jsonl(ROOT / "hf/review-ledger.jsonl", reviewed)
    domain = read_jsonl(ROOT / "domain/train.jsonl") + read_jsonl(
        ROOT / "domain/validation.jsonl"
    )
    tokenizer_path = Path(os.environ["GRANITE_SNAPSHOT"])
    tokenizer = AutoTokenizer.from_pretrained(
        str(tokenizer_path), local_files_only=True
    )
    template_hash = hashlib.file_digest(
        (tokenizer_path / "chat_template.jinja").open("rb"), "sha256"
    ).hexdigest()
    rejects = []
    rendered = []
    kept_hf = []
    for dataset, rows in [("hf", hf), ("domain", domain)]:
        groups = {s: set() for s in ("train", "validation")}
        keys = {s: set() for s in ("train", "validation")}
        for r in rows:
            validate_record(r)
            text = tokenizer.apply_chat_template(
                r["messages"],
                tools=r["tools"],
                tokenize=False,
                add_generation_prompt=False,
                enable_thinking=False,
            )
            ids = tokenizer.apply_chat_template(
                r["messages"],
                tools=r["tools"],
                tokenize=True,
                add_generation_prompt=False,
                enable_thinking=False,
            )
            tokens = token_count(ids)
            independently_encoded = tokenizer(text, add_special_tokens=False)[
                "input_ids"
            ]
            assert tokens == len(independently_encoded)
            if tokens > 4096:
                assert dataset == "hf", "Unexpected overlong domain record"
                rejects.append(
                    {
                        "record_id": r["record_id"],
                        "reason": "exceeds_training_context_4096",
                        "tokens": tokens,
                    }
                )
                continue
            # Check actual native envelopes for each assistant tool-call turn.
            for idx, m in enumerate(r["messages"]):
                if not m.get("tool_calls"):
                    continue
                before = tokenizer.apply_chat_template(
                    r["messages"][:idx],
                    tools=r["tools"],
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
                through = tokenizer.apply_chat_template(
                    r["messages"][: idx + 1],
                    tools=r["tools"],
                    tokenize=False,
                    add_generation_prompt=False,
                    enable_thinking=False,
                )
                assert through.startswith(before), (
                    r["record_id"],
                    "non_prefix_native_render",
                )
                native = through[len(before) :]
                decoded = granite_calls(native)
                expected = [c["function"] for c in m["tool_calls"]]
                assert len(decoded) == len(expected)
                for got, want in zip(decoded, expected):
                    assert got.name == want["name"]
                    # Current runtime parser preserves non-locations values as strings.
                    for key, value in want["arguments"].items():
                        expected_value = (
                            json.dumps(value, ensure_ascii=False)
                            if isinstance(value, (dict, list))
                            else str(value)
                        )
                        if isinstance(value, bool):
                            expected_value = str(value)
                        # Jinja's native tojson uses its own spacing/escaping for containers.
                        if isinstance(value, (dict, list)):
                            assert json.loads(got.arguments[key]) == value
                        else:
                            assert got.arguments[key] == expected_value, (
                                r["record_id"],
                                key,
                                got.arguments[key],
                                value,
                            )
            r["granite_tokens"] = tokens
            r["chat_template_sha256"] = template_hash
            groups[r["split"]].add(r["problem_group"])
            content_key = sha({"tools": r["tools"], "messages": r["messages"]})
            assert (
                content_key
                not in keys["validation" if r["split"] == "train" else "train"]
            )
            keys[r["split"]].add(content_key)
            if dataset == "hf":
                kept_hf.append(r)
            rendered.append(
                {
                    "dataset": dataset,
                    "record_id": r["record_id"],
                    "tokens": tokens,
                    "render_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "tool_protocol_roundtrip": "PASS",
                    "assistant_loss_mask_status": "NOT_TESTED: trainer/collator not implemented",
                }
            )
        assert not groups["train"] & groups["validation"]
    for dataset, rows in [("hf", kept_hf), ("domain", domain)]:
        for split in ("train", "validation"):
            write_jsonl(
                ROOT / dataset / (split + ".jsonl"),
                [r for r in rows if r["split"] == split],
            )
    write_jsonl(ROOT / "hf/context-rejections.jsonl", rejects)
    write_jsonl(ROOT / "native-render-checks.jsonl", rendered)
    # Existing domain smoke rows are regenerated from the checked records.
    for split in ("train", "validation"):
        d = [
            r for r in domain if r["split"] == split and r["fixture_id"].endswith("-00")
        ]
        assert len(d) == (32 if split == "train" else 8)
        write_jsonl(ROOT / "domain" / ("smoke-" + split + ".jsonl"), d)
    # Training recipes remain separate; do not silently create a token-unbalanced mixture.
    summary = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "unit_checks_passed": result.testsRun,
        "hf_reviewed_candidates": len(reviewed),
        "hf_agent_accepted_before_context": len(hf),
        "hf_context_rejections": len(rejects),
        "hf_pilot_records": len(kept_hf),
        "hf_counts": {
            s: dict(Counter(r["split"] for r in kept_hf if r["source_id"] == s))
            for s in ("nvidia/When2Call", "Team-ACE/ToolACE")
        },
        "domain_records": len(domain),
        "domain_counts": dict(Counter(r["split"] for r in domain)),
        "domain_categories": dict(Counter(r["category"] for r in domain)),
        "native_render_records": len(rendered),
        "native_render_max_tokens": max(r["tokens"] for r in rendered),
        "template_sha256": template_hash,
        "split_family_overlap": 0,
        "exact_cross_split_overlap": 0,
        "training_started": False,
        "training_smoke_status": "NOT_RUN",
        "loss_mask_status": "NOT_TESTED",
        "limitations": [
            "Public labels are agent-reviewed and schema-checked, not re-executed or human-certified.",
            "ToolACE extracts complete first-round prefixes only; source message ranges are recorded.",
            "Domain is 20 task families, 120 fixtures, 240 PL/EN conversations; not 240 independent problems.",
            "No final held-out evaluation set was created or consumed.",
            "Near-duplicate review beyond normalized exact text and tool/task-family grouping is not exhaustive.",
        ],
    }
    (ROOT / "quality-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
