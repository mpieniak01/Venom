from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from venom_core.api.routes import academy_conversion, academy_history, academy_training
from venom_core.api.routes import academy_uploads as au
from venom_core.api.schemas.academy import DatasetScopeRequest, TrainingRequest


class _Logger:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def info(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.infos.append(msg % args if args else msg)

    def warning(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.warnings.append(msg % args if args else msg)

    def error(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.errors.append(msg % args if args else msg)

    def exception(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.errors.append(msg % args if args else msg)


@contextmanager
def _dummy_lock(_path: Path):
    yield


def _prepare_workspace(tmp_path: Path):
    source_file = tmp_path / "src.txt"
    source_file.write_text("q\n\na", encoding="utf-8")
    converted_file = tmp_path / "out.jsonl"
    converted_file.write_text('{"instruction":"q","output":"a"}\n', encoding="utf-8")

    workspace = {
        "base_dir": tmp_path,
        "metadata_file": tmp_path / "files.json",
        "source_dir": tmp_path,
        "converted_dir": tmp_path,
    }
    items = [{"file_id": "src-id", "name": "src.txt", "category": "source"}]
    saved: dict[str, object] = {}
    return source_file, converted_file, workspace, items, saved


def test_academy_conversion_source_to_converted_path(tmp_path: Path):
    source_file, converted_file, workspace, items, saved = _prepare_workspace(tmp_path)
    source_item, converted_item = academy_conversion.convert_dataset_source_file(
        file_id="src-id",
        workspace=workspace,
        target_format="jsonl",
        check_path_traversal_fn=lambda _v: True,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        save_user_conversion_metadata_fn=lambda _path, payload: saved.setdefault(
            "items", payload
        ),
        find_conversion_item_fn=lambda _items, _fid: items[0],
        resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_file,
        source_to_records_fn=lambda _path: [
            {"instruction": "q", "input": "", "output": "a"}
        ],
        write_records_as_target_fn=lambda _records, _target: converted_file,
        build_conversion_item_fn=academy_conversion.build_conversion_item,
    )
    assert source_item["file_id"] == "src-id"
    assert converted_item["category"] == "converted"
    assert saved["items"]


def test_academy_conversion_selection_guard_and_media(tmp_path: Path):
    _, _, workspace, _, _ = _prepare_workspace(tmp_path)
    with pytest.raises(ValueError):
        academy_conversion.set_conversion_training_selection(
            file_id="bad",
            selected_for_training=True,
            workspace=workspace,
            check_path_traversal_fn=lambda _v: False,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: [],
            save_user_conversion_metadata_fn=lambda _path, _items: None,
            find_conversion_item_fn=lambda _items, _fid: None,
        )

    assert (
        academy_conversion.guess_media_type(tmp_path / "file.unknown")
        == "application/octet-stream"
    )


@pytest.mark.asyncio
async def test_academy_conversion_preview_branch(tmp_path: Path):
    text_path = tmp_path / "preview.txt"
    text_path.write_text("x" * 30, encoding="utf-8")
    preview, truncated = await academy_conversion.read_text_preview(
        file_path=text_path,
        max_chars=10,
    )
    assert len(preview) == 10
    assert truncated is True


def test_academy_training_scope_helpers_cover_branches(tmp_path: Path) -> None:
    logger = _Logger()
    curated = SimpleNamespace(
        examples=[],
        clear=lambda: None,
        filter_low_quality=lambda: 2,
        save_dataset=lambda **_kwargs: str(tmp_path / "dataset.jsonl"),
        get_statistics=lambda: {"total_examples": 23},
    )
    req = DatasetScopeRequest(
        include_lessons=True,
        include_git=True,
        include_task_history=True,
        lessons_limit=30,
        git_commits_limit=40,
        upload_ids=["u1"],
        conversion_file_ids=["c1"],
        quality_profile="balanced",
    )
    curated_payload = academy_training.curate_dataset_scope(
        request=req,
        req=SimpleNamespace(),
        resolve_conversion_file_ids_for_dataset_fn=lambda **_kwargs: ["c1"],
        get_dataset_curator_fn=lambda: curated,
        collect_scope_counts_fn=lambda _curator, _request: {
            "lessons": 10,
            "git": 7,
            "task_history": 3,
        },
        ingest_uploads_for_curate_fn=lambda _curator, _ids: 2,
        ingest_converted_files_for_curate_fn=lambda _curator, _req, _ids: 1,
        logger=logger,
    )
    assert curated_payload["uploads_count"] == 2
    assert curated_payload["converted_count"] == 1
    assert curated_payload["removed_low_quality"] == 2

    preview_req = DatasetScopeRequest(
        include_lessons=True,
        include_git=False,
        include_task_history=False,
        upload_ids=["u1"],
        conversion_file_ids=["c1"],
        quality_profile="strict",
    )
    preview_payload = academy_training.preview_dataset_scope(
        request=preview_req,
        req=SimpleNamespace(),
        resolve_conversion_file_ids_for_dataset_fn=lambda **_kwargs: ["c1"],
        get_dataset_curator_fn=lambda: curated,
        collect_scope_counts_fn=lambda _curator, _request: {
            "lessons": 4,
            "git": 0,
            "task_history": 0,
        },
        ingest_uploads_for_preview_fn=lambda _curator, _ids, warnings: warnings.append(
            "u-warn"
        )
        or 1,
        ingest_converted_files_for_preview_fn=lambda _curator, _req, _ids, warnings: (
            warnings.append("c-warn") or 2
        ),
        add_low_examples_warning_fn=lambda warnings, _n, _profile: warnings.append(
            "low"
        ),
        build_preview_samples_fn=lambda _curator: [{"instruction": "i"}],
        logger=logger,
    )
    assert preview_payload["total_examples"] == 23
    assert preview_payload["by_source"]["uploads"] == 1
    assert preview_payload["by_source"]["converted"] == 2
    assert preview_payload["warnings"] == ["u-warn", "c-warn", "low"]


def test_academy_history_error_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    logger = _Logger()

    # load_jobs_history: existing directory path should trigger open() failure branch.
    assert academy_history.load_jobs_history(tmp_path, logger=logger) == []
    assert logger.warnings

    jobs_file = tmp_path / "jobs.jsonl"
    jobs_file.write_text('{"job_id":"j1"}\n', encoding="utf-8")

    def _raise_load(*_args: Any, **_kwargs: Any):
        raise RuntimeError("load-boom")

    monkeypatch.setattr(academy_history, "load_jobs_history", _raise_load)
    academy_history.update_job_in_history(
        "j1", {"status": "running"}, jobs_file, logger=logger
    )
    assert any("Failed to update job" in msg for msg in logger.errors)

    blocked_file = tmp_path / "blocked"
    blocked_file.mkdir()
    academy_history.save_job_to_history({"job_id": "j2"}, blocked_file, logger=logger)
    assert any("Failed to save job" in msg for msg in logger.errors)


def test_academy_uploads_validation_and_ingestion(tmp_path: Path) -> None:
    logger = _Logger()

    class _Form:
        def getlist(self, _key: str):
            return [1, 2]

        def get(self, key: str, default: str = ""):
            if key == "tag":
                return 123
            if key == "description":
                return None
            return default

    files, tag, desc = au.parse_upload_form(_Form())
    assert files == [1, 2]
    assert tag == "user-upload"
    assert desc == ""

    assert (
        au.validate_training_record({"instruction": "short", "output": "short"})
        is False
    )
    assert au.validate_training_record("bad") is False
    assert (
        au.validate_training_record(
            {"instruction": "instruction-12345", "output": "output-123456789"}
        )
        is True
    )

    curator = SimpleNamespace(examples=[])
    assert (
        au.append_training_record_if_valid(
            curator,
            {"instruction": "instruction-12345", "output": "output-123456789"},
        )
        == 1
    )
    assert (
        au.append_training_record_if_valid(curator, {"instruction": "a", "output": "b"})
        == 0
    )

    text_file = tmp_path / "sample.md"
    text_file.write_text(
        "Instruction A long\n\nOutput A long enough\n\nInstruction B",
        encoding="utf-8",
    )
    assert au.ingest_text_upload(curator, text_file) == 1

    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "instruction,input,output\ninstruction-12345,,output-123456789\n",
        encoding="utf-8",
    )
    assert au.ingest_csv_upload(curator, csv_file) == 1

    assert len(au.build_preview_samples(SimpleNamespace(examples=[]))) == 0
    samples = au.build_preview_samples(
        SimpleNamespace(
            examples=[
                {
                    "instruction": "i",
                    "input": "",
                    "output": "x" * 260,
                }
            ]
        )
    )
    assert samples[0]["output"].endswith("...")

    warnings: list[str] = []
    au.add_low_examples_warning(
        warnings=warnings,
        total_examples=10,
        quality_profile="balanced",
    )
    assert warnings and "Low number of examples" in warnings[0]

    upload_file = tmp_path / "u1.jsonl"
    upload_file.write_text(
        '{"instruction":"instruction-12345","output":"output-123456789"}\n',
        encoding="utf-8",
    )

    calls: list[str] = []

    def _ingest(_curator: Any, _path: Path) -> int:
        calls.append("ok")
        return 2

    count = au.ingest_uploads_for_ids(
        curator=curator,
        upload_ids=["../bad", "missing", upload_file.name],
        uploads_dir=tmp_path,
        check_path_traversal_fn=lambda fid: ".." not in fid,
        ingest_upload_file_fn=_ingest,
        logger=logger,
    )
    assert count == 2
    assert calls == ["ok"]

    class _ExcWithDetail(Exception):
        def __init__(self, detail: str):
            super().__init__(detail)
            self.detail = detail

    preview_warnings: list[str] = []
    converted_count = au.ingest_converted_files_for_preview(
        curator=curator,
        conversion_file_ids=["../bad", "raw", "gone"],
        warnings=preview_warnings,
        check_path_traversal_fn=lambda fid: ".." not in fid,
        resolve_existing_user_file_fn=lambda *, file_id: (
            {"category": "source"},
            upload_file,
        )
        if file_id == "raw"
        else (_ for _ in ()).throw(_ExcWithDetail("gone")),
        ingest_upload_file_fn=_ingest,
    )
    assert converted_count == 0
    assert len(preview_warnings) == 3


@pytest.mark.asyncio
async def test_academy_uploads_process_and_persist_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logger = _Logger()

    class _Upload:
        def __init__(self, filename: str):
            self.filename = filename

        async def read(self, _size: int) -> bytes:
            return b""

    test_file = _Upload("ok.jsonl")

    cleanup_calls: list[Path] = []
    saved: list[dict[str, Any]] = []

    async def _persist_ok(**_kwargs: Any):
        return (12, b'{"instruction":"i","output":"o"}'), None

    monkeypatch.setattr(au, "persist_with_limits", _persist_ok)
    info, err = await au.process_uploaded_file(
        file=test_file,
        uploads_dir=tmp_path,
        tag="tag",
        description="desc",
        settings=SimpleNamespace(
            ACADEMY_ALLOWED_EXTENSIONS=[".jsonl"],
            ACADEMY_ALLOWED_DATASET_EXTENSIONS=[".jsonl"],
            ACADEMY_MAX_UPLOAD_SIZE_MB=1,
        ),
        check_path_traversal_fn=lambda _name: True,
        validate_file_extension_fn=lambda _name, allowed_extensions=None: bool(
            allowed_extensions
        ),
        compute_bytes_hash_fn=lambda _payload: "sha",
        estimate_records_from_content_fn=lambda *_args: 3,
        save_upload_metadata_fn=lambda payload: saved.append(payload),
        cleanup_uploaded_file_fn=lambda path: cleanup_calls.append(path),
        logger=logger,
    )
    assert err is None
    assert info is not None and info["records_estimate"] == 3
    assert saved and saved[0]["sha256"] == "sha"

    async def _persist_none(**_kwargs: Any):
        return None, None

    monkeypatch.setattr(au, "persist_with_limits", _persist_none)
    info2, err2 = await au.process_uploaded_file(
        file=test_file,
        uploads_dir=tmp_path,
        tag="tag",
        description="desc",
        settings=SimpleNamespace(
            ACADEMY_ALLOWED_EXTENSIONS=[".jsonl"],
            ACADEMY_ALLOWED_DATASET_EXTENSIONS=[".jsonl"],
            ACADEMY_MAX_UPLOAD_SIZE_MB=1,
        ),
        check_path_traversal_fn=lambda _name: True,
        validate_file_extension_fn=lambda _name, allowed_extensions=None: bool(
            allowed_extensions
        ),
        compute_bytes_hash_fn=lambda _payload: "sha",
        estimate_records_from_content_fn=lambda *_args: 0,
        save_upload_metadata_fn=lambda _payload: None,
        cleanup_uploaded_file_fn=lambda path: cleanup_calls.append(path),
        logger=logger,
    )
    assert info2 is None
    assert err2 is not None and "Failed to persist file" in err2["error"]

    def _boom_build(**_kwargs: Any):
        raise RuntimeError("boom")

    monkeypatch.setattr(au, "build_upload_info", _boom_build)
    monkeypatch.setattr(au, "persist_with_limits", _persist_ok)
    _, err3 = await au.process_uploaded_file(
        file=test_file,
        uploads_dir=tmp_path,
        tag="tag",
        description="desc",
        settings=SimpleNamespace(
            ACADEMY_ALLOWED_EXTENSIONS=[".jsonl"],
            ACADEMY_ALLOWED_DATASET_EXTENSIONS=[".jsonl"],
            ACADEMY_MAX_UPLOAD_SIZE_MB=1,
        ),
        check_path_traversal_fn=lambda _name: True,
        validate_file_extension_fn=lambda _name, allowed_extensions=None: bool(
            allowed_extensions
        ),
        compute_bytes_hash_fn=lambda _payload: "sha",
        estimate_records_from_content_fn=lambda *_args: 0,
        save_upload_metadata_fn=lambda _payload: None,
        cleanup_uploaded_file_fn=lambda path: cleanup_calls.append(path),
        logger=logger,
    )
    assert err3 is not None and "Unexpected error" in err3["error"]
    assert cleanup_calls


@pytest.mark.asyncio
async def test_academy_conversion_upload_and_resolve_user_file(tmp_path: Path) -> None:
    workspace = {
        "base_dir": tmp_path,
        "metadata_file": tmp_path / "files.json",
        "source_dir": tmp_path / "source",
        "converted_dir": tmp_path / "converted",
    }
    workspace["source_dir"].mkdir(parents=True, exist_ok=True)
    workspace["converted_dir"].mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []

    class _Upload:
        def __init__(self, filename: str):
            self.filename = filename

    async def _persist(**kwargs: Any):
        path = kwargs["file_path"]
        path.write_bytes(b"{}")
        return (2, b"{}"), None

    payload = await academy_conversion.upload_conversion_files_for_user(
        files=[_Upload("a.json"), _Upload("skip.txt")],
        workspace=workspace,
        settings=SimpleNamespace(
            ACADEMY_ALLOWED_EXTENSIONS=[".json", ".txt"],
            ACADEMY_ALLOWED_CONVERSION_EXTENSIONS=[".json"],
        ),
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        save_user_conversion_metadata_fn=lambda _path, updated: items.clear()
        or items.extend(updated),
        validate_upload_filename_fn=lambda file,
        _settings,
        *,
        allowed_extensions=None: (
            file.filename,
            None,
        )
        if file.filename.endswith(".json")
        else (None, {"name": file.filename, "error": "bad ext"}),
        persist_with_limits_fn=_persist,
        build_conversion_file_id_fn=lambda extension=None: f"id1{extension or ''}",
        build_conversion_item_fn=academy_conversion.build_conversion_item,
        normalize_conversion_item_fn=academy_conversion.normalize_conversion_item,
    )
    assert payload["uploaded"] == 1
    assert payload["failed"] == 1

    src = workspace["source_dir"] / "id1.json"
    src.write_text("{}", encoding="utf-8")
    items.append({"file_id": "id1.json", "category": "source"})

    item, file_path = academy_conversion.resolve_existing_user_file(
        workspace=workspace,
        file_id="id1.json",
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        find_conversion_item_fn=academy_conversion.find_conversion_item,
    )
    assert item["file_id"] == "id1.json"
    assert file_path.exists()


def _load_route_handlers_module() -> Any:
    module_path = (
        Path(__file__).resolve().parent.parent
        / "venom_core"
        / "services"
        / "academy"
        / "route_handlers.py"
    )
    spec = importlib.util.spec_from_file_location("route_handlers_cov_fix", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_route_academy_stub() -> Any:
    class _AcademyRouteError(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    logger = _Logger()
    academy = SimpleNamespace(
        logger=logger,
        AcademyRouteError=_AcademyRouteError,
        _to_http_exception=lambda exc: HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ),
        _ensure_academy_enabled=lambda: None,
        require_localhost_request=lambda _req: None,
        DATASET_REQUIRED_DETAIL="dataset required",
        TERMINAL_JOB_STATUSES={"finished", "failed", "cancelled"},
    )
    return academy


def test_route_handlers_curate_and_training_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    route_handlers = _load_route_handlers_module()
    academy = _build_route_academy_stub()

    request = DatasetScopeRequest(include_lessons=True, include_git=False)
    academy.academy_training = SimpleNamespace(
        curate_dataset_scope=lambda **_kwargs: {
            "dataset_path": str(tmp_path / "d.jsonl"),
            "stats": {"total_examples": 5},
            "scope_counts": {"lessons": 1, "git": 0, "task_history": 0},
            "uploads_count": 1,
            "converted_count": 0,
            "removed_low_quality": 0,
            "quality_profile": "balanced",
        },
        resolve_dataset_path=lambda *_args, **_kwargs: str(tmp_path / "d.jsonl"),
        ensure_trainable_base_model=lambda **_kwargs: "phi3",
        build_job_record=lambda **_kwargs: {
            "job_id": "training_1",
            "parameters": {"lora_rank": 8},
        },
    )
    academy.academy_uploads = SimpleNamespace(
        ingest_uploads_for_ids=lambda **_kwargs: 1,
        ingest_converted_files_for_ids=lambda **_kwargs: 0,
    )
    academy._resolve_conversion_file_ids_for_dataset = lambda **_kwargs: []
    academy._get_dataset_curator = lambda: SimpleNamespace()
    academy._get_uploads_dir = lambda: tmp_path
    academy._check_path_traversal = lambda _path: True
    academy._ingest_upload_file = lambda *_args: 1

    result = route_handlers.curate_dataset_handler(
        request=request,
        req=SimpleNamespace(),
        academy=academy,
    )
    assert result.success is True
    assert result.statistics["total_examples"] == 5

    updates: list[dict[str, Any]] = []
    academy._get_gpu_habitat = lambda: SimpleNamespace(
        run_training_job=lambda **_kwargs: {
            "container_id": "cid",
            "job_name": "training_1",
        }
    )
    academy._save_job_to_history = lambda _job: None
    academy._update_job_in_history = lambda _job_id, payload: updates.append(payload)
    academy._is_model_trainable = lambda _name: True

    fake_settings = SimpleNamespace(
        ACADEMY_TRAINING_DIR=str(tmp_path),
        ACADEMY_DEFAULT_BASE_MODEL="phi3",
        ACADEMY_MODELS_DIR=str(tmp_path / "models"),
    )
    monkeypatch.setitem(
        sys.modules, "venom_core.config", SimpleNamespace(SETTINGS=fake_settings)
    )

    training_resp = route_handlers.start_training_handler(
        request=TrainingRequest(),
        req=SimpleNamespace(),
        academy=academy,
    )
    assert training_resp.success is True
    assert any(item.get("status") == "running" for item in updates)


def test_route_handlers_convert_dataset_file_error_mapping() -> None:
    route_handlers = _load_route_handlers_module()
    academy = _build_route_academy_stub()
    academy._resolve_user_id = lambda _req: "u1"
    academy._get_user_conversion_workspace = lambda _uid: {"base_dir": Path(".")}
    academy._check_path_traversal = lambda _fid: True
    academy._user_conversion_metadata_lock = lambda _path: _dummy_lock(Path("."))
    academy._load_user_conversion_metadata = lambda _path: []
    academy._save_user_conversion_metadata = lambda _path, _items: None
    academy._find_conversion_item = lambda _items, _fid: None
    academy._resolve_workspace_file_path = lambda *_args, **_kwargs: Path(".")
    academy._source_to_records = lambda _path: []
    academy._write_records_as_target = lambda _records, _fmt: Path("x")
    academy._build_conversion_item = lambda **_kwargs: {}
    academy._normalize_conversion_item = lambda item: item

    academy.academy_conversion = SimpleNamespace(
        convert_dataset_source_file=lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Invalid file_id: bad")
        )
    )
    with pytest.raises(HTTPException) as exc_400:
        route_handlers.convert_dataset_file_handler(
            file_id="bad",
            payload=SimpleNamespace(target_format="json"),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc_400.value.status_code == 400

    academy.academy_conversion = SimpleNamespace(
        convert_dataset_source_file=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
    )
    with pytest.raises(HTTPException) as exc_500:
        route_handlers.convert_dataset_file_handler(
            file_id="x",
            payload=SimpleNamespace(target_format="json"),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc_500.value.status_code == 500


@pytest.mark.asyncio
async def test_route_handlers_upload_guard_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_handlers = _load_route_handlers_module()
    academy = _build_route_academy_stub()
    academy.academy_uploads = SimpleNamespace(
        parse_upload_form=lambda form: form.getlist("files"),
    )
    academy.academy_uploads.parse_upload_form = lambda form: (
        form.getlist("files"),
        "tag",
        "",
    )
    academy._process_uploaded_file = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("should not be called")
    )

    fake_settings = SimpleNamespace(ACADEMY_MAX_UPLOADS_PER_REQUEST=1)
    monkeypatch.setitem(
        sys.modules, "venom_core.config", SimpleNamespace(SETTINGS=fake_settings)
    )

    class _Req:
        async def form(self):
            return SimpleNamespace(
                getlist=lambda _key: [
                    SimpleNamespace(filename="a"),
                    SimpleNamespace(filename="b"),
                ],
                get=lambda _key, default="": default,
            )

    with pytest.raises(HTTPException) as exc:
        await route_handlers.upload_dataset_files_handler(
            req=_Req(),
            academy=academy,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_academy_uploads_persist_with_limits_error_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cleanup_calls: list[Path] = []
    logger = _Logger()

    async def _too_large(**_kwargs: Any):
        raise ValueError("FILE_TOO_LARGE:2048")

    monkeypatch.setattr(au, "persist_uploaded_file", _too_large)
    result, err = await au.persist_with_limits(
        file=SimpleNamespace(),
        file_path=tmp_path / "big.jsonl",
        filename="big.jsonl",
        settings=SimpleNamespace(ACADEMY_MAX_UPLOAD_SIZE_MB=1),
        logger=logger,
        cleanup_uploaded_file_fn=lambda path: cleanup_calls.append(path),
    )
    assert result is None
    assert err is not None and "File too large" in err["error"]

    async def _value_err(**_kwargs: Any):
        raise ValueError("broken")

    monkeypatch.setattr(au, "persist_uploaded_file", _value_err)
    _, err2 = await au.persist_with_limits(
        file=SimpleNamespace(),
        file_path=tmp_path / "bad.jsonl",
        filename="bad.jsonl",
        settings=SimpleNamespace(ACADEMY_MAX_UPLOAD_SIZE_MB=1),
        logger=logger,
        cleanup_uploaded_file_fn=lambda path: cleanup_calls.append(path),
    )
    assert err2 is not None and "Failed to save file" in err2["error"]

    async def _generic_err(**_kwargs: Any):
        raise OSError("disk")

    monkeypatch.setattr(au, "persist_uploaded_file", _generic_err)
    _, err3 = await au.persist_with_limits(
        file=SimpleNamespace(),
        file_path=tmp_path / "io.jsonl",
        filename="io.jsonl",
        settings=SimpleNamespace(ACADEMY_MAX_UPLOAD_SIZE_MB=1),
        logger=logger,
        cleanup_uploaded_file_fn=lambda path: cleanup_calls.append(path),
    )
    assert err3 is not None and "Failed to save file" in err3["error"]
    assert len(cleanup_calls) == 3


def test_academy_uploads_delete_upload_file_and_build_response(tmp_path: Path) -> None:
    logger = _Logger()
    with pytest.raises(ValueError):
        au.delete_upload_file(
            file_id="../bad",
            uploads_dir=tmp_path,
            check_path_traversal_fn=lambda file_id: ".." not in file_id,
            delete_upload_metadata_fn=lambda _fid: None,
            logger=logger,
        )

    with pytest.raises(FileNotFoundError):
        au.delete_upload_file(
            file_id="missing",
            uploads_dir=tmp_path,
            check_path_traversal_fn=lambda _fid: True,
            delete_upload_metadata_fn=lambda _fid: None,
            logger=logger,
        )

    file_path = tmp_path / "keep.json"
    file_path.write_text("{}", encoding="utf-8")
    deleted_ids: list[str] = []
    payload = au.delete_upload_file(
        file_id=file_path.name,
        uploads_dir=tmp_path,
        check_path_traversal_fn=lambda _fid: True,
        delete_upload_metadata_fn=lambda fid: deleted_ids.append(fid),
        logger=logger,
    )
    assert payload["success"] is True
    assert deleted_ids == [file_path.name]

    response = au.build_upload_response(
        uploaded_files=[{"id": "1"}],
        failed_files=[{"name": "bad"}],
    )
    assert response["uploaded"] == 1
    assert "failed" in response["message"]


def test_academy_uploads_validate_filename_and_cleanup(tmp_path: Path) -> None:
    logger = _Logger()
    upload = SimpleNamespace(filename=None)
    filename, err = au.validate_upload_filename(
        file=upload,
        settings=SimpleNamespace(ACADEMY_ALLOWED_EXTENSIONS=[".jsonl"]),
        check_path_traversal_fn=lambda _name: True,
        validate_file_extension_fn=lambda _name, allowed_extensions=None: True,
    )
    assert filename is None and err is None

    upload.filename = "../bad"
    _, err2 = au.validate_upload_filename(
        file=upload,
        settings=SimpleNamespace(ACADEMY_ALLOWED_EXTENSIONS=[".jsonl"]),
        check_path_traversal_fn=lambda _name: False,
        validate_file_extension_fn=lambda _name, allowed_extensions=None: True,
    )
    assert err2 is not None and "path traversal" in err2["error"]

    upload.filename = "a.exe"
    _, err3 = au.validate_upload_filename(
        file=upload,
        settings=SimpleNamespace(ACADEMY_ALLOWED_EXTENSIONS=[".jsonl"]),
        check_path_traversal_fn=lambda _name: True,
        validate_file_extension_fn=lambda _name, allowed_extensions=None: False,
    )
    assert err3 is not None and "Invalid file extension" in err3["error"]

    missing = tmp_path / "missing.bin"
    au.cleanup_uploaded_file(missing, logger=logger)
    existing = tmp_path / "x.bin"
    existing.write_bytes(b"x")

    original_unlink = os.unlink

    def _boom_unlink(path: str | bytes, *args: Any, **kwargs: Any):
        if Path(path) == existing:
            raise OSError("unlink-boom")
        return original_unlink(path, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "unlink", _boom_unlink)
        mp.setattr(Path, "unlink", lambda self, **_kwargs: _boom_unlink(self))
        au.cleanup_uploaded_file(existing, logger=logger)

    assert logger.warnings
