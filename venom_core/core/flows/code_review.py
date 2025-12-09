"""Moduł: code_review - Pętla Coder-Critic dla generowania i naprawy kodu."""

from uuid import UUID

from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Maksymalna liczba prób naprawy kodu przez pętlę Coder-Critic
MAX_REPAIR_ATTEMPTS = 2

# Maksymalna długość tekstu w promptach (zabezpieczenie przed prompt injection)
MAX_PROMPT_LENGTH = 500


class CodeReviewLoop:
    """Pętla generowania kodu z oceną przez CriticAgent."""

    def __init__(
        self,
        state_manager: StateManager,
        coder_agent: CoderAgent,
        critic_agent: CriticAgent,
    ):
        """
        Inicjalizacja CodeReviewLoop.

        Args:
            state_manager: Menedżer stanu zadań
            coder_agent: Agent generujący kod
            critic_agent: Agent sprawdzający kod
        """
        self.state_manager = state_manager
        self.coder_agent = coder_agent
        self.critic_agent = critic_agent

    async def execute(self, task_id: UUID, user_request: str) -> str:
        """
        Pętla generowania kodu z oceną przez CriticAgent.

        Args:
            task_id: ID zadania
            user_request: Żądanie użytkownika

        Returns:
            Zaakceptowany kod lub kod po naprawach
        """
        self.state_manager.add_log(
            task_id, "Rozpoczynam pętlę Coder-Critic (samonaprawa kodu)"
        )

        generated_code = None
        critic_feedback = None
        attempt = 0

        while attempt <= MAX_REPAIR_ATTEMPTS:
            attempt += 1

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
                repair_prompt = f"""FEEDBACK OD KRYTYKA:
{critic_feedback[:MAX_PROMPT_LENGTH]}

ORYGINALNE ŻĄDANIE UŻYTKOWNIKA:
{user_request[:MAX_PROMPT_LENGTH]}

POPRZEDNI KOD (fragment):
{code_preview}

Popraw kod zgodnie z feedbackiem. Wygeneruj poprawioną wersję."""
                generated_code = await self.coder_agent.process(repair_prompt)

            self.state_manager.add_log(
                task_id, f"Coder wygenerował kod ({len(generated_code)} znaków)"
            )

            # Krok 2: CriticAgent ocenia kod
            self.state_manager.add_log(task_id, "Critic: Ocena kodu...")
            review_input = f"USER_REQUEST: {user_request[:MAX_PROMPT_LENGTH]}\n\nCODE:\n{generated_code}"
            critic_feedback = await self.critic_agent.process(review_input)

            # Krok 3: Sprawdź czy zaakceptowano
            if "APPROVED" in critic_feedback:
                self.state_manager.add_log(
                    task_id, f"✅ Critic ZAAKCEPTOWAŁ kod po {attempt} próbach"
                )
                logger.info(
                    f"Zadanie {task_id}: Kod zaakceptowany po {attempt} próbach"
                )
                return generated_code

            # Jeśli odrzucono
            self.state_manager.add_log(
                task_id, f"❌ Critic ODRZUCIŁ kod: {critic_feedback[:100]}..."
            )

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
