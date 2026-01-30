import textwrap
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class McpToolMetadata:
    name: str
    description: str
    input_schema: Dict[str, Any]


class McpProxyGenerator:
    """
    Generuje kod Pythona dla skilla, który działa jako proxy do serwera MCP.
    """

    def generate_skill_code(
        self,
        skill_name: str,
        server_command: str,
        server_args: List[str],
        env_vars: Dict[str, str],
        tools: List[McpToolMetadata],
    ) -> str:
        """
        Generuje zawartość pliku .py dla skilla.

        Args:
            skill_name: Nazwa klasy skilla (np. "SqliteMcpSkill")
            server_command: Komenda do uruchomienia serwera (np. ścieżka do python w venv)
            server_args: Argumenty dla serwera
            env_vars: Zmienne środowiskowe dla procesu serwera
            tools: Lista wykrytych narzędzi MCP
        """

        methods_code = []
        for tool in tools:
            method = self._generate_tool_method(tool)
            methods_code.append(method)

        methods_block = "\n".join(methods_code)

        # Escaping backslashes for python string literals in the generated code
        server_command_repr = repr(server_command)
        server_args_repr = repr(server_args)
        env_vars_repr = repr(env_vars)

        code = f"""
# Poniższy kod został wygenerowany automatycznie przez Venom McpManager.
# Nie edytuj tego pliku ręcznie, chyba że wiesz co robisz.

import asyncio
import json
import os
import shutil
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action
from semantic_kernel.functions import kernel_function

class {skill_name}(BaseSkill):
    \"\"\"
    Skill generowany automatycznie, obsługujący serwer MCP: {skill_name}.
    \"\"\"

    def __init__(self):
        super().__init__()
        self.server_params = StdioServerParameters(
            command={server_command_repr},
            args={server_args_repr},
            env={{**os.environ, **{env_vars_repr}}}
        )
        # Note: MCP Client usually requires a context manager or async startup.
        # Since BaseSkill is sync init, we will manage the connection in method calls
        # or separate connect logic. For simplicity in this MVP, we establish
        # a fresh connection per call or manage a persistent one lazily.
        # Here we will use a 'run_tool' helper that connects on demand.

    async def _run_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        \"\"\"
        Helper method to run a specific tool on the MCP server.
        \"\"\"
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Call the tool
                    result = await session.call_tool(tool_name, arguments)

                    # Format result
                    output = []
                    if result.content:
                        for item in result.content:
                            if item.type == 'text':
                                output.append(item.text)
                            elif item.type == 'image':
                                output.append("[Image Content]")
                            elif item.type == 'resource':
                                output.append(f"[Resource: {{item.uri}}]")

                    final_text = "\\n".join(output)
                    if result.isError:
                        return f"❌ MCP Tool Error: {{final_text}}"
                    return final_text

        except Exception as e:
            self.logger.error(f"MCP Connection Error: {{e}}", exc_info=True)
            return f"❌ MCP Connection Error: {{e}}"

{methods_block}
        """
        return textwrap.dedent(code).strip()

    def _generate_tool_method(self, tool: McpToolMetadata) -> str:
        """
        Tworzy kod pojedynczej metody @kernel_function.
        """
        # Sanitize name
        method_name = tool.name.replace("-", "_").replace(".", "_")

        # Build docstring from description
        description = (
            tool.description.replace('"', '\\"')
            if tool.description
            else f"Runs {tool.name}"
        )

        # We must generate a signature that accepts **kwargs or simplified arguments.
        # For MVP, we will treat arguments as a single JSON string or **kwargs if possible.
        # Semantic Kernel supports annotated arguments.
        # Parsing the schema is complex.
        # Approach: We will expose a single 'arguments_json' param or
        # just generated parameters if schema is simple.
        # To strictly follow safe code generation, let's use **kwargs with types based on schema?
        # Too complex for MVP generator text manipulation.
        # SAFEST MVP STRATEGY:
        # One argument: arguments_json: Annotated[str, "JSON string with arguments"]
        # OR
        # Just use **kwargs and let the agent figure it out? No, SK needs introspection.

        # Let's try to parse the properties keys.
        props = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])

        # Construct args list
        # We start with self
        args_def = ["self"]

        # Docstring args
        doc_args = []

        # Dict construction code
        dict_construction = ["arguments = {"]

        for prop_name, prop_def in props.items():
            prop_desc = prop_def.get("description", "")

            # Helper to map JSON types to Python types hints
            # (Skipped for brevity, defaulting to Any or str)

            is_req = prop_name in required
            default_val = " = None" if not is_req else ""

            # Clean param name
            clean_prop = prop_name.replace("-", "_")

            args_def.append(f"{clean_prop}: str{default_val}")

            doc_args.append(f":param {clean_prop}: {prop_desc}")

            # Add to dict
            dict_construction.append(f"    '{prop_name}': {clean_prop},")

        dict_construction.append("}")

        # Join args
        signature = ", ".join(args_def)

        # Method body
        body = f"""
    @kernel_function(
        name="{method_name}",
        description="{description}"
    )
    @async_safe_action
    async def {method_name}({signature}) -> str:
        \"\"\"
        {description}
        \"\"\"
        # Construct arguments dictionary
        args_dict = {{}}
        {"".join([f"if {k.replace('-', '_')} is not None: args_dict['{k}'] = {k.replace('-', '_')}" + chr(10) + "        " for k in props.keys()])}

        return await self._run_mcp_tool("{tool.name}", args_dict)
        """

        return body
