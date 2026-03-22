"""Testy jednostkowe dla GhostAgent."""

# ruff: noqa: E402

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

# Mock pyautogui for headless environment
mock_pyautogui = MagicMock()
sys.modules["pyautogui"] = mock_pyautogui

from venom_core.agents.ghost_agent import ActionStep, GhostAgent
from venom_core.core.permission_guard import permission_guard


def _ghost_client(mod, ghost=None) -> TestClient:
    app = FastAPI()
    mod.set_dependencies(None, None, None, None, None, ghost)
    app.include_router(mod.router)
    return TestClient(app)


@pytest.fixture
def ghost_routes_mod():
    from venom_core.api.routes import agents as mod

    originals = (
        mod._gardener_agent,
        mod._shadow_agent,
        mod._file_watcher,
        mod._documenter_agent,
        mod._orchestrator,
        mod._ghost_agent,
        dict(mod._ghost_local_tasks),
        getattr(mod.SETTINGS, "ENABLE_GHOST_API", False),
        getattr(mod.SETTINGS, "ENABLE_GHOST_AGENT", False),
        getattr(mod.SETTINGS, "GHOST_RUNTIME_PROFILE", "desktop_safe"),
    )
    mod._ghost_run_store.clear()
    mod._ghost_local_tasks.clear()
    yield mod
    mod._ghost_run_store.clear()
    mod._ghost_local_tasks.clear()
    (
        mod._gardener_agent,
        mod._shadow_agent,
        mod._file_watcher,
        mod._documenter_agent,
        mod._orchestrator,
        mod._ghost_agent,
        local_tasks,
        mod.SETTINGS.ENABLE_GHOST_API,
        mod.SETTINGS.ENABLE_GHOST_AGENT,
        mod.SETTINGS.GHOST_RUNTIME_PROFILE,
    ) = originals
    mod._ghost_local_tasks.update(local_tasks)


class TestActionStep:
    """Testy dla ActionStep."""

    def test_action_step_initialization(self):
        """Test inicjalizacji ActionStep."""
        step = ActionStep("click", "Kliknij przycisk", {"x": 100, "y": 200})

        assert step.action_type == "click"
        assert step.description == "Kliknij przycisk"
        assert step.params == {"x": 100, "y": 200}
        assert step.status == "pending"
        assert step.result is None

    def test_action_step_without_params(self):
        """Test ActionStep bez parametrów."""
        step = ActionStep("screenshot", "Zrób zrzut")

        assert step.action_type == "screenshot"
        assert step.params == {}


class TestGhostAgent:
    """Testy dla GhostAgent."""

    @pytest.fixture
    def mock_kernel(self):
        """Fixture do tworzenia mock Kernel."""
        return MagicMock()

    @pytest.fixture
    def ghost_agent(self, mock_kernel):
        """Fixture do tworzenia GhostAgent."""
        with (
            patch("venom_core.agents.ghost_agent.VisionGrounding"),
            patch("venom_core.agents.ghost_agent.InputSkill"),
            patch("venom_core.agents.ghost_agent.SETTINGS") as mock_settings,
        ):
            # Mock SETTINGS to enable Ghost Agent in tests
            mock_settings.ENABLE_GHOST_AGENT = True
            mock_settings.GHOST_MAX_STEPS = 20
            mock_settings.GHOST_STEP_DELAY = 1.0
            mock_settings.GHOST_VERIFICATION_ENABLED = True
            mock_settings.GHOST_SAFETY_DELAY = 0.5

            agent = GhostAgent(
                kernel=mock_kernel,
                max_steps=10,
                step_delay=0.1,
                verification_enabled=False,
            )
            return agent

    def test_initialization(self, ghost_agent):
        """Test inicjalizacji GhostAgent."""
        assert ghost_agent.max_steps == 10
        assert ghost_agent.step_delay == pytest.approx(0.1)
        assert ghost_agent.verification_enabled is False
        assert ghost_agent.is_running is False
        assert ghost_agent.emergency_stop is False
        assert len(ghost_agent.action_history) == 0

    @pytest.mark.asyncio
    async def test_process_when_already_running(self, ghost_agent):
        """Test próby uruchomienia gdy agent już działa."""
        ghost_agent.is_running = True

        with patch("venom_core.agents.ghost_agent.SETTINGS") as mock_settings:
            mock_settings.ENABLE_GHOST_AGENT = True
            result = await ghost_agent.process("Otwórz notatnik")

            assert "już działa" in result
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_process_notepad_task(self, ghost_agent):
        """Test zadania otwarcia notatnika."""
        # Mock metod
        ghost_agent.input_skill.keyboard_hotkey = AsyncMock(return_value="✅ OK")
        ghost_agent.input_skill.keyboard_type = AsyncMock(return_value="✅ OK")

        with (
            patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab,
            patch("venom_core.agents.ghost_agent.SETTINGS") as mock_settings,
        ):
            mock_settings.ENABLE_GHOST_AGENT = True
            mock_grab.return_value = Image.new("RGB", (100, 100))

            result = await ghost_agent.process("Otwórz notatnik i napisz 'Hello Venom'")

            assert "RAPORT GHOST AGENT" in result
            assert "Wykonane kroki" in result
            # Sprawdź czy kroki zostały wykonane
            assert len(ghost_agent.action_history) > 0

    @pytest.mark.asyncio
    async def test_create_action_plan_notepad(self, ghost_agent):
        """Test tworzenia planu dla zadania notatnika."""
        plan = await ghost_agent._create_action_plan("Otwórz notatnik")

        assert len(plan) > 0
        # Powinien zawierać hotkey Win+R
        assert any(step.action_type == "hotkey" for step in plan)
        # Powinien zawierać type 'notepad'
        assert any(step.action_type == "type" for step in plan)

    @pytest.mark.asyncio
    async def test_create_action_plan_spotify(self, ghost_agent):
        """Test tworzenia planu dla Spotify."""
        plan = await ghost_agent._create_action_plan(
            "Włącz następną piosenkę w Spotify"
        )

        assert len(plan) > 0
        # Powinien zawierać screenshot i locate
        assert any(step.action_type == "screenshot" for step in plan)
        assert any(step.action_type == "locate" for step in plan)

    @pytest.mark.asyncio
    async def test_execute_plan_screenshot_step(self, ghost_agent):
        """Test wykonania kroku screenshot."""
        plan = [ActionStep("screenshot", "Zrób zrzut", {})]

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (100, 100))

            result = await ghost_agent._execute_plan(plan)

            assert "RAPORT" in result
            assert len(ghost_agent.action_history) == 1
            assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_click_step(self, ghost_agent):
        """Test wykonania kroku kliknięcia."""
        plan = [ActionStep("click", "Kliknij", {"x": 100, "y": 200})]

        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")

        result = await ghost_agent._execute_plan(plan)

        assert "RAPORT" in result
        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_type_step(self, ghost_agent):
        """Test wykonania kroku pisania."""
        plan = [ActionStep("type", "Wpisz tekst", {"text": "Hello"})]

        ghost_agent.input_skill.keyboard_type = AsyncMock(return_value="✅ Wpisano")

        await ghost_agent._execute_plan(plan)

        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_hotkey_step(self, ghost_agent):
        """Test wykonania kroku hotkey."""
        plan = [ActionStep("hotkey", "Naciśnij Ctrl+S", {"keys": "ctrl+s"})]

        ghost_agent.input_skill.keyboard_hotkey = AsyncMock(return_value="✅ Wykonano")

        await ghost_agent._execute_plan(plan)

        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_wait_step(self, ghost_agent):
        """Test wykonania kroku oczekiwania."""
        plan = [ActionStep("wait", "Czekaj 0.1s", {"duration": 0.01})]

        await ghost_agent._execute_plan(plan)

        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"
        assert "Oczekiwano" in ghost_agent.action_history[0].result

    @pytest.mark.asyncio
    async def test_execute_plan_locate_step(self, ghost_agent):
        """Test wykonania kroku lokalizacji."""
        plan = [ActionStep("locate", "Znajdź przycisk", {"description": "red button"})]

        ghost_agent.vision.locate_element = AsyncMock(return_value=(50, 50))

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (100, 100))

            await ghost_agent._execute_plan(plan)

            assert len(ghost_agent.action_history) == 1
            assert "znaleziony" in ghost_agent.action_history[0].result.lower()

    @pytest.mark.asyncio
    async def test_execute_plan_max_steps_limit(self, ghost_agent):
        """Test limitu maksymalnej liczby kroków."""
        ghost_agent.max_steps = 3
        # Stwórz plan z 5 krokami
        plan = [ActionStep("wait", f"Krok {i}", {"duration": 0.01}) for i in range(5)]

        await ghost_agent._execute_plan(plan)

        # Powinno wykonać tylko 3 kroki
        assert len(ghost_agent.action_history) <= 3

    @pytest.mark.asyncio
    async def test_execute_plan_with_emergency_stop(self, ghost_agent):
        """Test przerwania planu przez emergency stop."""
        plan = [ActionStep("wait", "Krok", {"duration": 0.01}) for _ in range(5)]

        # Aktywuj emergency stop po pierwszym kroku
        async def activate_emergency(*args):
            await asyncio.sleep(0.01)
            ghost_agent.emergency_stop = True

        emergency_task = asyncio.create_task(activate_emergency())

        result = await ghost_agent._execute_plan(plan)
        await emergency_task

        assert "Emergency Stop" in result or len(ghost_agent.action_history) < 5

    def test_generate_report(self, ghost_agent):
        """Test generowania raportu."""
        # Dodaj kilka kroków do historii
        step1 = ActionStep("click", "Krok 1", {})
        step1.status = "success"
        step1.result = "OK"

        step2 = ActionStep("type", "Krok 2", {})
        step2.status = "failed"
        step2.result = "Błąd"

        ghost_agent.action_history = [step1, step2]

        report = ghost_agent._generate_report()

        assert "RAPORT GHOST AGENT" in report
        assert "Wykonane kroki: 2" in report
        assert "Udane: 1" in report
        assert "Nieudane: 1" in report
        assert "Krok 1" in report
        assert "Krok 2" in report

    def test_emergency_stop_trigger(self, ghost_agent):
        """Test aktywacji emergency stop."""
        ghost_agent.is_running = True
        ghost_agent.emergency_stop_trigger()

        assert ghost_agent.emergency_stop is True
        assert ghost_agent.is_running is False

    def test_get_status(self, ghost_agent):
        """Test pobierania statusu agenta."""
        ghost_agent.input_skill.get_screen_size = MagicMock(return_value=(1920, 1080))

        status = ghost_agent.get_status()

        assert "is_running" in status
        assert "emergency_stop" in status
        assert "max_steps" in status
        assert status["max_steps"] == 10
        assert "screen_size" in status
        assert status["screen_size"] == (1920, 1080)

    @pytest.mark.asyncio
    async def test_execute_plan_click_with_located_coords(self, ghost_agent):
        """Test kliknięcia używając współrzędnych z locate."""
        plan = [
            ActionStep("locate", "Znajdź", {"description": "button"}),
            ActionStep("click", "Kliknij", {"use_located": True}),
        ]

        ghost_agent.vision.locate_element = AsyncMock(return_value=(100, 150))
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (200, 200))

            await ghost_agent._execute_plan(plan)

            # Sprawdź czy mouse_click został wywołany z właściwymi współrzędnymi
            ghost_agent.input_skill.mouse_click.assert_called_with(100, 150)

    def test_compute_screen_change_percent(self, ghost_agent):
        pre = (np.zeros((4, 4, 3), dtype=np.uint8),)
        post = np.full((4, 4, 3), 255, dtype=np.uint8)
        percent = ghost_agent._compute_screen_change_percent(pre[0], post)
        assert percent == pytest.approx(100.0)

    def test_verify_locate_step_false_when_result_missing(self, ghost_agent):
        step = ActionStep("locate", "locate")
        step.result = None
        assert ghost_agent._verify_locate_step(step) is False

    def test_verify_step_result_unknown_action_type_assumes_success(self, ghost_agent):
        step = ActionStep("unknown", "Unknown action")
        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (100, 100))
            assert ghost_agent._verify_step_result(step, None) is True

    @pytest.mark.asyncio
    async def test_vision_click_success_with_located_coords(self, ghost_agent):
        ghost_agent.vision.locate_element = AsyncMock(return_value=(320, 240))
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")
        ghost_agent.verification_enabled = False

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (300, 200))
            payload = await ghost_agent.vision_click(
                description="save button",
                require_visual_confirmation=False,
            )

        assert payload["status"] == "success"
        assert payload["coords"] == [320, 240]
        assert payload["used_fallback"] is False
        ghost_agent.input_skill.mouse_click.assert_called_once()

    @pytest.mark.asyncio
    async def test_vision_click_fail_closed_blocks_fallback(self, ghost_agent):
        ghost_agent.vision.locate_element = AsyncMock(return_value=None)
        ghost_agent.critical_fail_closed = True

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (300, 200))
            with pytest.raises(RuntimeError, match="Fail-closed"):
                await ghost_agent.vision_click(
                    description="login button",
                    fallback_coords=(10, 20),
                )

    @pytest.mark.asyncio
    async def test_vision_click_allows_fallback_in_power_mode(self, ghost_agent):
        ghost_agent.vision.locate_element = AsyncMock(return_value=None)
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")
        ghost_agent.apply_runtime_profile("desktop_power")
        ghost_agent.verification_enabled = False

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (300, 200))
            payload = await ghost_agent.vision_click(
                description="missing element",
                fallback_coords=(50, 60),
            )

        assert payload["status"] == "success"
        assert payload["used_fallback"] is True
        assert payload["runtime_profile"] == "desktop_power"

    @pytest.mark.asyncio
    async def test_vision_click_raises_when_click_execution_fails(self, ghost_agent):
        ghost_agent.vision.locate_element = AsyncMock(return_value=(100, 120))
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="❌ click failed")

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (300, 200))
            with pytest.raises(RuntimeError, match="click failed"):
                await ghost_agent.vision_click(
                    description="save button",
                    require_visual_confirmation=False,
                )

    @pytest.mark.asyncio
    async def test_vision_click_fail_closed_blocks_failed_verification(
        self, ghost_agent
    ):
        ghost_agent.vision.locate_element = AsyncMock(return_value=(200, 150))
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")
        ghost_agent.critical_fail_closed = True
        ghost_agent._verify_screen_change_step = MagicMock(return_value=False)

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (300, 200))
            with pytest.raises(
                RuntimeError, match="Fail-closed: weryfikacja kliknięcia"
            ):
                await ghost_agent.vision_click(
                    description="apply button",
                    require_visual_confirmation=True,
                )

    @pytest.mark.asyncio
    async def test_vision_click_with_fallback_only_description_empty(self, ghost_agent):
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")
        ghost_agent.apply_runtime_profile("desktop_power")

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (300, 200))
            payload = await ghost_agent.vision_click(
                description="",
                fallback_coords=(11, 22),
                require_visual_confirmation=False,
            )

        assert payload["coords"] == [11, 22]
        assert payload["used_fallback"] is True

    def test_apply_runtime_profile_safe_mode(self, ghost_agent):
        ghost_agent._explicit_overrides = {
            "max_steps": False,
            "step_delay": False,
            "verification_enabled": False,
            "critical_fail_closed": False,
        }

        payload = ghost_agent.apply_runtime_profile("desktop_safe")

        assert payload["profile"] == "desktop_safe"
        assert payload["critical_fail_closed"] is True


class _DummyCancelledTask:
    def __init__(self):
        self.cancel_called = False

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.cancel_called = True

    def __await__(self):
        async def _raise_cancel():
            raise asyncio.CancelledError

        return _raise_cancel().__await__()


class TestGhostApiFastlaneCoverage:
    def test_require_ghost_agent_raises_when_missing(self, ghost_routes_mod):
        ghost_routes_mod._ghost_agent = None
        with pytest.raises(
            RuntimeError, match=ghost_routes_mod.GHOST_AGENT_UNAVAILABLE_DETAIL
        ):
            ghost_routes_mod._require_ghost_agent()

    def test_store_helpers_and_hash(self, ghost_routes_mod):
        store = ghost_routes_mod._ghost_run_store
        store.clear()

        assert store.try_start({"task_id": "a1", "status": "running"}) is True
        assert store.try_start({"task_id": "a2", "status": "running"}) is False

        mismatch = store.update("other-task", {"status": "failed"})
        assert mismatch is not None
        assert mismatch["task_id"] == "a1"

        store.clear()
        assert store.update("missing", {"status": "failed"}) is None
        assert ghost_routes_mod._get_runtime_profile("missing") is None
        assert len(ghost_routes_mod._hash_content("sensitive")) == 64
        assert (
            ghost_routes_mod._GhostRunStateStore.is_active({"status": "running"})
            is True
        )
        assert (
            ghost_routes_mod._GhostRunStateStore.is_active({"status": "completed"})
            is False
        )

    def test_store_invalid_json_and_non_dict_payload(self, ghost_routes_mod):
        state_path = ghost_routes_mod._ghost_run_store._state_path
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{bad-json", encoding="utf-8")
        assert ghost_routes_mod._ghost_run_store.get() is None
        state_path.write_text('["not-a-dict"]', encoding="utf-8")
        assert ghost_routes_mod._ghost_run_store.get() is None

    @pytest.mark.asyncio
    async def test_run_process_cancel_watch_and_job_error(self, ghost_routes_mod):
        store = ghost_routes_mod._ghost_run_store
        store.clear()
        store.try_start({"task_id": "cancel-1", "status": "running"})

        async def _slow_process(_content: str) -> str:
            await asyncio.sleep(1.0)
            return "never"

        ghost = MagicMock()
        ghost.process = AsyncMock(side_effect=_slow_process)
        ghost.emergency_stop_trigger = MagicMock()

        with patch.object(ghost_routes_mod, "_ghost_agent", ghost):
            task = asyncio.create_task(
                ghost_routes_mod._run_ghost_process_with_cancel_watch(
                    task_id="cancel-1", content="open app"
                )
            )
            await asyncio.sleep(0.05)
            store.update("cancel-1", {"status": "cancelling"})
            with pytest.raises(asyncio.CancelledError):
                await task
        ghost.emergency_stop_trigger.assert_called_once()

        store.clear()
        store.try_start(
            {
                "task_id": "job-fail",
                "status": "running",
                "runtime_profile": "desktop_safe",
            }
        )
        ghost_routes_mod._ghost_local_tasks["job-fail"] = MagicMock()
        with (
            patch.object(
                ghost_routes_mod,
                "_run_ghost_process_with_cancel_watch",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(ghost_routes_mod, "_publish_ghost_audit", MagicMock()),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await ghost_routes_mod._run_ghost_job(
                    task_id="job-fail",
                    payload=ghost_routes_mod.GhostRunRequest(content="do"),
                    actor="tester",
                )

    def test_status_endpoint_branches(self, ghost_routes_mod):
        ghost = MagicMock()
        ghost.get_status.return_value = {"is_running": False}
        client = _ghost_client(ghost_routes_mod, ghost=ghost)

        ghost_routes_mod.SETTINGS.ENABLE_GHOST_API = False
        ghost_routes_mod.SETTINGS.ENABLE_GHOST_AGENT = False
        disabled = client.get("/api/v1/ghost/status")
        assert disabled.status_code == 200
        assert disabled.json()["run"] is None

        ghost_routes_mod.SETTINGS.ENABLE_GHOST_API = True
        ghost_routes_mod.SETTINGS.ENABLE_GHOST_AGENT = True
        missing = _ghost_client(ghost_routes_mod).get("/api/v1/ghost/status")
        assert missing.status_code == 503
        client = _ghost_client(ghost_routes_mod, ghost=ghost)

        store = ghost_routes_mod._ghost_run_store
        store.clear()
        store.try_start({"task_id": "task-1", "status": "running"})

        class _DoneTask:
            @staticmethod
            def done() -> bool:
                return True

        ghost_routes_mod._ghost_local_tasks["task-1"] = _DoneTask()
        ok = client.get("/api/v1/ghost/status")
        assert ok.status_code == 200
        assert ok.json()["task_active"] is False

        with patch.object(ghost, "get_status", side_effect=RuntimeError("status fail")):
            fail = client.get("/api/v1/ghost/status")
        assert fail.status_code == 500

    def test_start_endpoint_branches_and_accepts(self, ghost_routes_mod):
        ghost = MagicMock()
        ghost.apply_runtime_profile.return_value = {"profile": "desktop_safe"}
        client = _ghost_client(ghost_routes_mod, ghost=ghost)

        ghost_routes_mod.SETTINGS.ENABLE_GHOST_API = False
        ghost_routes_mod.SETTINGS.ENABLE_GHOST_AGENT = False
        assert (
            client.post("/api/v1/ghost/start", json={"content": "open"}).status_code
            == 503
        )

        ghost_routes_mod.SETTINGS.ENABLE_GHOST_API = True
        ghost_routes_mod.SETTINGS.ENABLE_GHOST_AGENT = True
        missing = _ghost_client(ghost_routes_mod).post(
            "/api/v1/ghost/start", json={"content": "open"}
        )
        assert missing.status_code == 503
        client = _ghost_client(ghost_routes_mod, ghost=ghost)

        with (
            patch.object(
                ghost_routes_mod,
                "ensure_data_mutation_allowed",
                side_effect=PermissionError("deny"),
            ),
            patch.object(
                ghost_routes_mod,
                "raise_permission_denied_http",
                side_effect=HTTPException(status_code=403, detail="deny"),
            ),
        ):
            denied = client.post("/api/v1/ghost/start", json={"content": "open"})
        assert denied.status_code == 403

        with patch.object(
            ghost_routes_mod._ghost_run_store,
            "get",
            return_value={"task_id": "x", "status": "running"},
        ):
            active = client.post("/api/v1/ghost/start", json={"content": "open"})
        assert active.status_code == 409

        with (
            patch.object(ghost_routes_mod._ghost_run_store, "get", return_value=None),
            patch.object(
                ghost_routes_mod._ghost_run_store, "try_start", return_value=False
            ),
        ):
            race = client.post("/api/v1/ghost/start", json={"content": "open"})
        assert race.status_code == 409

        with patch.object(
            ghost_routes_mod, "_run_ghost_job", new=AsyncMock(return_value="ok")
        ):
            started = client.post(
                "/api/v1/ghost/start",
                json={"content": "very secret", "runtime_profile": "desktop_power"},
            )
        assert started.status_code == 200
        state = ghost_routes_mod._ghost_run_store.get()
        assert state is not None
        assert state["content_length"] == len("very secret")
        assert "content" not in state
        assert "content_sha256" in state

    def test_cancel_endpoint_branches_and_local_cancel(self, ghost_routes_mod):
        ghost = MagicMock()
        ghost.emergency_stop_trigger = MagicMock()
        client = _ghost_client(ghost_routes_mod, ghost=ghost)

        ghost_routes_mod.SETTINGS.ENABLE_GHOST_API = False
        ghost_routes_mod.SETTINGS.ENABLE_GHOST_AGENT = False
        assert client.post("/api/v1/ghost/cancel").status_code == 503

        ghost_routes_mod.SETTINGS.ENABLE_GHOST_API = True
        ghost_routes_mod.SETTINGS.ENABLE_GHOST_AGENT = True
        assert (
            _ghost_client(ghost_routes_mod).post("/api/v1/ghost/cancel").status_code
            == 503
        )
        client = _ghost_client(ghost_routes_mod, ghost=ghost)

        with (
            patch.object(
                ghost_routes_mod,
                "ensure_data_mutation_allowed",
                side_effect=PermissionError("deny"),
            ),
            patch.object(
                ghost_routes_mod,
                "raise_permission_denied_http",
                side_effect=HTTPException(status_code=403, detail="deny"),
            ),
        ):
            denied = client.post("/api/v1/ghost/cancel")
        assert denied.status_code == 403

        ghost_routes_mod._ghost_run_store.clear()
        no_active = client.post("/api/v1/ghost/cancel")
        assert no_active.status_code == 200
        assert no_active.json()["cancelled"] is False

        ghost_routes_mod._ghost_run_store.try_start(
            {"task_id": "cancel-1", "status": "running"}
        )
        local_task = _DummyCancelledTask()
        ghost_routes_mod._ghost_local_tasks["cancel-1"] = local_task
        cancelled = client.post("/api/v1/ghost/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancelled"] is True
        assert local_task.cancel_called is True
        ghost.emergency_stop_trigger.assert_called()


class TestPermissionGuardFastlaneCoverage:
    def test_can_control_desktop_input_explicit_flag(self, monkeypatch):
        monkeypatch.setattr(
            permission_guard,
            "_levels",
            {456: MagicMock(permissions={"desktop_input_enabled": True})},
            raising=False,
        )
        monkeypatch.setattr(permission_guard, "_current_level", 456, raising=False)
        assert permission_guard.can_control_desktop_input() is True

    def test_can_control_desktop_input_fallback_shell(self, monkeypatch):
        monkeypatch.setattr(
            permission_guard,
            "_levels",
            {654: MagicMock(permissions={"shell_enabled": True})},
            raising=False,
        )
        monkeypatch.setattr(permission_guard, "_current_level", 654, raising=False)
        assert permission_guard.can_control_desktop_input() is True

    def test_can_control_desktop_input_unknown_level(self, monkeypatch):
        monkeypatch.setattr(permission_guard, "_levels", {}, raising=False)
        monkeypatch.setattr(permission_guard, "_current_level", 9999, raising=False)
        assert permission_guard.can_control_desktop_input() is False
