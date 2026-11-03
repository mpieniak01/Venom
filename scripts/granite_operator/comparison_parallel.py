"""Bounded task concurrency with one GPU owner and homogeneous inference batches."""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import contextlib
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from types import SimpleNamespace


@dataclass(frozen=True)
class Execution:
    concurrency: int = 1
    batch_size: int = 1
    batch_wait_ms: int = 20
    task_seconds: int = 60
    max_seconds: int = 7200
    host: str = "local"
    adaptive: bool = False
    max_concurrency: int = 8
    low_gpu_percent: int = 50
    high_memory_percent: int = 80
    window_trials: int = 16

    def validate(self):
        if (
            type(self.concurrency) is not int
            or self.concurrency not in (1, 2, 4, 8)
            or type(self.batch_size) is not int
            or not 1 <= self.batch_size <= self.concurrency
            or type(self.batch_wait_ms) is not int
            or not 0 <= self.batch_wait_ms <= 100
            or type(self.task_seconds) is not int
            or not 1 <= self.task_seconds <= 600
            or type(self.max_seconds) is not int
            or not 1 <= self.max_seconds <= 14400
            or self.host not in ("local", "remote")
            or type(self.adaptive) is not bool
            or type(self.max_concurrency) is not int
            or self.max_concurrency not in (1, 2, 4, 8)
            or (self.adaptive and self.concurrency > self.max_concurrency)
            or type(self.low_gpu_percent) is not int
            or not 1 <= self.low_gpu_percent <= 100
            or type(self.high_memory_percent) is not int
            or not 1 <= self.high_memory_percent <= 100
            or type(self.window_trials) is not int
            or not 8 <= self.window_trials <= 128
        ):
            raise ValueError("comparison_execution_invalid")
        return asdict(self)


def execution_options(parser):
    parser.add_argument("--concurrency", type=int, choices=(1, 2, 4, 8), default=None)
    parser.add_argument(
        "--adaptive", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--max-concurrency", type=int, choices=(1, 2, 4, 8))
    parser.add_argument("--low-gpu-percent", type=int, default=50)
    parser.add_argument("--high-memory-percent", type=int, default=80)
    parser.add_argument("--window-trials", type=int, default=16)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--batch-wait-ms", type=int, default=20)
    parser.add_argument("--task-seconds", type=int, default=60)
    parser.add_argument("--max-seconds", type=int, default=7200)
    parser.add_argument(
        "--execution-host", choices=("local", "remote"), default="local"
    )


def execution_from_args(args):
    remote = args.execution_host == "remote"
    concurrency = (
        args.concurrency if args.concurrency is not None else (4 if remote else 1)
    )
    adaptive = getattr(args, "adaptive", None)
    value = Execution(
        concurrency,
        args.batch_size if args.batch_size is not None else concurrency,
        args.batch_wait_ms,
        args.task_seconds,
        args.max_seconds,
        args.execution_host,
        adaptive=remote if adaptive is None else adaptive,
        max_concurrency=getattr(args, "max_concurrency", None) or (8 if remote else 2),
        low_gpu_percent=getattr(args, "low_gpu_percent", 50),
        high_memory_percent=getattr(args, "high_memory_percent", 80),
        window_trials=getattr(args, "window_trials", 16),
    )
    value.validate()
    return value


def _has_images(messages):
    return any(
        isinstance(message, dict)
        and isinstance(message.get("content"), list)
        and any(
            part.get("type") == "image"
            for part in message["content"]
            if isinstance(part, dict)
        )
        for message in messages
    )


def _image_items(messages):
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            yield from (
                item
                for item in content
                if isinstance(item, dict) and item.get("type") == "image"
            )


def _open_image(item):
    from pathlib import Path

    from PIL import Image

    from venom_core.services.granite_operator.contract import file_digest
    from venom_core.services.remote_training.paths import operator_path

    path = operator_path(Path(item["path"]))
    if file_digest(path) != item["sha256"]:
        raise ValueError("comparison_image_hash_changed")
    with Image.open(path) as source:
        if source.width * source.height > 16_000_000:
            raise ValueError("comparison_image_pixels_exceeded")
        return source.convert("RGB")


def _image_payload(session, messages, tools):
    from venom_core.services.gemma4_operator.protocol import render_messages

    if getattr(session, "gemma_profile", None) is None:
        raise ValueError("comparison_image_backend_unsupported")
    processor = getattr(session, "processor", None)
    if processor is None:
        from transformers import AutoProcessor

        processor = AutoProcessor.from_pretrained(
            session.snapshot,
            local_files_only=True,
            trust_remote_code=False,
            use_fast=False,
        )
        session.processor = processor
    images = []
    for index, item in enumerate(_image_items(messages)):
        if index >= 4:
            raise ValueError("comparison_image_count_exceeded")
        images.append(_open_image(item))
    text = render_messages(processor, messages, tools, session.gemma_profile)
    return processor(text=text, images=images, return_tensors="pt")


def _generate_image(session, request, inference):
    from scripts.granite_operator.comparison import generation_options

    messages, tools, arm, deadline = request
    payload = _image_payload(session, messages, tools)
    length = payload["input_ids"].shape[-1]
    if length + inference["max_new_tokens"] > inference["context"]:
        raise ValueError("comparison_context_limit")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("comparison_task_deadline")
    payload = payload.to("cuda", dtype=session.torch.bfloat16)
    context = (
        session.model.disable_adapter() if arm == "base" else contextlib.nullcontext()
    )
    session.torch.cuda.synchronize()
    start = time.monotonic()
    # NF4 keeps some vision normalization weights in FP32.
    with (
        context,
        session.torch.inference_mode(),
        session.torch.autocast("cuda", dtype=session.torch.bfloat16),
    ):
        output = session.model.generate(
            **payload,
            max_new_tokens=inference["max_new_tokens"],
            do_sample=False,
            use_cache=True,
            max_time=remaining,
            pad_token_id=session.tokenizer.pad_token_id,
            **generation_options(session),
        )
    session.torch.cuda.synchronize()
    generated = output[0, length:].tolist()
    stops = set(generation_options(session).get("eos_token_id", []))
    for index, token in enumerate(generated):
        if int(token) in stops:
            generated = generated[: index + 1]
            break
    return {
        "text": session.tokenizer.decode(generated, skip_special_tokens=False),
        "seconds": time.monotonic() - start,
        "tokens": len(generated),
        "input_tokens": length,
        "batch_size": 1,
        "modality": "image_text",
        "execution": "serialized_on_shared_model",
    }


def generate_batch(session, requests):
    """Run only on the scheduler thread; never toggle PEFT from task threads."""
    from scripts.granite_operator.comparison import (
        encode_prompt,
        generation_options,
        inference_settings,
    )

    inference = inference_settings(session)
    from venom_core.services.remote_training.host import is_gemma_model

    if is_gemma_model(getattr(getattr(session, "profile", None), "model", None)):
        from venom_core.services.gemma4_operator.training_worker import (
            require_cuda_placement,
        )

        require_cuda_placement(session.model)
    arm = requests[0][2]
    if any(r[2] != arm for r in requests):
        raise ValueError("comparison_mixed_adapter_batch")
    tokenizer, torch = session.tokenizer, session.torch
    if any(_has_images(request[0]) for request in requests):
        results = [
            _generate_image(session, request, inference)
            if _has_images(request[0])
            else generate_batch(session, [request])[0]
            for request in requests
        ]
        results[0]["batch_total_seconds"] = sum(row["seconds"] for row in results)
        return results
    encoded = [encode_prompt(session, request[0], request[1]) for request in requests]
    if any(
        len(ids) + inference["max_new_tokens"] > inference["context"] for ids in encoded
    ):
        raise ValueError("comparison_context_limit")
    previous = tokenizer.padding_side
    try:
        tokenizer.padding_side = "left"
        ids = tokenizer.pad(
            {"input_ids": encoded}, padding=True, return_tensors="pt"
        ).to("cuda")
    finally:
        tokenizer.padding_side = previous
    remaining = max(r[3] for r in requests) - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("comparison_task_deadline")
    context = (
        session.model.disable_adapter() if arm == "base" else contextlib.nullcontext()
    )
    torch.cuda.synchronize()
    start = time.monotonic()
    with context, torch.inference_mode():
        output = session.model.generate(
            **ids,
            max_new_tokens=inference["max_new_tokens"],
            do_sample=False,
            use_cache=True,
            max_time=remaining,
            pad_token_id=tokenizer.pad_token_id,
            **generation_options(session),
        )
    torch.cuda.synchronize()
    seconds = time.monotonic() - start
    batch_id = uuid.uuid4().hex
    results = []
    for index, prompt in enumerate(encoded):
        tokens = output[index, ids["input_ids"].shape[-1] :].tolist()
        configured = getattr(
            getattr(session.model, "generation_config", None), "eos_token_id", None
        )
        stop_ids = set(
            configured if isinstance(configured, (list, tuple)) else [configured]
        )
        native_stops = generation_options(session).get("eos_token_id")
        if native_stops is not None:
            stop_ids = set(native_stops)
        stop_ids.add(tokenizer.eos_token_id)
        for position, token in enumerate(tokens):
            if token in stop_ids:
                tokens = tokens[: position + 1]
                break
        results.append(
            {
                "text": tokenizer.decode(tokens, skip_special_tokens=False),
                "seconds": seconds,
                "tokens": len(tokens),
                "input_tokens": len(prompt),
                "batch_id": batch_id,
                "batch_size": len(requests),
            }
        )
    return results


class TaskScheduler:
    """One bounded set of task threads; all CUDA and adapter state stays here."""

    def __init__(self, session, execution, *, batcher=generate_batch):
        execution.validate()
        self.session, self.execution, self.batcher = session, execution, batcher
        self.pending = queue.Queue(maxsize=execution.concurrency)
        self.lock = threading.Lock()
        self.waiters = set()
        self.error = None
        self.stats = {
            "gpu_batch_seconds": 0.0,
            "batch_call_seconds": 0.0,
            "batches": 0,
            "batch_items": 0,
        }
        # Concurrent trials cannot reset shared CUDA peaks or perform GPU RPCs.
        self.trial_session = SimpleNamespace(
            profile=getattr(session, "profile", None),
            gemma_profile=getattr(session, "gemma_profile", None),
            comparison_protocol=getattr(session, "comparison_protocol", None),
            torch=SimpleNamespace(
                cuda=SimpleNamespace(
                    reset_peak_memory_stats=lambda: None,
                    max_memory_allocated=lambda: None,
                    max_memory_reserved=lambda: None,
                )
            ),
        )

    def generate(self, _session, messages, tools, arm, deadline):
        future = futures.Future()
        queued = time.monotonic()
        with self.lock:
            if self.error is not None:
                raise RuntimeError("comparison_scheduler_closed") from self.error
            self.waiters.add(future)
            self.pending.put_nowait((messages, tools, arm, deadline, future, queued))
        try:
            return future.result()
        finally:
            with self.lock:
                self.waiters.discard(future)

    def _dispatch(self, batch):
        now = time.monotonic()
        waits = [now - r[5] for r in batch]
        requests = [
            (r[0], r[1], r[2], min(r[3] + wait, self.deadline))
            for r, wait in zip(batch, waits)
        ]
        start = time.monotonic()
        try:
            generated = self.batcher(self.session, requests)
        except (ValueError, TimeoutError) as error:
            if str(error) not in (
                "comparison_context_limit",
                "comparison_task_deadline",
            ):
                raise
            if len(batch) > 1:
                for item in batch:
                    self._dispatch([item])
            else:
                error.queue_seconds = waits[0]
                batch[0][4].set_exception(error)
            return
        if len(generated) != len(batch):
            raise RuntimeError("comparison_batch_response_invalid")
        self.stats["batch_call_seconds"] += time.monotonic() - start
        self.stats["gpu_batch_seconds"] += generated[0].get(
            "batch_total_seconds", generated[0]["seconds"]
        )
        self.stats["batches"] += 1
        self.stats["batch_items"] += len(batch)
        for request, value, wait in zip(batch, generated, waits):
            if time.monotonic() >= min(request[3] + wait, self.deadline):
                deadline_error = TimeoutError("comparison_task_deadline")
                deadline_error.queue_seconds = wait
                request[4].set_exception(deadline_error)
            else:
                request[4].set_result({**value, "queue_seconds": wait})

    def run(self, jobs, trial, completed):
        """Persist completion on this thread; cancel pending work on any fatal error."""
        deadline = time.monotonic() + self.execution.max_seconds
        self.deadline = deadline
        backlog = []
        with futures.ThreadPoolExecutor(max_workers=self.execution.concurrency) as pool:
            workers = []
            try:
                workers = [pool.submit(trial, job, self) for job in jobs]
                while workers:
                    for worker in list(workers):
                        if worker.done():
                            completed(worker.result())
                            workers.remove(worker)
                    if time.monotonic() >= deadline:
                        raise TimeoutError("comparison_session_deadline")
                    if not workers:
                        break
                    if not backlog:
                        try:
                            backlog.append(self.pending.get(timeout=0.01))
                        except queue.Empty:
                            continue
                    arm = backlog[0][2]
                    until = min(
                        deadline, time.monotonic() + self.execution.batch_wait_ms / 1000
                    )
                    while (
                        len(backlog) < self.execution.concurrency
                        and time.monotonic() < until
                    ):
                        try:
                            backlog.append(
                                self.pending.get(
                                    timeout=max(0.001, until - time.monotonic())
                                )
                            )
                        except queue.Empty:
                            break
                    batch = [r for r in backlog if r[2] == arm][
                        : self.execution.batch_size
                    ]
                    backlog = [r for r in backlog if r not in batch]
                    self._dispatch(batch)
            finally:
                with self.lock:
                    self.error = RuntimeError("comparison_scheduler_closed")
                    for waiter in self.waiters:
                        if not waiter.done():
                            waiter.set_exception(self.error)
                for worker in workers:
                    worker.cancel()
