"""MCP-like adapter for local Venom skills (PoC for convergence path)."""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.execution.skills.google_calendar_skill import GoogleCalendarSkill
from venom_core.skills.mcp.proxy_generator import McpToolMetadata


def _map_json_type(type_name: str) -> str:
    lowered = (type_name or "").lower()
    if lowered.startswith("list") or lowered.startswith("typing.list"):
        return "array"
    if lowered in {"int", "float", "number"}:
        return "number"
    if lowered in {"bool", "boolean"}:
        return "boolean"
    return "string"


class SkillMcpLikeAdapter:
    """Adapts a local BaseSkill instance to MCP-like tool discovery/invocation."""

    def __init__(self, skill: Any):
        self.skill = skill
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._build_tool_index()

    def _build_tool_index(self) -> None:
        for attr_name in dir(self.skill):
            method = getattr(self.skill, attr_name, None)
            if not callable(method):
                continue

            kernel_name = getattr(method, "__kernel_function_name__", None)
            if not kernel_name:
                continue

            parameters = list(getattr(method, "__kernel_function_parameters__", []))
            self._tools[kernel_name] = {
                "method": method,
                "description": getattr(method, "__kernel_function_description__", "")
                or "",
                "parameters": parameters,
            }

    def list_tools(self) -> List[McpToolMetadata]:
        tools: List[McpToolMetadata] = []
        for tool_name, entry in self._tools.items():
            properties: Dict[str, Dict[str, Any]] = {}
            required: List[str] = []
            for param in entry["parameters"]:
                param_name = param["name"]
                schema: Dict[str, Any] = {
                    "type": _map_json_type(str(param.get("type_", "str"))),
                    "description": param.get("description") or "",
                }
                if "default_value" in param:
                    schema["default"] = param["default_value"]
                properties[param_name] = schema
                if param.get("is_required", False):
                    required.append(param_name)

            tools.append(
                McpToolMetadata(
                    name=tool_name,
                    description=entry["description"],
                    input_schema={
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                )
            )
        return sorted(tools, key=lambda item: item.name)

    async def invoke_tool(
        self, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        entry = self._tools[tool_name]
        method = entry["method"]
        args = arguments or {}

        required = {
            param["name"]
            for param in entry["parameters"]
            if param.get("is_required", False)
        }
        missing = sorted(name for name in required if name not in args)
        if missing:
            raise ValueError(f"Missing required arguments for {tool_name}: {missing}")

        accepted_names = {param["name"] for param in entry["parameters"]}
        kwargs = {name: value for name, value in args.items() if name in accepted_names}

        if inspect.iscoroutinefunction(method):
            return await method(**kwargs)
        return method(**kwargs)


class GitSkillMcpAdapter(SkillMcpLikeAdapter):
    """PoC adapter: exposes GitSkill as MCP-like tools."""

    def __init__(self, workspace_root: Optional[str] = None):
        super().__init__(GitSkill(workspace_root=workspace_root))


class FileSkillMcpAdapter(SkillMcpLikeAdapter):
    """PoC adapter: exposes FileSkill as MCP-like tools."""

    def __init__(self, workspace_root: Optional[str] = None):
        super().__init__(FileSkill(workspace_root=workspace_root))


class GoogleCalendarSkillMcpAdapter(SkillMcpLikeAdapter):
    """PoC adapter: exposes GoogleCalendarSkill as MCP-like tools."""

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
        venom_calendar_id: Optional[str] = None,
    ):
        super().__init__(
            GoogleCalendarSkill(
                credentials_path=credentials_path,
                token_path=token_path,
                venom_calendar_id=venom_calendar_id,
            )
        )
