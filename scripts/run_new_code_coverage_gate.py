#!/usr/bin/env python3
"""Run new-code coverage gate with fast-lane budget + optional fallback tests."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {proc.returncode}: {' '.join(cmd)}"
        )
    return proc


def _run_pytest(
    *,
    pytest_bin: str,
    tests: list[str],
    mark_expr: str,
    cov_target: str,
    coverage_xml: str,
    coverage_html: str,
    junit_xml: str,
    cov_fail_under: float,
    cov_append: bool,
) -> float:
    if not tests:
        return 0.0

    cmd = [
        pytest_bin,
        "-n",
        "4",
        *tests,
        "-o",
        "junit_family=xunit1",
        "-m",
        mark_expr,
        f"--cov={cov_target}",
        "--cov-report=term-missing:skip-covered",
        f"--cov-report=xml:{coverage_xml}",
        f"--cov-fail-under={cov_fail_under}",
    ]
    if coverage_html:
        cmd.append(f"--cov-report=html:{coverage_html}")
    if junit_xml:
        cmd.append(f"--junitxml={junit_xml}")
    if cov_append:
        cmd.append("--cov-append")

    started = time.monotonic()
    _run(cmd)
    return time.monotonic() - started


def _resolve_tests_with_metadata(
    resolver_mod,
    *,
    baseline_group: Path,
    new_code_group: Path,
    include_baseline: bool,
    diff_base: str,
    time_budget_sec: float,
    timings_junit_xml: str,
    exclude_slow_fastlane: bool,
    max_tests: int,
    catalog: str | None,
) -> tuple[list[str], list[dict[str, object]]]:
    return resolver_mod.resolve_tests_with_metadata(
        baseline_group=baseline_group,
        new_code_group=new_code_group,
        include_baseline=include_baseline,
        diff_base=diff_base,
        time_budget_sec=time_budget_sec,
        timings_junit_xml=timings_junit_xml,
        exclude_slow_fastlane=exclude_slow_fastlane,
        max_tests=max_tests,
        catalog_path=catalog,
    )


def _compute_uncovered_summary(
    checker_mod,
    *,
    coverage_xml: Path,
    sonar_config: Path,
    diff_base: str,
    scope: str,
    min_coverage: float,
) -> dict[str, object]:
    per_file, total_covered, total_coverable = (
        checker_mod.analyze_changed_lines_coverage(
            coverage_xml=coverage_xml,
            sonar_config=sonar_config,
            diff_base=diff_base,
            scope=scope,
        )
    )
    return checker_mod._summary_payload(
        per_file=per_file,
        total_covered=total_covered,
        total_coverable=total_coverable,
        min_coverage=min_coverage,
    )


def _fallback_candidates(
    resolver_mod,
    *,
    uncovered_files: list[str],
    already_selected: set[str],
    timings: dict[str, float],
    max_count: int,
) -> list[str]:
    if not uncovered_files:
        return []

    tests = resolver_mod.all_test_files()
    related = resolver_mod.related_tests_for_modules(uncovered_files, tests)

    direct: set[str] = set()
    for path in uncovered_files:
        stem = Path(path).stem
        candidate = f"tests/test_{stem}.py"
        if candidate in tests:
            direct.add(candidate)

    candidates = sorted((related | direct) - already_selected)
    filtered = [path for path in candidates if resolver_mod.is_light_test(path)]

    scored = sorted(
        filtered,
        key=lambda path: resolver_mod.estimate_test_cost(path, timings),
    )
    if max_count > 0:
        scored = scored[:max_count]
    return scored


def _to_pytest_nodeid(classname: str, test_name: str) -> str:
    parts = [part for part in classname.split(".") if part]
    if not parts:
        return f"{classname}::{test_name}" if classname else test_name

    file_path_str: str | None = None
    split_index = 0
    for idx in range(len(parts), 0, -1):
        candidate = Path("/".join(parts[:idx]) + ".py")
        if candidate.exists():
            file_path_str = candidate.as_posix()
            split_index = idx
            break

    if file_path_str is not None:
        suffix = parts[split_index:]
        if suffix:
            return f"{file_path_str}::{'::'.join(suffix)}::{test_name}"
        return f"{file_path_str}::{test_name}"

    return f"{classname}::{test_name}"


def _extract_failing_nodes(junit_xml: str, limit: int = 8) -> list[str]:
    path = Path(junit_xml)
    if not junit_xml or not path.exists():
        return []

    try:
        root = ET.parse(path).getroot()
    except Exception:
        return []

    nodes: list[str] = []
    for testcase in root.iter("testcase"):
        if testcase.find("failure") is None and testcase.find("error") is None:
            continue
        classname = testcase.attrib.get("classname", "").strip()
        test_name = testcase.attrib.get("name", "").strip()
        if not classname or not test_name:
            continue
        nodes.append(_to_pytest_nodeid(classname, test_name))
        if len(nodes) >= limit:
            break
    return nodes


def _print_pytest_failure_triage(
    *, pytest_bin: str, junit_xml: str, selected_tests: list[str]
) -> None:
    failing_nodes = _extract_failing_nodes(junit_xml)
    print("❌ Pytest run failed.")
    if failing_nodes:
        print("ℹ️ First failing tests:")
        for node in failing_nodes:
            print(f"  - {node}")
        print(f"ℹ️ Suggested rerun: {pytest_bin} -q {failing_nodes[0]}")
        return
    if selected_tests:
        print("ℹ️ Suggested rerun (first selected test):")
        print(f"  {pytest_bin} -q {selected_tests[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run new-code coverage gate")
    parser.add_argument("--pytest-bin", default="pytest")
    parser.add_argument("--baseline-group", required=True)
    parser.add_argument("--new-code-group", required=True)
    parser.add_argument("--include-baseline", type=int, default=1)
    parser.add_argument("--diff-base", default="origin/main")
    parser.add_argument("--time-budget-sec", type=float, default=0.0)
    parser.add_argument(
        "--timings-junit-xml", default="test-results/sonar/python-junit.xml"
    )
    parser.add_argument("--exclude-slow-fastlane", type=int, default=1)
    parser.add_argument("--max-tests", type=int, default=0)
    parser.add_argument("--catalog", default="")
    parser.add_argument("--fallback-coverage", type=int, default=1)
    parser.add_argument("--max-fallback-tests", type=int, default=20)
    parser.add_argument("--mark-expr", required=True)
    parser.add_argument("--cov-target", required=True)
    parser.add_argument("--coverage-xml", required=True)
    parser.add_argument("--coverage-html", default="")
    parser.add_argument("--junit-xml", default="")
    parser.add_argument("--cov-fail-under", type=float, default=0.0)
    parser.add_argument("--min-coverage", type=float, default=80.0)
    parser.add_argument("--sonar-config", default="sonar-project.properties")
    parser.add_argument("--telemetry-json", default="")
    args = parser.parse_args()

    resolver_mod = _load_module(
        "resolve_sonar_new_code_tests", Path("scripts/resolve_sonar_new_code_tests.py")
    )
    checker_mod = _load_module(
        "check_new_code_coverage", Path("scripts/check_new_code_coverage.py")
    )

    started = time.monotonic()
    fast_tests, metadata = _resolve_tests_with_metadata(
        resolver_mod,
        baseline_group=Path(args.baseline_group),
        new_code_group=Path(args.new_code_group),
        include_baseline=bool(args.include_baseline),
        diff_base=args.diff_base,
        time_budget_sec=args.time_budget_sec,
        timings_junit_xml=args.timings_junit_xml,
        exclude_slow_fastlane=bool(args.exclude_slow_fastlane),
        max_tests=args.max_tests,
        catalog=args.catalog,
    )

    if not fast_tests:
        print("❌ Resolver nie zwrócił testów do uruchomienia")
        return 1

    est_fast = sum(
        float(row.get("estimated_seconds", 0.0))
        for row in metadata
        if row.get("selected")
    )

    print("ℹ️ Fast lane tests:")
    for item in fast_tests:
        print(f"  {item}")

    try:
        pass1_duration = _run_pytest(
            pytest_bin=args.pytest_bin,
            tests=fast_tests,
            mark_expr=args.mark_expr,
            cov_target=args.cov_target,
            coverage_xml=args.coverage_xml,
            coverage_html=args.coverage_html,
            junit_xml=args.junit_xml,
            cov_fail_under=args.cov_fail_under,
            cov_append=False,
        )
    except RuntimeError as exc:
        _print_pytest_failure_triage(
            pytest_bin=args.pytest_bin,
            junit_xml=args.junit_xml,
            selected_tests=fast_tests,
        )
        print(str(exc))
        return 1

    summary = _compute_uncovered_summary(
        checker_mod,
        coverage_xml=Path(args.coverage_xml),
        sonar_config=Path(args.sonar_config),
        diff_base=args.diff_base,
        scope=args.cov_target,
        min_coverage=args.min_coverage,
    )

    fallback_tests: list[str] = []
    pass2_duration = 0.0

    if bool(args.fallback_coverage) and not bool(summary["pass"]):
        uncovered_files = [item["path"] for item in summary.get("uncovered_files", [])]
        timings = resolver_mod.load_junit_timings(args.timings_junit_xml)
        fallback_tests = _fallback_candidates(
            resolver_mod,
            uncovered_files=uncovered_files,
            already_selected=set(fast_tests),
            timings=timings,
            max_count=args.max_fallback_tests,
        )

        if fallback_tests:
            print("ℹ️ Fallback tests:")
            for item in fallback_tests:
                print(f"  {item}")

            try:
                pass2_duration = _run_pytest(
                    pytest_bin=args.pytest_bin,
                    tests=fallback_tests,
                    mark_expr=args.mark_expr,
                    cov_target=args.cov_target,
                    coverage_xml=args.coverage_xml,
                    coverage_html=args.coverage_html,
                    junit_xml=args.junit_xml,
                    cov_fail_under=args.cov_fail_under,
                    cov_append=True,
                )
            except RuntimeError as exc:
                _print_pytest_failure_triage(
                    pytest_bin=args.pytest_bin,
                    junit_xml=args.junit_xml,
                    selected_tests=fallback_tests,
                )
                print(str(exc))
                return 1

            summary = _compute_uncovered_summary(
                checker_mod,
                coverage_xml=Path(args.coverage_xml),
                sonar_config=Path(args.sonar_config),
                diff_base=args.diff_base,
                scope=args.cov_target,
                min_coverage=args.min_coverage,
            )

    total_duration = time.monotonic() - started
    selected_meta = [row for row in metadata if bool(row.get("selected"))]
    domain_breakdown: dict[str, int] = {}
    legacy_count = 0
    for row in selected_meta:
        domain = str(row.get("domain", "misc"))
        domain_breakdown[domain] = domain_breakdown.get(domain, 0) + 1
        if bool(row.get("legacy_targeted", False)):
            legacy_count += 1

    telemetry = {
        "fast_count": len(fast_tests),
        "fast_estimated_seconds": round(est_fast, 2),
        "fast_actual_seconds": round(pass1_duration, 2),
        "fallback_count": len(fallback_tests),
        "fallback_actual_seconds": round(pass2_duration, 2),
        "total_seconds": round(total_duration, 2),
        "rate_percent": summary.get("rate_percent"),
        "required_percent": summary.get("required_percent"),
        "pass": bool(summary.get("pass")),
        "selected_domains": dict(sorted(domain_breakdown.items())),
        "selected_legacy_targeted_count": legacy_count,
    }

    print("ℹ️ Telemetry:")
    print(json.dumps(telemetry, indent=2))

    if args.telemetry_json:
        path = Path(args.telemetry_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(telemetry, indent=2) + "\n", encoding="utf-8")

    if not bool(summary["pass"]):
        print("FAIL: changed-lines coverage is below required threshold.")
        return 1

    if int(summary.get("total_coverable", 0)) == 0:
        print("No coverable changed lines found (after exclusions).")
    else:
        print(
            "PASS: changed-lines coverage meets the threshold: "
            f"{summary['rate_percent']}% >= {summary['required_percent']}%"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
