"""Moduł: model_manager - Zarządca Modeli i Hot Swap dla Adapterów LoRA."""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ModelVersion:
    """
    Reprezentacja wersji modelu.
    """

    def __init__(
        self,
        version_id: str,
        base_model: str,
        adapter_path: Optional[str] = None,
        created_at: Optional[str] = None,
        performance_metrics: Optional[Dict] = None,
        is_active: bool = False,
    ):
        """
        Inicjalizacja wersji modelu.

        Args:
            version_id: Unikalny identyfikator wersji (np. "v1.0", "v1.1")
            base_model: Nazwa bazowego modelu
            adapter_path: Ścieżka do adaptera LoRA (jeśli istnieje)
            created_at: Timestamp utworzenia
            performance_metrics: Metryki wydajności (accuracy, loss, etc.)
            is_active: Czy to aktywna wersja w produkcji
        """
        self.version_id = version_id
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.created_at = created_at
        self.performance_metrics = performance_metrics or {}
        self.is_active = is_active

    def to_dict(self) -> Dict:
        """Konwertuje do słownika."""
        return {
            "version_id": self.version_id,
            "base_model": self.base_model,
            "adapter_path": self.adapter_path,
            "created_at": self.created_at,
            "performance_metrics": self.performance_metrics,
            "is_active": self.is_active,
        }


class ModelManager:
    """
    Zarządca Modeli - Hot Swap i Genealogia Inteligencji.

    Funkcjonalności:
    - Rejestracja nowych wersji modeli
    - Ładowanie adapterów LoRA (PEFT)
    - Hot swap (zamiana modelu bez restartu)
    - Historia wersji ("Genealogia Inteligencji")
    - Integracja z Ollama (tworzenie Modelfile z adapterem)
    """

    def __init__(self, models_dir: str = None):
        """
        Inicjalizacja ModelManager.

        Args:
            models_dir: Katalog z modelami (domyślnie ./data/models)
        """
        self.models_dir = Path(models_dir or "./data/models")
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Rejestr wersji modeli
        self.versions: Dict[str, ModelVersion] = {}

        # Aktywna wersja
        self.active_version: Optional[str] = None

        logger.info(f"ModelManager zainicjalizowany (models_dir={self.models_dir})")

    def register_version(
        self,
        version_id: str,
        base_model: str,
        adapter_path: Optional[str] = None,
        performance_metrics: Optional[Dict] = None,
    ) -> ModelVersion:
        """
        Rejestruje nową wersję modelu.

        Args:
            version_id: ID wersji
            base_model: Nazwa bazowego modelu
            adapter_path: Ścieżka do adaptera LoRA
            performance_metrics: Metryki wydajności

        Returns:
            Zarejestrowana wersja
        """
        from datetime import datetime

        version = ModelVersion(
            version_id=version_id,
            base_model=base_model,
            adapter_path=adapter_path,
            created_at=datetime.now().isoformat(),
            performance_metrics=performance_metrics,
            is_active=False,
        )

        self.versions[version_id] = version
        logger.info(f"Zarejestrowano wersję modelu: {version_id}")

        return version

    def activate_version(self, version_id: str) -> bool:
        """
        Aktywuje wersję modelu (hot swap).

        Args:
            version_id: ID wersji do aktywacji

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        if version_id not in self.versions:
            logger.error(f"Wersja {version_id} nie istnieje")
            return False

        # Dezaktywuj poprzednią wersję
        if self.active_version:
            self.versions[self.active_version].is_active = False

        # Aktywuj nową wersję
        self.versions[version_id].is_active = True
        self.active_version = version_id

        logger.info(f"Aktywowano wersję modelu: {version_id}")
        return True

    def get_active_version(self) -> Optional[ModelVersion]:
        """
        Zwraca aktywną wersję modelu.

        Returns:
            Aktywna wersja lub None
        """
        if not self.active_version:
            return None

        return self.versions.get(self.active_version)

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """
        Pobiera wersję modelu po ID.

        Args:
            version_id: ID wersji

        Returns:
            Wersja modelu lub None
        """
        return self.versions.get(version_id)

    def get_all_versions(self) -> List[ModelVersion]:
        """
        Zwraca wszystkie wersje modeli (sortowane od najnowszych).

        Returns:
            Lista wersji
        """
        return sorted(
            self.versions.values(),
            key=lambda v: v.created_at or "",
            reverse=True,
        )

    def create_ollama_modelfile(
        self, version_id: str, output_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Tworzy Modelfile dla Ollama z adapterem LoRA.

        Args:
            version_id: ID wersji modelu
            output_name: Nazwa wyjściowa modelu w Ollama (domyślnie venom-{version_id})

        Returns:
            Nazwa utworzonego modelu w Ollama lub None w przypadku błędu
        """
        version = self.get_version(version_id)
        if not version:
            logger.error(f"Wersja {version_id} nie istnieje")
            return None

        if not version.adapter_path:
            logger.error(f"Wersja {version_id} nie ma adaptera")
            return None

        output_name = output_name or f"venom-{version_id}"

        try:
            # Utwórz Modelfile
            modelfile_content = f"""FROM {version.base_model}
ADAPTER {version.adapter_path}

# Venom Model - version {version_id}
# Created: {version.created_at}
# Base: {version.base_model}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
"""

            # Zapisz Modelfile
            modelfile_path = self.models_dir / f"Modelfile.{version_id}"
            with open(modelfile_path, "w") as f:
                f.write(modelfile_content)

            logger.info(f"Utworzono Modelfile: {modelfile_path}")

            # Utwórz model w Ollama
            cmd = ["ollama", "create", output_name, "-f", str(modelfile_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"✅ Utworzono model w Ollama: {output_name}")
                return output_name
            else:
                logger.error(
                    f"❌ Błąd podczas tworzenia modelu w Ollama: {result.stderr}"
                )
                return None

        except subprocess.TimeoutExpired:
            logger.error("Timeout podczas tworzenia modelu w Ollama")
            return None
        except FileNotFoundError:
            logger.error("Ollama nie jest zainstalowane lub niedostępne w PATH")
            return None
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia Modelfile: {e}")
            return None

    def load_adapter_for_kernel(self, version_id: str, kernel_builder) -> bool:
        """
        Ładuje adapter LoRA do KernelBuilder (dla integracji z PEFT).

        Args:
            version_id: ID wersji modelu
            kernel_builder: Instancja KernelBuilder

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        # TODO: Implementacja ładowania PEFT adaptera
        # Wymaga rozszerzenia KernelBuilder o obsługę PEFT
        logger.warning("load_adapter_for_kernel() - funkcjonalność w rozwoju")
        return False

    def get_genealogy(self) -> Dict:
        """
        Zwraca "Genealogię Inteligencji" - historię wersji modeli.

        Returns:
            Słownik z informacjami o genealogii
        """
        versions_data = [v.to_dict() for v in self.get_all_versions()]

        return {
            "total_versions": len(self.versions),
            "active_version": self.active_version,
            "versions": versions_data,
        }

    def compare_versions(self, version_id_1: str, version_id_2: str) -> Optional[Dict]:
        """
        Porównuje dwie wersje modeli.

        Args:
            version_id_1: ID pierwszej wersji
            version_id_2: ID drugiej wersji

        Returns:
            Słownik z porównaniem lub None
        """
        v1 = self.get_version(version_id_1)
        v2 = self.get_version(version_id_2)

        if not v1 or not v2:
            logger.error("Jedna lub obie wersje nie istnieją")
            return None

        comparison = {
            "version_1": v1.to_dict(),
            "version_2": v2.to_dict(),
            "metrics_diff": {},
        }

        # Porównaj metryki
        for key in set(v1.performance_metrics.keys()) | set(
            v2.performance_metrics.keys()
        ):
            val1 = v1.performance_metrics.get(key)
            val2 = v2.performance_metrics.get(key)

            if val1 is not None and val2 is not None:
                try:
                    diff = val2 - val1
                    if val1 != 0:
                        diff_pct = (diff / val1) * 100
                    else:
                        # Jeśli val1 == 0, procentowa zmiana jest nieskończona (lub "N/A"), chyba że oba są zerowe
                        diff_pct = float("inf") if val2 != 0 else 0
                    comparison["metrics_diff"][key] = {
                        "v1": val1,
                        "v2": val2,
                        "diff": diff,
                        "diff_pct": diff_pct,
                    }
                except (TypeError, ValueError):
                    # Metryki niearytmetyczne
                    comparison["metrics_diff"][key] = {
                        "v1": val1,
                        "v2": val2,
                        "diff": "N/A",
                    }

        return comparison
