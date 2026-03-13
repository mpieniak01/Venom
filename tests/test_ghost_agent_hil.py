"""Manual hardware-in-loop scenarios for Ghost desktop automation."""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.ghost_agent import GhostAgent
from venom_core.core.permission_guard import permission_guard

pytestmark = [pytest.mark.asyncio, pytest.mark.manual_llm]


def _require_hil_env() -> None:
    if os.getenv("VENOM_GHOST_HIL") != "1":
        pytest.skip("Set VENOM_GHOST_HIL=1 to run manual hardware-in-loop scenarios.")
    if sys.platform.startswith("linux") and not (
        os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")
    ):
        pytest.skip(
            "Desktop display is not available (DISPLAY/WAYLAND_DISPLAY missing)."
        )
    try:
        import tkinter  # noqa: F401
    except Exception as exc:  # pragma: no cover - platform-dependent
        pytest.skip(f"Tkinter is not available: {exc}")


def _wait_for(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@dataclass
class _TkDesktopHarness:
    ready: threading.Event = field(default_factory=threading.Event)
    state: dict[str, Any] = field(
        default_factory=lambda: {"clicked": False, "submitted_text": ""}
    )
    coords: dict[str, tuple[int, int]] = field(default_factory=dict)
    _thread: threading.Thread | None = None
    _root: Any = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self.ready.wait(timeout=5):
            raise RuntimeError("Desktop harness did not start in time.")

    def stop(self) -> None:
        if self._root is not None:
            self._root.after(0, self._root.destroy)
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _center(self, widget: Any) -> tuple[int, int]:
        return (
            int(widget.winfo_rootx() + widget.winfo_width() / 2),
            int(widget.winfo_rooty() + widget.winfo_height() / 2),
        )

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        self._root = root
        root.title("Venom Ghost HIL Harness")
        root.geometry("360x180+120+120")
        root.attributes("-topmost", True)

        title = tk.Label(root, text="Ghost HIL")
        title.pack(pady=6)

        entry = tk.Entry(root, width=28)
        entry.pack(pady=6)

        def _on_click() -> None:
            self.state["clicked"] = True

        click_btn = tk.Button(root, text="Click me", command=_on_click)
        click_btn.pack(pady=4)

        def _on_submit() -> None:
            self.state["submitted_text"] = str(entry.get())

        submit_btn = tk.Button(root, text="Submit", command=_on_submit)
        submit_btn.pack(pady=4)
        root.bind("<Return>", lambda _event: _on_submit())

        root.update_idletasks()
        root.update()
        self.coords["entry"] = self._center(entry)
        self.coords["click_btn"] = self._center(click_btn)
        self.coords["submit_btn"] = self._center(submit_btn)
        self.ready.set()

        root.mainloop()


@pytest.fixture
def desktop_permission_level():
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(40)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


def _build_ghost_agent() -> GhostAgent:
    with patch("venom_core.agents.ghost_agent.SETTINGS") as settings_mock:
        settings_mock.ENABLE_GHOST_AGENT = True
        settings_mock.GHOST_MAX_STEPS = 20
        settings_mock.GHOST_STEP_DELAY = 0.1
        settings_mock.GHOST_VERIFICATION_ENABLED = True
        settings_mock.GHOST_SAFETY_DELAY = 0.02
        settings_mock.GHOST_RUNTIME_PROFILE = "desktop_safe"
        settings_mock.GHOST_CRITICAL_FAIL_CLOSED = True
        return GhostAgent(
            kernel=MagicMock(),
            step_delay=0.05,
            safety_delay=0.02,
            verification_enabled=False,
        )


async def test_hil_desktop_safe_blocks_fallback_without_visual_match(
    desktop_permission_level,
):
    _require_hil_env()
    harness = _TkDesktopHarness()
    harness.start()
    try:
        ghost = _build_ghost_agent()
        ghost.apply_runtime_profile("desktop_safe")
        ghost.vision.locate_element = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="Fail-closed"):
            await ghost.vision_click(
                description="click button in harness",
                fallback_coords=harness.coords["click_btn"],
                require_visual_confirmation=False,
            )

        assert harness.state["clicked"] is False
    finally:
        harness.stop()


async def test_hil_desktop_power_click_and_submit_via_keyboard(
    desktop_permission_level,
):
    _require_hil_env()
    harness = _TkDesktopHarness()
    harness.start()
    try:
        ghost = _build_ghost_agent()
        ghost.apply_runtime_profile("desktop_power")
        ghost.vision.locate_element = AsyncMock(return_value=None)

        await ghost.vision_click(
            description="click button in harness",
            fallback_coords=harness.coords["click_btn"],
            require_visual_confirmation=False,
        )
        assert _wait_for(lambda: harness.state["clicked"] is True, timeout=3)

        await ghost.vision_click(
            description="text input in harness",
            fallback_coords=harness.coords["entry"],
            require_visual_confirmation=False,
        )
        await ghost.input_skill.keyboard_type("hil-submit-ok", interval=0.01)
        await ghost.input_skill.keyboard_hotkey("enter")

        assert (
            _wait_for(
                lambda: harness.state["submitted_text"] == "hil-submit-ok", timeout=3
            )
            is True
        )
    finally:
        harness.stop()
