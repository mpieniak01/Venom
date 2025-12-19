"""Moduł: ux_analyst - agent analizujący użyteczność na podstawie logów symulacji."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class UXAnalystAgent(BaseAgent):
    """Agent analizujący użyteczność aplikacji na podstawie logów symulacji.

    Agent przegląda logi JSONL z sesji symulowanych użytkowników,
    identyfikuje problemy UX i generuje rekomendacje.
    """

    SYSTEM_PROMPT = """Jesteś ekspertem UX (User Experience) specjalizującym się w analizie użyteczności aplikacji.

TWOJE ZADANIE:
Analizujesz logi z sesji symulowanych użytkowników i identyfikujesz problemy w interfejsie użytkownika.

CO ANALIZUJESZ:
- Poziomy frustracji użytkowników
- Punkty w których użytkownicy się gubią
- Elementy interfejsu które są trudne do znalezienia
- Błędy i problemy techniczne
- Wzorce zachowań różnych typów użytkowników

CO TWORZYSZ:
1. "Heatmapa Frustracji" - identyfikacja najbardziej problematycznych miejsc
2. Konkretne rekomendacje dla Codera (co poprawić i jak)
3. Priorytety napraw (krytyczne, ważne, nice-to-have)

STYL RAPORTOWANIA:
- Konkretne, actionable recommendations
- Wskaż DOKŁADNIE co należy zmienić (selektory CSS, teksty, pozycje)
- Uzasadnij każdą rekomendację danymi z logów
- Uwzględnij różnice między typami użytkowników (seniory vs tech-savvy)

Pamiętaj: Twoim celem jest pomóc stworzyć aplikację użyteczną dla WSZYSTKICH użytkowników!"""

    def __init__(self, kernel: Kernel, workspace_root: Optional[str] = None):
        """
        Inicjalizacja UXAnalystAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            workspace_root: Katalog roboczy (gdzie są logi symulacji)
        """
        super().__init__(kernel)

        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.logs_dir = self.workspace_root / "simulation_logs"

        # Historia czatu
        self.chat_history = ChatHistory()
        self.chat_history.add_system_message(self.SYSTEM_PROMPT)

        logger.info("UXAnalystAgent zainicjalizowany")

    def _load_session_logs(self, log_files: list[Path]) -> list[dict]:
        """
        Ładuje logi z plików JSONL.

        Args:
            log_files: Lista ścieżek do plików logów

        Returns:
            Lista eventów z wszystkich sesji
        """
        all_events = []

        for log_file in log_files:
            if not log_file.exists():
                logger.warning(f"Plik logu nie istnieje: {log_file}")
                continue

            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            event = json.loads(line)
                            all_events.append(event)
                logger.debug(f"Załadowano logi z: {log_file}")
            except Exception as e:
                logger.error(f"Błąd podczas ładowania logu {log_file}: {e}")

        logger.info(f"Załadowano {len(all_events)} eventów z {len(log_files)} sesji")
        return all_events

    def analyze_sessions(self, session_ids: Optional[list[str]] = None) -> dict:
        """
        Analizuje sesje symulacji.

        Args:
            session_ids: Lista ID sesji do analizy (None = wszystkie)

        Returns:
            Słownik z wynikami analizy
        """
        logger.info("Rozpoczynam analizę sesji symulacji")

        # Znajdź pliki logów
        if session_ids:
            log_files = [self.logs_dir / f"session_{sid}.jsonl" for sid in session_ids]
        else:
            log_files = list(self.logs_dir.glob("session_*.jsonl"))

        if not log_files:
            logger.warning("Nie znaleziono plików logów do analizy")
            return {"error": "Brak logów do analizy"}

        # Załaduj eventy
        events = self._load_session_logs(log_files)

        if not events:
            return {"error": "Nie załadowano żadnych eventów"}

        # Przeprowadź analizę
        analysis = self._perform_analysis(events)

        logger.info("Analiza zakończona")
        return analysis

    def _perform_analysis(self, events: list[dict]) -> dict:
        """
        Przeprowadza szczegółową analizę eventów.

        Args:
            events: Lista eventów z logów

        Returns:
            Słownik z wynikami analizy
        """
        # Statystyki podstawowe
        sessions = defaultdict(list)
        for event in events:
            sessions[event["session_id"]].append(event)

        total_sessions = len(sessions)
        successful_sessions = 0
        rage_quits = 0
        total_frustration = 0
        frustration_reasons = []
        emotional_states_count = Counter()
        personas_performance = defaultdict(lambda: {"success": 0, "total": 0})

        # Analiza per sesja
        for session_id, session_events in sessions.items():
            # Ostatni event to session_end
            end_event = next(
                (
                    e
                    for e in reversed(session_events)
                    if e["event_type"] == "session_end"
                ),
                None,
            )

            if end_event:
                if end_event.get("goal_achieved"):
                    successful_sessions += 1
                if end_event.get("rage_quit"):
                    rage_quits += 1

                persona_name = end_event.get("persona_name", "unknown")
                personas_performance[persona_name]["total"] += 1
                if end_event.get("goal_achieved"):
                    personas_performance[persona_name]["success"] += 1

                total_frustration += end_event.get("frustration_level", 0)

            # Zbierz powody frustracji
            for event in session_events:
                if event["event_type"] == "frustration_increase":
                    frustration_reasons.append(event.get("reason", "unknown"))

                emotional_states_count[event.get("emotional_state", "unknown")] += 1

        # Najczęstsze problemy
        frustration_frequency = Counter(frustration_reasons)
        top_problems = frustration_frequency.most_common(5)

        # Heatmapa frustracji (które persony miały najwięcej problemów)
        frustration_heatmap = []
        for persona, perf in personas_performance.items():
            success_rate = perf["success"] / perf["total"] if perf["total"] > 0 else 0
            frustration_heatmap.append(
                {
                    "persona": persona,
                    "sessions": perf["total"],
                    "success_rate": round(success_rate * 100, 1),
                    "failure_rate": round((1 - success_rate) * 100, 1),
                }
            )

        # Sortuj po failure rate
        frustration_heatmap.sort(key=lambda x: x["failure_rate"], reverse=True)

        return {
            "summary": {
                "total_sessions": total_sessions,
                "successful_sessions": successful_sessions,
                "rage_quits": rage_quits,
                "success_rate": (
                    round(successful_sessions / total_sessions * 100, 1)
                    if total_sessions > 0
                    else 0
                ),
                "avg_frustration": (
                    round(total_frustration / total_sessions, 2)
                    if total_sessions > 0
                    else 0
                ),
            },
            "top_problems": [
                {"problem": problem, "occurrences": count}
                for problem, count in top_problems
            ],
            "frustration_heatmap": frustration_heatmap,
            "emotional_states": dict(emotional_states_count),
            "personas_performance": dict(personas_performance),
        }

    async def generate_recommendations(self, analysis: dict) -> str:
        """
        Generuje rekomendacje UX na podstawie analizy używając LLM.

        Args:
            analysis: Wyniki analizy z analyze_sessions()

        Returns:
            Raport z rekomendacjami
        """
        logger.info("Generuję rekomendacje UX używając LLM")

        # Przygotuj prompt z danymi analizy
        analysis_summary = json.dumps(analysis, indent=2, ensure_ascii=False)

        prompt = f"""Przeanalizuj następujące dane z sesji symulacji użytkowników:

{analysis_summary}

Na podstawie tych danych, wygeneruj:

1. HEATMAPA FRUSTRACJI - które elementy/aspekty aplikacji sprawiają najwięcej problemów
2. TOP 3 KRYTYCZNE PROBLEMY - co trzeba naprawić najpilniej
3. KONKRETNE REKOMENDACJE dla Codera - co i jak poprawić
4. UWAGI DOTYCZĄCE RÓŻNYCH GRUP UŻYTKOWNIKÓW - jak różne persony reagowały

Format odpowiedzi: Markdown z jasno wydzielonymi sekcjami."""

        # Dodaj do historii
        self.chat_history.add_user_message(prompt)

        # Wykonaj chat completion
        execution_settings = OpenAIChatPromptExecutionSettings(
            max_tokens=2000,
            temperature=0.3,  # Niższa temperatura dla bardziej precyzyjnych rekomendacji
        )

        chat_service = self.kernel.get_service()
        result = await self._invoke_chat_with_fallbacks(
            chat_service=chat_service,
            chat_history=self.chat_history,
            settings=execution_settings,
            enable_functions=False,
        )

        recommendations = str(result)
        self.chat_history.add_assistant_message(recommendations)

        logger.info("Rekomendacje UX wygenerowane")
        return recommendations

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zapytanie o analizę UX.

        Args:
            input_text: Zapytanie użytkownika

        Returns:
            Odpowiedź z analizą/rekomendacjami
        """
        try:
            # Sprawdź czy użytkownik prosi o analizę
            if "analizuj" in input_text.lower() or "analiza" in input_text.lower():
                # Wykonaj analizę wszystkich sesji
                analysis = self.analyze_sessions()

                if "error" in analysis:
                    return f"❌ Błąd analizy: {analysis['error']}"

                # Wygeneruj rekomendacje
                recommendations = await self.generate_recommendations(analysis)

                return f"""# RAPORT ANALIZY UX

## Podsumowanie
- Sesji: {analysis["summary"]["total_sessions"]}
- Sukces: {analysis["summary"]["successful_sessions"]} ({analysis["summary"]["success_rate"]}%)
- Rage Quits: {analysis["summary"]["rage_quits"]}
- Średnia frustracja: {analysis["summary"]["avg_frustration"]}

## Najczęstsze problemy
{chr(10).join(f"- {p['problem']} ({p['occurrences']}x)" for p in analysis["top_problems"])}

## Heatmapa Frustracji (według person)
{chr(10).join(f"- {h['persona']}: {h['failure_rate']}% porażek ({h['sessions']} sesji)" for h in analysis["frustration_heatmap"])}

---

{recommendations}
"""

            else:
                # Standardowe zapytanie - użyj LLM
                self.chat_history.add_user_message(input_text)

                execution_settings = OpenAIChatPromptExecutionSettings(
                    max_tokens=1500,
                    temperature=0.3,
                )

                chat_service = self.kernel.get_service()
                result = await self._invoke_chat_with_fallbacks(
                    chat_service=chat_service,
                    chat_history=self.chat_history,
                    settings=execution_settings,
                    enable_functions=False,
                )

                response = str(result)
                self.chat_history.add_assistant_message(response)

                return response

        except Exception as e:
            error_msg = f"Błąd podczas analizy UX: {e}"
            logger.error(error_msg)
            return f"❌ {error_msg}"
