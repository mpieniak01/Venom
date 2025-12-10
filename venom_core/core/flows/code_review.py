"""Moduł: code_review - Pętla Coder-Critic dla generowania i naprawy kodu."""

from uuid import UUID

from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.config import SETTINGS
from venom_core.core.state_manager import StateManager
from venom_core.core.token_economist import TokenEconomist
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Maksymalna liczba prób naprawy kodu przez pętlę Coder-Critic
MAX_REPAIR_ATTEMPTS = 2

# Maksymalna długość tekstu w promptach (zabezpieczenie przed prompt injection)
MAX_PROMPT_LENGTH = 500

# Maksymalny koszt sesji samo-naprawy (USD)
MAX_HEALING_COST = 0.50

# Liczba powtórzeń tego samego błędu prowadząca do przerwania (pętla śmierci)
MAX_ERROR_REPEATS = 2


class CodeReviewLoop:
    """Pętla generowania kodu z oceną przez CriticAgent."""

    def __init__(
        self,
        state_manager: StateManager,
        coder_agent: CoderAgent,
        critic_agent: CriticAgent,
        token_economist: TokenEconomist = None,
        file_skill: FileSkill = None,
    ):
        """
        Inicjalizacja CodeReviewLoop.

        Args:
            state_manager: Menedżer stanu zadań
            coder_agent: Agent generujący kod
            critic_agent: Agent sprawdzający kod
            token_economist: Token Economist do monitorowania kosztów (opcjonalny).
                Jeśli None, zostanie utworzona domyślna instancja.
            file_skill: FileSkill do operacji na plikach (opcjonalny).
                Jeśli None, zostanie utworzona domyślna instancja.

        Note:
            TokenEconomist i FileSkill używają domyślnej konfiguracji z SETTINGS
            jeśli nie są przekazane jawnie. Jest to bezpieczne dla większości przypadków,
            ale można przekazać skonfigurowane instancje dla specjalnych scenariuszy.
        """
        self.state_manager = state_manager
        self.coder_agent = coder_agent
        self.critic_agent = critic_agent
        self.token_economist = token_economist or TokenEconomist()
        self.file_skill = file_skill or FileSkill()

        # Tracking kosztów i błędów dla danej sesji
        self.session_cost = 0.0
        self.previous_errors = []

    async def execute(self, task_id: UUID, user_request: str) -> str:
        """
        Pętla generowania kodu z oceną przez CriticAgent.
        Wspiera dynamiczną zmianę pliku docelowego oraz wykrywanie pętli błędów.

        Args:
            task_id: ID zadania
            user_request: Żądanie użytkownika

        Returns:
            Zaakceptowany kod lub kod po naprawach
        """
        self.state_manager.add_log(
            task_id, "Rozpoczynam pętlę Coder-Critic (samonaprawa kodu)"
        )

        # Reset tracking dla nowej sesji
        self.session_cost = 0.0
        self.previous_errors = []

        generated_code = None
        critic_feedback = None
        attempt = 0
        current_file = None  # Aktualny plik w trakcie naprawy

        while attempt <= MAX_REPAIR_ATTEMPTS:
            attempt += 1

            # Sprawdź budżet przed iteracją
            if self.session_cost > MAX_HEALING_COST:
                budget_msg = f"⚠️ Przekroczono budżet sesji ({self.session_cost:.2f}$ > {MAX_HEALING_COST}$). Przerywam samonaprawę."
                self.state_manager.add_log(task_id, budget_msg)
                logger.warning(f"Zadanie {task_id}: {budget_msg}")
                return f"{budget_msg}\n\nOSTATNI KOD:\n{generated_code or 'Brak kodu'}"

            # Krok 1: CoderAgent generuje kod
            if attempt == 1:
                self.state_manager.add_log(
                    task_id, f"Coder: Próba {attempt} - generowanie kodu"
                )
                generated_code = await self.coder_agent.process(user_request)
            else:
                # Kolejne próby - przekaż feedback od Krytyka
                self.state_manager.add_log(
                    task_id, f"Coder: Próba {attempt} - naprawa na podstawie feedbacku"
                )
                # Ogranicz długość poprzedniego kodu w promptcie dla wydajności
                code_preview = (
                    generated_code[:MAX_PROMPT_LENGTH] + "..."
                    if len(generated_code) > MAX_PROMPT_LENGTH
                    else generated_code
                )

                # Jeśli Krytyk wskazał inny plik do naprawy
                file_context = ""
                if current_file:
                    file_context = f"\n\n⚠️ UWAGA: Naprawiamy teraz plik '{current_file}', ponieważ testy/kod wykazały błąd w tym pliku."
                    # Spróbuj wczytać treść pliku
                    try:
                        file_content = await self.file_skill.read_file(current_file)
                        file_context += f"\n\nOBECNA TREŚĆ PLIKU '{current_file}':\n{file_content[:MAX_PROMPT_LENGTH]}"
                    except Exception as e:
                        logger.warning(
                            f"Nie udało się wczytać pliku {current_file}: {e}"
                        )
                        file_context += f"\n\nPlik '{current_file}' nie istnieje jeszcze - musisz go stworzyć."

                repair_prompt = f"""FEEDBACK OD KRYTYKA:
{critic_feedback[:MAX_PROMPT_LENGTH]}

ORYGINALNE ŻĄDANIE UŻYTKOWNIKA:
{user_request[:MAX_PROMPT_LENGTH]}

POPRZEDNI KOD (fragment):
{code_preview}{file_context}

Popraw kod zgodnie z feedbackiem. Wygeneruj poprawioną wersję."""
                generated_code = await self.coder_agent.process(repair_prompt)

            # Estymuj koszt tej iteracji (użyj modelu z konfiguracji lub domyślnego)
            model_name = getattr(SETTINGS, "DEFAULT_COST_MODEL", "gpt-3.5-turbo")
            
            # Użyj rzeczywistego prompta do estymacji kosztów
            actual_prompt = user_request if attempt == 1 else repair_prompt
            estimated_cost = self.token_economist.estimate_request_cost(
                prompt=actual_prompt,
                expected_output_tokens=len(generated_code) // 4,
                model_name=model_name,
            )
            self.session_cost += estimated_cost.get("total_cost_usd", 0.0)

            self.state_manager.add_log(
                task_id,
                f"Coder wygenerował kod ({len(generated_code)} znaków). Koszt sesji: ${self.session_cost:.4f}",
            )

            # Krok 2: CriticAgent ocenia kod
            self.state_manager.add_log(task_id, "Critic: Ocena kodu...")
            review_input = f"USER_REQUEST: {user_request[:MAX_PROMPT_LENGTH]}\n\nCODE:\n{generated_code}"
            critic_feedback = await self.critic_agent.process(review_input)

            # Krok 3: Sprawdź czy zaakceptowano
            if "APPROVED" in critic_feedback:
                self.state_manager.add_log(
                    task_id,
                    f"✅ Critic ZAAKCEPTOWAŁ kod po {attempt} próbach. Koszt sesji: ${self.session_cost:.4f}",
                )
                logger.info(
                    f"Zadanie {task_id}: Kod zaakceptowany po {attempt} próbach"
                )
                return generated_code

            # Krok 4: Wykrywanie pętli błędów (Loop Detection)
            error_hash = hash(critic_feedback)
            # Wykrywamy pętlę, jeśli ten sam błąd pojawił się już MAX_ERROR_REPEATS-1 razy
            # (łącznie z bieżącym wystąpieniem będzie MAX_ERROR_REPEATS)
            if self.previous_errors.count(error_hash) >= MAX_ERROR_REPEATS - 1:
                loop_msg = f"🔄 Wykryto pętlę błędów: ten sam błąd wystąpił {MAX_ERROR_REPEATS} razy. Model nie potrafi tego naprawić."
                self.state_manager.add_log(task_id, loop_msg)
                logger.warning(f"Zadanie {task_id}: {loop_msg}")
                return f"{loop_msg}\n\nOSTATNI FEEDBACK:\n{critic_feedback}\n\n---\n\n{generated_code}"

            self.previous_errors.append(error_hash)

            # Krok 5: Analiza diagnostyczna i ewentualna zmiana pliku docelowego
            diagnostic = self.critic_agent.analyze_error(critic_feedback)

            # Jeśli odrzucono
            analysis_preview = diagnostic.get("analysis", "Brak analizy")[:100]
            self.state_manager.add_log(
                task_id, f"❌ Critic ODRZUCIŁ kod: {analysis_preview}..."
            )

            # Sprawdź czy Krytyk wskazuje na inny plik
            target_file_change = diagnostic.get("target_file_change")
            if target_file_change and target_file_change != current_file:
                new_file = target_file_change
                self.state_manager.add_log(
                    task_id,
                    f"🔀 Zmiana celu naprawy: {current_file or '(brak)'} -> {new_file}",
                )
                logger.info(
                    f"Zadanie {task_id}: Przełączam kontekst naprawy na plik {new_file}"
                )
                current_file = new_file

            # Jeśli to była ostatnia próba
            if attempt > MAX_REPAIR_ATTEMPTS:
                self.state_manager.add_log(
                    task_id,
                    f"⚠️ Wyczerpano limit prób ({MAX_REPAIR_ATTEMPTS}). Zwracam ostatnią wersję z ostrzeżeniem.",
                )
                logger.warning(
                    f"Zadanie {task_id}: Przekroczono limit napraw, zwracam kod z ostrzeżeniem"
                )
                # Ogranicz rozmiar feedbacku w finalnej wiadomości
                feedback_summary = (
                    critic_feedback[:MAX_PROMPT_LENGTH] + "..."
                    if len(critic_feedback) > MAX_PROMPT_LENGTH
                    else critic_feedback
                )
                return f"⚠️ OSTRZEŻENIE: Kod nie został w pełni zaakceptowany po {MAX_REPAIR_ATTEMPTS} próbach.\n\nUWAGI KRYTYKA:\n{feedback_summary}\n\n---\n\n{generated_code}"

        # Nie powinno się tu dostać, ale dla bezpieczeństwa
        return generated_code or "Błąd: nie udało się wygenerować kodu"
