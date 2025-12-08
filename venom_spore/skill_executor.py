"""Executor skill'ów na węźle Spore."""

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

        return await handler(method_name, parameters)

    async def _handle_shell(self, method_name: str, parameters: Dict[str, Any]) -> str:
        """
        Obsługuje ShellSkill.

        Args:
            method_name: Nazwa metody
            parameters: Parametry

        Returns:
            Wynik wykonania komendy
        """
        if method_name == "run":
            command = parameters.get("command", "")
            timeout = parameters.get("timeout", 30)

            try:
                result = subprocess.run(
                    command,
                    shell=True,
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

    async def _handle_file(self, method_name: str, parameters: Dict[str, Any]) -> str:
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
            file_path = self.workspace_root / path

            try:
                if not file_path.exists():
                    return f"❌ Plik nie istnieje: {path}"
                return file_path.read_text(encoding="utf-8")
            except Exception as e:
                return f"❌ Błąd odczytu: {str(e)}"

        elif method_name == "write_file":
            path = parameters.get("path", "")
            content = parameters.get("content", "")
            file_path = self.workspace_root / path

            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                return f"✅ Zapisano plik: {path}"
            except Exception as e:
                return f"❌ Błąd zapisu: {str(e)}"

        elif method_name == "list_files":
            path = parameters.get("path", ".")
            dir_path = self.workspace_root / path

            try:
                if not dir_path.exists():
                    return f"❌ Katalog nie istnieje: {path}"

                files = []
                for item in dir_path.iterdir():
                    files.append(f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}")
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
            "has_gpu": False,  # TODO: Wykrywanie GPU
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
