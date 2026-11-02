"""Bounded remote-first concurrency policy, with measured GPU headroom."""

from __future__ import annotations

import gc
import subprocess
import time
from dataclasses import replace

from scripts.granite_operator.comparison_parallel import TaskScheduler


def gpu_sample():
    try:
        response = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
                "--id=0",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        utilization, used, total = map(float, response.stdout.strip().split(","))
        if not 0 <= utilization <= 100 or not 0 <= used <= total or total <= 0:
            return None
        return {"gpu_percent": utilization, "memory_percent": used / total * 100}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class AdaptiveScheduler:
    """Resize only between bounded windows, after old tasks have stopped."""

    def __init__(
        self,
        session,
        execution,
        *,
        factory=TaskScheduler,
        sample=gpu_sample,
        changed=lambda event: None,
    ):
        execution.validate()
        self.session, self.execution = session, execution
        self.factory, self.sample, self.changed = factory, sample, changed
        self.stats = {
            "gpu_batch_seconds": 0.0,
            "batch_call_seconds": 0.0,
            "batches": 0,
            "batch_items": 0,
            "decisions": [],
            "gpu_samples": [],
        }

    def run(self, jobs, trial, completed):
        end = time.monotonic() + self.execution.max_seconds
        width = self.execution.concurrency
        ceiling = self.execution.max_concurrency
        pending = list(enumerate(jobs))
        self._decision(None, width, "initial")
        oom = getattr(self.session.torch, "OutOfMemoryError", ())
        while pending:
            remaining = int(end - time.monotonic())
            if remaining < 1:
                raise TimeoutError("comparison_session_deadline")
            current = pending[: self.execution.window_trials]
            active = replace(
                self.execution,
                concurrency=width,
                batch_size=min(
                    width,
                    max(
                        1,
                        self.execution.batch_size * width // self.execution.concurrency,
                    ),
                ),
                max_seconds=remaining,
                adaptive=False,
            )
            runner = self.factory(self.session, active)
            samples, finished = [], []
            timeouts = 0
            original = runner.batcher
            last = float("-inf")

            def monitored(session, requests):
                nonlocal last
                result = original(session, requests)
                if time.monotonic() - last >= 5:
                    last = time.monotonic()
                    reading = self.sample()
                    if reading is not None:
                        samples.append(reading)
                        self.stats["gpu_samples"].append(
                            {**reading, "concurrency": width}
                        )
                return result

            runner.batcher = monitored

            def execute(item, scheduler):
                number, job = item
                return number, trial(job, scheduler)

            def persist(item):
                nonlocal timeouts
                number, row = item
                completed(row)
                finished.append(number)
                timeouts += row.get("failure") in ("task_timeout", "tool_timeout")

            exhausted = False
            try:
                runner.run(current, execute, persist)
            except oom:
                exhausted = True
            for key in (
                "gpu_batch_seconds",
                "batch_call_seconds",
                "batches",
                "batch_items",
            ):
                self.stats[key] += runner.stats[key]
            if not exhausted and len(finished) != len(current):
                raise RuntimeError("comparison_incomplete")
            pending = [item for item in pending if item[0] not in finished]
            if exhausted or timeouts:
                if width == 1 and exhausted:
                    raise RuntimeError("comparison_oom_at_minimum_concurrency")
                lower = max(1, width // 2)
                ceiling = min(ceiling, lower)
                self._decision(
                    width, lower, "cuda_oom" if exhausted else "task_timeouts"
                )
                width = lower
                if exhausted:
                    gc.collect()
                    self.session.torch.cuda.empty_cache()
            elif (
                len(samples) >= 3
                and max(s["gpu_percent"] for s in samples)
                < self.execution.low_gpu_percent
                and max(s["memory_percent"] for s in samples)
                < self.execution.high_memory_percent
            ):
                higher = min(ceiling, width * 2)
                if pending and higher > width:
                    self._decision(width, higher, "low_gpu_with_memory_headroom")
                    width = higher

    def _decision(self, old, new, reason):
        event = {"from": old, "to": new, "reason": reason}
        self.stats["decisions"].append(event)
        self.changed(event)
