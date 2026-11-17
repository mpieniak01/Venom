"""Replay frozen source/calculator traces offline; never invoke a model or HTTP."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from venom_core.services.grounded_dialogue import (
    AnswerDraft,
    CalculationClaim,
    CalculationPlan,
    Evidence,
    GroundedTurn,
    SourceDocument,
    SourceRef,
    TurnPlan,
    detect_requirements,
    execute_grounded_turn,
    text_hash,
)


def _normal(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
        if not unicodedata.combining(c)
    )


class FrozenPacket:
    """Adapter for explicitly complete cards, not entire upstream web pages."""

    def __init__(self, cards: list[dict]) -> None:
        self.cards = {c["id"]: c for c in cards}
        if len(self.cards) != len(cards):
            raise ValueError("duplicate_source")
        self.read_log: list[str] = []

    def current_ref(self, source_id: str) -> SourceRef:
        card = self.cards[source_id]
        return SourceRef(source_id, card["version"], text_hash(card["text"]))

    def search(self, query: str) -> list[SourceRef]:
        # Same deterministic search as the frozen experiment, with no answer key.
        words = {w[:5] for w in re.findall(r"[a-z0-9]+", _normal(query)) if len(w) > 2}
        scored = []
        for card in self.cards.values():
            hay = _normal(card["title"] + " " + card["keywords"] + " " + card["id"])
            score = sum(w in hay for w in words)
            if score:
                scored.append((score, card["id"]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [self.current_ref(ident) for _, ident in scored[:3]]

    def read(self, ref: SourceRef) -> SourceDocument:
        card = self.cards[ref.source_id]
        self.read_log.append(ref.source_id)
        return SourceDocument(
            self.current_ref(ref.source_id),
            card["text"],
            complete=True,
            available=card["status"] == "available",
        )


def replay(previous: Path) -> dict:
    frozen = json.loads((previous / "frozen.json").read_text())
    for name, expected in frozen["files"].items():
        if hashlib.sha256((previous / name).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen_input_changed: " + name)
    cards = json.loads((previous / "sources.json").read_text())
    rows = [
        json.loads(line) for line in (previous / "rows.jsonl").read_text().splitlines()
    ]
    rows_hash = hashlib.sha256((previous / "rows.jsonl").read_bytes()).hexdigest()
    if (
        rows_hash
        != json.loads((previous / "generation-proof.json").read_text())["rows_sha256"]
    ):
        raise ValueError("responses_changed")
    packet = FrozenPacket(cards)
    checks = []
    completed_reads = 0
    for row in rows:
        for index, call in enumerate(row["tools"]):
            key = f"{row['case']}:{row['turn']}:{index}"
            if call["name"] == "search_sources":
                query = call["arguments"]["query"]
                references = packet.search(query)
                assert [r.source_id for r in references] == [
                    r["source_id"] for r in call["result"]["results"]
                ]
                before = len(packet.read_log)
                evidence = GroundedTurn(packet).prepare(
                    TurnPlan("Przeczytaj źródła.", key, source_query=query)
                )
                actual_reads = len(packet.read_log) - before
                ok = actual_reads == len(references) and len(evidence.sources) + len(
                    evidence.unavailable
                ) == len(references)
                checks.append(
                    {
                        "trace": key,
                        "kind": "search_then_full_read",
                        "pass": ok,
                        "documents_read": actual_reads,
                        "complete_available": [
                            d.ref.source_id for d in evidence.sources
                        ],
                        "unavailable": list(evidence.unavailable),
                    }
                )
                completed_reads += len(evidence.sources)
            elif call["name"] == "read_source":
                ref = packet.current_ref(call["arguments"]["source_id"])
                document = packet.read(ref)
                checks.append(
                    {
                        "trace": key,
                        "kind": "read_source",
                        "pass": document.text == call["result"]["text"]
                        and document.complete,
                    }
                )
            elif call["name"] == "calculate":
                expression = call["arguments"]["expression"]
                recorded_value = call["result"]["result"]

                def draft(
                    evidence: Evidence, value: str = recorded_value
                ) -> AnswerDraft:
                    return AnswerDraft(
                        evidence.evidence_id, (CalculationClaim("result", value, ""),)
                    )

                answer = execute_grounded_turn(
                    TurnPlan(
                        "Oblicz.",
                        key,
                        calculations=(CalculationPlan("result", expression),),
                    ),
                    packet,
                    draft,
                )
                checks.append(
                    {
                        "trace": key,
                        "kind": "calculate_and_publish",
                        "pass": answer.text.endswith("= " + recorded_value),
                        "expression": expression,
                        "value": recorded_value,
                        "answer": answer.text,
                    }
                )
            else:
                raise ValueError("unexpected_tool")
    # Expected labels are used ONLY here for offline routing measurement.
    routing = []
    extra = []
    for case in json.loads((previous / "dev.json").read_text()):
        prior: list[str] = []
        for index, turn in enumerate(case["turns"], 1):
            predicted = detect_requirements(turn["user"], prior)
            mode = turn["tool_expectation"]["mode"]
            data = {
                "case": case["id"],
                "turn": index,
                "user": turn["user"],
                "predicted": asdict(predicted),
            }
            if mode != "none":
                data.update(
                    expected=mode,
                    detected=predicted.sources
                    if mode == "source"
                    else predicted.calculation,
                )
                routing.append(data)
            elif predicted.sources or predicted.calculation:
                extra.append(data)
            prior.append(turn["user"])
    counts = Counter(c["kind"] for c in checks)
    return {
        "protocol": "grounded-tool-contracts-offline-v1",
        "previous_protocol_sha256": frozen["protocol_sha256"],
        "rows_sha256": rows_hash,
        "trace_checks": checks,
        "counts": dict(counts),
        "all_24_traces_pass": len(checks) == 24 and all(c["pass"] for c in checks),
        "automatic_full_available_reads_after_11_searches": completed_reads,
        "routing": {
            "required": len(routing),
            "detected": sum(c["detected"] for c in routing),
            "cases": routing,
            "additional_interventions": extra,
        },
        "no_training": True,
        "no_inference": True,
        "openrouter_cost_usd": "0",
        "interpretation": "Replay proves tool/receipt contracts, not corrected model answers. A detected calculation without an expression blocks before drafting. The semantic correctness of an expression and free prose still needs review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "all_24_traces_pass",
                    "counts",
                    "automatic_full_available_reads_after_11_searches",
                )
            }
        )
    )
    print(
        "Required routing:",
        result["routing"]["detected"],
        "/",
        result["routing"]["required"],
    )
    if (
        not result["all_24_traces_pass"]
        or result["routing"]["detected"] != result["routing"]["required"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
