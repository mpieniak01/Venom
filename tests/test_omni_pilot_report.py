"""Exercise the Omni acceptance report with local JSON fixtures."""

import pytest

from scripts.ollama_bench.omni_pilot import result_template, summarize, write_json


@pytest.fixture
def report_input(tmp_path):
    manifest = tmp_path / "manifest.json"
    suite = [
        {"id": "layout", "group": "visual", "scope": "paired", "turns": [{}, {}]},
        {"id": "lookup", "group": "visual", "scope": "paired", "turns": [{}]},
        {"id": "clarify", "group": "voice", "scope": "paired", "turns": [{}]},
        {"id": "no-image", "group": "voice", "scope": "api_control", "turns": [{}]},
        {"id": "offline", "group": "voice", "scope": "mock_transport", "turns": [{}]},
    ]
    write_json(manifest, {"cases": suite})
    return manifest, tmp_path / "results.json", result_template(manifest, suite)


def _summarize(report_input):
    manifest, path, results = report_input
    write_json(path, results)
    return summarize(manifest, path)


def _observed(turn, *, latency, error=None):
    """Record an observed turn with all applicable criteria graded."""
    turn.update(
        checks={key: True for key in turn["checks"]},
        latency_ms=latency,
        trace="observed-turn.json",
        error=error,
    )


def test_summarize_rejects_changed_manifest_bytes(report_input):
    manifest, _, _ = report_input
    with manifest.open("a", encoding="utf-8") as stream:
        stream.write("\n")

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        _summarize(report_input)


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown"])
def test_summarize_requires_exactly_one_row_per_target_and_case(report_input, change):
    """Reject omitted, duplicate or unrelated cases in the operator results."""
    _, _, results = report_input
    rows = results["rows"]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(rows[0])
    else:
        rows[0]["case"] = "unknown"

    with pytest.raises(ValueError, match="exactly one row"):
        _summarize(report_input)


@pytest.mark.parametrize("turn_count", [1, 3])
def test_summarize_requires_each_turn_of_a_multiturn_case(report_input, turn_count):
    _, _, results = report_input
    turns = results["rows"][0]["turns"]
    results["rows"][0]["turns"] = (turns + [turns[1]])[:turn_count]

    with pytest.raises(ValueError):
        _summarize(report_input)


@pytest.mark.parametrize(
    "checks",
    [
        {"intent": True, "tool": True, "grounding": True},
        {
            "intent": True,
            "tool": True,
            "grounding": True,
            "speech": True,
            "history": True,
        },
        {"intent": 1, "tool": True, "grounding": True, "speech": True},
    ],
    ids=["missing", "extra", "non-boolean"],
)
def test_summarize_rejects_invalid_checks(report_input, checks):
    _, _, results = report_input
    results["rows"][0]["turns"][0]["checks"] = checks

    with pytest.raises(ValueError, match="invalid checks"):
        _summarize(report_input)


@pytest.mark.parametrize("latency", [-1, True, float("inf"), float("nan"), "20"])
def test_summarize_rejects_invalid_latency(report_input, latency):
    _, _, results = report_input
    results["rows"][0]["turns"][0]["latency_ms"] = latency

    with pytest.raises(ValueError, match="invalid latency"):
        _summarize(report_input)


@pytest.mark.parametrize("error", [None, "transcription failed"])
def test_summarize_requires_trace_for_observed_turn(report_input, error):
    _, _, results = report_input
    turn = results["rows"][0]["turns"][0]
    _observed(turn, latency=None, error=error)
    turn["trace"] = None

    with pytest.raises(ValueError, match="missing evidence reference"):
        _summarize(report_input)


@pytest.mark.parametrize("missing", ["build", "model", "runtime"])
def test_summarize_requires_identity_for_observed_results(report_input, missing):
    _, _, results = report_input
    results.update(build="build-1", model="omni-test", runtime="runtime-test")
    results[missing] = None
    _observed(results["rows"][1]["turns"][0], latency=30)

    with pytest.raises(
        ValueError, match="require build, model, and runtime identities"
    ):
        _summarize(report_input)


def test_summarize_accepts_ungraded_template_without_identities(report_input):
    """Report both interfaces as pending until the operator records observations."""
    report = _summarize(report_input)

    assert report["run"] == {"build": None, "model": None, "runtime": None}
    assert report["paired"] == {"pending/pending": 3}
    for target in ("studio", "full"):
        assert report[target]["cases"] == {"pending": 3}
        assert report[target]["latency_samples"] == 0
        assert report[target]["median_ms"] is None
        assert report[target]["p95_ms"] is None


def test_summarize_aggregates_multiturn_statuses_and_latency_by_interface(report_input):
    """Pair case statuses by ID even when the operator reorders result rows."""
    _, _, results = report_input
    identities = {"build": "build-1", "model": "omni-test", "runtime": "runtime-test"}
    results.update(identities)
    turns = {(row["target"], row["case"]): row["turns"] for row in results["rows"]}
    _observed(turns["studio", "layout"][0], latency=300)
    _observed(turns["studio", "layout"][1], latency=100)
    _observed(turns["studio", "lookup"][0], latency=600, error="document unavailable")
    _observed(turns["full", "layout"][0], latency=400)
    _observed(turns["full", "layout"][1], latency=50)
    turns["full", "layout"][1]["checks"]["history"] = False
    _observed(turns["full", "lookup"][0], latency=200)
    results["rows"].reverse()

    report = _summarize(report_input)

    assert report["run"] == identities
    assert report["paired"] == {"pass/fail": 1, "fail/pass": 1, "pending/pending": 1}
    assert report["studio"] == {
        "cases": {"pass": 1, "fail": 1, "pending": 1},
        "groups": {"visual": {"pass": 1, "fail": 1}, "voice": {"pending": 1}},
        "latency_samples": 3,
        "median_ms": 300,
        "p95_ms": 600,
    }
    assert report["full"] == {
        "cases": {"pass": 1, "fail": 1, "pending": 1},
        "groups": {"visual": {"pass": 1, "fail": 1}, "voice": {"pending": 1}},
        "latency_samples": 3,
        "median_ms": 200,
        "p95_ms": 400,
    }


def test_summarize_uses_nearest_rank_for_p95(tmp_path):
    """Distinguish nearest-rank p95 from the maximum and interpolated percentiles."""
    manifest = tmp_path / "manifest.json"
    suite = [
        {"id": f"case-{index}", "group": "visual", "scope": "paired", "turns": [{}]}
        for index in range(22)
    ]
    write_json(manifest, {"cases": suite})
    results = result_template(manifest, suite)
    results.update(build="build-1", model="omni-test", runtime="runtime-test")
    for index, row in enumerate(reversed(results["rows"][:22])):
        _observed(row["turns"][0], latency=index * 10)

    report = _summarize((manifest, tmp_path / "results.json", results))

    assert report["studio"]["latency_samples"] == 22
    assert report["studio"]["median_ms"] == 105
    assert report["studio"]["p95_ms"] == 200
    assert report["full"]["latency_samples"] == 0
