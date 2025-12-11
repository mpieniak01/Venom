"""Moduł: system_status - Agent raportujący stan infrastruktury Venom."""

from typing import List

import httpx
from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class SystemStatusAgent(BaseAgent):
    """
    Agent odpowiedzialny za raportowanie statusu usług i serwisów Venom.

    Zamiast używać LLM, agent bezpośrednio pyta API o wyniki monitoringu,
    a następnie formatuje zwięzły raport w języku polskim.
    """

    def __init__(
        self,
        kernel: Kernel,
        status_endpoint: str = "http://localhost:8000/api/v1/system/services",
    ):
        super().__init__(kernel)
        self.status_endpoint = status_endpoint.rstrip("/")
        logger.info("SystemStatusAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Pobiera status usług i generuje raport tekstowy.

        Args:
            input_text: Oryginalne zapytanie użytkownika (niewykorzystywane)

        Returns:
            Raport statusu w języku polskim
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.status_endpoint)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.error(f"Nie udało się pobrać statusu usług: {exc}")
            return (
                "❌ Nie udało się pobrać aktualnego statusu usług. "
                "Spróbuj ponownie za chwilę lub sprawdź logi ServiceMonitor."
            )

        services = data.get("services", [])
        if not services:
            return "ℹ️ Brak monitorowanych usług w ServiceMonitor."

        return self._format_report(services)

    def _format_report(self, services: List[dict]) -> str:
        """Buduje raport tekstowy na podstawie listy usług."""
        status_groups = {"online": 0, "degraded": 0, "offline": 0, "unknown": 0}
        critical_alerts = []

        for service in services:
            status = service.get("status", "unknown").lower()
            if status not in status_groups:
                status = "unknown"
            status_groups[status] += 1

            if service.get("is_critical") and status != "online":
                critical_alerts.append(service)

        lines = [
            "🛰️ **Raport infrastruktury Venom**",
            f"- Online: {status_groups['online']}, ⚠️ Degraded: {status_groups['degraded']}, "
            f"⛔ Offline: {status_groups['offline']}",
        ]

        if critical_alerts:
            lines.append("\n‼️ **Krytyczne alerty:**")
            for service in critical_alerts:
                lines.append(
                    f"• {service['name']} – status: {service['status'].upper()} "
                    f"(ostatnie sprawdzenie: {service.get('last_check') or 'brak danych'})"
                )

        lines.append("\n📋 **Szczegóły usług:**")
        status_emojis = {
            "online": "🟢",
            "degraded": "🟠",
            "offline": "🔴",
            "unknown": "⚪",
        }

        for service in sorted(
            services, key=lambda s: (s.get("is_critical"), s["name"]), reverse=True
        ):
            status = service.get("status", "unknown").lower()
            emoji = status_emojis.get(status, "⚪")
            latency = service.get("latency_ms")
            latency_text = (
                f"{latency:.0f} ms"
                if isinstance(latency, (int, float))
                else "brak danych"
            )
            last_check = service.get("last_check") or "brak danych"
            importance = " (krytyczna)" if service.get("is_critical") else ""

            lines.append(
                f"{emoji} {service['name']}{importance} – {status.upper()}, "
                f"opóźnienie: {latency_text}, ostatni pomiar: {last_check}"
            )

        return "\n".join(lines)
