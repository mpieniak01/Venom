"""Default question setup is explicit, pinned and keeps datasets out of Git."""

import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from scripts import bootstrap_dependency_profile as bootstrap
from scripts import prepare_benchmark_questions as setup


@pytest.fixture
def payload(monkeypatch):
    data = json.dumps(
        {"questions": [{"id": 1, "question": "fixture question"}]}
    ).encode()
    monkeypatch.setattr(setup, "SOURCE_SHA256", hashlib.sha256(data).hexdigest())
    return data


def test_offline_history_restore_and_existing_custom_bank_are_idempotent(
    tmp_path, monkeypatch, payload
):
    calls = []

    def git(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=payload)

    monkeypatch.setattr(setup.subprocess, "run", git)
    first = setup.prepare(tmp_path)
    assert first["created"] is True
    assert first["source"] == "pinned_git_history"
    assert (tmp_path / setup.SOURCE_PATH).read_bytes() == payload
    assert setup.prepare(tmp_path)["created"] is False
    assert len(calls) == 1
    custom = json.dumps(
        {"questions": [{"id": 2, "question": "operator fixture"}]}
    ).encode()
    (tmp_path / setup.SOURCE_PATH).write_bytes(custom)
    assert setup.prepare(tmp_path)["source"] == "existing_local"
    assert (tmp_path / setup.SOURCE_PATH).read_bytes() == custom


def test_download_requires_explicit_opt_in_and_validates_source(
    tmp_path, monkeypatch, payload
):
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout=b""),
    )
    requested = []

    def fetch(url, *, timeout):
        requested.append(url)
        return io.BytesIO(payload)

    monkeypatch.setattr(setup, "urlopen", fetch)
    with pytest.raises(FileNotFoundError, match="--download"):
        setup.prepare(tmp_path)
    assert requested == []
    result = setup.prepare(tmp_path, download=True)
    assert result["created"] is True
    assert requested == [setup.SOURCE_URL]


def test_corrupt_source_does_not_create_question_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"corrupt"),
    )
    with pytest.raises(ValueError, match="checksum_mismatch"):
        setup.prepare(tmp_path)
    assert not (tmp_path / setup.SOURCE_PATH).exists()


def test_install_flag_runs_explicit_preparation_after_dependencies(
    tmp_path, monkeypatch
):
    import sys

    installed = []
    executed = []
    monkeypatch.setattr(
        bootstrap, "install_profile", lambda *args, **kwargs: installed.append(True)
    )
    monkeypatch.setattr(
        bootstrap.subprocess, "run", lambda command, **kwargs: executed.append(command)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bootstrap",
            "--profile",
            "light",
            "--venv",
            str(tmp_path / "venv"),
            "--root",
            str(tmp_path),
            "--prepare-benchmark-questions",
        ],
    )
    assert bootstrap.main() == 0
    assert installed == [True]
    assert len(executed) == 1
    assert "prepare_benchmark_questions.py" in executed[0][1]
    assert "--download" in executed[0]


def test_explicit_download_works_without_git_binary(tmp_path, monkeypatch, payload):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(setup.subprocess, "run", no_git)
    monkeypatch.setattr(setup, "urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    assert setup.prepare(tmp_path, download=True)["created"] is True
