"""Testy dla ScenarioWeaver."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.simulation.scenario_weaver import ScenarioSpec, ScenarioWeaver


class TestScenarioSpec:
    """Testy dla ScenarioSpec."""

    def test_scenario_spec_creation(self):
        """Test tworzenia specyfikacji scenariusza."""
        spec = ScenarioSpec(
            title="Test Scenario",
            description="Test description",
            task_prompt="Do something",
            test_cases=["test1", "test2"],
            difficulty="medium",
            libraries=["pytest", "asyncio"],
            metadata={"key": "value"},
        )

        assert spec.title == "Test Scenario"
        assert spec.description == "Test description"
        assert spec.task_prompt == "Do something"
        assert len(spec.test_cases) == 2
        assert spec.difficulty == "medium"
        assert len(spec.libraries) == 2
        assert spec.metadata["key"] == "value"


class TestScenarioWeaver:
    """Testy dla ScenarioWeaver."""

    @pytest.fixture
    def mock_kernel(self):
        """Mock Semantic Kernel."""
        kernel = MagicMock()
        chat_service = MagicMock()
        kernel.get_service.return_value = chat_service
        return kernel

    def test_initialization(self, mock_kernel):
        """Test inicjalizacji ScenarioWeaver."""
        weaver = ScenarioWeaver(mock_kernel, complexity="complex")

        assert weaver.kernel == mock_kernel
        assert weaver.complexity == "complex"
        assert weaver.execution_settings.temperature == pytest.approx(0.8)

    def test_initialization_default_complexity(self, mock_kernel):
        """Test inicjalizacji z domyślną złożonością."""
        weaver = ScenarioWeaver(mock_kernel)

        assert weaver.complexity in ["simple", "medium", "complex"]

    @pytest.mark.asyncio
    async def test_weave_scenario_success(self, mock_kernel):
        """Test generowania scenariusza - sukces."""
        # Mock odpowiedź LLM
        mock_response = MagicMock()
        mock_response.__str__.return_value = """```json
{
  "title": "Test Scenario",
  "description": "A test description",
  "task_prompt": "Implement something",
  "test_cases": ["test1", "test2"],
  "difficulty": "medium",
  "libraries": ["pytest"]
}
```"""

        mock_kernel.get_service.return_value.get_chat_message_contents = AsyncMock(
            return_value=[mock_response]
        )

        weaver = ScenarioWeaver(mock_kernel, complexity="medium")

        scenario = await weaver.weave_scenario(
            knowledge_fragment="Some documentation about pytest"
        )

        assert isinstance(scenario, ScenarioSpec)
        assert scenario.title == "Test Scenario"
        assert scenario.description == "A test description"
        assert scenario.difficulty == "medium"
        assert len(scenario.test_cases) == 2
        assert "pytest" in scenario.libraries

    @pytest.mark.asyncio
    async def test_weave_scenario_with_libraries(self, mock_kernel):
        """Test generowania scenariusza z podanymi bibliotekami."""
        mock_response = MagicMock()
        mock_response.__str__.return_value = """```json
{
  "title": "Custom Libraries Test",
  "description": "Using custom libs",
  "task_prompt": "Test task",
  "test_cases": ["test1"],
  "difficulty": "simple",
  "libraries": ["numpy", "pandas"]
}
```"""

        mock_kernel.get_service.return_value.get_chat_message_contents = AsyncMock(
            return_value=[mock_response]
        )

        weaver = ScenarioWeaver(mock_kernel)

        scenario = await weaver.weave_scenario(
            knowledge_fragment="Docs", libraries=["numpy", "pandas"]
        )

        assert "numpy" in scenario.libraries
        assert "pandas" in scenario.libraries

    @pytest.mark.asyncio
    async def test_weave_scenario_json_parse_error(self, mock_kernel):
        """Test generowania scenariusza - błąd parsowania JSON."""
        # Mock odpowiedź z niepoprawnym JSON
        mock_response = MagicMock()
        mock_response.__str__.return_value = "This is not valid JSON"

        mock_kernel.get_service.return_value.get_chat_message_contents = AsyncMock(
            return_value=[mock_response]
        )

        weaver = ScenarioWeaver(mock_kernel)

        # Powinien zwrócić fallback scenariusz
        scenario = await weaver.weave_scenario(knowledge_fragment="Some docs")

        assert isinstance(scenario, ScenarioSpec)
        assert scenario.metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_weave_scenario_llm_error(self, mock_kernel):
        """Test generowania scenariusza - błąd LLM."""
        # Mock wywołuje exception
        mock_kernel.get_service.return_value.get_chat_message_contents = AsyncMock(
            side_effect=Exception("LLM error")
        )

        weaver = ScenarioWeaver(mock_kernel)

        # Powinien zwrócić fallback scenariusz
        scenario = await weaver.weave_scenario(knowledge_fragment="Some docs")

        assert isinstance(scenario, ScenarioSpec)
        assert scenario.metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_weave_multiple_scenarios(self, mock_kernel):
        """Test generowania wielu scenariuszy."""
        # Mock odpowiedzi LLM
        mock_response = MagicMock()
        mock_response.__str__.return_value = """```json
{
  "title": "Scenario",
  "description": "Description",
  "task_prompt": "Task",
  "test_cases": ["test"],
  "difficulty": "medium",
  "libraries": ["lib"]
}
```"""

        mock_kernel.get_service.return_value.get_chat_message_contents = AsyncMock(
            return_value=[mock_response]
        )

        weaver = ScenarioWeaver(mock_kernel)

        fragments = ["Fragment 1", "Fragment 2", "Fragment 3"]

        scenarios = await weaver.weave_multiple_scenarios(fragments, count=3)

        assert len(scenarios) == 3
        for scenario in scenarios:
            assert isinstance(scenario, ScenarioSpec)

    @pytest.mark.asyncio
    async def test_weave_multiple_scenarios_limited(self, mock_kernel):
        """Test generowania wielu scenariuszy - limit mniejszy niż fragmenty."""
        mock_response = MagicMock()
        mock_response.__str__.return_value = """```json
{
  "title": "Scenario",
  "description": "Description",
  "task_prompt": "Task",
  "test_cases": ["test"],
  "difficulty": "medium",
  "libraries": ["lib"]
}
```"""

        mock_kernel.get_service.return_value.get_chat_message_contents = AsyncMock(
            return_value=[mock_response]
        )

        weaver = ScenarioWeaver(mock_kernel)

        fragments = [
            "Fragment 1",
            "Fragment 2",
            "Fragment 3",
            "Fragment 4",
            "Fragment 5",
        ]

        # Generuj tylko 2 scenariusze z 5 fragmentów
        scenarios = await weaver.weave_multiple_scenarios(fragments, count=2)

        assert len(scenarios) == 2

    def test_create_fallback_scenario(self, mock_kernel):
        """Test tworzenia fallback scenariusza."""
        weaver = ScenarioWeaver(mock_kernel)

        scenario = weaver._create_fallback_scenario(
            knowledge_fragment="Documentation about Pandas library functions",
            difficulty="simple",
        )

        assert isinstance(scenario, ScenarioSpec)
        assert scenario.difficulty == "simple"
        assert scenario.metadata.get("fallback") is True
        assert len(scenario.test_cases) > 0

    def test_create_fallback_scenario_without_keywords(self, mock_kernel):
        weaver = ScenarioWeaver(mock_kernel)
        scenario = weaver._create_fallback_scenario("a, bb, c.", difficulty="medium")
        assert scenario.metadata.get("fallback") is True
        assert scenario.title.startswith("Eksploracja")
        assert scenario.libraries
