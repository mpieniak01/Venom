"""Testy dla DreamEngine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.dream_engine import DreamEngine, DreamState
from venom_core.simulation.scenario_weaver import ScenarioSpec


class TestDreamEngine:
    """Testy dla DreamEngine."""

    @pytest.fixture
    def mock_components(self, tmp_path):
        """Mock komponentów wymaganych przez DreamEngine."""
        kernel = MagicMock()
        graph_rag = MagicMock()
        lessons_store = MagicMock()
        energy_manager = MagicMock()
        scenario_weaver = MagicMock()
        coder_agent = MagicMock()
        guardian_agent = MagicMock()

        # Mock podstawowych metod
        energy_manager.register_alert_callback = MagicMock()
        energy_manager.set_low_priority = MagicMock(return_value=True)

        # Ustaw temporary output dir
        with patch("venom_core.core.dream_engine.SETTINGS") as mock_settings:
            mock_settings.DREAMING_OUTPUT_DIR = str(tmp_path / "synthetic_training")
            mock_settings.DREAMING_MAX_SCENARIOS = 5
            mock_settings.DREAMING_SCENARIO_COMPLEXITY = "medium"
            mock_settings.DREAMING_VALIDATION_STRICT = True
            mock_settings.DREAMING_PROCESS_PRIORITY = 19

            return {
                "kernel": kernel,
                "graph_rag": graph_rag,
                "lessons_store": lessons_store,
                "energy_manager": energy_manager,
                "scenario_weaver": scenario_weaver,
                "coder_agent": coder_agent,
                "guardian_agent": guardian_agent,
            }

    @pytest.fixture
    def dream_engine(self, mock_components, tmp_path):
        """Fixture DreamEngine z mockami."""
        with patch("venom_core.core.dream_engine.SETTINGS") as mock_settings:
            mock_settings.DREAMING_OUTPUT_DIR = str(tmp_path / "synthetic_training")
            mock_settings.DREAMING_MAX_SCENARIOS = 5
            mock_settings.DREAMING_SCENARIO_COMPLEXITY = "medium"
            mock_settings.DREAMING_VALIDATION_STRICT = True
            mock_settings.DREAMING_PROCESS_PRIORITY = 19

            engine = DreamEngine(
                kernel=mock_components["kernel"],
                graph_rag=mock_components["graph_rag"],
                lessons_store=mock_components["lessons_store"],
                energy_manager=mock_components["energy_manager"],
                scenario_weaver=mock_components["scenario_weaver"],
                coder_agent=mock_components["coder_agent"],
                guardian_agent=mock_components["guardian_agent"],
            )
            return engine

    def test_initialization(self, dream_engine, mock_components):
        """Test inicjalizacji DreamEngine."""
        assert dream_engine.state == DreamState.IDLE
        assert dream_engine.current_session_id is None
        assert dream_engine.dreams_count == 0
        assert dream_engine.successful_dreams == 0

        # Sprawdź czy callback zarejestrowany
        mock_components["energy_manager"].register_alert_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_enter_rem_phase_no_knowledge(self, dream_engine, mock_components):
        """Test enter_rem_phase gdy brak wiedzy w GraphRAG."""
        # Mock get_knowledge_clusters zwraca pustą listę
        with patch.object(
            dream_engine, "_get_knowledge_clusters", new_callable=AsyncMock
        ) as mock_get_knowledge:
            mock_get_knowledge.return_value = []

            report = await dream_engine.enter_rem_phase()

            assert report["status"] == "no_knowledge"
            assert report["dreams_attempted"] == 0
            assert report["dreams_successful"] == 0
            assert dream_engine.state == DreamState.IDLE

    @pytest.mark.asyncio
    async def test_enter_rem_phase_success(self, dream_engine, mock_components):
        """Test enter_rem_phase - sukces."""
        # Mock get_knowledge_clusters
        with patch.object(
            dream_engine, "_get_knowledge_clusters", new_callable=AsyncMock
        ) as mock_get_knowledge:
            mock_get_knowledge.return_value = ["Fragment 1", "Fragment 2"]

            # Mock scenario_weaver
            mock_scenario = ScenarioSpec(
                title="Test Scenario",
                description="Test",
                task_prompt="Do something",
                test_cases=["test1"],
                difficulty="medium",
                libraries=["pytest"],
                metadata={},
            )
            mock_components["scenario_weaver"].weave_multiple_scenarios = AsyncMock(
                return_value=[mock_scenario, mock_scenario]
            )

            # Mock dream_scenario
            with patch.object(
                dream_engine, "_dream_scenario", new_callable=AsyncMock
            ) as mock_dream:
                mock_dream.return_value = {
                    "success": True,
                    "scenario": "Test Scenario",
                    "dream_id": "test123",
                }

                report = await dream_engine.enter_rem_phase(max_scenarios=2)

                assert report["status"] == "completed"
                assert report["dreams_attempted"] == 2
                assert report["dreams_successful"] == 2
                assert report["success_rate"] == pytest.approx(1.0)
                assert dream_engine.state == DreamState.IDLE

    @pytest.mark.asyncio
    async def test_enter_rem_phase_interrupted(self, dream_engine, mock_components):
        """Test enter_rem_phase - przerwanie."""
        with patch.object(
            dream_engine, "_get_knowledge_clusters", new_callable=AsyncMock
        ) as mock_get_knowledge:
            mock_get_knowledge.return_value = ["Fragment 1"]

            mock_scenario = ScenarioSpec(
                title="Test",
                description="Test",
                task_prompt="Task",
                test_cases=["test"],
                difficulty="medium",
                libraries=["lib"],
                metadata={},
            )
            mock_components["scenario_weaver"].weave_multiple_scenarios = AsyncMock(
                return_value=[mock_scenario]
            )

            # Mock dream_scenario - ustaw state na INTERRUPTED
            def interrupt_dream(scenario):
                dream_engine.state = DreamState.INTERRUPTED
                return {"success": False, "scenario": "Test"}

            with patch.object(
                dream_engine, "_dream_scenario", side_effect=interrupt_dream
            ):
                report = await dream_engine.enter_rem_phase()

                assert report["status"] == "interrupted"
                assert dream_engine.state == DreamState.IDLE

    @pytest.mark.asyncio
    async def test_get_knowledge_clusters_empty_graph(
        self, dream_engine, mock_components
    ):
        """Test pobierania klastrów wiedzy - pusty graf."""
        mock_components["graph_rag"].get_stats.return_value = {"total_nodes": 0}

        fragments = await dream_engine._get_knowledge_clusters(5)

        assert len(fragments) == 0

    @pytest.mark.asyncio
    async def test_get_knowledge_clusters_success(self, dream_engine, mock_components):
        """Test pobierania klastrów wiedzy - sukces."""
        # Mock graph store
        mock_graph = MagicMock()
        mock_graph.degree.return_value = [
            ("node1", 10),
            ("node2", 8),
            ("node3", 5),
        ]
        mock_graph.nodes.get.return_value = {
            "type": "Module",
            "description": "Test module",
        }
        mock_graph.neighbors.return_value = ["related1", "related2"]

        mock_components["graph_rag"].get_stats.return_value = {"total_nodes": 3}
        mock_components["graph_rag"].graph_store.graph = mock_graph

        fragments = await dream_engine._get_knowledge_clusters(2)

        assert len(fragments) > 0
        assert all("Entity:" in f for f in fragments)

    def test_extract_code_from_response_with_python_block(self, dream_engine):
        """Test wyciągania kodu z odpowiedzi LLM - blok ```python```."""
        response = """Here is the code:
```python
def hello():
    print("Hello")
```
That's it!"""

        code = dream_engine._extract_code_from_response(response)

        assert "def hello():" in code
        assert 'print("Hello")' in code
        assert "Here is the code:" not in code

    def test_extract_code_from_response_with_generic_block(self, dream_engine):
        """Test wyciągania kodu - blok ```"""
        response = """Code:
```
x = 42
print(x)
```"""

        code = dream_engine._extract_code_from_response(response)

        assert "x = 42" in code
        assert "Code:" not in code

    def test_extract_code_from_response_no_blocks(self, dream_engine):
        """Test wyciągania kodu - brak bloków."""
        response = "x = 42\nprint(x)"

        code = dream_engine._extract_code_from_response(response)

        assert code == "x = 42\nprint(x)"

    def test_handle_wake_up(self, dream_engine):
        """Test callbacka wake_up."""
        dream_engine.state = DreamState.DREAMING

        dream_engine._handle_wake_up()

        assert dream_engine.state == DreamState.INTERRUPTED

    def test_handle_wake_up_when_idle(self, dream_engine):
        """Test callbacka wake_up gdy IDLE."""
        dream_engine.state = DreamState.IDLE

        dream_engine._handle_wake_up()

        # State nie powinien się zmienić
        assert dream_engine.state == DreamState.IDLE

    @pytest.mark.asyncio
    async def test_dream_scenario_without_strict_validation(
        self, dream_engine, mock_components, tmp_path
    ):
        """Test _dream_scenario gdy DREAMING_VALIDATION_STRICT jest False."""
        with patch("venom_core.core.dream_engine.SETTINGS") as mock_settings:
            mock_settings.DREAMING_VALIDATION_STRICT = False
            mock_settings.DREAMING_OUTPUT_DIR = str(tmp_path / "synthetic_training")

            # Mock scenario
            scenario = ScenarioSpec(
                title="Test No Validation",
                description="Test without validation",
                task_prompt="Write code",
                test_cases=["test1"],
                difficulty="simple",
                libraries=["lib"],
                metadata={},
            )

            # Mock coder response
            mock_components["coder_agent"].process = AsyncMock(
                return_value="```python\nprint('test')\n```"
            )

            # Set output dir
            dream_engine.output_dir = tmp_path / "synthetic_training"
            dream_engine.output_dir.mkdir(parents=True, exist_ok=True)

            # Run dream scenario
            result = await dream_engine._dream_scenario(scenario)

            # Powinien zapisać bez walidacji
            assert result["success"] is True
            # Guardian nie powinien być wywołany
            mock_components["guardian_agent"].process.assert_not_called()

    def test_get_statistics(self, dream_engine, tmp_path):
        """Test pobierania statystyk."""
        dream_engine.dreams_count = 10
        dream_engine.successful_dreams = 7

        # Utwórz kilka plików dream
        output_dir = tmp_path / "synthetic_training"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "dream_001.py").write_text("# Dream 1")
        (output_dir / "dream_002.py").write_text("# Dream 2")

        # Ustaw output_dir w engine
        dream_engine.output_dir = output_dir

        stats = dream_engine.get_statistics()

        assert stats["state"] == DreamState.IDLE
        assert stats["total_dreams"] == 10
        assert stats["successful_dreams"] == 7
        assert stats["success_rate"] == pytest.approx(0.7)
        assert stats["saved_dreams_count"] == 2
