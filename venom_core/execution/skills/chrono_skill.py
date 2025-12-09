"""Moduł: chrono_skill - Umiejętności Czasowe (Timeline Branching & State Management)."""

from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from venom_core.core.chronos import ChronosEngine
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ChronoSkill:
    """
    Skill do zarządzania stanem systemu i liniami czasu.

    Umożliwia:
    - Tworzenie checkpointów (punktów przywracania)
    - Przywracanie stanu do poprzedniego punktu
    - Zarządzanie liniami czasu (tworzenie, scalanie)
    - Eksperymentowanie na oddzielnych liniach czasowych
    """

    def __init__(self, chronos_engine: Optional[ChronosEngine] = None):
        """
        Inicjalizacja ChronoSkill.

        Args:
            chronos_engine: Silnik zarządzania czasem (utworzony automatycznie jeśli None)
        """
        self.chronos = chronos_engine or ChronosEngine()
        logger.info("ChronoSkill zainicjalizowany")

    @kernel_function(
        name="create_checkpoint",
        description="Tworzy checkpoint (punkt przywracania) całego stanu systemu. Używaj przed ryzykownymi operacjami.",
    )
    async def create_checkpoint(
        self,
        name: Annotated[str, "Nazwa checkpointu (user-friendly)"],
        description: Annotated[str, "Opcjonalny opis checkpointu"] = "",
        timeline: Annotated[str, "Nazwa linii czasowej (domyślnie 'main')"] = "main",
    ) -> str:
        """
        Tworzy checkpoint całego stanu systemu.

        Args:
            name: Nazwa checkpointu
            description: Opcjonalny opis
            timeline: Nazwa linii czasowej

        Returns:
            Komunikat z ID utworzonego checkpointu
        """
        try:
            checkpoint_id = self.chronos.create_checkpoint(
                name=name, description=description, timeline=timeline
            )
            return (
                f"✓ Checkpoint '{name}' utworzony pomyślnie.\n"
                f"ID: {checkpoint_id}\n"
                f"Timeline: {timeline}\n"
                f"Możesz przywrócić ten stan używając: restore_checkpoint('{checkpoint_id}')"
            )
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia checkpointu: {e}")
            return f"✗ Błąd podczas tworzenia checkpointu: {e}"

    @kernel_function(
        name="restore_checkpoint",
        description="Przywraca system do stanu z checkpointu. UWAGA: Obecne zmiany zostaną utracone!",
    )
    async def restore_checkpoint(
        self,
        checkpoint_id: Annotated[str, "ID checkpointu do przywrócenia"],
        timeline: Annotated[str, "Nazwa linii czasowej (domyślnie 'main')"] = "main",
    ) -> str:
        """
        Przywraca system do stanu z checkpointu.

        Args:
            checkpoint_id: ID checkpointu
            timeline: Nazwa linii czasowej

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            success = self.chronos.restore_checkpoint(
                checkpoint_id=checkpoint_id, timeline=timeline
            )

            if success:
                return (
                    f"✓ System przywrócony do checkpointu {checkpoint_id}.\n"
                    f"Timeline: {timeline}\n"
                    f"Wszystkie zmiany od tego punktu zostały cofnięte."
                )
            else:
                return (
                    f"✗ Nie udało się przywrócić checkpointu {checkpoint_id}.\n"
                    f"Sprawdź logi aby uzyskać więcej informacji."
                )

        except Exception as e:
            logger.error(f"Błąd podczas przywracania checkpointu: {e}")
            return f"✗ Błąd podczas przywracania checkpointu: {e}"

    @kernel_function(
        name="list_checkpoints",
        description="Wyświetla listę wszystkich dostępnych checkpointów dla danej linii czasowej.",
    )
    async def list_checkpoints(
        self,
        timeline: Annotated[str, "Nazwa linii czasowej (domyślnie 'main')"] = "main",
    ) -> str:
        """
        Wyświetla listę checkpointów.

        Args:
            timeline: Nazwa linii czasowej

        Returns:
            Lista checkpointów w formacie tekstowym
        """
        try:
            checkpoints = self.chronos.list_checkpoints(timeline=timeline)

            if not checkpoints:
                return f"Brak checkpointów na timeline '{timeline}'."

            result = f"Checkpointy na timeline '{timeline}':\n\n"
            for cp in checkpoints:
                result += (
                    f"• {cp.name} (ID: {cp.checkpoint_id})\n"
                    f"  Timestamp: {cp.timestamp}\n"
                )
                if cp.description:
                    result += f"  Opis: {cp.description}\n"
                result += "\n"

            return result

        except Exception as e:
            logger.error(f"Błąd podczas listowania checkpointów: {e}")
            return f"✗ Błąd podczas listowania checkpointów: {e}"

    @kernel_function(
        name="delete_checkpoint",
        description="Usuwa checkpoint. Operacja nieodwracalna!",
    )
    async def delete_checkpoint(
        self,
        checkpoint_id: Annotated[str, "ID checkpointu do usunięcia"],
        timeline: Annotated[str, "Nazwa linii czasowej (domyślnie 'main')"] = "main",
    ) -> str:
        """
        Usuwa checkpoint.

        Args:
            checkpoint_id: ID checkpointu
            timeline: Nazwa linii czasowej

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            success = self.chronos.delete_checkpoint(
                checkpoint_id=checkpoint_id, timeline=timeline
            )

            if success:
                return f"✓ Checkpoint {checkpoint_id} usunięty z timeline '{timeline}'."
            else:
                return f"✗ Nie udało się usunąć checkpointu {checkpoint_id}."

        except Exception as e:
            logger.error(f"Błąd podczas usuwania checkpointu: {e}")
            return f"✗ Błąd podczas usuwania checkpointu: {e}"

    @kernel_function(
        name="branch_timeline",
        description="Tworzy nową linię czasową (branch) do eksperymentowania. Działa jak Git branch dla całego stanu systemu.",
    )
    async def branch_timeline(
        self,
        name: Annotated[str, "Nazwa nowej linii czasowej"],
    ) -> str:
        """
        Tworzy nową linię czasową (branch).

        Args:
            name: Nazwa nowej linii czasowej

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            # Najpierw utwórz nową timeline
            success = self.chronos.create_timeline(name=name)

            if not success:
                return f"✗ Nie udało się utworzyć timeline '{name}'. Możliwe, że już istnieje."

            # Następnie utwórz checkpoint na głównej linii jako punkt rozgałęzienia
            try:
                checkpoint_id = self.chronos.create_checkpoint(
                    name=f"branch_point_{name}",
                    description=f"Punkt rozgałęzienia dla timeline '{name}'",
                    timeline="main",
                )

                return (
                    f"✓ Nowa timeline '{name}' utworzona.\n"
                    f"Punkt rozgałęzienia (checkpoint): {checkpoint_id}\n"
                    f"Możesz teraz eksperymentować na tej linii czasowej używając parametru timeline='{name}'.\n"
                    f"Aby wrócić do głównej linii: restore_checkpoint('{checkpoint_id}', timeline='main')"
                )

            except Exception as cp_error:
                logger.warning(
                    f"Timeline utworzona, ale nie udało się utworzyć checkpointu: {cp_error}"
                )
                return (
                    f"⚠️ Timeline '{name}' utworzona, ale checkpoint nie został zapisany.\n"
                    f"Możesz ręcznie utworzyć checkpoint na timeline 'main' przed eksperymentowaniem."
                )

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia timeline: {e}")
            return f"✗ Błąd podczas tworzenia timeline: {e}"

    @kernel_function(
        name="list_timelines",
        description="Wyświetla listę wszystkich dostępnych linii czasowych.",
    )
    async def list_timelines(self) -> str:
        """
        Wyświetla listę wszystkich linii czasowych.

        Returns:
            Lista linii czasowych
        """
        try:
            timelines = self.chronos.list_timelines()

            if not timelines:
                return "Brak linii czasowych."

            result = "Dostępne linie czasowe:\n\n"
            for tl in timelines:
                checkpoints_count = len(self.chronos.list_checkpoints(timeline=tl))
                result += f"• {tl} ({checkpoints_count} checkpointów)\n"

            return result

        except Exception as e:
            logger.error(f"Błąd podczas listowania linii czasowych: {e}")
            return f"✗ Błąd podczas listowania linii czasowych: {e}"

    @kernel_function(
        name="merge_timeline",
        description="Scala wiedzę z eksperymentalnej linii czasowej do głównej (zaawansowane).",
    )
    async def merge_timeline(
        self,
        source: Annotated[str, "Nazwa źródłowej linii czasowej"],
        target: Annotated[str, "Nazwa docelowej linii czasowej"] = "main",
    ) -> str:
        """
        Scala wiedzę z dwóch linii czasowych (zaawansowane).

        UWAGA: To jest uproszczona implementacja. W pełnej wersji
        wymagałaby inteligentnego mergowania konfliktów.

        Args:
            source: Źródłowa timeline
            target: Docelowa timeline

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            # To jest placeholder - pełna implementacja wymaga:
            # 1. Porównania zmian między timelines
            # 2. Wykrycia konfliktów
            # 3. Inteligentnego mergowania wiedzy (np. przez LLM)

            return (
                f"⚠️ Merge timeline to zaawansowana funkcja.\n"
                f"Próba scalenia: {source} → {target}\n"
                f"UWAGA: W obecnej wersji merge wymaga manualnej interwencji.\n"
                f"Zalecane kroki:\n"
                f"1. Sprawdź checkpointy na obu timelines: list_checkpoints('{source}') i list_checkpoints('{target}')\n"
                f"2. Zdecyduj, które zmiany zachować\n"
                f"3. Użyj restore_checkpoint() aby przełączyć się między timelines"
            )

        except Exception as e:
            logger.error(f"Błąd podczas merge timeline: {e}")
            return f"✗ Błąd podczas merge timeline: {e}"
