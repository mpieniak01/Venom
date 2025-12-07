"""Testy dla PromptManager."""

import pytest
import yaml

from venom_core.core.prompt_manager import PromptManager


class TestPromptManager:
    """Testy dla klasy PromptManager."""

    @pytest.fixture
    def temp_prompts_dir(self, tmp_path):
        """Fixture: tymczasowy katalog na prompty."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        return prompts_dir

    @pytest.fixture
    def sample_prompt_file(self, temp_prompts_dir):
        """Fixture: przykładowy plik promptu."""
        prompt_data = {
            "agent": "test_agent",
            "version": "1.0",
            "parameters": {"temperature": 0.5},
            "template": "You are a test agent.",
        }
        prompt_file = temp_prompts_dir / "test_agent.yaml"
        with open(prompt_file, "w") as f:
            yaml.dump(prompt_data, f)
        return prompt_file

    def test_initialization(self, temp_prompts_dir):
        """Test inicjalizacji menedżera."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        assert manager.prompts_dir == temp_prompts_dir
        assert len(manager.prompts_cache) == 0

    def test_load_prompt_success(self, temp_prompts_dir, sample_prompt_file):
        """Test załadowania promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        prompt_data = manager.load_prompt("test_agent")

        assert prompt_data["agent"] == "test_agent"
        assert prompt_data["version"] == "1.0"
        assert prompt_data["template"] == "You are a test agent."
        assert "_loaded_at" in prompt_data

    def test_load_prompt_not_found(self, temp_prompts_dir):
        """Test ładowania nieistniejącego promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        with pytest.raises(FileNotFoundError):
            manager.load_prompt("nonexistent_agent")

    def test_get_prompt_success(self, temp_prompts_dir, sample_prompt_file):
        """Test pobrania template promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        template = manager.get_prompt("test_agent")
        assert template == "You are a test agent."

    def test_get_prompt_with_fallback(self, temp_prompts_dir):
        """Test fallback promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        fallback = "Fallback prompt"
        template = manager.get_prompt("nonexistent", fallback=fallback)
        assert template == fallback

    def test_get_parameters(self, temp_prompts_dir, sample_prompt_file):
        """Test pobrania parametrów promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        params = manager.get_parameters("test_agent")
        assert params["temperature"] == 0.5

    def test_get_parameters_nonexistent(self, temp_prompts_dir):
        """Test pobrania parametrów nieistniejącego promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))
        params = manager.get_parameters("nonexistent")
        assert params == {}

    def test_cache_mechanism(self, temp_prompts_dir, sample_prompt_file):
        """Test mechanizmu cache."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Pierwsze załadowanie
        manager.load_prompt("test_agent")
        assert "test_agent" in manager.prompts_cache

        # Drugie załadowanie - powinno użyć cache
        manager.load_prompt("test_agent")
        assert len(manager.prompts_cache) == 1

    def test_hot_reload(self, temp_prompts_dir, sample_prompt_file):
        """Test hot-reload promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Załaduj prompt
        manager.load_prompt("test_agent")

        # Zmień plik
        prompt_data = {
            "agent": "test_agent",
            "version": "2.0",
            "parameters": {"temperature": 0.7},
            "template": "Updated template",
        }
        with open(sample_prompt_file, "w") as f:
            yaml.dump(prompt_data, f)

        # Hot reload
        success = manager.hot_reload("test_agent")
        assert success is True

        # Sprawdź czy załadowano nową wersję
        prompt = manager.load_prompt("test_agent")
        assert prompt["version"] == "2.0"
        assert prompt["template"] == "Updated template"

    def test_reload_all(self, temp_prompts_dir):
        """Test przeładowania wszystkich promptów."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Stwórz kilka promptów
        for i in range(3):
            prompt_data = {
                "agent": f"agent_{i}",
                "version": "1.0",
                "parameters": {},
                "template": f"Agent {i}",
            }
            prompt_file = temp_prompts_dir / f"agent_{i}.yaml"
            with open(prompt_file, "w") as f:
                yaml.dump(prompt_data, f)

            manager.load_prompt(f"agent_{i}")

        # Przeładuj wszystkie
        count = manager.reload_all()
        assert count == 3

    def test_list_prompts(self, temp_prompts_dir):
        """Test listowania dostępnych promptów."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Stwórz kilka promptów
        for i in range(3):
            prompt_data = {"agent": f"agent_{i}", "template": "Test"}
            prompt_file = temp_prompts_dir / f"agent_{i}.yaml"
            with open(prompt_file, "w") as f:
                yaml.dump(prompt_data, f)

        prompts = manager.list_prompts()
        assert len(prompts) == 3
        assert "agent_0" in prompts
        assert "agent_1" in prompts
        assert "agent_2" in prompts

    def test_create_prompt_template(self, temp_prompts_dir):
        """Test tworzenia nowego szablonu promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        success = manager.create_prompt_template(
            agent_name="new_agent",
            template="New agent template",
            version="1.5",
            parameters={"temperature": 0.8},
        )

        assert success is True

        # Sprawdź czy plik został utworzony
        prompt_file = temp_prompts_dir / "new_agent.yaml"
        assert prompt_file.exists()

        # Sprawdź zawartość
        with open(prompt_file, "r") as f:
            data = yaml.safe_load(f)
        assert data["agent"] == "new_agent"
        assert data["version"] == "1.5"
        assert data["template"] == "New agent template"

    def test_create_prompt_template_already_exists(
        self, temp_prompts_dir, sample_prompt_file
    ):
        """Test próby utworzenia istniejącego promptu."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        success = manager.create_prompt_template(
            agent_name="test_agent", template="Should not create"
        )

        assert success is False

    def test_get_cache_status(self, temp_prompts_dir, sample_prompt_file):
        """Test statusu cache."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Załaduj prompt
        manager.load_prompt("test_agent")

        status = manager.get_cache_status()
        assert status["cached_prompts"] == 1
        assert "test_agent" in status["cache_entries"]
        assert "test_agent" in status["available_prompts"]

    def test_invalid_yaml(self, temp_prompts_dir):
        """Test obsługi nieprawidłowego YAML."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Stwórz nieprawidłowy plik YAML
        invalid_file = temp_prompts_dir / "invalid.yaml"
        with open(invalid_file, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(ValueError):
            manager.load_prompt("invalid")

    def test_missing_template_field(self, temp_prompts_dir):
        """Test obsługi braku wymaganego pola template."""
        manager = PromptManager(prompts_dir=str(temp_prompts_dir))

        # Stwórz plik bez pola template
        prompt_data = {"agent": "incomplete", "version": "1.0"}
        prompt_file = temp_prompts_dir / "incomplete.yaml"
        with open(prompt_file, "w") as f:
            yaml.dump(prompt_data, f)

        with pytest.raises(ValueError, match="template"):
            manager.load_prompt("incomplete")
