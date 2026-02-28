#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileRuntime:
    file_path: str
    lane: str
    domain: str
    legacy_targeted: bool
    tests: int
    total_seconds: float
    failures: int
    impact_score: float


def _load_group(path: Path) -> set[str]:
    tests: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tests.add(line)
    return tests


def _resolve_lane(
    file_path: str, ci_lite_tests: set[str], new_code_tests: set[str]
) -> str:
    if file_path in ci_lite_tests:
        return "ci-lite"
    if file_path in new_code_tests:
        return "new-code"
    return "other"


def _lane_weight(lane: str) -> float:
    return {"ci-lite": 3.0, "new-code": 2.0}.get(lane, 1.0)


def _load_catalog(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    tests = payload.get("tests", [])
    if not isinstance(tests, list):
        return {}
    out: dict[str, dict[str, object]] = {}
    for item in tests:
        if not isinstance(item, dict):
            continue
        test_path = str(item.get("path", "")).strip()
        if not test_path:
            continue
        out[test_path] = item
    return out


def _load_junit_file_runtimes(
    junit_xml: Path,
    ci_lite_tests: set[str],
    new_code_tests: set[str],
    catalog: dict[str, dict[str, object]],
) -> tuple[list[FileRuntime], set[str]]:
    root = ET.parse(junit_xml).getroot()
    aggregates: dict[str, dict[str, Any]] = {}
    failing_files: set[str] = set()

    for testcase in root.iter("testcase"):
        file_path = testcase.attrib.get("file") or ""
        if not file_path:
            continue
        if file_path not in aggregates:
            lane = _resolve_lane(file_path, ci_lite_tests, new_code_tests)
            aggregates[file_path] = {
                "lane": lane,
                "tests": 0,
                "seconds": 0.0,
                "failures": 0,
            }
        entry = aggregates[file_path]
        entry["tests"] += 1
        try:
            entry["seconds"] += float(testcase.attrib.get("time", "0") or 0.0)
        except ValueError:
            pass

        failed = (
            testcase.find("failure") is not None or testcase.find("error") is not None
        )
        if failed:
            entry["failures"] += 1
            failing_files.add(file_path)

    results: list[FileRuntime] = []
    for file_path, payload in aggregates.items():
        score = payload["seconds"] * _lane_weight(payload["lane"])
        catalog_entry = catalog.get(file_path, {})
        results.append(
            FileRuntime(
                file_path=file_path,
                lane=payload["lane"],
                domain=str(catalog_entry.get("domain", "misc")),
                legacy_targeted=bool(catalog_entry.get("legacy_targeted", False)),
                tests=int(payload["tests"]),
                total_seconds=round(float(payload["seconds"]), 3),
                failures=int(payload["failures"]),
                impact_score=round(float(score), 3),
            )
        )

    results.sort(key=lambda item: item.impact_score, reverse=True)
    return results, failing_files


def _load_recent_lastfailed(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return set()
    return {str(nodeid) for nodeid in payload.keys()}


def _nodeid_to_test_file(nodeid: str) -> str | None:
    if "::" not in nodeid:
        return None
    test_file = nodeid.split("::", 1)[0]
    if test_file.startswith("tests/") and test_file.endswith(".py"):
        return test_file
    return None


def _recommendations(
    runtimes: list[FileRuntime],
    *,
    slow_threshold: float,
    fast_threshold: float,
    min_tests_for_promotion: int,
    recent_lastfailed: set[str],
    failing_files: set[str],
) -> dict[str, list[str]]:
    demote_candidates = [
        item.file_path
        for item in runtimes
        if item.lane == "ci-lite" and item.total_seconds >= slow_threshold
    ]
    promote_candidates = [
        item.file_path
        for item in runtimes
        if item.lane == "new-code"
        and item.failures == 0
        and item.legacy_targeted is False
        and item.tests >= min_tests_for_promotion
        and item.total_seconds <= fast_threshold
    ]

    recently_failed_files = {
        _nodeid_to_test_file(nodeid) for nodeid in recent_lastfailed
    }
    recently_failed_files.discard(None)

    flaky_candidates = sorted(failing_files | recently_failed_files)
    return {
        "promote_to_ci_lite": sorted(set(promote_candidates)),
        "consider_demotion_from_ci_lite": sorted(set(demote_candidates)),
        "flaky_candidates": flaky_candidates,
    }


def build_report(
    *,
    junit_xml: Path,
    ci_lite_group: Path,
    new_code_group: Path,
    slow_threshold: float,
    fast_threshold: float,
    min_tests_for_promotion: int,
    lastfailed_path: Path | None,
    top_n: int,
    catalog_path: Path | None,
) -> dict[str, Any]:
    ci_lite_tests = _load_group(ci_lite_group)
    new_code_tests = _load_group(new_code_group)
    catalog = _load_catalog(catalog_path)
    runtimes, failing_files = _load_junit_file_runtimes(
        junit_xml, ci_lite_tests, new_code_tests, catalog
    )
    recent_lastfailed = _load_recent_lastfailed(lastfailed_path)
    recommendations = _recommendations(
        runtimes,
        slow_threshold=slow_threshold,
        fast_threshold=fast_threshold,
        min_tests_for_promotion=min_tests_for_promotion,
        recent_lastfailed=recent_lastfailed,
        failing_files=failing_files,
    )

    domain_breakdown: dict[str, float] = {}
    for item in runtimes:
        domain_breakdown[item.domain] = round(
            domain_breakdown.get(item.domain, 0.0) + item.total_seconds, 3
        )

    return {
        "summary": {
            "files_count": len(runtimes),
            "ci_lite_files": sum(1 for item in runtimes if item.lane == "ci-lite"),
            "new_code_files": sum(1 for item in runtimes if item.lane == "new-code"),
            "other_files": sum(1 for item in runtimes if item.lane == "other"),
            "total_runtime_seconds": round(
                sum(item.total_seconds for item in runtimes), 3
            ),
            "legacy_targeted_files": sum(
                1 for item in runtimes if item.legacy_targeted
            ),
        },
        "domain_runtime_seconds": dict(
            sorted(domain_breakdown.items(), key=lambda item: (-item[1], item[0]))
        ),
        "top_impact_files": [asdict(item) for item in runtimes[:top_n]],
        "recommendations": recommendations,
    }


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _history_entry(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files_count": report["summary"]["files_count"],
        "ci_lite_files": report["summary"]["ci_lite_files"],
        "new_code_files": report["summary"]["new_code_files"],
        "total_runtime_seconds": report["summary"]["total_runtime_seconds"],
    }


def _attach_trend_and_history(
    report: dict[str, Any], *, history_file: Path | None, append_history: bool
) -> None:
    if history_file is None:
        return
    history = _load_history(history_file)
    current = _history_entry(report)
    previous = history[-1] if history else None
    if append_history:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with history_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(current, ensure_ascii=False) + "\n")

    delta = None
    if previous is not None:
        prev_runtime = float(previous.get("total_runtime_seconds", 0.0) or 0.0)
        delta = round(current["total_runtime_seconds"] - prev_runtime, 3)

    report["trend"] = {
        "history_file": str(history_file),
        "history_points_before_append": len(history),
        "runtime_delta_vs_previous_seconds": delta,
        "previous_total_runtime_seconds": (
            float(previous.get("total_runtime_seconds", 0.0)) if previous else None
        ),
        "current_total_runtime_seconds": current["total_runtime_seconds"],
        "history_appended": bool(append_history),
    }


def _print_text(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("Test intelligence report")
    print(
        f"- files: {summary['files_count']} "
        f"(ci-lite={summary['ci_lite_files']}, new-code={summary['new_code_files']}, other={summary['other_files']})"
    )
    print(f"- total runtime: {summary['total_runtime_seconds']}s")
    print(f"- legacy-targeted files: {summary['legacy_targeted_files']}")
    trend = report.get("trend")
    if isinstance(trend, dict):
        delta = trend.get("runtime_delta_vs_previous_seconds")
        if delta is None:
            print("- runtime trend: no previous point")
        else:
            print(f"- runtime trend delta vs previous: {delta}s")
    print("- top impact files:")
    for item in report["top_impact_files"]:
        print(
            f"  * {item['file_path']} | lane={item['lane']} | domain={item['domain']} | "
            f"tests={item['tests']} | sec={item['total_seconds']} | score={item['impact_score']}"
        )
    print("- top domains by runtime:")
    for domain, sec in list(report.get("domain_runtime_seconds", {}).items())[:10]:
        print(f"  * {domain}: {sec}s")

    rec = report["recommendations"]
    print("- recommendations:")
    print(f"  * promote_to_ci_lite: {len(rec['promote_to_ci_lite'])}")
    print(
        f"  * consider_demotion_from_ci_lite: {len(rec['consider_demotion_from_ci_lite'])}"
    )
    print(f"  * flaky_candidates: {len(rec['flaky_candidates'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate lightweight test intelligence report."
    )
    parser.add_argument(
        "--junit-xml",
        type=Path,
        default=Path("test-results/sonar/python-junit.xml"),
        help="JUnit XML report path.",
    )
    parser.add_argument(
        "--ci-lite-group",
        type=Path,
        default=Path("config/pytest-groups/ci-lite.txt"),
        help="CI lite test group file.",
    )
    parser.add_argument(
        "--new-code-group",
        type=Path,
        default=Path("config/pytest-groups/sonar-new-code.txt"),
        help="Sonar new-code test group file.",
    )
    parser.add_argument(
        "--lastfailed",
        type=Path,
        default=Path(".pytest_cache/v/cache/lastfailed"),
        help="Pytest lastfailed cache path (optional).",
    )
    parser.add_argument(
        "--slow-threshold",
        type=float,
        default=1.8,
        help="Per-file runtime threshold for ci-lite demotion candidates.",
    )
    parser.add_argument(
        "--fast-threshold",
        type=float,
        default=0.1,
        help="Per-file runtime threshold for new-code promotion candidates.",
    )
    parser.add_argument(
        "--min-tests-for-promotion",
        type=int,
        default=3,
        help="Minimum number of test cases in file to consider promotion from new-code to ci-lite.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=15,
        help="Number of highest impact files to include.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--history-file",
        type=Path,
        default=Path("test-results/sonar/test-intelligence-history.jsonl"),
        help="Optional JSONL history file for trend tracking.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config/testing/test_catalog.json"),
        help="Optional test catalog for domain and legacy-targeted metadata.",
    )
    parser.add_argument(
        "--append-history",
        type=int,
        default=1,
        help="Append current summary into history file (1/0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        junit_xml=args.junit_xml,
        ci_lite_group=args.ci_lite_group,
        new_code_group=args.new_code_group,
        slow_threshold=args.slow_threshold,
        fast_threshold=args.fast_threshold,
        min_tests_for_promotion=args.min_tests_for_promotion,
        lastfailed_path=args.lastfailed,
        top_n=args.top_n,
        catalog_path=args.catalog,
    )
    _attach_trend_and_history(
        report,
        history_file=args.history_file,
        append_history=bool(args.append_history),
    )
    if args.output == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
