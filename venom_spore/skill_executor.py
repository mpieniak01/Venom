"""Executor skill'ów na węźle Spore."""

import asyncio
import inspect
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict

PATH_SYMLINK_BLOCKED_ERROR = "❌ Zabroniony dostęp: symlink poza workspace"
PATH_OUTSIDE_WORKSPACE_ERROR = "❌ Zabroniony dostęp: ścieżka poza workspace"
SKILLS_HANDLERS = ("ShellSkill", "FileSkill")
SHELL_DANGEROUS_PATTERNS = ("rm -rf", "mkfs", "dd if=", "> /dev/", "sudo", "su ")


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
        if method_name != "run":
            raise ValueError(f"Metoda {method_name} nie jest obsługiwana w ShellSkill")
        command = parameters.get("command", "")
        timeout = parameters.get("timeout", 30)

        blocked_pattern = self._find_dangerous_pattern(command)
        if blocked_pattern:
            return (
                "❌ Zabroniona komenda: komenda zawiera niebezpieczny "
                f"pattern '{blocked_pattern}'"
            )

        return await self._execute_shell_command(command, timeout)

    def _find_dangerous_pattern(self, command: str) -> str | None:
        command_lower = command.lower()
        for pattern in SHELL_DANGEROUS_PATTERNS:
            if pattern in command_lower:
                return pattern
        return None

    async def _execute_shell_command(self, command: str, timeout: int) -> str:
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

    def _handle_file(self, method_name: str, parameters: Dict[str, Any]) -> str:
        """
        Obsługuje FileSkill.

        Args:
            method_name: Nazwa metody
            parameters: Parametry

        Returns:
            Wynik operacji
        """
        file_handlers = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_files": self._list_files,
        }
        handler = file_handlers.get(method_name)
        if handler is None:
            raise ValueError(f"Metoda {method_name} nie jest obsługiwana w FileSkill")
        return handler(parameters)

    def _resolve_workspace_path(self, path: str) -> tuple[Path | None, str | None]:
        try:
            resolved_path = (self.workspace_root / path).resolve()
            workspace_resolved = self.workspace_root.resolve()
            if resolved_path.is_symlink():
                real_path = resolved_path.resolve()
                if (
                    workspace_resolved not in real_path.parents
                    and real_path != workspace_resolved
                ):
                    return None, PATH_SYMLINK_BLOCKED_ERROR
            if (
                workspace_resolved not in resolved_path.parents
                and resolved_path != workspace_resolved
            ):
                return None, PATH_OUTSIDE_WORKSPACE_ERROR
            return resolved_path, None
        except Exception as e:
            return None, f"❌ Nieprawidłowa ścieżka: {str(e)}"

    def _read_file(self, parameters: Dict[str, Any]) -> str:
        path = parameters.get("path", "")
        file_path, error = self._resolve_workspace_path(path)
        if error:
            return error
        assert file_path is not None

        try:
            if not file_path.exists():
                return f"❌ Plik nie istnieje: {path}"
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"❌ Błąd odczytu: {str(e)}"

    def _write_file(self, parameters: Dict[str, Any]) -> str:
        path = parameters.get("path", "")
        content = parameters.get("content", "")
        file_path, error = self._resolve_workspace_path(path)
        if error:
            return error
        assert file_path is not None

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"✅ Zapisano plik: {path}"
        except Exception as e:
            return f"❌ Błąd zapisu: {str(e)}"

    def _list_files(self, parameters: Dict[str, Any]) -> str:
        path = parameters.get("path", ".")
        dir_path, error = self._resolve_workspace_path(path)
        if error:
            return error
        assert dir_path is not None

        try:
            if not dir_path.exists():
                return f"❌ Katalog nie istnieje: {path}"
            files = [
                f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}"
                for item in dir_path.iterdir()
            ]
            return "\n".join(files)
        except Exception as e:
            return f"❌ Błąd listowania: {str(e)}"

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Pobiera informacje o możliwościach węzła.

        Returns:
            Słownik z możliwościami
        """
        import psutil

        # Dostępne skill'e
        skills = list(SKILLS_HANDLERS)

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
