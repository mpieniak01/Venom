"""MCP-like adapter for local Venom skills (PoC for convergence path)."""

from __future__ import annotations

import copy
import inspect
from typing import Any, Dict, List, Optional

from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.execution.skills.google_calendar_skill import GoogleCalendarSkill
from venom_core.skills.mcp.proxy_generator import McpToolMetadata


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

            metadata = getattr(method, "__venom_tool__", None)
            if not metadata:
                continue
            from agent_framework import FunctionTool

            tool = FunctionTool(
                name=metadata["name"], description=metadata["description"], func=method
            )
            self._tools[tool.name] = {
                "method": method,
                "description": metadata["description"],
                "schema": tool.parameters(),
                "input_model": tool.input_model,
            }

    def list_tools(self) -> List[McpToolMetadata]:
        tools = [
            McpToolMetadata(
                name=name,
                description=entry["description"],
                input_schema=copy.deepcopy(entry["schema"]),
            )
            for name, entry in self._tools.items()
        ]
        return sorted(tools, key=lambda item: item.name)

    async def invoke_tool(
        self, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        entry = self._tools[tool_name]
        method = entry["method"]
        args = arguments or {}

        schema = entry["schema"]
        required = set(schema.get("required", []))
        missing = sorted(name for name in required if name not in args)
        if missing:
            raise ValueError(f"Missing required arguments for {tool_name}: {missing}")
        accepted_names = set(schema.get("properties", {}))
        kwargs = {name: value for name, value in args.items() if name in accepted_names}
        model = entry["input_model"]
        if model is not None:
            kwargs = model.model_validate(kwargs).model_dump(exclude_unset=True)

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
