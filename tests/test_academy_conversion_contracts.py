from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from venom_core.api.routes import academy_conversion


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
