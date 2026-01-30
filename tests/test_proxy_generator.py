import pytest

from venom_core.skills.mcp.proxy_generator import McpProxyGenerator, McpToolMetadata


class TestMcpProxyGenerator:
    @pytest.fixture
    def generator(self):
        return McpProxyGenerator()

    def test_generate_simple_skill(self, generator):
        meta = McpToolMetadata(
            name="calculator",
            description="A simple calculator",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "string", "description": "First number"},
                    "b": {"type": "string", "description": "Second number"},
                },
            },
        )

        code = generator.generate_skill_code(
            skill_name="CalcSkill",
            server_command="python",
            server_args=["server.py"],
            env_vars={"TEST": "1"},
            tools=[meta],
        )

        # Assertions
        assert "class CalcSkill(BaseSkill):" in code
        assert 'command="python"' in code or "command='python'" in code
        assert '"TEST": "1"' in code or "'TEST': '1'" in code

        # Check method generation
        assert "@kernel_function" in code
        assert 'name="calculator"' in code
        assert 'description="A simple calculator"' in code
        assert "async def calculator(self, a: str = None, b: str = None)" in code

    def test_sanitize_names(self, generator):
        meta = McpToolMetadata(
            name="deep-research", description="Deep.", input_schema={}
        )

        code = generator.generate_skill_code(
            skill_name="ResearchSkill",
            server_command="cmd",
            server_args=[],
            env_vars={},
            tools=[meta],
        )

        assert 'name="deep_research"' in code
        assert "async def deep_research(self)" in code
