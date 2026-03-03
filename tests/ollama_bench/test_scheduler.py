from scripts.ollama_bench.scheduler import (
    Job,
    _build_jobs,
    _job_timeout_seconds,
    _make_summary,
    _parse_artifact_from_output,
    _parse_timeout_overrides,
)


def test_build_jobs_contains_single_and_loop_per_model():
    jobs = _build_jobs(
        models=["m1", "m2"],
        tasks=["python_simple", "python_complex"],
        loop_task="python_complex_bugfix",
        first_sieve_task=None,
    )
    assert len(jobs) == 6
    assert jobs[0].mode == "single"
    assert jobs[0].task == "python_simple"
    assert jobs[2].mode == "loop"
    assert jobs[2].model == "m1"
    assert jobs[5].mode == "loop"
    assert jobs[5].model == "m2"


def test_build_jobs_with_sieve_adds_first_job_per_model():
    jobs = _build_jobs(
        models=["m1"],
        tasks=["python_complex"],
        loop_task="python_complex_bugfix",
        first_sieve_task="python_sanity",
    )
    assert len(jobs) == 3
    assert jobs[0].task == "python_sanity"
    assert jobs[0].role == "sieve"
    assert jobs[1].task == "python_complex"
    assert jobs[2].mode == "loop"


def test_parse_artifact_from_json_output():
    out = '{"artifact": "data/benchmarks/x/single_m1_python_complex.json", "passed": false}'
    assert (
        _parse_artifact_from_output(out)
        == "data/benchmarks/x/single_m1_python_complex.json"
    )


def test_make_summary_counts_statuses():
    jobs = [
        Job(
            id="a", model="m1", mode="single", task="python_complex", status="completed"
        ),
        Job(
            id="b",
            model="m1",
            mode="loop",
            task="python_complex_bugfix",
            status="failed",
            rc=2,
        ),
        Job(id="c", model="m2", mode="single", task="python_complex", status="pending"),
        Job(
            id="d",
            model="m2",
            mode="loop",
            task="python_complex_bugfix",
            status="skipped",
        ),
    ]
    summary = _make_summary(meta={"run": "x"}, jobs=jobs)
    assert summary["total_jobs"] == 4
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert summary["pending"] == 1
    assert summary["skipped"] == 1
    assert summary["failed_jobs"][0]["id"] == "b"


def test_parse_timeout_overrides_accepts_json_object():
    overrides = _parse_timeout_overrides(
        '{"codestral:latest": 420, "deepcoder:latest": 360}'
    )
    assert overrides["codestral:latest"] == 420
    assert overrides["deepcoder:latest"] == 360


def test_job_timeout_seconds_uses_override_when_present():
    args = type("Args", (), {"timeout": 180})()
    job = Job(id="x", model="codestral:latest", mode="single", task="python_sanity")
    timeout = _job_timeout_seconds(job, args, {"codestral:latest": 420})
    assert timeout == 420
