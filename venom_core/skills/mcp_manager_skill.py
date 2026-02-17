import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.core.autonomy_enforcement import require_shell_permission
from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action
from venom_core.skills.mcp.proxy_generator import McpProxyGenerator, McpToolMetadata

# Import MCP Client for introspection
MCPClientSession: Any = None
MCPStdioServerParameters: Any = None
mcp_stdio_client: Any = None
try:
    from mcp import ClientSession as MCPClientSession
    from mcp import StdioServerParameters as MCPStdioServerParameters
    from mcp.client.stdio import stdio_client as mcp_stdio_client

    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - środowiska bez optional dependency
    _MCP_AVAILABLE = False

# Backward-compatible aliases used in tests and monkeypatch hooks.
ClientSession = MCPClientSession
StdioServerParameters = MCPStdioServerParameters
stdio_client = mcp_stdio_client


class McpManagerSkill(BaseSkill):
    """
    Skill zarządzający importem i cyklem życia narzędzi MCP (Model Context Protocol).
    """

    # Allowlista zmiennych środowiskowych dla procesów MCP (minimalna bezpieczna konfiguracja)
    SAFE_ENV_VARS = {
        # Podstawowe zmienne systemowe
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "LANG",
        "LC_ALL",
        "TZ",
        # Zmienne Pythona
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        # Zmienne workspace (potrzebne dla działania MCP)
        "WORKSPACE_ROOT",
        "REPO_ROOT",
        # Zmienne potrzebne dla niektórych narzędzi MCP
        "TERM",
        "DISPLAY",
        "PWD",
    }

    def __init__(self):
        super().__init__()
        self.mcp_root = (
            Path(SETTINGS.WORKSPACE_ROOT) / "venom_core" / "skills" / "mcp"
        ).resolve()
        self.repos_root = self.mcp_root / "_repos"
        self.custom_skills_dir = (
            Path(SETTINGS.WORKSPACE_ROOT) / "venom_core" / "skills" / "custom"
        ).resolve()

        # Ensure dirs exist
        self.repos_root.mkdir(parents=True, exist_ok=True)
        self.custom_skills_dir.mkdir(parents=True, exist_ok=True)

        self.generator = McpProxyGenerator()

    def _sanitize_env_for_mcp(
        self, base_env: Optional[Mapping[str, str]] = None
    ) -> Dict[str, str]:
        """
        Sanityzuje zmienne środowiskowe do bezpiecznego przekazania do procesu MCP.

        Filtruje wrażliwe dane jak API keys, tokeny, hasła, zachowując tylko
        niezbędne zmienne systemowe i workspace.

        Args:
            base_env: Bazowe środowisko (domyślnie os.environ)

        Returns:
            Bezpieczny słownik zmiennych środowiskowych
        """
        if base_env is None:
            base_env = os.environ

        # Filtruj tylko dozwolone zmienne
        safe_env = {
            key: value for key, value in base_env.items() if key in self.SAFE_ENV_VARS
        }

        # Dodaj PYTHONUNBUFFERED dla lepszego logowania
        safe_env["PYTHONUNBUFFERED"] = "1"

        self.logger.debug(
            f"Sanityzowano env: {len(base_env)} -> {len(safe_env)} zmiennych "
            f"(odfiltrowano {len(base_env) - len(safe_env)} zmiennych)"
        )

        return safe_env

    @kernel_function(
        name="import_mcp_tool_from_git",
        description="Pobiera narzędzie MCP z Git, instaluje zależności i tworzy skill Venoma.",
    )
    @async_safe_action
    async def import_mcp_tool(
        self,
        repo_url: str,
        tool_name: str,
        install_command: str = "pip install .",
        server_entrypoint: str = "python server.py",
    ) -> str:
        """
        Importuje narzędzie MCP.

        Args:
            repo_url: URL repozytorium Git
            tool_name: Nazwa narzędzia (używana do nazw plików i klas)
            install_command: Komenda instalacji (uruchamiana w venv)
            server_entrypoint: Komenda uruchomienia serwera (względna do root repo)
        """
        require_shell_permission()

        self.logger.info(f"Rozpoczynam import MCP: {tool_name} z {repo_url}")

        repo_dir = self.repos_root / tool_name

        # 1. Clone or Pull
        if repo_dir.exists():
            self.logger.info(
                f"Katalog {repo_dir} istnieje. Usuwam i klonuję ponownie (Clean Install)."
            )
            shutil.rmtree(repo_dir)

        await self._run_shell(f"git clone {repo_url} {repo_dir}")
        self.logger.info("Repozytorium sklonowane.")

        # 2. Setup Venv
        venv_dir = repo_dir / ".venv"
        await self._run_shell(f"python3 -m venv {venv_dir}")

        venv_python = venv_dir / "bin" / "python"
        venv_pip = venv_dir / "bin" / "pip"

        self.logger.info(f"Venv utworzony w {venv_dir}")

        # 3. Install Deps
        # Upgrade pip first
        await self._run_shell(f"{venv_pip} install --upgrade pip")
        # Install deps (install command provided by user usually 'pip install -r requirements.txt' or 'pip install .')
        # We execute it inside the repo dir
        full_install_cmd = f"{venv_pip} install ."
        if (repo_dir / "requirements.txt").exists():
            full_install_cmd = f"{venv_pip} install -r requirements.txt"

        # Allow override if specified differently (simple logic for now)
        if install_command != "pip install .":
            # Replace generic 'pip' with venv pip
            full_install_cmd = install_command.replace("pip ", f"{venv_pip} ")

        await self._run_shell(full_install_cmd, cwd=repo_dir)
        self.logger.info("Zależności zainstalowane.")

        # 4. Introspect (List Tools)
        # We need to construct the exact command to run the server
        # server_entrypoint might be "python main.py" -> we need "{venv_python} main.py"
        server_cmd_parts = server_entrypoint.split()
        if server_cmd_parts[0] == "python":
            server_cmd_parts[0] = str(venv_python)

        # Resolve script paths to absolute
        final_server_args = []
        for arg in server_cmd_parts[1:]:
            possible_path = repo_dir / arg
            if possible_path.exists():
                final_server_args.append(str(possible_path))
            else:
                final_server_args.append(arg)

        final_server_command = server_cmd_parts[0]

        self.logger.info(
            f"Introspekcja narzędzi. Server cmd: {final_server_command} {final_server_args}"
        )

        # Sanityzuj env przed przekazaniem do procesu MCP (bezpieczeństwo)
        safe_env = self._sanitize_env_for_mcp()

        tools_metadata = await self._introspect_tools(
            final_server_command,
            final_server_args,
            cwd=repo_dir,
            env=safe_env,
        )

        if not tools_metadata:
            return f"⚠️ Nie wykryto żadnych narzędzi w serwerze MCP {tool_name}. Import przerwany."

        tool_names = [t.name for t in tools_metadata]
        self.logger.info(f"Wykryto narzędzia: {tool_names}")

        # 5. Generate Proxy Code
        skill_class_name = f"{tool_name.capitalize()}McpSkill"
        # Sanitize class name (remove special chars)
        skill_class_name = "".join(x for x in skill_class_name.title() if x.isalnum())

        code = self.generator.generate_skill_code(
            skill_name=skill_class_name,
            server_command=str(final_server_command),
            server_args=final_server_args,
            env_vars={"PYTHONUNBUFFERED": "1"},  # Force unbuffered for stdio
            tools=tools_metadata,
        )

        output_file = self.custom_skills_dir / f"mcp_{tool_name}.py"
        await asyncio.to_thread(output_file.write_text, code, "utf-8")

        return (
            f"✅ Sukces! Narzędzie '{tool_name}' zaimportowane.\n"
            f"Wykryte funkcje: {', '.join(tool_names)}\n"
            f"Skill zapisany w: {output_file}\n"
            f"Zostanie załadowany przez SkillManager automatycznie (hot-reload)."
        )

    async def _run_shell(self, cmd: str, cwd: Optional[Path] = None) -> str:
        """Uruchamia komendę powłoki asynchronicznie."""
        require_shell_permission()

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            self.logger.error(f"Command failed: {cmd}\nError: {error_msg}")
            raise RuntimeError(f"Shell command failed: {error_msg}")

        return stdout.decode().strip()

    async def _introspect_tools(
        self, command: str, args: List[str], cwd: Path, env: Dict[str, str]
    ) -> List[McpToolMetadata]:
        """
        Uruchamia serwer MCP na chwilę, aby pobrać listę narzędzi.
        """
        if not _MCP_AVAILABLE:
            raise RuntimeError(
                "Biblioteka 'mcp' nie jest zainstalowana. "
                "Zainstaluj optional dependency, aby używać introspekcji MCP."
            )

        # Upewnij się, że env zawiera PYTHONUNBUFFERED i PYTHONPATH
        final_env = {**env, "PYTHONUNBUFFERED": "1"}
        if "PYTHONPATH" not in final_env and cwd:
            final_env["PYTHONPATH"] = str(cwd)

        server_params = StdioServerParameters(command=command, args=args, env=final_env)

        tools_list = []
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # List tools
                    result = await session.list_tools()

                    for tool in result.tools:
                        tools_list.append(
                            McpToolMetadata(
                                name=tool.name,
                                description=tool.description or "",
                                input_schema=tool.inputSchema,
                            )
                        )
        except Exception as e:
            self.logger.error(f"Introspekcja nieudana: {e}")
            raise e

        return tools_list
