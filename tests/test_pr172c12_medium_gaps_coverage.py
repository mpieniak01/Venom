"""PR-172C-12 coverage tests for medium-gap modules.

Targets:
  venom_core/learning/training_metrics_parser.py  (92% → ~100%)
  venom_core/learning/dataset_curator.py          (49% → ~75%+)
  venom_core/execution/kernel_builder.py          (73% → ~90%+)
  venom_core/infrastructure/cloud_provisioner.py  (65% → ~85%+)
  venom_core/ops/work_ledger.py                   (83% → ~95%+)
  venom_core/ui/component_engine.py               (97% → 100%)
  venom_core/ui/notifier.py                       (52% → ~85%+)
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# training_metrics_parser.py – except branches + aggregate_metrics branches
# ---------------------------------------------------------------------------


class TestTrainingMetricsParserGaps:
    """Cover remaining branches in training_metrics_parser.py."""

    def setup_method(self):
        from venom_core.learning.training_metrics_parser import TrainingMetricsParser

        self.parser = TrainingMetricsParser()

    def test_extract_epoch_continue_on_index_error(self, monkeypatch):
        """_extract_epoch continues past a bad match (only 1 group) and returns None."""
        import re

        fake_match = MagicMock()
        # group(1) OK, group(2) raises IndexError → continue
        fake_match.group = MagicMock(side_effect=[1, IndexError("no group")])
        monkeypatch.setattr(re, "search", MagicMock(side_effect=[fake_match, None, None, None]))
        result = self.parser._extract_epoch("Epoch 1/3")
        assert result is None

    def test_extract_loss_continue_on_value_error(self, monkeypatch):
        """_extract_loss continues past a match that raises ValueError and returns None."""
        import re

        fake_match = MagicMock()
        fake_match.group = MagicMock(side_effect=[ValueError("bad")])
        monkeypatch.setattr(re, "search", MagicMock(side_effect=[fake_match, None, None]))
        result = self.parser._extract_loss("Loss: ???")
        assert result is None

    def test_extract_learning_rate_continue_on_value_error(self, monkeypatch):
        """_extract_learning_rate handles ValueError and returns None."""
        import re

        fake_match = MagicMock()
        fake_match.group = MagicMock(side_effect=[ValueError("bad")])
        monkeypatch.setattr(re, "search", MagicMock(side_effect=[fake_match, None]))
        result = self.parser._extract_learning_rate("lr: ???")
        assert result is None

    def test_extract_accuracy_continue_on_value_error(self, monkeypatch):
        """_extract_accuracy handles ValueError and returns None."""
        import re

        fake_match = MagicMock()
        fake_match.group = MagicMock(side_effect=[ValueError("bad")])
        monkeypatch.setattr(re, "search", MagicMock(side_effect=[fake_match, None]))
        result = self.parser._extract_accuracy("acc: ???")
        assert result is None

    def test_extract_step_continue_on_index_error(self, monkeypatch):
        """_extract_step handles IndexError on second group and returns None."""
        import re

        fake_match = MagicMock()
        fake_match.group = MagicMock(side_effect=[100, IndexError("no group 2")])
        monkeypatch.setattr(re, "search", MagicMock(side_effect=[fake_match, None]))
        result = self.parser._extract_step("Step 100")
        assert result is None

    def test_aggregate_metrics_with_all_fields(self):
        """aggregate_metrics covers total_epochs, learning_rate, accuracy branches."""
        from venom_core.learning.training_metrics_parser import TrainingMetrics

        m1 = TrainingMetrics(
            epoch=1, total_epochs=5, loss=0.5, learning_rate=1e-4, accuracy=0.8,
            progress_percent=20.0
        )
        m2 = TrainingMetrics(
            epoch=2, total_epochs=5, loss=0.4, learning_rate=9e-5, accuracy=0.85,
            progress_percent=40.0
        )
        result = self.parser.aggregate_metrics([m1, m2])
        assert result["total_epochs"] == 5
        assert result["learning_rate"] == pytest.approx(9e-5)
        assert result["accuracy"] == pytest.approx(0.85)
        assert result["min_loss"] == pytest.approx(0.4)
        assert result["avg_loss"] == pytest.approx(0.45)
        assert result["progress_percent"] == pytest.approx(40.0)
        assert len(result["loss_history"]) == 2

    def test_aggregate_metrics_no_loss_values(self):
        """aggregate_metrics with no loss values — no min/avg/history keys."""
        from venom_core.learning.training_metrics_parser import TrainingMetrics

        m = TrainingMetrics(epoch=1, total_epochs=3)
        result = self.parser.aggregate_metrics([m])
        assert "min_loss" not in result
        assert result["current_epoch"] == 1


# ---------------------------------------------------------------------------
# dataset_curator.py – collect_from_lessons, git, task, bytes output,
#                       save_dataset (sharegpt + error), statistics
# ---------------------------------------------------------------------------


class TestDatasetCuratorGaps:
    """Cover remaining branches in dataset_curator.py."""

    def _make_curator(self, tmpdir, **kwargs):
        from venom_core.learning.dataset_curator import DatasetCurator

        return DatasetCurator(output_dir=str(tmpdir), **kwargs)

    def test_training_example_bytes_output(self):
        """TrainingExample decodes bytes output correctly."""
        from venom_core.learning.dataset_curator import TrainingExample

        ex = TrainingExample("inst", "input text", b"output bytes")
        assert ex.output == "output bytes"

    def test_collect_from_lessons_no_store(self, tmp_path):
        """collect_from_lessons returns 0 when lessons_store is None."""
        curator = self._make_curator(tmp_path)
        assert curator.collect_from_lessons() == 0

    def test_collect_from_lessons_with_success(self, tmp_path):
        """collect_from_lessons collects successful lessons."""
        mock_lesson = MagicMock()
        mock_lesson.result = "✅ sukces"
        mock_lesson.situation = "some situation"
        mock_lesson.action = "some action"
        mock_lesson.feedback = "lesson learned"
        mock_lesson.lesson_id = "lesson-1"
        mock_lesson.timestamp = "2024-01-01T00:00:00"
        mock_lesson.tags = []
        mock_lesson.metadata = {}

        mock_store = MagicMock()
        mock_store.get_all_lessons = MagicMock(return_value=[mock_lesson])

        curator = self._make_curator(tmp_path, lessons_store=mock_store)
        count = curator.collect_from_lessons()
        assert count == 1
        assert len(curator.examples) == 1

    def test_collect_from_lessons_skips_failure(self, tmp_path):
        """collect_from_lessons skips lessons without success marker."""
        mock_lesson = MagicMock()
        mock_lesson.result = "Failed"
        mock_lesson.situation = "situation"
        mock_lesson.action = "action"
        mock_lesson.feedback = "feedback"
        mock_lesson.tags = []
        mock_lesson.metadata = {}

        mock_store = MagicMock()
        mock_store.get_all_lessons = MagicMock(return_value=[mock_lesson])

        curator = self._make_curator(tmp_path, lessons_store=mock_store)
        count = curator.collect_from_lessons()
        assert count == 0

    def test_collect_from_lessons_with_tags(self, tmp_path):
        """collect_from_lessons calls get_lessons_by_tags when tags provided."""
        mock_store = MagicMock()
        mock_store.get_lessons_by_tags = MagicMock(return_value=[])

        curator = self._make_curator(tmp_path, lessons_store=mock_store)
        count = curator.collect_from_lessons(tags=["python"])
        assert count == 0
        mock_store.get_lessons_by_tags.assert_called_once_with(["python"])

    def test_collect_from_lessons_exception(self, tmp_path):
        """collect_from_lessons handles exceptions gracefully."""
        mock_store = MagicMock()
        mock_store.get_all_lessons = MagicMock(side_effect=RuntimeError("crash"))

        curator = self._make_curator(tmp_path, lessons_store=mock_store)
        assert curator.collect_from_lessons() == 0

    def test_collect_from_git_history_no_skill(self, tmp_path):
        """collect_from_git_history returns 0 when git_skill is None."""
        curator = self._make_curator(tmp_path)
        assert curator.collect_from_git_history() == 0

    def test_collect_from_task_history_no_manager(self, tmp_path):
        """collect_from_task_history returns 0 when state_manager is None."""
        curator = self._make_curator(tmp_path)
        assert curator.collect_from_task_history() == 0

    def test_collect_from_task_history_with_completed_tasks(self, tmp_path):
        """collect_from_task_history collects completed tasks."""
        mock_task = MagicMock()
        mock_task.status = "completed"
        mock_task.result = "This is a sufficiently long result text"
        mock_task.request = "User request text"
        mock_task.task_id = "task-1"
        mock_task.assigned_agent = "coder"
        mock_task.created_at = None

        mock_manager = MagicMock()
        mock_manager.get_all_tasks = MagicMock(return_value=[mock_task])

        curator = self._make_curator(tmp_path, state_manager=mock_manager)
        count = curator.collect_from_task_history()
        assert count == 1

    def test_collect_from_task_history_skips_incomplete(self, tmp_path):
        """collect_from_task_history skips non-completed when only_completed=True."""
        mock_task = MagicMock()
        mock_task.status = "pending"
        mock_task.result = "result text here for length"
        mock_task.request = "request"

        mock_manager = MagicMock()
        mock_manager.get_all_tasks = MagicMock(return_value=[mock_task])

        curator = self._make_curator(tmp_path, state_manager=mock_manager)
        assert curator.collect_from_task_history(only_completed=True) == 0

    def test_collect_from_task_history_skips_short_result(self, tmp_path):
        """collect_from_task_history skips tasks with very short results."""
        mock_task = MagicMock()
        mock_task.status = "completed"
        mock_task.result = "short"
        mock_task.request = "request"

        mock_manager = MagicMock()
        mock_manager.get_all_tasks = MagicMock(return_value=[mock_task])

        curator = self._make_curator(tmp_path, state_manager=mock_manager)
        assert curator.collect_from_task_history() == 0

    def test_collect_from_task_history_exception(self, tmp_path):
        """collect_from_task_history handles exceptions gracefully."""
        mock_manager = MagicMock()
        mock_manager.get_all_tasks = MagicMock(side_effect=RuntimeError("crash"))

        curator = self._make_curator(tmp_path, state_manager=mock_manager)
        assert curator.collect_from_task_history() == 0

    def test_save_dataset_sharegpt_format(self, tmp_path):
        """save_dataset writes valid ShareGPT JSONL."""
        from venom_core.learning.dataset_curator import TrainingExample

        curator = self._make_curator(tmp_path)
        curator.examples = [
            TrainingExample("inst", "input text long enough", "output text long enough")
        ]
        path = curator.save_dataset(filename="test.jsonl", format="sharegpt")
        assert path.exists()
        with open(path, "r") as f:
            data = json.loads(f.readline())
        assert "conversations" in data

    def test_save_dataset_empty_raises(self, tmp_path):
        """save_dataset raises ValueError when no examples collected."""
        curator = self._make_curator(tmp_path)
        with pytest.raises(ValueError, match="Brak przykładów"):
            curator.save_dataset()

    def test_save_dataset_invalid_format_raises(self, tmp_path):
        """save_dataset raises ValueError for unknown format."""
        from venom_core.learning.dataset_curator import TrainingExample

        curator = self._make_curator(tmp_path)
        curator.examples = [TrainingExample("i", "input long enough text", "output text")]
        with pytest.raises(ValueError, match="Nieznany format"):
            curator.save_dataset(format="unknown")  # type: ignore[arg-type]  # intentionally invalid value to test the guard

    def test_get_statistics_with_examples(self, tmp_path):
        """get_statistics includes source breakdown and length averages."""
        from venom_core.learning.dataset_curator import TrainingExample

        curator = self._make_curator(tmp_path)
        ex = TrainingExample("inst", "some input text here", "some output text")
        ex.metadata = {"source": "lessons_store"}
        curator.examples = [ex]

        stats = curator.get_statistics()
        assert stats["total_examples"] == 1
        assert "lessons_store" in stats["sources"]
        assert "avg_input_length" in stats
        assert "avg_output_length" in stats

    def test_curator_clear(self, tmp_path):
        """clear() empties the examples list."""
        from venom_core.learning.dataset_curator import TrainingExample

        curator = self._make_curator(tmp_path)
        curator.examples = [TrainingExample("i", "x" * 20, "y" * 20)]
        curator.clear()
        assert len(curator.examples) == 0

    def test_collect_from_lessons_synthetic_flag(self, tmp_path):
        """collect_from_lessons correctly sets synthetic flag from tags."""
        mock_lesson = MagicMock()
        mock_lesson.result = "sukces done"
        mock_lesson.situation = "situation for task"
        mock_lesson.action = "action taken"
        mock_lesson.feedback = "good feedback"
        mock_lesson.lesson_id = "lesson-2"
        mock_lesson.timestamp = "2024-01-01"
        mock_lesson.tags = ["synthetic"]
        mock_lesson.metadata = {}

        mock_store = MagicMock()
        mock_store.get_all_lessons = MagicMock(return_value=[mock_lesson])

        curator = self._make_curator(tmp_path, lessons_store=mock_store)
        count = curator.collect_from_lessons()
        assert count == 1
        assert curator.examples[0].metadata["synthetic"] is True


# ---------------------------------------------------------------------------
# kernel_builder.py – multi-service, routing, FORCE_LOCAL, getters, unknown type
# ---------------------------------------------------------------------------


class TestKernelBuilderGaps:
    """Cover remaining branches in kernel_builder.py."""

    def _make_mock_settings(self, **overrides):
        s = MagicMock()
        s.LLM_SERVICE_TYPE = "local"
        s.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        s.LLM_LOCAL_API_KEY = "EMPTY"
        s.LLM_MODEL_NAME = "llama3"
        s.OPENAI_API_KEY = None
        s.GOOGLE_API_KEY = None
        s.FORCE_LOCAL_MODEL = False
        s.AI_MODE = ""
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    def test_get_model_router(self):
        """get_model_router returns the ModelRouter instance."""
        from venom_core.execution.kernel_builder import KernelBuilder

        kb = KernelBuilder(settings=self._make_mock_settings())
        mr = kb.get_model_router()
        assert mr is kb.model_router

    def test_get_prompt_manager(self):
        """get_prompt_manager returns the PromptManager instance."""
        from venom_core.execution.kernel_builder import KernelBuilder

        kb = KernelBuilder(settings=self._make_mock_settings())
        pm = kb.get_prompt_manager()
        assert pm is kb.prompt_manager

    def test_get_token_economist(self):
        """get_token_economist returns the TokenEconomist instance."""
        from venom_core.execution.kernel_builder import KernelBuilder

        kb = KernelBuilder(settings=self._make_mock_settings())
        te = kb.get_token_economist()
        assert te is kb.token_economist

    def test_build_kernel_force_local(self):
        """build_kernel uses local service when FORCE_LOCAL_MODEL=True."""
        from venom_core.execution.kernel_builder import KernelBuilder

        settings = self._make_mock_settings(
            FORCE_LOCAL_MODEL=True, LLM_SERVICE_TYPE="openai"
        )
        kb = KernelBuilder(settings=settings)

        registered = {}
        def mock_register_service(kernel, service_type, service_id=None, model_name=None, enable_grounding=False):
            registered["service_type"] = service_type

        with patch.object(kb, "_register_service", side_effect=mock_register_service):
            kb.build_kernel()

        assert registered["service_type"] == "local"

    def test_build_kernel_ai_mode_local(self):
        """build_kernel uses local service when AI_MODE='LOCAL'."""
        from venom_core.execution.kernel_builder import KernelBuilder

        settings = self._make_mock_settings(AI_MODE="LOCAL", LLM_SERVICE_TYPE="openai")
        kb = KernelBuilder(settings=settings)

        registered = {}
        def mock_register_service(kernel, service_type, service_id=None, model_name=None, enable_grounding=False):
            registered["service_type"] = service_type

        with patch.object(kb, "_register_service", side_effect=mock_register_service):
            kb.build_kernel()

        assert registered["service_type"] == "local"

    def test_build_kernel_with_routing(self):
        """build_kernel uses router recommendation when task is provided."""
        from venom_core.execution.kernel_builder import KernelBuilder
        from venom_core.core.model_router import ServiceId

        settings = self._make_mock_settings()
        kb = KernelBuilder(settings=settings, enable_routing=True)

        kb.model_router.get_routing_info = MagicMock(return_value={
            "selected_service": ServiceId.LOCAL.value,
            "complexity": "low",
        })

        registered = {}
        def mock_register_service(kernel, service_type, service_id=None, model_name=None, enable_grounding=False):
            registered["service_type"] = service_type

        with patch.object(kb, "_register_service", side_effect=mock_register_service):
            kb.build_kernel(task="write tests")

        assert "service_type" in registered

    def test_register_service_unknown_type_raises(self):
        """_register_service raises ValueError for unknown service type."""
        from venom_core.execution.kernel_builder import KernelBuilder
        from semantic_kernel import Kernel

        kb = KernelBuilder(settings=self._make_mock_settings())
        with pytest.raises(ValueError, match="Nieznany typ serwisu"):
            kb._register_service(Kernel(), "unknown_service")

    def test_register_google_service_unavailable_raises(self):
        """_register_google_service raises ValueError when Google SDK is missing."""
        from venom_core.execution.kernel_builder import KernelBuilder
        import venom_core.execution.kernel_builder as kbmod
        from semantic_kernel import Kernel

        kb = KernelBuilder(settings=self._make_mock_settings())
        original = kbmod.GOOGLE_AVAILABLE
        kbmod.GOOGLE_AVAILABLE = False
        try:
            with pytest.raises(ValueError, match="SDK Gemini"):
                kb._register_google_service(Kernel(), "google", "gemini-pro", False)
        finally:
            kbmod.GOOGLE_AVAILABLE = original

    def test_register_google_service_no_api_key_raises(self):
        """_register_google_service raises ValueError when GOOGLE_API_KEY missing."""
        from venom_core.execution.kernel_builder import KernelBuilder
        import venom_core.execution.kernel_builder as kbmod
        from semantic_kernel import Kernel

        kb = KernelBuilder(settings=self._make_mock_settings(GOOGLE_API_KEY=None))
        original = kbmod.GOOGLE_AVAILABLE
        kbmod.GOOGLE_AVAILABLE = True
        try:
            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                kb._register_google_service(Kernel(), "google", "gemini-pro", False)
        finally:
            kbmod.GOOGLE_AVAILABLE = original

    def test_register_openai_service_no_key_raises(self):
        """_register_openai_service raises ValueError when OPENAI_API_KEY missing."""
        from venom_core.execution.kernel_builder import KernelBuilder
        from semantic_kernel import Kernel

        kb = KernelBuilder(settings=self._make_mock_settings(OPENAI_API_KEY=None))
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            kb._register_openai_service(Kernel(), "openai", "gpt-4", False)

    def test_register_azure_service_missing_config_raises(self):
        """_register_azure_service raises NotImplementedError when credentials missing."""
        from venom_core.execution.kernel_builder import KernelBuilder
        from semantic_kernel import Kernel

        settings = self._make_mock_settings()
        settings.AZURE_OPENAI_ENDPOINT = None
        settings.AZURE_OPENAI_KEY = None
        kb = KernelBuilder(settings=settings)
        with pytest.raises(NotImplementedError, match="Azure OpenAI"):
            kb._register_azure_service(Kernel(), "azure", "gpt-4", False)

    def test_build_kernel_multi_service(self):
        """build_kernel in multi_service mode calls _register_all_services."""
        from venom_core.execution.kernel_builder import KernelBuilder

        settings = self._make_mock_settings()
        kb = KernelBuilder(settings=settings, enable_multi_service=True)

        with patch.object(kb, "_register_all_services") as mock_all:
            kb.build_kernel()
            mock_all.assert_called_once()

    def test_register_all_services_local_exception(self):
        """_register_all_services catches local service registration error."""
        from venom_core.execution.kernel_builder import KernelBuilder
        from semantic_kernel import Kernel

        settings = self._make_mock_settings(OPENAI_API_KEY=None)
        kb = KernelBuilder(settings=settings)

        with patch.object(kb, "_register_service", side_effect=Exception("local fail")):
            # Should not raise
            kb._register_all_services(Kernel())

    def test_register_all_services_with_openai_key(self):
        """_register_all_services registers OpenAI services when key available."""
        from venom_core.execution.kernel_builder import KernelBuilder
        from semantic_kernel import Kernel

        settings = self._make_mock_settings(OPENAI_API_KEY="sk-test-key")
        kb = KernelBuilder(settings=settings)

        calls = []
        def mock_register(kernel, service_type, service_id=None, model_name=None, enable_grounding=False):
            calls.append((service_type, service_id))

        with patch.object(kb, "_register_service", side_effect=mock_register):
            kb._register_all_services(Kernel())

        service_ids = [c[1] for c in calls]
        assert "local_llm" in service_ids
        assert "cloud_fast" in service_ids
        assert "cloud_high" in service_ids


# ---------------------------------------------------------------------------
# cloud_provisioner.py – SSH error paths, mDNS, stop_broadcasting, hive
# ---------------------------------------------------------------------------


class TestCloudProvisionerGaps:
    """Cover remaining branches in cloud_provisioner.py."""

    def _make_provisioner(self, **kwargs):
        from venom_core.infrastructure.cloud_provisioner import CloudProvisioner

        return CloudProvisioner(
            ssh_key_path=None,
            default_user="root",
            timeout=30,
            agent_id="test-agent-id",
            **kwargs,
        )

    @pytest.mark.asyncio
    async def test_execute_ssh_command_no_key_no_password_raises(self):
        """_execute_ssh_command raises CloudProvisionerError without credentials."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        cp = self._make_provisioner()
        with pytest.raises(CloudProvisionerError, match="Brak klucza SSH"):
            await cp._execute_ssh_command("host", "echo test", password=None)

    @pytest.mark.asyncio
    async def test_execute_ssh_command_timeout_raises(self):
        """_execute_ssh_command raises CloudProvisionerError on timeout."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        cp = self._make_provisioner()

        with patch(
            "venom_core.infrastructure.cloud_provisioner.asyncssh.connect",
            side_effect=asyncio.TimeoutError(),
        ):
            with pytest.raises(CloudProvisionerError, match="Timeout"):
                await cp._execute_ssh_command("host", "echo test", password="pw")

    @pytest.mark.asyncio
    async def test_execute_ssh_command_generic_exception(self):
        """_execute_ssh_command wraps unexpected exceptions in CloudProvisionerError."""
        from venom_core.infrastructure.cloud_provisioner import (
            CloudProvisionerError,
            ASYNCSSH_ERROR,
        )

        cp = self._make_provisioner()

        with patch(
            "venom_core.infrastructure.cloud_provisioner.asyncssh.connect",
            side_effect=RuntimeError("generic"),
        ):
            with pytest.raises(CloudProvisionerError, match="Nieoczekiwany błąd"):
                await cp._execute_ssh_command("host", "echo test", password="pw")

    @pytest.mark.asyncio
    async def test_check_deployment_health_error_exit_code(self):
        """check_deployment_health returns error dict on non-zero exit_code."""
        cp = self._make_provisioner()

        with patch.object(
            cp,
            "_execute_ssh_command",
            AsyncMock(return_value=("", "container not found", 1)),
        ):
            result = await cp.check_deployment_health("host", "mystack", password="pw")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_check_deployment_health_unreachable(self):
        """check_deployment_health returns unreachable on CloudProvisionerError."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        cp = self._make_provisioner()

        with patch.object(
            cp,
            "_execute_ssh_command",
            AsyncMock(side_effect=CloudProvisionerError("unreachable")),
        ):
            result = await cp.check_deployment_health("host", "mystack", password="pw")
        assert result["status"] == "unreachable"

    @pytest.mark.asyncio
    async def test_check_deployment_health_invalid_stack_name(self):
        """check_deployment_health raises CloudProvisionerError for invalid stack name."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        cp = self._make_provisioner()
        with pytest.raises(CloudProvisionerError, match="Invalid stack_name"):
            await cp.check_deployment_health("host", "bad stack!", password="pw")

    @pytest.mark.asyncio
    async def test_deploy_stack_missing_compose_file(self, tmp_path):
        """deploy_stack raises CloudProvisionerError when compose file is missing."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        cp = self._make_provisioner()
        with pytest.raises(CloudProvisionerError, match="Plik docker-compose nie istnieje"):
            await cp.deploy_stack(
                "host", "mystack", str(tmp_path / "nonexistent.yml"), password="pw"
            )

    @pytest.mark.asyncio
    async def test_deploy_stack_invalid_stack_name(self, tmp_path):
        """deploy_stack raises CloudProvisionerError for invalid stack_name characters."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'")
        cp = self._make_provisioner()
        with pytest.raises(CloudProvisionerError, match="Invalid stack_name"):
            await cp.deploy_stack("host", "bad stack!", str(compose_file), password="pw")

    @pytest.mark.asyncio
    async def test_deploy_stack_no_credentials(self, tmp_path):
        """deploy_stack raises CloudProvisionerError without SSH credentials."""
        from venom_core.infrastructure.cloud_provisioner import CloudProvisionerError

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'")
        cp = self._make_provisioner()
        with pytest.raises(CloudProvisionerError, match="Brak klucza SSH"):
            await cp.deploy_stack("host", "mystack", str(compose_file))

    def test_start_broadcasting_no_zeroconf(self):
        """start_broadcasting returns error when zeroconf not available."""
        import venom_core.infrastructure.cloud_provisioner as cp_mod

        cp = self._make_provisioner()
        original = cp_mod.ZEROCONF_AVAILABLE
        cp_mod.ZEROCONF_AVAILABLE = False
        try:
            result = cp.start_broadcasting()
        finally:
            cp_mod.ZEROCONF_AVAILABLE = original
        assert result["status"] == "error"

    def test_stop_broadcasting_not_running(self):
        """stop_broadcasting returns 'not_running' when mDNS was never started."""
        cp = self._make_provisioner()
        result = cp.stop_broadcasting()
        assert result["status"] == "not_running"

    def test_get_service_url_strips_local_suffix(self):
        """get_service_url strips .local suffix before building URL."""
        cp = self._make_provisioner()
        url = cp.get_service_url("venom.local")
        assert "venom.local" in url
        assert "venom.local.local" not in url

    @pytest.mark.asyncio
    async def test_register_in_hive_no_url(self):
        """register_in_hive skips when no hive_url is configured."""
        cp = self._make_provisioner()
        cp.hive_url = None
        result = await cp.register_in_hive()
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_register_in_hive_success(self):
        """register_in_hive returns registered status on 200 response."""
        cp = self._make_provisioner()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"registered": True})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.apost = AsyncMock(return_value=mock_response)

        with patch(
            "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient",
            return_value=mock_client,
        ):
            result = await cp.register_in_hive("http://hive.example.com")
        assert result["status"] == "registered"
        assert cp.hive_registered is True

    @pytest.mark.asyncio
    async def test_register_in_hive_error_status(self):
        """register_in_hive returns error dict on non-2xx response."""
        cp = self._make_provisioner()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.apost = AsyncMock(return_value=mock_response)

        with patch(
            "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient",
            return_value=mock_client,
        ):
            result = await cp.register_in_hive("http://hive.example.com")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_register_in_hive_timeout(self):
        """register_in_hive returns timeout status on httpx.TimeoutException."""
        import httpx

        cp = self._make_provisioner()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.apost = AsyncMock(side_effect=httpx.TimeoutException("t/o"))

        with patch(
            "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient",
            return_value=mock_client,
        ):
            result = await cp.register_in_hive("http://hive.example.com")
        assert result["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_register_in_hive_connection_error(self):
        """register_in_hive returns connection_error on httpx.RequestError."""
        import httpx

        cp = self._make_provisioner()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.apost = AsyncMock(
            side_effect=httpx.RequestError("conn refused", request=MagicMock())
        )

        with patch(
            "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient",
            return_value=mock_client,
        ):
            result = await cp.register_in_hive("http://hive.example.com")
        assert result["status"] == "connection_error"

    @pytest.mark.asyncio
    async def test_register_in_hive_generic_exception(self):
        """register_in_hive returns error on unexpected exceptions."""
        cp = self._make_provisioner()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.apost = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient",
            return_value=mock_client,
        ):
            result = await cp.register_in_hive("http://hive.example.com")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_register_in_hive_invalid_json_response(self):
        """register_in_hive handles invalid JSON from Hive gracefully."""
        cp = self._make_provisioner()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(side_effect=ValueError("not json"))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.apost = AsyncMock(return_value=mock_response)

        with patch(
            "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient",
            return_value=mock_client,
        ):
            result = await cp.register_in_hive("http://hive.example.com")
        assert result["status"] == "error"
        assert "Invalid JSON" in result["message"]


# ---------------------------------------------------------------------------
# work_ledger.py – update/duplicate/overrun/predict/recommend/record branches
# ---------------------------------------------------------------------------


class TestWorkLedgerGaps:
    """Cover remaining branches in work_ledger.py."""

    @pytest.fixture
    def ledger(self, tmp_path):
        from venom_core.ops.work_ledger import WorkLedger

        return WorkLedger(storage_path=str(tmp_path / "ledger.json"))

    def _log(self, ledger, task_id="t1"):
        from venom_core.ops.work_ledger import TaskComplexity

        return ledger.log_task(
            task_id=task_id,
            name="Task",
            description="Desc",
            estimated_minutes=30,
            complexity=TaskComplexity.MEDIUM,
        )

    def test_log_task_update_existing(self, ledger):
        """log_task updates an existing task when task_id already exists."""
        from venom_core.ops.work_ledger import TaskComplexity

        self._log(ledger, "t1")
        updated = ledger.log_task(
            "t1", "New Name", "New Desc", 60, TaskComplexity.HIGH,
            metadata={"key": "val"},
        )
        assert updated.name == "New Name"
        assert updated.description == "New Desc"
        assert updated.metadata.get("key") == "val"

    def test_start_task_missing_returns_false(self, ledger):
        """start_task returns False for non-existent task."""
        assert ledger.start_task("missing") is False

    def test_update_progress_missing_returns_false(self, ledger):
        """update_progress returns False for non-existent task."""
        assert ledger.update_progress("missing", 50) is False

    def test_update_progress_all_fields(self, ledger):
        """update_progress sets all optional fields."""
        self._log(ledger)
        result = ledger.update_progress(
            "t1", 50.0, actual_minutes=15, files_touched=3,
            api_calls=10, tokens=500,
        )
        assert result is True
        t = ledger.get_task("t1")
        assert t.actual_minutes == 15
        assert t.files_touched == 3
        assert t.api_calls_made == 10
        assert t.tokens_used == 500

    def test_update_progress_overrun_status(self, ledger):
        """update_progress sets OVERRUN status when actual >> estimated."""
        from venom_core.ops.work_ledger import TaskStatus

        self._log(ledger)
        # 30 estimated × 1.5 = 45; set actual to 50 → overrun
        ledger.update_progress("t1", 80.0, actual_minutes=50)
        t = ledger.get_task("t1")
        assert t.status == TaskStatus.OVERRUN

    def test_complete_task_missing_returns_false(self, ledger):
        """complete_task returns False for non-existent task."""
        assert ledger.complete_task("missing") is False

    def test_complete_task_with_actual_minutes(self, ledger):
        """complete_task sets actual_minutes when provided."""
        from venom_core.ops.work_ledger import TaskStatus

        self._log(ledger)
        ledger.complete_task("t1", actual_minutes=25.0)
        t = ledger.get_task("t1")
        assert t.status == TaskStatus.COMPLETED
        assert t.actual_minutes == 25.0

    def test_add_risk_missing_returns_false(self, ledger):
        """add_risk returns False for non-existent task."""
        assert ledger.add_risk("missing", "some risk") is False

    def test_add_risk_skips_duplicate(self, ledger):
        """add_risk does not duplicate an already-added risk."""
        self._log(ledger)
        ledger.add_risk("t1", "risk A")
        ledger.add_risk("t1", "risk A")  # duplicate
        t = ledger.get_task("t1")
        assert t.risks.count("risk A") == 1

    def test_predict_overrun_missing_task(self, ledger):
        """predict_overrun returns error dict for non-existent task."""
        result = ledger.predict_overrun("missing")
        assert "error" in result

    def test_predict_overrun_not_in_progress(self, ledger):
        """predict_overrun returns will_overrun=False for non-IN_PROGRESS task."""
        self._log(ledger)
        result = ledger.predict_overrun("t1")
        assert result["will_overrun"] is False

    def test_predict_overrun_no_progress_data(self, ledger):
        """predict_overrun returns will_overrun=False when progress_percent is 0."""
        from venom_core.ops.work_ledger import TaskStatus

        self._log(ledger)
        ledger.start_task("t1")
        result = ledger.predict_overrun("t1")
        assert result["will_overrun"] is False
        assert "reason" in result

    def test_predict_overrun_with_progress(self, ledger):
        """predict_overrun returns projection when progress is available."""
        self._log(ledger)
        ledger.start_task("t1")
        ledger.update_progress("t1", 50.0, actual_minutes=25)
        result = ledger.predict_overrun("t1")
        assert "projected_total_minutes" in result

    def test_get_overrun_recommendation_branches(self, ledger):
        """_get_overrun_recommendation covers all threshold branches."""
        rec_5 = ledger._get_overrun_recommendation(5)
        rec_20 = ledger._get_overrun_recommendation(20)
        rec_40 = ledger._get_overrun_recommendation(40)
        rec_60 = ledger._get_overrun_recommendation(60)
        # All should return non-empty strings
        for rec in [rec_5, rec_20, rec_40, rec_60]:
            assert isinstance(rec, str) and len(rec) > 0
        # They should all be distinct (different thresholds produce different text)
        assert len({rec_5, rec_20, rec_40, rec_60}) == 4

    def test_list_tasks_filter_by_complexity(self, ledger):
        """list_tasks filters by complexity."""
        from venom_core.ops.work_ledger import TaskComplexity

        self._log(ledger, "t1")
        ledger.log_task("t2", "T2", "d2", 60, TaskComplexity.HIGH)
        result = ledger.list_tasks(complexity=TaskComplexity.MEDIUM)
        assert all(t.complexity == TaskComplexity.MEDIUM for t in result)

    def test_record_api_usage_missing_returns_false(self, ledger):
        """record_api_usage returns False for non-existent task."""
        assert ledger.record_api_usage("missing", "openai", 100) is False

    def test_record_api_usage_accumulates(self, ledger):
        """record_api_usage accumulates tokens and calls per provider."""
        self._log(ledger)
        ledger.record_api_usage("t1", "openai", 500, ops=2)
        ledger.record_api_usage("t1", "openai", 300, ops=1)
        t = ledger.get_task("t1")
        assert t.tokens_used == 800
        assert t.api_calls_made == 3
        assert t.metadata["api_usage"]["openai"]["tokens"] == 800

    def test_load_tasks_handles_null_json(self, tmp_path):
        """WorkLedger handles null/corrupt JSON gracefully."""
        storage = tmp_path / "bad.json"
        storage.write_text("null")
        from venom_core.ops.work_ledger import WorkLedger

        ledger = WorkLedger(storage_path=str(storage))
        assert len(ledger.tasks) == 0

    def test_summaries_with_accuracy(self, ledger):
        """summaries computes estimation_accuracy_percent for completed tasks."""
        self._log(ledger)
        ledger.start_task("t1")
        ledger.complete_task("t1", actual_minutes=30)
        result = ledger.summaries()
        assert result["total_tasks"] == 1
        assert result["completed"] == 1
        assert result["estimation_accuracy_percent"] > 0


# ---------------------------------------------------------------------------
# component_engine.py – card widget with actions (lines 254→260, 257→256)
# ---------------------------------------------------------------------------


class TestComponentEngineGaps:
    """Cover remaining branches in component_engine.py."""

    def setup_method(self):
        from venom_core.ui.component_engine import ComponentEngine

        self.engine = ComponentEngine()

    def test_create_card_widget_no_actions(self):
        """create_card_widget without actions takes the falsy-actions branch."""
        widget = self.engine.create_card_widget(title="Simple Card", content="Body")
        assert widget.data["title"] == "Simple Card"
        assert "actions" not in widget.data
        assert not widget.events  # empty events dict

    def test_create_card_widget_with_actions(self):
        """create_card_widget with actions having id+intent populates events."""
        widget = self.engine.create_card_widget(
            title="My Card",
            content="Some content",
            icon="🔥",
            actions=[
                {"id": "approve", "intent": "APPROVE_ACTION", "label": "Approve"},
                {"id": "reject", "intent": "REJECT_ACTION", "label": "Reject"},
            ],
        )
        assert widget.data["actions"] is not None
        # events dict should be populated
        assert widget.events is not None
        assert widget.events.get("approve") == "APPROVE_ACTION"
        assert widget.events.get("reject") == "REJECT_ACTION"

    def test_create_card_widget_action_without_intent_skipped(self):
        """create_card_widget skips actions that don't have both id and intent."""
        widget = self.engine.create_card_widget(
            title="Card",
            content="Content",
            actions=[
                {"id": "ok"},  # missing intent
                {"intent": "DO_SOMETHING"},  # missing id
            ],
        )
        # Neither action should register an event
        assert len(widget.events or {}) == 0


# ---------------------------------------------------------------------------
# notifier.py – send_toast branches, _detect_wsl, _check_dependencies,
#               handle_action, get_status
# ---------------------------------------------------------------------------


class TestNotifierGaps:
    """Cover remaining branches in notifier.py."""

    def _make_notifier(self, system="Linux", is_wsl=False, webhook=None):
        """Create Notifier with patched platform.system."""
        with patch("platform.system", return_value=system):
            n = __import__("venom_core.ui.notifier", fromlist=["Notifier"]).Notifier(
                webhook_handler=webhook
            )
        n.system = system
        n._is_wsl = is_wsl
        return n

    def test_detect_wsl_true(self):
        """_detect_wsl returns True when /proc/version contains 'microsoft'."""
        from venom_core.ui.notifier import Notifier

        with patch(
            "builtins.open",
            mock_open(read_data="Linux version 5.10.0-microsoft-standard"),
        ):
            n = Notifier.__new__(Notifier)
            result = n._detect_wsl()
        assert result is True

    def test_detect_wsl_false_on_exception(self):
        """_detect_wsl returns False when /proc/version cannot be read."""
        from venom_core.ui.notifier import Notifier

        with patch("builtins.open", side_effect=OSError("no such file")):
            n = Notifier.__new__(Notifier)
            result = n._detect_wsl()
        assert result is False

    def test_check_dependencies_windows(self):
        """_check_dependencies path for Windows system."""
        n = self._make_notifier(system="Windows", is_wsl=False)
        # Should not raise; Windows path logs info
        n._check_dependencies()

    def test_check_dependencies_linux_no_notify_send(self):
        """_check_dependencies on Linux when notify-send returns non-zero."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            n._check_dependencies()  # should not raise

    def test_check_dependencies_linux_exception(self):
        """_check_dependencies on Linux handles subprocess exception."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        with patch("subprocess.run", side_effect=Exception("no subprocess")):
            n._check_dependencies()  # should not raise

    def test_check_dependencies_wsl(self):
        """_check_dependencies path for WSL2."""
        n = self._make_notifier(system="Linux", is_wsl=True)
        n._check_dependencies()  # should not raise

    @pytest.mark.asyncio
    async def test_send_toast_windows_path(self):
        """send_toast routes to _send_toast_windows on Windows."""
        n = self._make_notifier(system="Windows", is_wsl=False)
        with patch.object(n, "_send_toast_windows", AsyncMock(return_value=True)):
            result = await n.send_toast("Title", "Msg")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_toast_linux_path(self):
        """send_toast routes to _send_toast_linux on Linux (non-WSL)."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        with patch.object(n, "_send_toast_linux", AsyncMock(return_value=True)):
            result = await n.send_toast("Title", "Msg")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_toast_wsl_path(self):
        """send_toast routes to _send_toast_wsl on WSL2."""
        n = self._make_notifier(system="Linux", is_wsl=True)
        with patch.object(n, "_send_toast_wsl", AsyncMock(return_value=True)):
            result = await n.send_toast("Title", "Msg")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_toast_unsupported_system(self):
        """send_toast returns False on unsupported system."""
        n = self._make_notifier(system="FreeBSD", is_wsl=False)
        result = await n.send_toast("Title", "Msg")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_toast_with_action_payload(self):
        """send_toast logs debug when action_payload is passed."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        with patch.object(n, "_send_toast_linux", AsyncMock(return_value=True)):
            result = await n.send_toast("T", "M", action_payload={"key": "value"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_toast_exception_returns_false(self):
        """send_toast catches exceptions and returns False."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        with patch.object(n, "_send_toast_linux", AsyncMock(side_effect=RuntimeError("crash"))):
            result = await n.send_toast("Title", "Msg")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_toast_linux_failure(self):
        """_send_toast_linux returns False when notify-send exits non-zero."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await n._send_toast_linux("T", "M", "normal")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_toast_linux_file_not_found(self):
        """_send_toast_linux returns False when notify-send is not installed."""
        n = self._make_notifier(system="Linux", is_wsl=False)
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("notify-send not found"),
        ):
            result = await n._send_toast_linux("T", "M", "normal")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_toast_wsl_failure(self):
        """_send_toast_wsl returns False when PowerShell exits non-zero."""
        n = self._make_notifier(system="Linux", is_wsl=True)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await n._send_toast_wsl("Title", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_powershell_toast_success_returns_true(self):
        """_send_toast_windows_powershell returns True when PS succeeds."""
        n = self._make_notifier(system="Windows", is_wsl=False)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await n._send_toast_windows_powershell("Title", "Message")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_toast_wsl_success_returns_true(self):
        """_send_toast_wsl returns True when PowerShell exits successfully."""
        n = self._make_notifier(system="Linux", is_wsl=True)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await n._send_toast_wsl("Title", "Message")
        assert result is True

    @pytest.mark.asyncio
    async def test_powershell_toast_failure_returns_false(self):
        """_send_toast_windows_powershell returns False when PS exits non-zero."""
        n = self._make_notifier(system="Windows", is_wsl=False)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"err"))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await n._send_toast_windows_powershell("Title", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_action_with_webhook(self):
        """handle_action calls webhook_handler with the payload."""
        handler = AsyncMock()
        from venom_core.ui.notifier import Notifier

        n = Notifier(webhook_handler=handler)
        await n.handle_action({"action": "test"})
        handler.assert_awaited_once_with({"action": "test"})

    @pytest.mark.asyncio
    async def test_handle_action_without_webhook(self):
        """handle_action does nothing when webhook_handler is None."""
        from venom_core.ui.notifier import Notifier

        n = Notifier(webhook_handler=None)
        await n.handle_action({"action": "test"})  # Should not raise

    @pytest.mark.asyncio
    async def test_handle_action_exception_swallowed(self):
        """handle_action catches exceptions from webhook_handler."""
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        from venom_core.ui.notifier import Notifier

        n = Notifier(webhook_handler=handler)
        await n.handle_action({"action": "test"})  # Should not raise

    def test_get_status(self):
        """get_status returns system info dict."""
        from venom_core.ui.notifier import Notifier

        n = Notifier(webhook_handler=AsyncMock())
        status = n.get_status()
        assert "system" in status
        assert "is_wsl" in status
        assert status["webhook_handler_set"] is True
