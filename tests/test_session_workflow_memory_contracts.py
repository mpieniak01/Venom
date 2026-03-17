"""
Coverage tests for:
  - venom_core/services/session_store.py
  - venom_core/services/workflow_operations.py
  - venom_core/memory/workflow_store.py
  - venom_core/memory/memory_skill.py
  - venom_core/memory/embedding_service.py

Goals: cover CRUD, TTL/error handling, status transitions, storage errors.
All external calls (LLM, model, DB) are mocked.
"""

# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# session_store.py
# ---------------------------------------------------------------------------
from venom_core.services.session_store import SessionStore


class TestSessionStoreEdgeCases:
    """Additional edge cases for SessionStore not covered by base tests."""

    # ------------------------------------------------------------------
    # _resolve_store_path: no store_path → return default (line 41)
    # ------------------------------------------------------------------
    def test_resolve_default_path_when_store_path_is_none(self, tmp_path):
        """When store_path=None, the default path inside MEMORY_ROOT is used."""
        with patch("venom_core.services.session_store.SETTINGS") as mock_settings:
            mock_settings.MEMORY_ROOT = str(tmp_path)
            store = SessionStore(store_path=None)
        expected = (tmp_path / "session_store.json").resolve()
        assert store._store_path == expected

    # ------------------------------------------------------------------
    # _resolve_store_path: relative path → resolved under MEMORY_ROOT (line 45)
    # ------------------------------------------------------------------
    def test_resolve_relative_store_path(self, tmp_path):
        """A relative store_path should be resolved under MEMORY_ROOT."""
        with patch("venom_core.services.session_store.SETTINGS") as mock_settings:
            mock_settings.MEMORY_ROOT = str(tmp_path)
            store = SessionStore(store_path="sub/session.json")
        expected = (tmp_path / "sub" / "session.json").resolve()
        assert store._store_path == expected

    # ------------------------------------------------------------------
    # _load: sessions field is not a dict (lines 77-80)
    # ------------------------------------------------------------------
    def test_load_ignores_non_dict_sessions(self, tmp_path):
        """If 'sessions' in JSON is a list, _sessions should be reset to {}."""
        store_path = tmp_path / "s.json"
        store_path.write_text(
            json.dumps({"boot_id": "x", "sessions": ["bad"]}),
            encoding="utf-8",
        )
        store = SessionStore(store_path=str(store_path))
        assert store._sessions == {}

    # ------------------------------------------------------------------
    # _load: JSON load exception (lines 78-80 except block)
    # ------------------------------------------------------------------
    def test_load_exception_resets_sessions(self, tmp_path):
        """Corrupt JSON file should silently reset sessions to {}."""
        store_path = tmp_path / "s.json"
        store_path.write_text("not json!!!", encoding="utf-8")
        store = SessionStore(store_path=str(store_path))
        assert store._sessions == {}

    # ------------------------------------------------------------------
    # _save: exception is swallowed (line 88)
    # ------------------------------------------------------------------
    def test_save_exception_is_swallowed(self, tmp_path):
        """_save should log a warning and not raise on write errors."""
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        # Make the store path un-writable by replacing with a bad path
        store._store_path = Path("/no/such/dir/session.json")
        # Should not raise
        store._save()

    # ------------------------------------------------------------------
    # append_message: empty session_id → early return (line 98)
    # ------------------------------------------------------------------
    def test_append_message_empty_session_id_is_noop(self, tmp_path):
        """append_message with falsy session_id should be a no-op."""
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store.append_message("", {"role": "user", "content": "x"})
        assert store._sessions == {}

    # ------------------------------------------------------------------
    # append_message: knowledge_metadata merging with existing meta (lines 107-112)
    # ------------------------------------------------------------------
    def test_append_message_merges_knowledge_metadata_with_existing(self, tmp_path):
        """New knowledge_metadata should be merged into entry's existing metadata."""
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        entry_with_meta = {
            "role": "user",
            "content": "text",
            "knowledge_metadata": {"key_a": "v1"},
        }
        store.append_message(
            "s1",
            entry_with_meta,
            knowledge_metadata={"key_b": "v2"},
        )
        history = store.get_history("s1")
        assert len(history) == 1
        km = history[0]["knowledge_metadata"]
        assert km["key_a"] == "v1"
        assert km["key_b"] == "v2"

    # ------------------------------------------------------------------
    # get_history: empty session_id → [] (line 125)
    # ------------------------------------------------------------------
    def test_get_history_empty_session_id_returns_empty(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        assert store.get_history("") == []

    # ------------------------------------------------------------------
    # get_history: with limit (line 133)
    # ------------------------------------------------------------------
    def test_get_history_with_limit(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        for i in range(5):
            store.append_message("s1", {"role": "user", "content": str(i)})
        result = store.get_history("s1", limit=2)
        assert len(result) == 2
        assert result[-1]["content"] == "4"

    # ------------------------------------------------------------------
    # set_summary: empty session_id → early return (line 143)
    # ------------------------------------------------------------------
    def test_set_summary_empty_session_id_is_noop(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store.set_summary("", "summary text")
        assert store._sessions == {}

    # ------------------------------------------------------------------
    # get_summary: empty session_id → None (line 173)
    # ------------------------------------------------------------------
    def test_get_summary_empty_session_id_returns_none(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        assert store.get_summary("") is None

    # ------------------------------------------------------------------
    # get_summary: summary=None branch (line 159 + fallthrough to None)
    # ------------------------------------------------------------------
    def test_get_summary_no_summary_returns_none(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store.append_message("s1", {"role": "user", "content": "x"})
        assert store.get_summary("s1") is None

    # ------------------------------------------------------------------
    # get_summary: dict summary with non-string content → None (line 167)
    # ------------------------------------------------------------------
    def test_get_summary_dict_with_non_string_content(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store._sessions["s1"] = {"summary": {"content": 42}}
        assert store.get_summary("s1") is None

    # ------------------------------------------------------------------
    # get_summary_entry: empty session_id → None (line 173)
    # ------------------------------------------------------------------
    def test_get_summary_entry_empty_session_id(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        assert store.get_summary_entry("") is None

    # ------------------------------------------------------------------
    # get_summary_entry: session without summary → None (lines 188->191)
    # ------------------------------------------------------------------
    def test_get_summary_entry_no_summary_returns_none(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store.append_message("s1", {"role": "user", "content": "x"})
        assert store.get_summary_entry("s1") is None

    # ------------------------------------------------------------------
    # get_summary_entry: dict summary → returns copy (line 180)
    # ------------------------------------------------------------------
    def test_get_summary_entry_dict_summary(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store._sessions["s1"] = {
            "summary": {"content": "text", "knowledge_metadata": {"k": "v"}}
        }
        result = store.get_summary_entry("s1")
        assert result == {"content": "text", "knowledge_metadata": {"k": "v"}}

    # ------------------------------------------------------------------
    # clear_session: does not exist → returns False (lines 194-196 via else)
    # ------------------------------------------------------------------
    def test_clear_session_nonexistent_returns_false(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        assert store.clear_session("nonexistent") is False

    # ------------------------------------------------------------------
    # clear_all: clears all sessions (lines 193-196)
    # ------------------------------------------------------------------
    def test_clear_all_empties_all_sessions(self, tmp_path):
        store = SessionStore(store_path=str(tmp_path / "s.json"))
        store.append_message("s1", {"role": "user", "content": "a"})
        store.append_message("s2", {"role": "user", "content": "b"})
        store.clear_all()
        assert store._sessions == {}
        assert store.get_history("s1") == []


# ---------------------------------------------------------------------------
# workflow_operations.py
# ---------------------------------------------------------------------------
from venom_core.api.schemas.workflow_control import (
    ReasonCode,
    WorkflowOperation,
    WorkflowStatus,
)
from venom_core.services.workflow_operations import (
    WorkflowOperationService,
    get_workflow_service,
)


class TestWorkflowOperationsEdgeCases:
    """Cover missing lines in WorkflowOperationService."""

    @pytest.fixture(autouse=True)
    def mock_audit(self):
        """Mock the audit trail so tests don't create real audit entries."""
        with patch(
            "venom_core.services.workflow_operations.get_control_plane_audit_trail"
        ) as mock_get:
            mock_get.return_value = MagicMock()
            yield mock_get

    @pytest.fixture
    def service(self):
        return WorkflowOperationService()

    # ------------------------------------------------------------------
    # _validate_and_parse_uuid: AttributeError path (lines 123-124)
    # ------------------------------------------------------------------
    def test_validate_uuid_raises_for_none_input(self, service):
        """None input should raise ValueError (AttributeError wrapped as ValueError)."""
        with pytest.raises((ValueError, TypeError)):
            service._validate_and_parse_uuid(None)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # _invalid_uuid_response (line 135)
    # ------------------------------------------------------------------
    def test_invalid_uuid_response_structure(self, service):
        """_invalid_uuid_response returns a properly shaped response."""
        resp = service._invalid_uuid_response("bad-id", WorkflowOperation.PAUSE)
        assert resp.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert resp.status == WorkflowStatus.IDLE
        assert "bad-id" in resp.message

    # ------------------------------------------------------------------
    # pause_workflow: invalid UUID (lines 167-168)
    # ------------------------------------------------------------------
    def test_pause_invalid_uuid_returns_error(self, service):
        resp = service.pause_workflow("not-a-uuid", "system")
        assert resp.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert resp.operation == WorkflowOperation.PAUSE

    # ------------------------------------------------------------------
    # resume_workflow: invalid UUID (lines 259-260)
    # ------------------------------------------------------------------
    def test_resume_invalid_uuid_returns_error(self, service):
        resp = service.resume_workflow("bad-uuid", "system")
        assert resp.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert resp.operation == WorkflowOperation.RESUME

    # ------------------------------------------------------------------
    # cancel_workflow: invalid UUID (lines 342-343)
    # ------------------------------------------------------------------
    def test_cancel_invalid_uuid_returns_error(self, service):
        resp = service.cancel_workflow("bad", "system")
        assert resp.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert resp.operation == WorkflowOperation.CANCEL

    # ------------------------------------------------------------------
    # retry_workflow: invalid UUID (lines 427-428)
    # ------------------------------------------------------------------
    def test_retry_invalid_uuid_returns_error(self, service):
        resp = service.retry_workflow("bad", "system", step_id="s1")
        assert resp.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert resp.operation == WorkflowOperation.RETRY

    # ------------------------------------------------------------------
    # dry_run: invalid UUID (lines 517-518)
    # ------------------------------------------------------------------
    def test_dry_run_invalid_uuid_returns_error(self, service):
        resp = service.dry_run("bad", "system")
        assert resp.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert resp.operation == WorkflowOperation.DRY_RUN

    # ------------------------------------------------------------------
    # get_latest_workflow_status: empty workflows (lines 569-571)
    # ------------------------------------------------------------------
    def test_get_latest_status_empty_returns_idle(self, service):
        assert service.get_latest_workflow_status() == WorkflowStatus.IDLE

    # ------------------------------------------------------------------
    # get_latest_workflow_status: with workflows (lines 573-580)
    # ------------------------------------------------------------------
    def test_get_latest_status_with_workflows(self, service):
        wf_id = str(uuid4())
        service.register_workflow(wf_id, WorkflowStatus.RUNNING)
        status = service.get_latest_workflow_status()
        assert status == WorkflowStatus.RUNNING

    # ------------------------------------------------------------------
    # get_latest_workflow_status: KeyError/ValueError fallback (lines 577-580)
    # ------------------------------------------------------------------
    def test_get_latest_status_bad_status_value_returns_idle(self, service):
        wf_id = str(uuid4())
        service.register_workflow(wf_id)
        service._workflows[wf_id]["status"] = "INVALID_STATUS_VALUE"
        status = service.get_latest_workflow_status()
        assert status == WorkflowStatus.IDLE

    # ------------------------------------------------------------------
    # get_workflow_service alias (line 619)
    # ------------------------------------------------------------------
    def test_get_workflow_service_alias(self):
        svc1 = get_workflow_service()
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        svc2 = get_workflow_operation_service()
        assert svc1 is svc2

    # ------------------------------------------------------------------
    # pause_workflow: forbidden transition triggers audit log (lines 193-201)
    # ------------------------------------------------------------------
    def test_pause_idle_workflow_triggers_audit_failure_log(self, service, mock_audit):
        wf_id = str(uuid4())
        service.register_workflow(wf_id)
        resp = service.pause_workflow(wf_id, "system")
        assert resp.reason_code == ReasonCode.FORBIDDEN_TRANSITION
        # Audit log_operation should have been called with result="failure"
        audit_instance = service._audit_trail
        assert audit_instance.log_operation.called
        call_kwargs = audit_instance.log_operation.call_args[1]
        assert call_kwargs["result"] == "failure"


# ---------------------------------------------------------------------------
# workflow_store.py
# ---------------------------------------------------------------------------
from venom_core.memory.workflow_store import Workflow, WorkflowStep, WorkflowStore


class TestWorkflowStoreCoverage:
    """Cover missing lines in WorkflowStore."""

    @pytest.fixture
    def ws(self, tmp_path):
        return WorkflowStore(workspace_root=str(tmp_path))

    @pytest.fixture
    def basic_workflow(self):
        return Workflow(
            workflow_id="wf_001",
            name="Test WF",
            description="A test workflow",
            steps=[
                WorkflowStep(
                    step_id=1,
                    action_type="click",
                    description="Click submit",
                    params={
                        "element_description": "Submit button",
                        "fallback_coords": {"x": 10, "y": 20},
                    },
                ),
                WorkflowStep(
                    step_id=2,
                    action_type="type",
                    description="Type hello",
                    params={"text": "hello", "param_name": "user_input"},
                ),
            ],
        )

    # ------------------------------------------------------------------
    # load_workflow: exception during file read (lines 145-147)
    # ------------------------------------------------------------------
    def test_load_workflow_bad_json_returns_none(self, ws):
        """Corrupt JSON workflow file returns None."""
        wf_id = "bad_wf"
        bad_file = ws.workflows_dir / f"{wf_id}.json"
        bad_file.write_text("not json", encoding="utf-8")
        result = ws.load_workflow(wf_id)
        assert result is None

    # ------------------------------------------------------------------
    # list_workflows: exception on single file (lines 174-176)
    # ------------------------------------------------------------------
    def test_list_workflows_skips_bad_file(self, ws, basic_workflow):
        """list_workflows should skip corrupt JSON files without raising."""
        ws.save_workflow(basic_workflow)
        # Create a corrupt file
        (ws.workflows_dir / "bad.json").write_text("not json", encoding="utf-8")
        result = ws.list_workflows()
        # At least the good workflow is returned
        assert any(w["workflow_id"] == "wf_001" for w in result)

    # ------------------------------------------------------------------
    # delete_workflow: unlink raises exception (lines 206-208)
    # ------------------------------------------------------------------
    def test_delete_workflow_exception_returns_false(self, ws, basic_workflow):
        """If unlink raises, delete_workflow returns False."""
        ws.save_workflow(basic_workflow)
        with patch.object(Path, "unlink", side_effect=OSError("disk full")):
            result = ws.delete_workflow("wf_001")
        assert result is False

    # ------------------------------------------------------------------
    # delete_workflow: workflow not found (line 200)
    # ------------------------------------------------------------------
    def test_delete_workflow_not_found(self, ws):
        assert ws.delete_workflow("nonexistent") is False

    # ------------------------------------------------------------------
    # update_step: step not found (line 226)
    # ------------------------------------------------------------------
    def test_update_step_not_found_returns_false(self, ws, basic_workflow):
        ws.save_workflow(basic_workflow)
        result = ws.update_step("wf_001", step_id=999, updates={"description": "x"})
        assert result is False

    # ------------------------------------------------------------------
    # update_step: workflow not found (line 222)
    # ------------------------------------------------------------------
    def test_update_step_workflow_not_found(self, ws):
        result = ws.update_step("nonexistent", step_id=1, updates={"description": "x"})
        assert result is False

    # ------------------------------------------------------------------
    # add_step: empty steps → step_id = 1 (line 267)
    # ------------------------------------------------------------------
    def test_add_step_to_empty_workflow_sets_step_id_1(self, ws):
        wf = Workflow(workflow_id="wf_empty", name="Empty", description="no steps")
        ws.save_workflow(wf)
        new_step = WorkflowStep(
            step_id=0, action_type="wait", description="wait", params={"duration": 1.0}
        )
        result = ws.add_step("wf_empty", new_step)
        assert result is True
        loaded = ws.load_workflow("wf_empty")
        assert loaded.steps[0].step_id == 1

    # ------------------------------------------------------------------
    # add_step: position insert (line 261/271)
    # ------------------------------------------------------------------
    def test_add_step_at_position(self, ws, basic_workflow):
        ws.save_workflow(basic_workflow)
        # Clear cache so fresh load from file
        ws.workflows_cache.clear()
        new_step = WorkflowStep(
            step_id=0,
            action_type="wait",
            description="Inserted step",
            params={"duration": 0.5},
        )
        result = ws.add_step("wf_001", new_step, position=0)
        assert result is True
        loaded = ws.load_workflow("wf_001")
        # The inserted step should be at index 0
        assert loaded.steps[0].description == "Inserted step"

    # ------------------------------------------------------------------
    # add_step: workflow not found returns False (line 261)
    # ------------------------------------------------------------------
    def test_add_step_workflow_not_found_returns_false(self, ws):
        step = WorkflowStep(step_id=0, action_type="click", description="x", params={})
        result = ws.add_step("nonexistent", step)
        assert result is False

    # ------------------------------------------------------------------
    # remove_step: step not found (line 294)
    # ------------------------------------------------------------------
    def test_remove_step_not_found_returns_false(self, ws, basic_workflow):
        ws.save_workflow(basic_workflow)
        result = ws.remove_step("wf_001", step_id=999)
        assert result is False

    # ------------------------------------------------------------------
    # remove_step: workflow not found returns False (line 292)
    # ------------------------------------------------------------------
    def test_remove_step_workflow_not_found(self, ws):
        assert ws.remove_step("nonexistent", step_id=1) is False

    # ------------------------------------------------------------------
    # export_to_python: hotkey, wait, disabled, and type steps (lines 392-398)
    # ------------------------------------------------------------------
    def test_export_to_python_all_step_types(self, ws, tmp_path):
        wf = Workflow(
            workflow_id="wf_export",
            name="Export WF",
            description="Test all step types",
            steps=[
                WorkflowStep(
                    step_id=1,
                    action_type="hotkey",
                    description="Press Ctrl+C",
                    params={"keys": ["ctrl", "c"]},
                ),
                WorkflowStep(
                    step_id=2,
                    action_type="wait",
                    description="Wait 2s",
                    params={"duration": 2.0},
                ),
                WorkflowStep(
                    step_id=3,
                    action_type="type",
                    description="Type with default param name",
                    params={"text": "hello"},  # no param_name → uses 'text'
                ),
                WorkflowStep(
                    step_id=4,
                    action_type="click",
                    description="Disabled click",
                    params={},
                    enabled=False,
                ),
            ],
        )
        ws.save_workflow(wf)
        output_path = ws.export_to_python("wf_export")
        assert output_path is not None
        content = Path(output_path).read_text(encoding="utf-8")
        assert "keyboard_hotkey" in content
        assert "_wait" in content
        assert "keyboard_type" in content
        assert "DISABLED" in content

    # ------------------------------------------------------------------
    # export_to_python: with explicit output_path (lines 408->413)
    # ------------------------------------------------------------------
    def test_export_to_python_with_explicit_output_path(
        self, ws, tmp_path, basic_workflow
    ):
        ws.save_workflow(basic_workflow)
        out_file = tmp_path / "my_output.py"
        result = ws.export_to_python("wf_001", output_path=out_file)
        assert result == str(out_file)
        assert out_file.exists()

    # ------------------------------------------------------------------
    # search_workflows: finds by name and description
    # ------------------------------------------------------------------
    def test_search_workflows_finds_matches(self, ws, basic_workflow):
        ws.save_workflow(basic_workflow)
        results = ws.search_workflows("test")
        assert len(results) >= 1

    # ------------------------------------------------------------------
    # _sanitize_identifier: special cases
    # ------------------------------------------------------------------
    def test_sanitize_identifier_path_traversal(self, ws):
        result = ws._sanitize_identifier("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_sanitize_identifier_starts_with_digit(self, ws):
        result = ws._sanitize_identifier("123abc")
        assert result.startswith("_")

    def test_sanitize_identifier_empty(self, ws):
        result = ws._sanitize_identifier("")
        assert result == "workflow"


# ---------------------------------------------------------------------------
# memory_skill.py
# ---------------------------------------------------------------------------
from venom_core.memory.memory_skill import MemorySkill


class TestMemorySkillCoverage:
    """Cover MemorySkill methods (file at 0% baseline)."""

    @pytest.fixture
    def mock_vector_store(self):
        return MagicMock()

    @pytest.fixture
    def skill(self, mock_vector_store):
        return MemorySkill(vector_store=mock_vector_store)

    # ------------------------------------------------------------------
    # recall: results found
    # ------------------------------------------------------------------
    def test_recall_returns_formatted_results(self, skill, mock_vector_store):
        mock_vector_store.search.return_value = [
            {
                "text": "Python is great",
                "score": 0.95,
                "metadata": {"category": "docs"},
            },
            {"text": "Venom agent", "score": 0.80, "metadata": {}},
        ]
        result = skill.recall("Python")
        assert "Python is great" in result
        assert "Venom agent" in result
        assert "docs" in result

    # ------------------------------------------------------------------
    # recall: no results
    # ------------------------------------------------------------------
    def test_recall_no_results_returns_no_match_message(self, skill, mock_vector_store):
        mock_vector_store.search.return_value = []
        result = skill.recall("unknown topic")
        assert "Nie znalazłem" in result

    # ------------------------------------------------------------------
    # recall: vector_store raises exception
    # ------------------------------------------------------------------
    def test_recall_exception_returns_error_message(self, skill, mock_vector_store):
        mock_vector_store.search.side_effect = RuntimeError("DB error")
        result = skill.recall("query")
        assert (
            "błąd" in result.lower()
            or "error" in result.lower()
            or "Wystąpił" in result
        )

    # ------------------------------------------------------------------
    # memorize: success path
    # ------------------------------------------------------------------
    def test_memorize_returns_confirmation(self, skill, mock_vector_store):
        mock_vector_store.upsert.return_value = {"message": "1 chunk(s) upserted"}
        result = skill.memorize("Important fact", category="rule")
        assert "zapisana" in result or "chunk" in result
        mock_vector_store.upsert.assert_called_once_with(
            text="Important fact",
            metadata={"category": "rule"},
            chunk_text=True,
        )

    # ------------------------------------------------------------------
    # memorize: default category
    # ------------------------------------------------------------------
    def test_memorize_default_category(self, skill, mock_vector_store):
        mock_vector_store.upsert.return_value = {"message": "saved"}
        skill.memorize("Some content")
        call_kwargs = mock_vector_store.upsert.call_args[1]
        assert call_kwargs["metadata"]["category"] == "general"

    # ------------------------------------------------------------------
    # memorize: exception from vector_store
    # ------------------------------------------------------------------
    def test_memorize_exception_returns_error_message(self, skill, mock_vector_store):
        mock_vector_store.upsert.side_effect = RuntimeError("write error")
        result = skill.memorize("content")
        assert "błąd" in result.lower() or "Wystąpił" in result

    # ------------------------------------------------------------------
    # memory_search: results found
    # ------------------------------------------------------------------
    def test_memory_search_returns_formatted_results(self, skill, mock_vector_store):
        mock_vector_store.search.return_value = [
            {
                "text": "search result",
                "score": 0.99,
                "metadata": {"category": "code"},
            }
        ]
        result = skill.memory_search("some query", limit=1)
        assert "search result" in result
        assert "0.9900" in result

    # ------------------------------------------------------------------
    # memory_search: no results
    # ------------------------------------------------------------------
    def test_memory_search_no_results(self, skill, mock_vector_store):
        mock_vector_store.search.return_value = []
        result = skill.memory_search("no results query")
        assert "Brak wyników" in result

    # ------------------------------------------------------------------
    # memory_search: exception
    # ------------------------------------------------------------------
    def test_memory_search_exception_returns_error(self, skill, mock_vector_store):
        mock_vector_store.search.side_effect = RuntimeError("boom")
        result = skill.memory_search("query")
        assert "Błąd" in result or "błąd" in result.lower()

    # ------------------------------------------------------------------
    # MemorySkill: default vector_store creation path
    # ------------------------------------------------------------------
    def test_memory_skill_default_vector_store(self):
        """MemorySkill without a vector_store argument creates its own."""
        with patch("venom_core.memory.memory_skill.VectorStore") as mock_vs_cls:
            mock_vs_cls.return_value = MagicMock()
            skill = MemorySkill()
            mock_vs_cls.assert_called_once()
            assert skill.vector_store is mock_vs_cls.return_value


# ---------------------------------------------------------------------------
# embedding_service.py
# ---------------------------------------------------------------------------
from venom_core.memory.embedding_service import (
    LOCAL_EMBEDDING_DIMENSION,
    EmbeddingService,
)


class TestEmbeddingServiceCoverage:
    """Cover missing lines in EmbeddingService."""

    # ------------------------------------------------------------------
    # __init__: FORCE_LOCAL_MODEL override (line 31)
    # ------------------------------------------------------------------
    def test_init_force_local_model(self):
        """When FORCE_LOCAL_MODEL=True and service_type=None, use local."""
        with patch("venom_core.memory.embedding_service.SETTINGS") as mock_s:
            mock_s.LLM_SERVICE_TYPE = "openai"
            mock_s.FORCE_LOCAL_MODEL = True
            mock_s.AI_MODE = "CLOUD"
            svc = EmbeddingService(service_type=None)
        assert svc.service_type == "local"

    def test_init_ai_mode_local(self):
        """When AI_MODE='LOCAL' and service_type=None, use local."""
        with patch("venom_core.memory.embedding_service.SETTINGS") as mock_s:
            mock_s.LLM_SERVICE_TYPE = "openai"
            mock_s.FORCE_LOCAL_MODEL = False
            mock_s.AI_MODE = "LOCAL"
            svc = EmbeddingService(service_type=None)
        assert svc.service_type == "local"

    # ------------------------------------------------------------------
    # _ensure_model_loaded: local ImportError (lines 54-58)
    # ------------------------------------------------------------------
    def test_ensure_model_loaded_local_import_error(self):
        """If sentence_transformers not available, ImportError is re-raised."""
        svc = EmbeddingService(service_type="local")
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with pytest.raises((ImportError, TypeError)):
                svc._ensure_model_loaded()

    # ------------------------------------------------------------------
    # _ensure_model_loaded: local model load exception → fallback mode (lines 59-65)
    # ------------------------------------------------------------------
    def test_ensure_model_loaded_local_model_exception_enables_fallback(self):
        """If SentenceTransformer raises non-ImportError, fallback mode is set."""
        svc = EmbeddingService(service_type="local")

        class FakeST:
            def __init__(self, model_name):
                raise RuntimeError("model load failed")

        # Inject a fake sentence_transformers module
        import sys
        import types

        fake_module = types.ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = FakeST
        original = sys.modules.get("sentence_transformers")
        sys.modules["sentence_transformers"] = fake_module
        try:
            svc._ensure_model_loaded()
        finally:
            if original is None:
                sys.modules.pop("sentence_transformers", None)
            else:
                sys.modules["sentence_transformers"] = original

        assert svc._local_fallback_mode is True

    # ------------------------------------------------------------------
    # _ensure_model_loaded: openai ImportError (lines 78-82)
    # ------------------------------------------------------------------
    def test_ensure_model_loaded_openai_import_error(self):
        """If openai not installed, ImportError is re-raised."""
        svc = EmbeddingService(service_type="openai")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises((ImportError, TypeError)):
                svc._ensure_model_loaded()

    # ------------------------------------------------------------------
    # _ensure_model_loaded: openai missing API key (lines 70-73)
    # ------------------------------------------------------------------
    def test_ensure_model_loaded_openai_missing_api_key(self):
        """ValueError is raised when OPENAI_API_KEY is empty."""
        svc = EmbeddingService(service_type="openai")

        class FakeOpenAI:
            def __init__(self, api_key):
                pass

        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI = FakeOpenAI
        with patch.dict(sys.modules, {"openai": fake_openai_module}):
            with patch("venom_core.memory.embedding_service.SETTINGS") as mock_s:
                mock_s.OPENAI_API_KEY = ""
                with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                    svc._ensure_model_loaded()

    # ------------------------------------------------------------------
    # _ensure_model_loaded: openai success path (lines 75-77)
    # ------------------------------------------------------------------
    def test_ensure_model_loaded_openai_success(self):
        """Successful openai init sets _client."""
        svc = EmbeddingService(service_type="openai")
        svc._model = None
        svc._client = None

        class FakeOpenAI:
            def __init__(self, api_key):
                self.api_key = api_key

        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI = FakeOpenAI
        with patch.dict(sys.modules, {"openai": fake_openai_module}):
            with patch("venom_core.memory.embedding_service.SETTINGS") as mock_s:
                mock_s.OPENAI_API_KEY = "sk-test123"
                svc._ensure_model_loaded()
        assert svc._client is not None

    # ------------------------------------------------------------------
    # _get_embedding_impl: local fallback mode path (line 102)
    # ------------------------------------------------------------------
    def test_get_embedding_impl_local_fallback_mode(self):
        """When _local_fallback_mode=True, uses _generate_fallback_embedding."""
        svc = EmbeddingService(service_type="local")
        svc._local_fallback_mode = True
        svc._ensure_model_loaded = lambda: None  # skip real loading
        result = svc._get_embedding_impl("test text")
        assert len(result) == LOCAL_EMBEDDING_DIMENSION

    # ------------------------------------------------------------------
    # get_embeddings_batch: local with model loaded (lines 182-186)
    # ------------------------------------------------------------------
    def test_get_embeddings_batch_local_with_model(self):
        """Batch embedding with local model calls model.encode."""
        svc = EmbeddingService(service_type="local")

        class DummyVec:
            def tolist(self):
                return [0.1] * 384

        class DummyModel:
            def encode(self, texts, convert_to_numpy=True):
                return [DummyVec() for _ in texts]

        svc._model = DummyModel()
        svc._ensure_model_loaded = lambda: None

        results = svc.get_embeddings_batch(["a", "b", "c"])
        assert len(results) == 3
        assert all(len(r) == 384 for r in results)

    # ------------------------------------------------------------------
    # get_embeddings_batch: openai path (line 189)
    # ------------------------------------------------------------------
    def test_get_embeddings_batch_openai_path(self):
        """Batch embedding with openai calls the API."""
        svc = EmbeddingService(service_type="openai")

        fake_resp = SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[0.1, 0.2]),
                SimpleNamespace(embedding=[0.3, 0.4]),
            ]
        )

        class FakeEmbeddingAPI:
            def create(self, model, input):
                return fake_resp

        fake_client = SimpleNamespace(embeddings=FakeEmbeddingAPI())
        svc._client = fake_client
        svc._ensure_model_loaded = lambda: None

        results = svc.get_embeddings_batch(["text1", "text2"])
        assert results == [[0.1, 0.2], [0.3, 0.4]]

    # ------------------------------------------------------------------
    # get_embeddings_batch: local model missing without fallback raises (line 185)
    # ------------------------------------------------------------------
    def test_get_embeddings_batch_local_model_none_raises(self):
        """If no model and no fallback, RuntimeError is raised."""
        svc = EmbeddingService(service_type="local")
        svc._model = None
        svc._local_fallback_mode = False
        svc._ensure_model_loaded = lambda: None  # don't actually load

        with pytest.raises(RuntimeError):
            svc.get_embeddings_batch(["a"])

    # ------------------------------------------------------------------
    # embedding_dimension: local with model loaded (using get_sentence_embedding_dimension)
    # ------------------------------------------------------------------
    def test_embedding_dimension_local_model_loaded(self):
        svc = EmbeddingService(service_type="local")
        model_mock = MagicMock()
        model_mock.get_sentence_embedding_dimension.return_value = 384
        svc._model = model_mock
        assert svc.embedding_dimension == 384

    # ------------------------------------------------------------------
    # embedding_dimension: openai
    # ------------------------------------------------------------------
    def test_embedding_dimension_openai(self):
        svc = EmbeddingService(service_type="openai")
        assert svc.embedding_dimension == 1536

    # ------------------------------------------------------------------
    # clear_cache
    # ------------------------------------------------------------------
    def test_clear_cache(self):
        svc = EmbeddingService(service_type="local")
        svc._local_fallback_mode = True
        svc._ensure_model_loaded = lambda: None
        svc.get_embedding("hello")
        svc.clear_cache()
        info = svc._get_embedding_cached.cache_info()
        assert info.currsize == 0
