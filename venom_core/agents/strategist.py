"""Moduł: strategist - agent planowania i zarządzania złożonością zadań."""

import json
import re
from typing import Dict, Optional

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.complexity_skill import ComplexitySkill
from venom_core.ops.work_ledger import TaskComplexity, TaskStatus, WorkLedger
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class StrategistAgent(BaseAgent):
    """
    Agent Strategist - planista i analityk złożoności.

    Strategist odpowiada za:
    - Ocenę złożoności zadań przed realizacją
    - Dzielenie dużych zadań na mniejsze
    - Monitorowanie postępu i wykrywanie overrun
    - Ostrzeganie przed scope creep
    - Zarządzanie wykorzystaniem zewnętrznych API
    """

    # Limity dla zewnętrznych API (dziennie)
    DEFAULT_API_LIMITS = {
        "openai": {"calls": 1000, "tokens": 1000000},
        "anthropic": {"calls": 500, "tokens": 500000},
        "google": {"calls": 1000, "tokens": 1000000},
    }

    def __init__(
        self,
        kernel: Kernel,
        work_ledger: Optional[WorkLedger] = None,
        api_limits: Optional[Dict[str, Dict[str, int]]] = None,
    ):
        """
        Inicjalizacja Strategist Agent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            work_ledger: Instancja Work Ledger (opcjonalnie)
            api_limits: Limity dla zewnętrznych API
        """
        super().__init__(kernel)

        self.work_ledger = work_ledger or WorkLedger()
        self.complexity_skill = ComplexitySkill()
        self.api_limits = api_limits or self.DEFAULT_API_LIMITS

        # Rejestracja skill w kernel
        self.kernel.add_plugin(self.complexity_skill, "complexity")

        logger.info("StrategistAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie - analizuje i planuje.

        Args:
            input_text: Opis zadania lub komenda

        Returns:
            Analiza i rekomendacje
        """
        # Parsuj komendę
        if input_text.startswith("analyze:"):
            task_desc = input_text.replace("analyze:", "").strip()
            return await self.analyze_task(task_desc)

        elif input_text.startswith("monitor:"):
            task_id = input_text.replace("monitor:", "").strip()
            return self.monitor_task(task_id)

        elif input_text.startswith("report"):
            return self.generate_report()

        elif input_text.startswith("check_api:"):
            provider = input_text.replace("check_api:", "").strip()
            return self.check_api_usage(provider)

        else:
            # Domyślnie: analiza zadania
            return await self.analyze_task(input_text)

    async def analyze_task(
        self, task_description: str, task_id: Optional[str] = None
    ) -> str:
        """
        Analizuje zadanie pod kątem złożoności, czasu i ryzyk.

        Args:
            task_description: Opis zadania
            task_id: Opcjonalny ID zadania (jeśli brak, wygeneruje)

        Returns:
            Analiza z rekomendacjami
        """
        logger.info(f"Analiza zadania: {task_description[:50]}...")

        # Użyj ComplexitySkill do analizy
        complexity_result = await self.complexity_skill.estimate_complexity(
            task_description
        )
        time_result = await self.complexity_skill.estimate_time(task_description)
        risks_result = await self.complexity_skill.flag_risks(task_description)

        # Wyciągnij złożoność z wyniku
        complexity = self._extract_complexity(complexity_result)

        # Sugeruj podział jeśli zadanie jest duże
        subtasks_result = ""
        if complexity in [TaskComplexity.HIGH, TaskComplexity.EPIC]:
            subtasks_result = await self.complexity_skill.suggest_subtasks(
                task_description
            )

        # Szacuj czas
        estimated_minutes = self._extract_time(time_result)

        # Zaloguj do Work Ledger
        if task_id is None:
            # Wygeneruj ID z opisu
            task_id = f"task_{hash(task_description) % 100000}"

        self.work_ledger.log_task(
            task_id=task_id,
            name=task_description[:100],
            description=task_description,
            estimated_minutes=estimated_minutes,
            complexity=complexity,
            metadata={"analyzed_by": "strategist"},
        )

        # Sprawdź ryzyka i dodaj do zadania
        if "⚠️" in risks_result:
            risk_lines = [
                line
                for line in risks_result.split("\n")
                if line.strip().startswith("[")
            ]
            for risk_line in risk_lines:
                self.work_ledger.add_risk(task_id, risk_line.strip())

        # Przygotuj raport
        result = "=" * 60 + "\n"
        result += "STRATEGIST ANALYSIS\n"
        result += "=" * 60 + "\n\n"
        result += f"📋 Zadanie: {task_description[:80]}...\n"
        result += f"🆔 Task ID: {task_id}\n\n"

        result += "--- ZŁOŻONOŚĆ ---\n"
        result += complexity_result + "\n\n"

        result += "--- SZACOWANIE CZASU ---\n"
        result += time_result + "\n\n"

        result += "--- RYZYKA ---\n"
        result += risks_result + "\n\n"

        if subtasks_result:
            result += "--- SUGEROWANY PODZIAŁ ---\n"
            result += subtasks_result + "\n\n"

        # Rekomendacje Strategista
        result += "=" * 60 + "\n"
        result += "REKOMENDACJE STRATEGIST\n"
        result += "=" * 60 + "\n"
        result += self._generate_recommendations(
            complexity, estimated_minutes, risks_result
        )

        return result

    def monitor_task(self, task_id: str) -> str:
        """
        Monitoruje postęp zadania i wykrywa overrun.

        Args:
            task_id: Identyfikator zadania

        Returns:
            Status monitoringu
        """
        task = self.work_ledger.get_task(task_id)
        if not task:
            return f"❌ Zadanie {task_id} nie istnieje w Work Ledger."

        # Sprawdź prognozę overrun
        overrun_prediction = self.work_ledger.predict_overrun(task_id)

        result = "=" * 60 + "\n"
        result += f"MONITORING: {task.name}\n"
        result += "=" * 60 + "\n\n"

        result += f"Status: {task.status.value}\n"
        result += f"Postęp: {task.progress_percent:.1f}%\n"
        result += f"Szacowany czas: {task.estimated_minutes:.0f} minut\n"
        result += f"Rzeczywisty czas: {task.actual_minutes:.0f} minut\n"
        result += f"Złożoność: {task.complexity.value}\n\n"

        # Prognoza
        if overrun_prediction.get("will_overrun"):
            result += "⚠️ OSTRZEŻENIE: Przewidywane przekroczenie estymacji!\n"
            result += f"Prognozowany całkowity czas: {overrun_prediction['projected_total_minutes']:.0f} minut\n"
            result += f"Przekroczenie: {overrun_prediction['overrun_percent']:.1f}%\n"
            result += f"Rekomendacja: {overrun_prediction['recommendation']}\n\n"
        else:
            result += "✅ Zadanie w normie - zgodnie z estymacją.\n\n"

        # Ryzyka
        if task.risks:
            result += "Zidentyfikowane ryzyka:\n"
            for i, risk in enumerate(task.risks, 1):
                result += f"  {i}. {risk}\n"
            result += "\n"

        # API usage
        if task.api_calls_made > 0:
            result += f"API Calls: {task.api_calls_made}\n"
            result += f"Tokens Used: {task.tokens_used}\n"

            if "api_usage" in task.metadata:
                result += "\nBreakdown per provider:\n"
                for provider, usage in task.metadata["api_usage"].items():
                    result += f"  - {provider}: {usage['calls']} calls, {usage['tokens']} tokens\n"

        return result

    def generate_report(self) -> str:
        """
        Generuje raport ze wszystkich zadań.

        Returns:
            Raport podsumowujący
        """
        summary = self.work_ledger.summaries()

        result = "=" * 60 + "\n"
        result += "STRATEGIST REPORT - OPERATIONS DASHBOARD\n"
        result += "=" * 60 + "\n\n"

        result += f"📊 Łączna liczba zadań: {summary['total_tasks']}\n"

        # Handle empty case
        if summary["total_tasks"] == 0:
            result += "\n" + summary.get("message", "Brak zadań w systemie") + "\n"
            return result

        result += f"✅ Ukończone: {summary['completed']}\n"
        result += f"🔄 W trakcie: {summary['in_progress']}\n"
        result += f"⚠️ Overrun: {summary['overrun']}\n\n"

        result += f"⏱️ Łączny szacowany czas: {summary['total_estimated_minutes']:.0f} minut ({summary['total_estimated_minutes'] / 60:.1f}h)\n"
        result += f"⏱️ Łączny rzeczywisty czas: {summary['total_actual_minutes']:.0f} minut ({summary['total_actual_minutes'] / 60:.1f}h)\n"
        result += f"🎯 Dokładność estymacji: {summary['estimation_accuracy_percent']:.1f}%\n\n"

        # Breakdown po złożoności
        result += "Breakdown po złożoności:\n"
        for complexity, stats in summary["complexity_breakdown"].items():
            result += f"  - {complexity}: {stats['count']} zadań (ukończonych: {stats['completed']})\n"
            result += f"    Średni czas: {stats['avg_estimated_minutes']:.0f} minut\n"

        result += (
            f"\n📁 Łącznie plików zmodyfikowanych: {summary['total_files_touched']}\n"
        )
        result += f"🌐 Łącznie wywołań API: {summary['total_api_calls']}\n"
        result += f"🔤 Łącznie tokenów: {summary['total_tokens_used']}\n"

        return result

    def check_api_usage(self, provider: Optional[str] = None) -> str:
        """
        Sprawdza wykorzystanie zewnętrznych API.

        Args:
            provider: Opcjonalnie - sprawdź konkretnego providera

        Returns:
            Raport wykorzystania API
        """
        summary = self.work_ledger.summaries()

        result = "=" * 60 + "\n"
        result += "API USAGE REPORT\n"
        result += "=" * 60 + "\n\n"

        # Handle empty case
        total_api_calls = summary.get("total_api_calls", 0)
        total_tokens = summary.get("total_tokens_used", 0)

        result += f"Łączne wywołania API: {total_api_calls}\n"
        result += f"Łączne tokeny użyte: {total_tokens}\n\n"

        # Sprawdź limity per provider
        result += "Limity API:\n"
        for prov, limits in self.api_limits.items():
            if provider and prov != provider:
                continue

            # Policz aktualne użycie
            current_calls = 0
            current_tokens = 0

            for task in self.work_ledger.list_tasks():
                if "api_usage" in task.metadata and prov in task.metadata["api_usage"]:
                    current_calls += task.metadata["api_usage"][prov]["calls"]
                    current_tokens += task.metadata["api_usage"][prov]["tokens"]

            calls_percent = (
                (current_calls / limits["calls"]) * 100 if limits["calls"] > 0 else 0
            )
            tokens_percent = (
                (current_tokens / limits["tokens"]) * 100 if limits["tokens"] > 0 else 0
            )

            status = "✅"
            if calls_percent > 80 or tokens_percent > 80:
                status = "⚠️"
            if calls_percent > 95 or tokens_percent > 95:
                status = "🚨"

            result += f"\n{status} {prov.upper()}:\n"
            result += (
                f"  Calls: {current_calls}/{limits['calls']} ({calls_percent:.1f}%)\n"
            )
            result += f"  Tokens: {current_tokens}/{limits['tokens']} ({tokens_percent:.1f}%)\n"

            # Rekomendacje
            if calls_percent > 90 or tokens_percent > 90:
                result += "  🚨 OSTRZEŻENIE: Zbliżasz się do limitu - rozważ użycie lokalnych modeli.\n"
            elif calls_percent > 75 or tokens_percent > 75:
                result += "  ⚠️ Uwaga: Wysokie zużycie - monitoruj.\n"

        return result

    def suggest_local_fallback(self, task_description: str) -> str:
        """
        Sugeruje lokalne alternatywy dla zadań intensywnych API.

        Args:
            task_description: Opis zadania

        Returns:
            Rekomendacja fallback
        """
        desc_lower = task_description.lower()

        suggestions = []

        if "obraz" in desc_lower or "image" in desc_lower or "dall-e" in desc_lower:
            suggestions.append(
                "🎨 Generowanie obrazów: Rozważ Stable Diffusion (lokalny) zamiast DALL-E/Midjourney"
            )

        if "embedding" in desc_lower or "wektoryzacja" in desc_lower:
            suggestions.append(
                "📊 Embeddingi: Użyj sentence-transformers (lokalny) zamiast OpenAI embeddings"
            )

        if "analiza tekstu" in desc_lower and "duży" in desc_lower:
            suggestions.append(
                "📄 Analiza dużych tekstów: Podziel na mniejsze fragmenty lub użyj lokalnego LLM"
            )

        if not suggestions:
            return "✅ Brak sugestii lokalnych fallbacków - kontynuuj z API."

        result = "💡 SUGESTIE LOKALNYCH FALLBACKÓW:\n\n"
        result += "\n".join(suggestions)
        result += "\n\nKorzyści: Brak limitów API, niższe koszty operacyjne, większa prywatność."

        return result

    def should_pause_task(self, task_id: str) -> bool:
        """
        Decyduje czy zadanie powinno zostać wstrzymane.

        Args:
            task_id: Identyfikator zadania

        Returns:
            True jeśli zadanie powinno być wstrzymane
        """
        task = self.work_ledger.get_task(task_id)
        if not task or task.status != TaskStatus.IN_PROGRESS:
            return False

        # Sprawdź overrun
        overrun = self.work_ledger.predict_overrun(task_id)
        if overrun.get("will_overrun"):
            overrun_percent = overrun.get("overrun_percent", 0)
            if overrun_percent > 100:
                logger.warning(
                    f"Zadanie {task_id} przekracza estymację o {overrun_percent:.0f}% - rekomendacja PAUSE"
                )
                return True

        # Sprawdź ryzyka
        if len(task.risks) > 3:
            logger.warning(
                f"Zadanie {task_id} ma {len(task.risks)} ryzyk - rekomendacja PAUSE"
            )
            return True

        return False

    def _extract_complexity(self, complexity_result: str) -> TaskComplexity:
        """Wyciąga poziom złożoności z wyniku tekstowego."""
        for complexity in TaskComplexity:
            if complexity.value in complexity_result:
                return complexity
        return TaskComplexity.MEDIUM

    def _extract_time(self, time_result: str) -> float:
        """
        Wyciąga szacowany czas z wyniku tekstowego.
        Obsługuje format JSON {"estimated_minutes": X, "complexity": Y} oraz
        starszy format {"minutes": X} oraz tekstowy "Oszacowany czas: X".

        Args:
            time_result: Wynik tekstowy z estimate_time

        Returns:
            Szacowany czas w minutach
        """
        # Najpierw spróbuj wyciągnąć JSON z początku odpowiedzi
        try:
            # Szukaj JSON na początku stringa
            lines = time_result.strip().split("\n")
            for line in lines:
                line = line.strip()
                # Sprawdź czy linia wygląda jak JSON przed parsowaniem
                if line.startswith("{") and line.endswith("}"):
                    try:
                        data = json.loads(line)
                        # Preferuj nowy format z "estimated_minutes"
                        minutes = data.get("estimated_minutes")
                        if minutes is None:
                            minutes = data.get("minutes")
                        if minutes is not None:
                            logger.debug(f"Wyciągnięto czas z JSON: {minutes} minut")
                            return float(minutes)
                    except json.JSONDecodeError:
                        # Jeśli to nie jest JSON, kontynuuj do następnej linii
                        continue
        except (ValueError, AttributeError) as e:
            logger.debug(f"Błąd podczas iteracji po liniach: {e}")

        # Fallback: szukaj wzorca tekstowego "Oszacowany czas: X"
        match = re.search(r"Oszacowany czas:\s*(\d+)", time_result)
        if match:
            minutes = float(match.group(1))
            logger.debug(f"Wyciągnięto czas z tekstu: {minutes} minut")
            return minutes

        # Ostatni fallback: zwróć wartość domyślną z ostrzeżeniem
        logger.warning(
            f"Nie udało się wyciągnąć czasu z wyniku. Używam domyślnej wartości 30 minut. "
            f"Wynik: {time_result[:100]}"
        )
        return 30.0

    def _generate_recommendations(
        self, complexity: TaskComplexity, estimated_minutes: float, risks: str
    ) -> str:
        """Generuje rekomendacje na podstawie analizy."""
        recommendations = []

        # Rekomendacje na podstawie złożoności
        if complexity == TaskComplexity.EPIC:
            recommendations.append(
                "🚨 EPIC Task: Obowiązkowy podział na mniejsze PR-y. Nie próbuj wykonać w jednym sprint."
            )
        elif complexity == TaskComplexity.HIGH:
            recommendations.append(
                "⚠️ HIGH Complexity: Rozważ podział na 2-3 mniejsze zadania."
            )

        # Rekomendacje czasowe
        if estimated_minutes > 240:  # > 4h
            recommendations.append(
                f"⏱️ Szacowany czas: {estimated_minutes / 60:.1f}h - zaplanuj wielodniową pracę."
            )
        elif estimated_minutes > 120:  # > 2h
            recommendations.append(
                "⏱️ Zadanie długie - zaplanuj przerwy i regularne commity."
            )

        # Rekomendacje na podstawie ryzyk
        if "⚠️" in risks and len(risks.split("\n")) > 5:
            recommendations.append(
                "🛡️ Wysokie ryzyko: Rozpocznij od prototypu lub proof-of-concept."
            )

        # Ogólne best practices
        if complexity in [
            TaskComplexity.MEDIUM,
            TaskComplexity.HIGH,
            TaskComplexity.EPIC,
        ]:
            recommendations.append(
                "📝 Zalecane: Napisz plan działania przed rozpoczęciem kodowania."
            )

        if not recommendations:
            recommendations.append(
                "✅ Zadanie w rozsądnym zakresie - możesz kontynuować."
            )

        return "\n".join(recommendations) + "\n"
