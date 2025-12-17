"""Locust scenario – opcjonalny test obciążeniowy chatu."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from gevent import sleep
from locust import HttpUser, between, task


class ChatUser(HttpUser):
    """
    Symulacja użytkownika wysyłającego proste zapytania.

    - POST /api/v1/tasks
    - Poll /api/v1/tasks/{id} aż do zakończenia
    """

    wait_time = between(0.5, 2.0)
    host = os.getenv("LOCUST_TARGET", "http://localhost:8000")
    poll_interval = float(os.getenv("LOCUST_POLL_INTERVAL", "0.5"))
    timeout_seconds = float(os.getenv("LOCUST_TIMEOUT", "25"))

    @task
    def chat_roundtrip(self):
        payload: Dict[str, Any] = {
            "content": f"Locust benchmark {time.time()}",
            "store_knowledge": False,
        }
        with self.client.post(
            "/api/v1/tasks",
            json=payload,
            name="/api/v1/tasks [POST]",
        ) as response:
            if not response.ok:
                return
            task_id = response.json()["task_id"]

        deadline = time.perf_counter() + self.timeout_seconds
        while time.perf_counter() < deadline:
            with self.client.get(
                f"/api/v1/tasks/{task_id}",
                name="/api/v1/tasks/{id} [GET]",
                timeout=30,
            ) as detail:
                if not detail.ok:
                    break
                status = detail.json().get("status")
                if status in {"COMPLETED", "FAILED"}:
                    return
            sleep(self.poll_interval)
