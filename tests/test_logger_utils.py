from types import SimpleNamespace

from venom_core.utils import logger as logger_module


def _message(level: str, msg: str):
    return SimpleNamespace(
        record={
            "level": SimpleNamespace(name=level),
            "message": msg,
        }
    )


def test_set_event_broadcaster_updates_global():
    sentinel = object()
    logger_module.set_event_broadcaster(sentinel)
    assert logger_module._event_broadcaster is sentinel


def test_log_sink_ignores_message_without_record():
    logger_module._log_tasks.clear()
    logger_module.set_event_broadcaster(object())
    logger_module.log_sink(object())
    assert logger_module._log_tasks == set()


def test_log_sink_runtime_error_from_event_loop_is_ignored(monkeypatch):
    logger_module._log_tasks.clear()
    logger_module.set_event_broadcaster(object())
    monkeypatch.setattr(
        "venom_core.utils.logger.asyncio.get_event_loop",
        lambda: (_ for _ in ()).throw(RuntimeError("no loop")),
    )
    logger_module.log_sink(_message("INFO", "hello"))
    assert logger_module._log_tasks == set()


def test_log_sink_schedules_broadcast_task_when_loop_running(monkeypatch):
    class DummyBroadcaster:
        async def broadcast_log(self, level, message):
            return f"{level}:{message}"

    class DummyTask:
        def __init__(self):
            self.cb = None

        def add_done_callback(self, cb):
            self.cb = cb

    class DummyLoop:
        def __init__(self):
            self.created = 0

        def is_running(self):
            return True

        def create_task(self, coro):
            self.created += 1
            coro.close()
            return DummyTask()

    logger_module._log_tasks.clear()
    logger_module.set_event_broadcaster(DummyBroadcaster())
    loop = DummyLoop()
    monkeypatch.setattr("venom_core.utils.logger.asyncio.get_event_loop", lambda: loop)

    logger_module.log_sink(_message("WARNING", "broadcast me"))
    assert loop.created == 1
    assert len(logger_module._log_tasks) == 1


def test_log_sink_create_task_exception_is_ignored(monkeypatch):
    class DummyBroadcaster:
        async def broadcast_log(self, level, message):
            return f"{level}:{message}"

    class DummyLoop:
        def is_running(self):
            return True

        def create_task(self, coro):
            coro.close()
            raise RuntimeError("task fail")

    logger_module._log_tasks.clear()
    logger_module.set_event_broadcaster(DummyBroadcaster())
    monkeypatch.setattr("venom_core.utils.logger.asyncio.get_event_loop", DummyLoop)

    logger_module.log_sink(_message("ERROR", "x"))
    assert logger_module._log_tasks == set()
