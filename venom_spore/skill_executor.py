"""Executor skill'ów na węźle Spore."""

import asyncio
import inspect
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict


class SkillExecutor:
    """Wykonywacz skill'ów na węźle Spore."""

    def __init__(self, workspace_root: str = "./workspace"):
        """
        Inicjalizacja executora.

        Args:
            workspace_root: Ścieżka do workspace
        """
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    async def execute(
        self, skill_name: str, method_name: str, parameters: Dict[str, Any]
    ) -> Any:
        """
        Wykonuje skill na węźle.

        Args:
            skill_name: Nazwa skilla (np. "ShellSkill")
            method_name: Nazwa metody (np. "run")
            parameters: Parametry wywołania

        Returns:
            Wynik wykonania

        Raises:
            ValueError: Jeśli skill nie jest obsługiwany
        """
        # Mapowanie skill -> handler
        handlers = {
            "ShellSkill": self._handle_shell,
            "FileSkill": self._handle_file,
        }

        handler = handlers.get(skill_name)
        if not handler:
            raise ValueError(f"Skill {skill_name} nie jest obsługiwany przez ten węzeł")

        result = handler(method_name, parameters)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _handle_shell(self, method_name: str, parameters: Dict[str, Any]) -> str:
        """
        Obsługuje ShellSkill.

        SECURITY WARNING: Używa shell=True z podstawową walidacją blacklist.
        W produkcji rozważ:
        - Użycie whitelist dopuszczalnych komend
        - Użycie subprocess z listą argumentów zamiast shell=True
        - Dedykowany parser komend z sandboxingiem
        - Ograniczenie do predefiniowanych skryptów

        Args:
            method_name: Nazwa metody
            parameters: Parametry

        Returns:
            Wynik wykonania komendy
        """
        if method_name == "run":
            command = parameters.get("command", "")
            timeout = parameters.get("timeout", 30)

            # SECURITY: Podstawowa walidacja - blokuj niebezpieczne komendy
            # UWAGA: To nie jest kompletna ochrona! Można obejść przez:
            # - Różne warianty spacji/tabs (rm\t-rf)
            # - Kodowanie (base64, hex)
            # - Aliasy i funkcje shell
            # W produkcji użyj whitelist lub subprocess bez shell=True
            dangerous_patterns = ["rm -rf", "mkfs", "dd if=", "> /dev/", "sudo", "su "]
            for pattern in dangerous_patterns:
                if pattern in command.lower():
                    return f"❌ Zabroniona komenda: komenda zawiera niebezpieczny pattern '{pattern}'"

            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    shell=True,  # SECURITY RISK - rozważ przepisanie na subprocess bez shell
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(self.workspace_root),
                )
                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]\n{result.stderr}"
                return output
            except subprocess.TimeoutExpired:
                return f"❌ Timeout: komenda nie zakończyła się w ciągu {timeout}s"
            except Exception as e:
                return f"❌ Błąd wykonania: {str(e)}"
        else:
            raise ValueError(f"Metoda {method_name} nie jest obsługiwana w ShellSkill")

    def _handle_file(self, method_name: str, parameters: Dict[str, Any]) -> str:
        """
        Obsługuje FileSkill.

        Args:
            method_name: Nazwa metody
            parameters: Parametry

        Returns:
            Wynik operacji
        """
        if method_name == "read_file":
            path = parameters.get("path", "")

            # SECURITY: Walidacja path traversal
            try:
                file_path = (self.workspace_root / path).resolve()
                workspace_resolved = self.workspace_root.resolve()

                # Sprawdź czy ścieżka jest w workspace (obsługa symlinków)
                if file_path.is_symlink():
                    real_path = file_path.resolve()
                    if (
                        workspace_resolved not in real_path.parents
                        and real_path != workspace_resolved
                    ):
                        return "❌ Zabroniony dostęp: symlink poza workspace"

                # Sprawdź czy ścieżka jest w workspace
                if (
                    workspace_resolved not in file_path.parents
                    and file_path != workspace_resolved
                ):
                    return "❌ Zabroniony dostęp: ścieżka poza workspace"
            except Exception as e:
                return f"❌ Nieprawidłowa ścieżka: {str(e)}"

            try:
                if not file_path.exists():
                    return f"❌ Plik nie istnieje: {path}"
                return file_path.read_text(encoding="utf-8")
            except Exception as e:
                return f"❌ Błąd odczytu: {str(e)}"

        elif method_name == "write_file":
            path = parameters.get("path", "")
            content = parameters.get("content", "")

            # SECURITY: Walidacja path traversal
            try:
                file_path = (self.workspace_root / path).resolve()
                workspace_resolved = self.workspace_root.resolve()

                # Sprawdź czy ścieżka jest w workspace (obsługa symlinków)
                if file_path.is_symlink():
                    real_path = file_path.resolve()
                    if (
                        workspace_resolved not in real_path.parents
                        and real_path != workspace_resolved
                    ):
                        return "❌ Zabroniony dostęp: symlink poza workspace"

                # Sprawdź czy ścieżka jest w workspace
                if (
                    workspace_resolved not in file_path.parents
                    and file_path != workspace_resolved
                ):
                    return "❌ Zabroniony dostęp: ścieżka poza workspace"
            except Exception as e:
                return f"❌ Nieprawidłowa ścieżka: {str(e)}"

            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                return f"✅ Zapisano plik: {path}"
            except Exception as e:
                return f"❌ Błąd zapisu: {str(e)}"

        elif method_name == "list_files":
            path = parameters.get("path", ".")

            # SECURITY: Walidacja path traversal
            try:
                dir_path = (self.workspace_root / path).resolve()
                workspace_resolved = self.workspace_root.resolve()

                # Sprawdź czy ścieżka jest w workspace (obsługa symlinków)
                if dir_path.is_symlink():
                    real_path = dir_path.resolve()
                    if (
                        workspace_resolved not in real_path.parents
                        and real_path != workspace_resolved
                    ):
                        return "❌ Zabroniony dostęp: symlink poza workspace"

                # Sprawdź czy ścieżka jest w workspace
                if (
                    workspace_resolved not in dir_path.parents
                    and dir_path != workspace_resolved
                ):
                    return "❌ Zabroniony dostęp: ścieżka poza workspace"
            except Exception as e:
                return f"❌ Nieprawidłowa ścieżka: {str(e)}"

            try:
                if not dir_path.exists():
                    return f"❌ Katalog nie istnieje: {path}"

                files = []
                for item in dir_path.iterdir():
                    files.append(
                        f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}"
                    )
                return "\n".join(files)
            except Exception as e:
                return f"❌ Błąd listowania: {str(e)}"

        else:
            raise ValueError(f"Metoda {method_name} nie jest obsługiwana w FileSkill")

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Pobiera informacje o możliwościach węzła.

        Returns:
            Słownik z możliwościami
        """
        import psutil

        # Dostępne skill'e
        skills = ["ShellSkill", "FileSkill"]

        # Informacje o systemie
        cpu_count = os.cpu_count() or 1
        memory = psutil.virtual_memory()
        memory_mb = int(memory.total / (1024 * 1024))

        return {
            "skills": skills,
            "cpu_cores": cpu_count,
            "memory_mb": memory_mb,
            "has_gpu": self._detect_gpu(),
            "has_docker": self._check_docker(),
            "platform": platform.system().lower(),
        }

    def _check_docker(self) -> bool:
        """Sprawdza czy Docker jest dostępny."""
        try:
            subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
            return True
        except Exception:
            return False

    def _detect_gpu(self) -> bool:
        """
        Wykrywa dostępność GPU.

        Note: Obecnie zwraca False. Do implementacji w przyszłości:
        - Użyj nvidia-ml-py lub pynvml dla NVIDIA GPU
        - Użyj rocm dla AMD GPU
        - Sprawdź /dev/dri dla Intel GPU
        """
        # TODO: Implementacja wykrywania GPU
        # Wymaga: pip install nvidia-ml-py3 (dla NVIDIA)
        return False
