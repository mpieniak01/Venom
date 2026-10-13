"""Moduł: core_skill - narzędzia do bezpiecznych operacji na kodzie źródłowym Venom."""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from venom_core.core.autonomy_enforcement import require_core_patch_permission
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CoreSkill:
    """
    Skill do operacji chirurgicznych na kodzie źródłowym Venom.

    Zapewnia bezpieczne narzędzia do:
    - Modyfikacji plików z automatycznym backupem
    - Wycofywania zmian (rollback)
    - Restartu procesu Venom

    UWAGA: Ten skill powinien być używany TYLKO przez SystemEngineerAgent
    i TYLKO po weryfikacji zmian w Mirror World.
    """

    def __init__(self, backup_dir: Optional[str] = None):
        """
        Inicjalizacja CoreSkill.

        Args:
            backup_dir: Katalog do przechowywania backupów (domyślnie ./data/backups)
        """
        if backup_dir:
            self.backup_dir = Path(backup_dir).resolve()
        else:
            self.backup_dir = Path("./data/backups").resolve()

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"CoreSkill zainicjalizowany z backup_dir: {self.backup_dir}")

    @kernel_function(
        name="hot_patch",
        description="Bezpiecznie modyfikuje plik z automatycznym backupem. Używaj TYLKO po weryfikacji w Mirror World.",
    )
    def hot_patch(
        self,
        file_path: Annotated[
            str, "Ścieżka do pliku do zmodyfikowania (relatywna lub bezwzględna)"
        ],
        content: Annotated[str, "Nowa zawartość pliku"],
        create_backup: Annotated[
            bool, "Czy utworzyć backup przed zmianą (domyślnie True)"
        ] = True,
    ) -> str:
        """
        Bezpiecznie modyfikuje plik z opcjonalnym backupem.

        Args:
            file_path: Ścieżka do pliku
            content: Nowa zawartość pliku
            create_backup: Czy utworzyć backup

        Returns:
            Komunikat o wyniku operacji
        """
        require_core_patch_permission()

        try:
            path = Path(file_path).resolve()

            # Sprawdź czy plik istnieje
            if not path.exists():
                return f"❌ Plik {file_path} nie istnieje"

            # Sprawdź czy to nie katalog
            if path.is_dir():
                return f"❌ {file_path} jest katalogiem, nie plikiem"

            # Utwórz backup jeśli wymagany
            backup_path = None
            if create_backup:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"{path.name}.{timestamp}.bak"
                backup_path = self.backup_dir / backup_filename

                shutil.copy2(path, backup_path)
                logger.info(f"Utworzono backup: {backup_path}")

            # Zapisz nową zawartość
            path.write_text(content, encoding="utf-8")
            logger.info(f"✅ Zmodyfikowano plik: {path}")

            result = f"✅ Plik {file_path} został zmodyfikowany"
            if backup_path:
                result += f"\nBackup: {backup_path}"

            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas modyfikacji pliku {file_path}: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @kernel_function(
        name="rollback",
        description="Przywraca plik z backupu (.bak). Używaj gdy zmiana spowodowała problemy.",
    )
    def rollback(
        self,
        file_path: Annotated[str, "Ścieżka do pliku do przywrócenia"],
        backup_file: Annotated[
            Optional[str],
            "Opcjonalna ścieżka do konkretnego backupu (jeśli nie podano, użyje najnowszego)",
        ] = None,
    ) -> str:
        """
        Przywraca plik z backupu.

        Args:
            file_path: Ścieżka do pliku do przywrócenia
            backup_file: Opcjonalna ścieżka do konkretnego backupu

        Returns:
            Komunikat o wyniku operacji
        """
        require_core_patch_permission()

        try:
            path = Path(file_path).resolve()
            filename = path.name

            # Jeśli nie podano backupu, znajdź najnowszy
            if not backup_file:
                # Znajdź wszystkie backupy tego pliku
                backups = sorted(
                    self.backup_dir.glob(f"{filename}.*.bak"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )

                if not backups:
                    return f"❌ Brak backupów dla pliku {file_path}"

                backup_path = backups[0]
                logger.info(f"Znaleziono najnowszy backup: {backup_path}")
            else:
                backup_path = Path(backup_file).resolve()
                if not backup_path.exists():
                    return f"❌ Backup {backup_file} nie istnieje"

            # Przywróć z backupu
            shutil.copy2(backup_path, path)
            logger.info(f"✅ Przywrócono plik {path} z backupu {backup_path}")

            return f"✅ Plik {file_path} przywrócony z backupu\nBackup: {backup_path}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas rollback pliku {file_path}: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @kernel_function(
        name="list_backups",
        description="Wyświetla listę dostępnych backupów dla pliku.",
    )
    def list_backups(
        self,
        file_path: Annotated[
            Optional[str],
            "Opcjonalna ścieżka do pliku (jeśli nie podano, pokaże wszystkie backupy)",
        ] = None,
    ) -> str:
        """
        Wyświetla listę backupów.

        Args:
            file_path: Opcjonalna ścieżka do pliku

        Returns:
            Lista backupów
        """
        try:
            if file_path:
                filename = Path(file_path).name
                backups = sorted(
                    self.backup_dir.glob(f"{filename}.*.bak"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
            else:
                backups = sorted(
                    self.backup_dir.glob("*.bak"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )

            if not backups:
                return "Brak backupów"

            result = f"Znaleziono {len(backups)} backup(ów):\n\n"
            for backup in backups:
                mtime = datetime.fromtimestamp(backup.stat().st_mtime)
                size = backup.stat().st_size
                result += f"- {backup.name} ({size} bajtów, {mtime.strftime('%Y-%m-%d %H:%M:%S')})\n"

            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas listowania backupów: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @kernel_function(
        name="restart_service",
        description="OSTROŻNIE: Restartuje proces Venom. Używaj TYLKO po pomyślnej weryfikacji zmian.",
    )
    def restart_service(
        self,
        confirm: Annotated[bool, "Potwierdzenie restartu (musi być True)"] = False,
    ) -> str:
        """
        Restartuje proces Venom.

        UWAGA: To jest destrukcyjna operacja! Proces zostanie zrestartowany.
        Wszystkie niezapisane dane mogą zostać utracone.

        Args:
            confirm: Potwierdzenie (musi być True)

        Returns:
            Komunikat o wyniku operacji
        """
        if not confirm:
            return "❌ Restart wymaga potwierdzenia (confirm=True). Operacja anulowana."

        require_core_patch_permission()
        logger.warning("🔄 RESTART PROCESU VENOM...")

        try:
            # Opcja 1: Restart przez os.execv (zamieni bieżący proces)
            # To jest najbezpieczniejsza metoda dla długo działających serwisów
            python = sys.executable
            args = [python] + sys.argv

            logger.info(f"Restart procesu: {python} {' '.join(sys.argv)}")

            # Wykonaj restart
            os.execv(python, args)

            # Ten kod nigdy się nie wykona, bo proces zostanie zastąpiony
            return "🔄 Restarting..."

        except Exception as e:
            error_msg = f"❌ Błąd podczas restartu: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @kernel_function(
        name="verify_syntax",
        description="Sprawdza poprawność składni Pythona w pliku bez wykonywania kodu.",
    )
    def verify_syntax(
        self,
        file_path: Annotated[str, "Ścieżka do pliku .py do sprawdzenia"],
    ) -> str:
        """
        Sprawdza poprawność składni Pythona.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Komunikat o wyniku sprawdzenia
        """
        try:
            path = Path(file_path).resolve()

            if not path.exists():
                return f"❌ Plik {file_path} nie istnieje"

            if path.suffix != ".py":
                return f"⚠️ Plik {file_path} nie jest plikiem Python (.py)"

            # Czytaj plik
            code = path.read_text(encoding="utf-8")

            # Sprawdź składnię
            try:
                compile(code, str(path), "exec")
                return f"✅ Składnia pliku {file_path} jest poprawna"
            except SyntaxError as se:
                return f"❌ Błąd składni w {file_path}:\nLinia {se.lineno}: {se.msg}\n{se.text}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas weryfikacji składni {file_path}: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    def get_backup_dir(self) -> Path:
        """
        Zwraca katalog z backupami.

        Returns:
            Ścieżka do katalogu z backupami
        """
        return self.backup_dir
