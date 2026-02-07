"""Moduł: prompt_manager - zarządzanie promptami z plików YAML."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

yaml: Any = None
try:  # pragma: no cover - zależne od środowiska
    import yaml as _yaml

    yaml = _yaml
except ImportError:  # pragma: no cover
    pass

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class PromptManager:
    """Menedżer promptów z obsługą hot-reload i wersjonowania."""

    def __init__(self, prompts_dir: str = "./data/prompts"):
        """
        Inicjalizacja Prompt Manager.

        Args:
            prompts_dir: Katalog z plikami YAML promptów
        """
        self.prompts_dir = Path(prompts_dir)
        self.prompts_cache: Dict[str, dict] = {}
        self.file_timestamps: Dict[str, float] = {}

        # Utwórz katalog jeśli nie istnieje
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"PromptManager zainicjalizowany (katalog: {self.prompts_dir})")

    def load_prompt(self, agent_name: str, force_reload: bool = False) -> dict:
        """
        Ładuje prompt dla danego agenta z pliku YAML.

        Args:
            agent_name: Nazwa agenta (np. "coder_agent")
            force_reload: Czy wymusić ponowne załadowanie (domyślnie False)

        Returns:
            Dict z danymi promptu (template, parameters, version, itp.)

        Raises:
            FileNotFoundError: Jeśli plik promptu nie istnieje
            ValueError: Jeśli plik YAML jest nieprawidłowy
        """
        # Sprawdź czy plik istnieje
        prompt_file = self.prompts_dir / f"{agent_name}.yaml"

        if not prompt_file.exists():
            logger.error(f"Plik promptu nie istnieje: {prompt_file}")
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        # Pobierz timestamp pliku
        file_mtime = prompt_file.stat().st_mtime

        # Sprawdź czy prompt jest w cache i czy nie zmienił się
        if (
            not force_reload
            and agent_name in self.prompts_cache
            and agent_name in self.file_timestamps
            and self.file_timestamps[agent_name] == file_mtime
        ):
            logger.debug(f"Używam cache dla promptu: {agent_name}")
            return self.prompts_cache[agent_name]

        if yaml is None:
            raise RuntimeError("Brak zależności PyYAML (pip install PyYAML)")

        # Załaduj plik YAML
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_data = yaml.safe_load(f)

            if not prompt_data:
                raise ValueError(f"Plik YAML jest pusty: {prompt_file}")

            # Walidacja struktury
            if "template" not in prompt_data:
                raise ValueError(
                    f"Brak wymaganego pola 'template' w pliku: {prompt_file}"
                )

            # Dodaj metadata
            prompt_data["_loaded_at"] = datetime.now().isoformat()
            prompt_data["_file_path"] = str(prompt_file)

            # Zapisz w cache
            self.prompts_cache[agent_name] = prompt_data
            self.file_timestamps[agent_name] = file_mtime

            logger.info(
                f"Załadowano prompt dla {agent_name} (wersja: {prompt_data.get('version', 'N/A')})"
            )
            return prompt_data

        except yaml.YAMLError as e:
            logger.error(f"Błąd parsowania YAML dla {agent_name}: {e}")
            raise ValueError(f"Invalid YAML in {prompt_file}: {e}")

    def get_prompt(self, agent_name: str, fallback: Optional[str] = None) -> str:
        """
        Zwraca template promptu dla agenta.

        Args:
            agent_name: Nazwa agenta
            fallback: Opcjonalny fallback prompt jeśli plik nie istnieje

        Returns:
            String z szablonem promptu
        """
        try:
            prompt_data = self.load_prompt(agent_name)
            return prompt_data["template"]
        except FileNotFoundError:
            if fallback:
                logger.warning(
                    f"Plik promptu dla {agent_name} nie istnieje, używam fallback"
                )
                return fallback
            raise

    def get_parameters(self, agent_name: str) -> dict:
        """
        Zwraca parametry promptu (np. temperature, max_tokens).

        Args:
            agent_name: Nazwa agenta

        Returns:
            Dict z parametrami
        """
        try:
            prompt_data = self.load_prompt(agent_name)
            return prompt_data.get("parameters", {})
        except FileNotFoundError:
            logger.warning(
                f"Plik promptu dla {agent_name} nie istnieje, zwracam puste parametry"
            )
            return {}

    def hot_reload(self, agent_name: str) -> bool:
        """
        Wymusza przeładowanie promptu z pliku (hot-reload).

        Args:
            agent_name: Nazwa agenta

        Returns:
            True jeśli przeładowanie się powiodło, False w przeciwnym razie
        """
        try:
            self.load_prompt(agent_name, force_reload=True)
            logger.info(f"Hot-reload wykonany dla: {agent_name}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas hot-reload dla {agent_name}: {e}")
            return False

    def reload_all(self) -> int:
        """
        Przeładowuje wszystkie prompty z cache.

        Returns:
            Liczba przeładowanych promptów
        """
        count = 0
        for agent_name in list(self.prompts_cache.keys()):
            if self.hot_reload(agent_name):
                count += 1

        logger.info(f"Przeładowano {count} promptów")
        return count

    def list_prompts(self) -> list:
        """
        Zwraca listę dostępnych promptów.

        Returns:
            Lista nazw agentów (bez rozszerzenia .yaml)
        """
        prompts = []
        for file in self.prompts_dir.glob("*.yaml"):
            prompts.append(file.stem)

        return sorted(prompts)

    def create_prompt_template(
        self,
        agent_name: str,
        template: str,
        version: str = "1.0",
        parameters: Optional[dict] = None,
    ) -> bool:
        """
        Tworzy nowy plik promptu z szablonu.

        Args:
            agent_name: Nazwa agenta
            template: Treść promptu
            version: Wersja promptu (domyślnie "1.0")
            parameters: Opcjonalne parametry (temperature, max_tokens, itp.)

        Returns:
            True jeśli utworzenie się powiodło, False w przeciwnym razie
        """
        prompt_file = self.prompts_dir / f"{agent_name}.yaml"

        if prompt_file.exists():
            logger.warning(
                f"Plik promptu już istnieje: {prompt_file}, pomijam tworzenie"
            )
            return False

        prompt_data = {
            "agent": agent_name,
            "version": version,
            "parameters": parameters or {"temperature": 0.7},
            "template": template,
        }

        try:
            with open(prompt_file, "w", encoding="utf-8") as f:
                yaml.dump(prompt_data, f, allow_unicode=True, sort_keys=False)

            logger.info(f"Utworzono plik promptu: {prompt_file}")
            return True

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia pliku promptu: {e}")
            return False

    def get_cache_status(self) -> dict:
        """
        Zwraca status cache promptów.

        Returns:
            Dict z informacjami o cache
        """
        return {
            "cached_prompts": len(self.prompts_cache),
            "prompts_dir": str(self.prompts_dir),
            "available_prompts": self.list_prompts(),
            "cache_entries": list(self.prompts_cache.keys()),
        }
