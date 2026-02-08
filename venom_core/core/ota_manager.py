"""Moduł: ota_manager - Over-The-Air Updates dla węzłów Spore."""

import asyncio
import hashlib
import importlib
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.infrastructure.message_broker import MessageBroker
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

aiofiles: Any = None
try:  # pragma: no cover - zależne od środowiska
    aiofiles = importlib.import_module("aiofiles")
except Exception:  # pragma: no cover
    aiofiles = None

logger = get_logger(__name__)
REQUIREMENTS_FILENAME = "requirements.txt"


class OTAPackage:
    """Reprezentacja paczki aktualizacji OTA."""

    def __init__(
        self,
        version: str,
        description: str,
        package_path: Path,
        checksum: str,
        created_at: Optional[datetime] = None,
    ):
        """
        Inicjalizacja paczki OTA.

        Args:
            version: Wersja paczki (np. "1.2.3")
            description: Opis zmian
            package_path: Ścieżka do pliku .zip z kodem
            checksum: Suma kontrolna SHA256
            created_at: Data utworzenia
        """
        self.version = version
        self.description = description
        self.package_path = package_path
        self.checksum = checksum
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje paczkę do słownika."""
        return {
            "version": self.version,
            "description": self.description,
            "package_path": str(self.package_path),
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
            "size_bytes": (
                self.package_path.stat().st_size if self.package_path.exists() else 0
            ),
        }


class OTAManager:
    """
    Manager aktualizacji Over-The-Air dla węzłów Spore.

    Propaguje ewolucje kodu (z PR 021) do wszystkich węzłów w klastrze.
    Mechanizm:
    1. Nexus wystawia endpoint HTTP z paczką kodu (zip)
    2. Na sygnał UPDATE_SYSTEM (Redis Pub/Sub), Spores:
       - Pobierają nowy kod
       - Instalują zależności
       - Wykonują bezpieczny restart
    """

    def __init__(
        self, message_broker: MessageBroker, workspace_root: Optional[str] = None
    ):
        """
        Inicjalizacja OTAManager.

        Args:
            message_broker: Broker wiadomości Redis
            workspace_root: Katalog workspace (domyślnie z SETTINGS)
        """
        self.message_broker = message_broker
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.ota_dir = self.workspace_root / "ota_packages"
        self.ota_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"OTAManager zainicjalizowany, katalog OTA: {self.ota_dir}")

    async def create_package(
        self,
        version: str,
        description: str,
        source_paths: List[Path],
        include_dependencies: bool = True,
    ) -> Optional[OTAPackage]:
        """
        Tworzy paczkę aktualizacji OTA.

        Args:
            version: Wersja paczki (np. "1.2.3")
            description: Opis zmian
            source_paths: Lista ścieżek do zapakowania (katalogi/pliki)
            include_dependencies: Czy dołączyć plik zależności

        Returns:
            OTAPackage lub None w przypadku błędu
        """
        try:
            # Nazwa pliku paczki
            package_filename = (
                f"venom_ota_{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            )
            package_path = self.ota_dir / package_filename

            logger.info(f"Tworzenie paczki OTA: {package_filename}")

            # Utwórz ZIP
            with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Dodaj źródła
                for source_path in source_paths:
                    if not source_path.exists():
                        logger.warning(f"Ścieżka nie istnieje: {source_path}, pomijam")
                        continue

                    if source_path.is_file():
                        # Pojedynczy plik
                        zipf.write(source_path, source_path.name)
                    elif source_path.is_dir():
                        # Katalog - dodaj rekursywnie
                        for file_path in source_path.rglob("*"):
                            if file_path.is_file():
                                # Relatywna ścieżka w ZIP
                                arcname = file_path.relative_to(source_path.parent)
                                zipf.write(file_path, arcname)

                # Dodaj plik zależności jeśli wymagane
                if include_dependencies:
                    req_path = Path(REQUIREMENTS_FILENAME)
                    if req_path.exists():
                        zipf.write(req_path, REQUIREMENTS_FILENAME)
                        logger.info(f"Dodano {REQUIREMENTS_FILENAME} do paczki")

            # Oblicz checksum
            checksum = await self._calculate_checksum(package_path)

            # Utwórz obiekt OTAPackage
            package = OTAPackage(
                version=version,
                description=description,
                package_path=package_path,
                checksum=checksum,
            )

            logger.info(
                f"Paczka OTA utworzona: {package_filename}, rozmiar: {package_path.stat().st_size} bytes"
            )

            return package

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia paczki OTA: {e}")
            return None

    async def _calculate_checksum(self, file_path: Path) -> str:
        """
        Oblicza sumę kontrolną SHA256 pliku.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Suma kontrolna SHA256 (hex)
        """
        if aiofiles is None:
            raise RuntimeError("aiofiles nie jest zainstalowane")
        sha256_hash = hashlib.sha256()
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(8192)
                if not chunk:
                    break
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    async def broadcast_update(
        self, package: OTAPackage, target_nodes: Optional[List[str]] = None
    ) -> bool:
        """
        Wysyła sygnał aktualizacji do węzłów.

        Args:
            package: Paczka aktualizacji
            target_nodes: Lista ID węzłów do zaktualizowania (None = wszystkie)

        Returns:
            True jeśli broadcast wysłany, False w przeciwnym razie
        """
        try:
            # Przygotuj dane aktualizacji
            update_data = {
                "version": package.version,
                "description": package.description,
                "package_url": build_http_url(
                    "localhost",
                    SETTINGS.NEXUS_PORT,
                    f"/ota/download/{package.package_path.name}",
                ),
                "checksum": package.checksum,
                "target_nodes": target_nodes,
                "created_at": package.created_at.isoformat(),
            }

            # Wyślij broadcast
            await self.message_broker.broadcast_control(
                command="UPDATE_SYSTEM", data=update_data
            )

            logger.info(
                f"Broadcast UPDATE_SYSTEM wysłany: wersja {package.version}, węzły: {target_nodes or 'wszystkie'}"
            )

            return True

        except Exception as e:
            logger.error(f"Błąd podczas wysyłania broadcast update: {e}")
            return False

    async def apply_update(
        self, package_url: str, expected_checksum: str, restart_after: bool = True
    ) -> bool:
        """
        Aplikuje aktualizację na lokalnym węźle (Spore).

        Args:
            package_url: URL do pobrania paczki
            expected_checksum: Oczekiwana suma kontrolna
            restart_after: Czy restartować proces po aktualizacji

        Returns:
            True jeśli aktualizacja udana, False w przeciwnym razie
        """
        try:
            logger.info(f"Rozpoczynam aktualizację OTA z {package_url}")

            # 1. Pobierz paczkę
            package_path = await self._download_package(package_url)
            if not package_path:
                return False

            # 2. Weryfikuj checksum
            actual_checksum = await self._calculate_checksum(package_path)
            if actual_checksum != expected_checksum:
                logger.error(
                    f"Checksum nie zgadza się! Oczekiwano: {expected_checksum}, otrzymano: {actual_checksum}"
                )
                return False

            logger.info("Checksum zweryfikowany poprawnie")

            # 3. Rozpakuj paczkę
            extract_dir = self.workspace_root / "ota_extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(package_path, "r") as zipf:
                zipf.extractall(extract_dir)

            logger.info(f"Paczka rozpakowana do: {extract_dir}")

            # 4. Skopiuj pliki do właściwych lokalizacji
            # Użyj katalogu instalacji Venom zamiast Path.cwd()
            venom_root = Path(__file__).parent.parent.parent
            await self._copy_files(extract_dir, venom_root)

            # 5. Instaluj zależności jeśli plik zależności istnieje
            requirements_path = extract_dir / REQUIREMENTS_FILENAME
            if requirements_path.exists():
                logger.info("Instaluję zależności...")
                await self._install_dependencies(requirements_path)

            # 6. Restart procesu jeśli wymagane
            if restart_after:
                logger.info("Planowanie restartu procesu...")
                self._schedule_restart()

            logger.info("Aktualizacja OTA ukończona pomyślnie")
            return True

        except Exception as e:
            logger.error(f"Błąd podczas aplikowania aktualizacji OTA: {e}")
            return False

    async def _download_package(self, package_url: str) -> Optional[Path]:
        """
        Pobiera paczkę z URL.

        Args:
            package_url: URL paczki

        Returns:
            Ścieżka do pobranego pliku lub None
        """
        try:
            import httpx

            filename = package_url.split("/")[-1]
            download_path = self.ota_dir / f"download_{filename}"

            async with httpx.AsyncClient() as client:
                response = await client.get(package_url, timeout=60.0)
                response.raise_for_status()

                if aiofiles is None:
                    raise RuntimeError("aiofiles nie jest zainstalowane")
                async with aiofiles.open(download_path, "wb") as f:
                    await f.write(response.content)

            logger.info(f"Paczka pobrana: {download_path}")
            return download_path

        except Exception as e:
            logger.error(f"Błąd podczas pobierania paczki: {e}")
            return None

    async def _copy_files(self, source_dir: Path, target_dir: Path):
        """
        Kopiuje pliki z source_dir do target_dir.

        Args:
            source_dir: Katalog źródłowy
            target_dir: Katalog docelowy
        """
        import shutil

        def _copy_files_sync() -> None:
            for item in source_dir.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(source_dir)
                    target_path = target_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Backup starego pliku jeśli istnieje
                    if target_path.exists():
                        backup_path = target_path.with_suffix(
                            target_path.suffix + ".backup"
                        )
                        shutil.copy2(target_path, backup_path)

                    # Skopiuj nowy plik
                    shutil.copy2(item, target_path)
                    logger.debug(f"Skopiowano: {rel_path}")

        await asyncio.to_thread(_copy_files_sync)

    async def _install_dependencies(self, requirements_path: Path) -> bool:
        """
        Instaluje zależności z pliku zależności.

        UWAGA: Szczegółowe uwagi bezpieczeństwa dotyczące instalacji zależności
        znajdują się w dokumentacji: patrz docs/THE_HIVE.md, sekcja Security.

        Args:
            requirements_path: Ścieżka do pliku zależności

        Returns:
            True jeśli instalacja udana
        """
        try:
            # Timeout instalacji zależności konfigurowalny przez SETTINGS
            timeout = getattr(SETTINGS, "OTA_DEPENDENCY_INSTALL_TIMEOUT", 300)

            # Uruchom pip install
            result = await asyncio.to_thread(
                subprocess.run,
                ["pip", "install", "-r", str(requirements_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                logger.info("Zależności zainstalowane pomyślnie")
                return True
            else:
                logger.error(f"Błąd instalacji zależności: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Błąd podczas instalacji zależności: {e}")
            return False

    def _schedule_restart(self):
        """
        Planuje restart procesu.

        UWAGA: W obecnej implementacji tylko loguje ostrzeżenie.
        W produkcji należy użyć systemd/supervisor lub mechanizmu
        zarządzania procesami do bezpiecznego restartu.
        """
        # W produkcji: użyj systemd, supervisor lub innego mechanizmu
        # Na razie: log informacji
        logger.warning(
            "⚠️ Restart wymagany! Węzeł powinien zostać zrestartowany ręcznie lub przez orchestrator."
        )
        # Opcjonalnie: można użyć os.execv() do restartu procesu
        # import os
        # import sys
        # os.execv(sys.executable, ['python'] + sys.argv)

    def list_packages(self) -> List[Dict[str, Any]]:
        """
        Lista dostępnych paczek OTA.

        Returns:
            Lista słowników z informacjami o paczkach
        """
        packages = []
        for package_file in self.ota_dir.glob("venom_ota_*.zip"):
            try:
                # Parse nazwy pliku dla podstawowych informacji
                # Format: venom_ota_{version}_{timestamp}.zip
                parts = package_file.stem.split("_")
                version = parts[2] if len(parts) > 2 else "unknown"

                packages.append(
                    {
                        "filename": package_file.name,
                        "version": version,
                        "path": str(package_file),
                        "size_bytes": package_file.stat().st_size,
                        "created_at": datetime.fromtimestamp(
                            package_file.stat().st_mtime
                        ).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Nie można przetworzyć paczki {package_file}: {e}")

        return sorted(packages, key=lambda p: p["created_at"], reverse=True)

    def cleanup_old_packages(self, keep_latest: int = 5):
        """
        Usuwa stare paczki OTA, zostawiając najnowsze.

        Args:
            keep_latest: Liczba najnowszych paczek do zachowania
        """
        packages = self.list_packages()

        if len(packages) <= keep_latest:
            logger.info(f"Brak paczek do usunięcia (znaleziono {len(packages)})")
            return

        # Usuń stare paczki
        to_delete = packages[keep_latest:]
        for package in to_delete:
            try:
                package_path = Path(package["path"])
                package_path.unlink()
                logger.info(f"Usunięto starą paczkę: {package['filename']}")
            except Exception as e:
                logger.error(f"Nie można usunąć paczki {package['filename']}: {e}")

        logger.info(f"Usunięto {len(to_delete)} starych paczek")
