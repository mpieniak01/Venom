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
# Ustawiona na MAX_REPAIR_ATTEMPTS + 1, aby dać pętli szansę wykorzystać pełny budżet prób
MAX_ERROR_REPEATS = MAX_REPAIR_ATTEMPTS + 1


class CodeReviewLoop:
    """Pętla generowania kodu z oceną przez CriticAgent."""

    def __init__(
        self,
        state_manager: StateManager,
        coder_agent: CoderAgent,
        critic_agent: CriticAgent,
        token_economist: TokenEconomist | None = None,
        file_skill: FileSkill | None = None,
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
        self.previous_errors: list[int] = []

    @staticmethod
    def _summarize_text(text: str, limit: int = MAX_PROMPT_LENGTH) -> str:
        if len(text) > limit:
            return text[:limit] + "..."
        return text

    def _build_budget_exceeded_result(self, generated_code: str) -> str:
        budget_msg = (
            f"⚠️ Przekroczono budżet sesji ({self.session_cost:.2f}$ > "
            f"{MAX_HEALING_COST}$). Przerywam samonaprawę."
        )
        return f"{budget_msg}\n\nOSTATNI KOD:\n{generated_code or 'Brak kodu'}"

    def _build_loop_detected_result(
        self, loop_msg: str, critic_feedback: str, generated_code: str
    ) -> str:
        feedback_summary = self._summarize_text(critic_feedback)
        return (
            f"⚠️ OSTRZEŻENIE: {loop_msg}\n\n"
            f"UWAGI KRYTYKA:\n{feedback_summary}\n\n---\n\n{generated_code}"
        )

    def _build_max_attempts_result(
        self, generated_code: str, critic_feedback: str
    ) -> str:
        feedback_summary = self._summarize_text(critic_feedback)
        return (
            "⚠️ OSTRZEŻENIE: Kod nie został w pełni zaakceptowany po "
            f"{MAX_REPAIR_ATTEMPTS} próbach.\n\nUWAGI KRYTYKA:\n{feedback_summary}"
            f"\n\n---\n\n{generated_code}"
        )

    async def _generate_code_for_attempt(
        self,
        *,
        task_id: UUID,
        attempt: int,
        user_request: str,
        generated_code: str,
        critic_feedback: str,
        current_file: str | None,
    ) -> tuple[str, str]:
        if attempt == 1:
            self.state_manager.add_log(
                task_id, f"Coder: Próba {attempt} - generowanie kodu"
            )
            generated = await self.coder_agent.process(user_request)
            return generated, user_request

        self.state_manager.add_log(
            task_id, f"Coder: Próba {attempt} - naprawa na podstawie feedbacku"
        )
        code_preview = self._summarize_text(generated_code)

        file_context = ""
        if current_file:
            file_context = (
                f"\n\n⚠️ UWAGA: Naprawiamy teraz plik '{current_file}', "
                "ponieważ testy/kod wykazały błąd w tym pliku."
            )
            try:
                file_content = await self.file_skill.read_file(current_file)
                file_context += (
                    f"\n\nOBECNA TREŚĆ PLIKU '{current_file}':\n"
                    f"{self._summarize_text(file_content)}"
                )
            except Exception as exc:
                logger.warning(f"Nie udało się wczytać pliku {current_file}: {exc}")
                file_context += f"\n\nPlik '{current_file}' nie istnieje jeszcze - musisz go stworzyć."

        repair_prompt = f"""FEEDBACK OD KRYTYKA:
{self._summarize_text(critic_feedback)}

ORYGINALNE ŻĄDANIE UŻYTKOWNIKA:
{self._summarize_text(user_request)}

POPRZEDNI KOD (fragment):
{code_preview}{file_context}

Popraw kod zgodnie z feedbackiem. Wygeneruj poprawioną wersję."""
        generated = await self.coder_agent.process(repair_prompt)
        return generated, repair_prompt

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

        generated_code = ""
        critic_feedback = ""
        attempt = 0
        current_file: str | None = None  # Aktualny plik w trakcie naprawy

        while attempt <= MAX_REPAIR_ATTEMPTS:
            attempt += 1

            budget_warning = self._should_stop_for_budget()
            if budget_warning:
                self.state_manager.add_log(task_id, budget_warning)
                logger.warning(f"Zadanie {task_id}: {budget_warning}")
                return self._build_budget_exceeded_result(generated_code)

            generated_code = await self._run_coder_iteration(
                task_id=task_id,
                attempt=attempt,
                user_request=user_request,
                generated_code=generated_code,
                critic_feedback=critic_feedback,
                current_file=current_file,
            )

            critic_feedback, diagnostic = await self._run_critic_iteration(
                task_id=task_id,
                user_request=user_request,
                generated_code=generated_code,
            )

            # Krok 3: Sprawdź czy zaakceptowano
            if self._is_feedback_approved(critic_feedback):
                self._log_approved_result(task_id=task_id, attempt=attempt)
                return generated_code

            # Krok 4: Wykrywanie pętli błędów (Loop Detection)
            loop_result = self._check_error_loop(
                task_id=task_id,
                attempt=attempt,
                critic_feedback=critic_feedback,
                generated_code=generated_code,
            )
            if loop_result is not None:
                return loop_result

            self._log_rejected_feedback(task_id=task_id, diagnostic=diagnostic)
            current_file = self._resolve_target_file_change(
                task_id=task_id,
                current_file=current_file,
                diagnostic=diagnostic,
            )

            # Jeśli to była ostatnia próba
            if attempt > MAX_REPAIR_ATTEMPTS:
                return self._finalize_attempt_result(
                    task_id=task_id,
                    generated_code=generated_code,
                    critic_feedback=critic_feedback,
                )

        # Nie powinno się tu dostać, ale dla bezpieczeństwa
        return generated_code or "Błąd: nie udało się wygenerować kodu"

    def _log_approved_result(self, *, task_id: UUID, attempt: int) -> None:
        self.state_manager.add_log(
            task_id,
            f"✅ Critic ZAAKCEPTOWAŁ kod po {attempt} próbach. Koszt sesji: ${self.session_cost:.4f}",
        )
        logger.info(f"Zadanie {task_id}: Kod zaakceptowany po {attempt} próbach")

    def _check_error_loop(
        self, *, task_id: UUID, attempt: int, critic_feedback: str, generated_code: str
    ) -> str | None:
        error_hash = hash(critic_feedback)
        # Wykrywamy pętlę, jeśli ten sam błąd pojawił się już MAX_ERROR_REPEATS-1 razy
        # (łącznie z bieżącym wystąpieniem będzie MAX_ERROR_REPEATS)
        if self.previous_errors.count(error_hash) < MAX_ERROR_REPEATS - 1:
            self.previous_errors.append(error_hash)
            return None

        loop_msg = (
            "🔄 Wykryto pętlę błędów: ten sam błąd wystąpił "
            f"{MAX_ERROR_REPEATS} razy. Model nie potrafi tego naprawić."
        )
        self.state_manager.add_log(task_id, loop_msg)
        logger.warning(f"Zadanie {task_id}: {loop_msg}")
        if attempt > MAX_REPAIR_ATTEMPTS:
            self.state_manager.add_log(
                task_id,
                f"⚠️ Wyczerpano limit prób ({MAX_REPAIR_ATTEMPTS}). Zwracam ostatnią wersję z ostrzeżeniem.",
            )
        return self._build_loop_detected_result(
            loop_msg=loop_msg,
            critic_feedback=critic_feedback,
            generated_code=generated_code,
        )

    def _log_rejected_feedback(self, *, task_id: UUID, diagnostic: dict) -> None:
        analysis_preview = diagnostic.get("analysis", "Brak analizy")[:100]
        self.state_manager.add_log(
            task_id, f"❌ Critic ODRZUCIŁ kod: {analysis_preview}..."
        )

    def _resolve_target_file_change(
        self, *, task_id: UUID, current_file: str | None, diagnostic: dict
    ) -> str | None:
        target_file_change = diagnostic.get("target_file_change")
        if not target_file_change or target_file_change == current_file:
            return current_file

        new_file = target_file_change
        self.state_manager.add_log(
            task_id,
            f"🔀 Zmiana celu naprawy: {current_file or '(brak)'} -> {new_file}",
        )
        logger.info(
            f"Zadanie {task_id}: Przełączam kontekst naprawy na plik {new_file}"
        )
        return new_file

    def _should_stop_for_budget(self) -> str | None:
        if self.session_cost <= MAX_HEALING_COST:
            return None
        return (
            f"⚠️ Przekroczono budżet sesji ({self.session_cost:.2f}$ > "
            f"{MAX_HEALING_COST}$). Przerywam samonaprawę."
        )

    async def _run_coder_iteration(
        self,
        *,
        task_id: UUID,
        attempt: int,
        user_request: str,
        generated_code: str,
        critic_feedback: str,
        current_file: str | None,
    ) -> str:
        generated_code, actual_prompt = await self._generate_code_for_attempt(
            task_id=task_id,
            attempt=attempt,
            user_request=user_request,
            generated_code=generated_code,
            critic_feedback=critic_feedback,
            current_file=current_file,
        )
        model_name = getattr(SETTINGS, "DEFAULT_COST_MODEL", "gpt-3.5-turbo")
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
        return generated_code

    async def _run_critic_iteration(
        self, *, task_id: UUID, user_request: str, generated_code: str
    ) -> tuple[str, dict]:
        self.state_manager.add_log(task_id, "Critic: Ocena kodu...")
        review_input = f"USER_REQUEST: {user_request[:MAX_PROMPT_LENGTH]}\n\nCODE:\n{generated_code}"
        critic_feedback = await self.critic_agent.process(review_input)
        diagnostic = self.critic_agent.analyze_error(critic_feedback)
        return critic_feedback, diagnostic

    @staticmethod
    def _is_feedback_approved(critic_feedback: str) -> bool:
        return "APPROVED" in critic_feedback

    def _finalize_attempt_result(
        self, *, task_id: UUID, generated_code: str, critic_feedback: str
    ) -> str:
        self.state_manager.add_log(
            task_id,
            f"⚠️ Wyczerpano limit prób ({MAX_REPAIR_ATTEMPTS}). Zwracam ostatnią wersję z ostrzeżeniem.",
        )
        logger.warning(
            f"Zadanie {task_id}: Przekroczono limit napraw, zwracam kod z ostrzeżeniem"
        )
        return self._build_max_attempts_result(
            generated_code=generated_code,
            critic_feedback=critic_feedback,
        )
