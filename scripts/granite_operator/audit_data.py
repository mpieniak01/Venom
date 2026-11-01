"""Independent audit of generated files and recorded execution evidence."""

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.granite_operator.validate_material import check_receipt  # noqa: E402
from venom_core.services.granite_operator.contract import (  # noqa: E402
    file_digest,
    load_profile,
    validate_conversation,
)

ROOT = Path(os.environ["GRANITE_DATA_ROOT"]).resolve()


def rows(path):
    return [
        json.loads(line) for line in path.open(encoding="utf-8-sig") if line.strip()
    ]


def fingerprint(text):
    return re.sub(r"\s+", " ", re.sub(r"\d+", "<n>", text.casefold())).strip()


def main():
    if (ROOT / "pilot-manifest.json").exists():
        raise ValueError("manifest_already_exists")
    profile = load_profile(
        Path(
            os.environ.get(
                "GRANITE_PROFILE", REPO / "config/granite_operator_profile.json"
            )
        )
    )
    downloads = ROOT / "download-manifest.json"
    source_receipts = json.loads(downloads.read_text()) if downloads.exists() else []
    for receipt in source_receipts:
        file = Path(receipt["local_path"])
        assert file.stat().st_size == receipt["bytes"]
        assert (
            hashlib.file_digest(file.open("rb"), "sha256").hexdigest()
            == receipt["sha256"]
        )
    receipts = {
        r["fixture_id"]: r for r in rows(ROOT / "domain/execution-receipts.jsonl")
    }
    n = 0
    by_fixture = Counter()
    near = {}
    files = {}
    for dataset in ("hf", "domain"):
        sets = {
            split: rows(ROOT / dataset / (split + ".jsonl"))
            for split in ("train", "validation")
        }
        for split, records in sets.items():
            for r in records:
                validate_conversation(r, split)
                assert (
                    r["training_allowed"] == (split == "train") and r["split"] == split
                )
                if "granite_tokens" in r:
                    assert 10 < r["granite_tokens"] <= profile.context
                if dataset == "domain":
                    evidence = receipts[r["fixture_id"]]
                    assert r["oracle_passed"] is True
                    quality = check_receipt(r, evidence)
                    assert r["execution_verified"] == bool(quality["commands"])
                    by_fixture[r["fixture_id"]] += 1
                else:
                    assert r["execution_verified"] is False
                    assert r["source_split"] == "train"
                key = fingerprint(
                    json.dumps(
                        {"tools": r["tools"], "messages": r["messages"]},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                other = near.get((dataset, key))
                assert other in (None, split), r["record_id"]
                near[(dataset, key)] = split
                n += 1
            file = ROOT / dataset / (split + ".jsonl")
            files[str(file.relative_to(ROOT))] = {
                "rows": len(records),
                "bytes": file.stat().st_size,
                "sha256": hashlib.file_digest(file.open("rb"), "sha256").hexdigest(),
            }
        assert not {r["problem_group"] for r in sets["train"]} & {
            r["problem_group"] for r in sets["validation"]
        }
    assert set(receipts) == set(by_fixture)
    for name, expected in [("smoke-train.jsonl", 32), ("smoke-validation.jsonl", 8)]:
        if not (ROOT / "domain" / name).exists():
            continue
        small = rows(ROOT / "domain" / name)
        assert len(small) == expected
        assert len({r["problem_group"] for r in small}) == expected // 2
    corpus = "\n".join((ROOT / name).read_text() for name in files)
    assert not re.search(
        r"sk-proj-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----",
        corpus,
    )
    assert "venom-maintenance-v1:" not in corpus
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
    )
    manifest = {
        "status": "DATA_PREPARED_FOR_SMALL_PILOT_NOT_TRAINING_QUALIFIED",
        "canonical_schema": "messages + tools; no instruction/response flattening",
        "datasets": files,
        "records_audited": n,
        "download_hashes_verified": bool(source_receipts),
        "context": profile.context,
        "execution_receipts": {
            "path": "domain/execution-receipts.jsonl",
            "rows": len(receipts),
            "sha256": file_digest(ROOT / "domain/execution-receipts.jsonl"),
        },
        "domain_receipts_verified": True,
        "group_split_disjoint": True,
        "normalized_numeric_whitespace_exact_cross_split_overlap": 0,
        "semantic_near_duplicate_guarantee": False,
        "training_smoke_status": "NOT_RUN",
        "loss_mask_status": "NOT_TESTED",
        "new_eval_test_set": "NOT_CREATED",
        "raw_codex_content_in_training": False,
        "gpu_training_started": False,
    }
    (ROOT / "pilot-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
