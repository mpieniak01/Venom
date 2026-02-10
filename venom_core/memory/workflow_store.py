"""
Moduł: workflow_store - Magazyn Procedur (Workflow Store).

Przechowuje zmapowane procedury i workflow wygenerowane przez ApprenticeAgent.
Umożliwia edycję i zarządzanie workflow.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.code_generation_utils import escape_string_for_code
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WorkflowStep:
    """Reprezentacja pojedynczego kroku workflow."""

    step_id: int
    action_type: str  # 'click', 'type', 'hotkey', 'wait'
    description: str
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class Workflow:
    """Reprezentacja workflow."""

    workflow_id: str
    name: str
    description: str
    steps: List[WorkflowStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_session_id: Optional[str] = None
    skill_file_path: Optional[str] = None


class WorkflowStore:
    """
    Magazyn Procedur - baza wiedzy proceduralnej.

    Funkcjonalność:
    - Przechowywanie workflow (nazwa -> kroki)
    - Ładowanie/zapisywanie workflow do JSON
    - Edycja kroków workflow
    - Listowanie dostępnych workflow
    - Integracja z DesignerAgent
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja WorkflowStore.

        Args:
            workspace_root: Katalog główny workspace
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT)
        self.workflows_dir = self.workspace_root / "workflows"
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

        # Cache workflow w pamięci
        self.workflows_cache: Dict[str, Workflow] = {}

        logger.info(f"WorkflowStore zainicjalizowany (dir: {self.workflows_dir})")

    def save_workflow(self, workflow: Workflow) -> str:
        """
        Zapisuje workflow do pliku.

        Args:
            workflow: Workflow do zapisania

        Returns:
            Ścieżka do pliku
        """
        # Aktualizuj timestamp
        workflow.updated_at = datetime.now().isoformat()

        # Konwertuj do dict
        workflow_dict = asdict(workflow)

        # Ścieżka do pliku
        workflow_file = self.workflows_dir / f"{workflow.workflow_id}.json"

        # Zapisz
        with open(workflow_file, "w", encoding="utf-8") as f:
            json.dump(workflow_dict, f, indent=2, ensure_ascii=False)

        # Zaktualizuj cache
        self.workflows_cache[workflow.workflow_id] = workflow

        logger.info(f"Workflow zapisany: {workflow.workflow_id}")
        return str(workflow_file)

    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """
        Ładuje workflow z pliku.

        Args:
            workflow_id: ID workflow

        Returns:
            Workflow lub None
        """
        # Sprawdź cache
        if workflow_id in self.workflows_cache:
            return self.workflows_cache[workflow_id]

        # Ścieżka do pliku
        workflow_file = self.workflows_dir / f"{workflow_id}.json"

        if not workflow_file.exists():
            logger.error(f"Workflow nie znaleziony: {workflow_id}")
            return None

        try:
            with open(workflow_file, "r", encoding="utf-8") as f:
                workflow_dict = json.load(f)

            # Konwertuj steps z dict do WorkflowStep
            steps = [
                WorkflowStep(**step_dict)
                for step_dict in workflow_dict.get("steps", [])
            ]
            workflow_dict["steps"] = steps

            workflow = Workflow(**workflow_dict)

            # Dodaj do cache
            self.workflows_cache[workflow_id] = workflow

            logger.info(f"Workflow załadowany: {workflow_id}")
            return workflow

        except Exception as e:
            logger.error(f"Błąd podczas ładowania workflow {workflow_id}: {e}")
            return None

    def list_workflows(self) -> List[Dict[str, Any]]:
        """
        Lista wszystkich workflow.

        Returns:
            Lista dict z podstawowymi informacjami o workflow
        """
        workflows = []

        for workflow_file in self.workflows_dir.glob("*.json"):
            try:
                with open(workflow_file, "r", encoding="utf-8") as f:
                    workflow_dict = json.load(f)

                # Podstawowe info
                workflows.append(
                    {
                        "workflow_id": workflow_dict.get("workflow_id"),
                        "name": workflow_dict.get("name"),
                        "description": workflow_dict.get("description"),
                        "steps_count": len(workflow_dict.get("steps", [])),
                        "created_at": workflow_dict.get("created_at"),
                        "updated_at": workflow_dict.get("updated_at"),
                    }
                )
            except Exception as e:
                logger.error(f"Błąd podczas ładowania workflow {workflow_file}: {e}")
                continue

        return sorted(workflows, key=lambda w: w["updated_at"], reverse=True)

    def delete_workflow(self, workflow_id: str) -> bool:
        """
        Usuwa workflow.

        Args:
            workflow_id: ID workflow

        Returns:
            True jeśli usunięto
        """
        workflow_file = self.workflows_dir / f"{workflow_id}.json"

        if not workflow_file.exists():
            logger.error(f"Workflow nie znaleziony: {workflow_id}")
            return False

        try:
            workflow_file.unlink()

            # Usuń z cache
            if workflow_id in self.workflows_cache:
                del self.workflows_cache[workflow_id]

            logger.info(f"Workflow usunięty: {workflow_id}")
            return True

        except Exception as e:
            logger.error(f"Błąd podczas usuwania workflow {workflow_id}: {e}")
            return False

    def update_step(
        self, workflow_id: str, step_id: int, updates: Dict[str, Any]
    ) -> bool:
        """
        Aktualizuje pojedynczy krok workflow.

        Args:
            workflow_id: ID workflow
            step_id: ID kroku
            updates: Słownik z aktualizacjami

        Returns:
            True jeśli zaktualizowano
        """
        workflow = self.load_workflow(workflow_id)
        if not workflow:
            return False

        # Znajdź krok
        step = next((s for s in workflow.steps if s.step_id == step_id), None)
        if not step:
            logger.error(f"Krok {step_id} nie znaleziony w workflow {workflow_id}")
            return False

        # Aktualizuj
        for key, value in updates.items():
            if hasattr(step, key):
                setattr(step, key, value)

        # Zapisz
        self.save_workflow(workflow)

        logger.info(f"Zaktualizowano krok {step_id} w workflow {workflow_id}")
        return True

    def add_step(
        self, workflow_id: str, step: WorkflowStep, position: Optional[int] = None
    ) -> bool:
        """
        Dodaje nowy krok do workflow.

        Args:
            workflow_id: ID workflow
            step: Krok do dodania
            position: Opcjonalna pozycja (None = na końcu)

        Returns:
            True jeśli dodano
        """
        workflow = self.load_workflow(workflow_id)
        if not workflow:
            return False

        # Ustaw step_id
        if workflow.steps:
            step.step_id = max(s.step_id for s in workflow.steps) + 1
        else:
            step.step_id = 1

        # Dodaj na pozycji
        if position is not None and 0 <= position < len(workflow.steps):
            workflow.steps.insert(position, step)
        else:
            workflow.steps.append(step)

        # Zapisz
        self.save_workflow(workflow)

        logger.info(f"Dodano krok {step.step_id} do workflow {workflow_id}")
        return True

    def remove_step(self, workflow_id: str, step_id: int) -> bool:
        """
        Usuwa krok z workflow.

        Args:
            workflow_id: ID workflow
            step_id: ID kroku do usunięcia

        Returns:
            True jeśli usunięto
        """
        workflow = self.load_workflow(workflow_id)
        if not workflow:
            return False

        # Znajdź i usuń
        original_length = len(workflow.steps)
        workflow.steps = [s for s in workflow.steps if s.step_id != step_id]

        if len(workflow.steps) == original_length:
            logger.error(f"Krok {step_id} nie znaleziony w workflow {workflow_id}")
            return False

        # Zapisz
        self.save_workflow(workflow)

        logger.info(f"Usunięto krok {step_id} z workflow {workflow_id}")
        return True

    def export_to_python(
        self, workflow_id: str, output_path: Optional[Path] = None
    ) -> Optional[str]:
        """
        Eksportuje workflow do skryptu Python.

        Args:
            workflow_id: ID workflow
            output_path: Opcjonalna ścieżka wyjściowa

        Returns:
            Ścieżka do pliku lub None
        """
        workflow = self.load_workflow(workflow_id)
        if not workflow:
            return None

        # Walidacja workflow_id jako bezpiecznego identyfikatora Python
        safe_function_name = self._sanitize_identifier(workflow.workflow_id)

        # Bezpiecznie eskejpuj wartości dla generowanego kodu
        workflow_name_repr = escape_string_for_code(workflow.name)
        workflow_desc_repr = escape_string_for_code(workflow.description)

        # Generuj kod
        code = f'''"""
Workflow: {workflow.name}
{workflow.description}

Wygenerowany automatycznie z WorkflowStore.
"""

from venom_core.agents.ghost_agent import GhostAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def {safe_function_name}(ghost_agent: GhostAgent, **kwargs):
    """
    {workflow.description}

    Args:
        ghost_agent: Instancja GhostAgent
        **kwargs: Parametry workflow
    """
    logger.info("Rozpoczynam workflow: %s", {workflow_name_repr})
    logger.info("Opis workflow: %s", {workflow_desc_repr})

'''

        for step in workflow.steps:
            if not step.enabled:
                desc_repr = escape_string_for_code(step.description)
                code += f"    # DISABLED: Krok {step.step_id}: {desc_repr}\n"
                continue

            desc_repr = escape_string_for_code(step.description)
            code += f"    # Krok {step.step_id}: {desc_repr}\n"

            if step.action_type == "click":
                element_desc = step.params.get("element_description", "unknown")
                element_desc_repr = escape_string_for_code(element_desc)
                fallback_coords = step.params.get("fallback_coords", {})
                x = fallback_coords.get("x", 0)
                y = fallback_coords.get("y", 0)

                code += "    await ghost_agent.vision_click(\n"
                code += f"        description={element_desc_repr},\n"
                code += f"        fallback_coords=({x}, {y})\n"
                code += "    )\n"

            elif step.action_type == "type":
                text = step.params.get("text", "")
                text_repr = escape_string_for_code(text)
                param_name = step.params.get("param_name", "text")
                # Sanityzuj param_name - musi być poprawnym identyfikatorem Python
                param_name_safe = self._sanitize_identifier(param_name)

                code += f'    text = kwargs.get("{param_name_safe}", {text_repr})\n'
                code += "    await ghost_agent.input_skill.keyboard_type(text=text)\n"

            elif step.action_type == "hotkey":
                keys = step.params.get("keys", [])
                code += f"    await ghost_agent.input_skill.keyboard_hotkey({keys})\n"

            elif step.action_type == "wait":
                duration = step.params.get("duration", 1.0)
                code += f"    await ghost_agent._wait({duration})\n"

            code += "\n"

        code += f'    logger.info("Workflow zakończony: %s", {workflow_name_repr})\n'
        # Użyj repr pojedynczo dla bezpieczeństwa, ale bez podwójnego eskejpowania
        return_msg = f"✅ Workflow {workflow.name} wykonany pomyślnie"
        code += f"    return {repr(return_msg)}\n"

        # Zapisz do pliku
        if not output_path:
            output_path = (
                self.workspace_root / "custom_skills" / f"{workflow.workflow_id}.py"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code, encoding="utf-8")

        logger.info(f"Workflow wyeksportowany do: {output_path}")
        return str(output_path)

    def search_workflows(self, query: str) -> List[Dict[str, Any]]:
        """
        Wyszukuje workflow po nazwie lub opisie.

        Args:
            query: Zapytanie

        Returns:
            Lista pasujących workflow
        """
        all_workflows = self.list_workflows()
        query_lower = query.lower()

        return [
            w
            for w in all_workflows
            if query_lower in w["name"].lower()
            or query_lower in w["description"].lower()
        ]

    def _sanitize_identifier(self, identifier: str) -> str:
        """
        Sanitizuje identyfikator aby był bezpiecznym identyfikatorem Python.

        Args:
            identifier: Identyfikator do sanityzacji

        Returns:
            Bezpieczny identyfikator (tylko alfanumeryczne znaki i _)
        """
        # Najpierw neutralizuj próby przejścia do katalogu nadrzędnego
        identifier = re.sub(r"\.\.[\\/]", "____", identifier)
        identifier = identifier.replace("..", "____")

        # Zamień separatory ścieżek na podkreślenia
        identifier = re.sub(r"[\\/]", "_", identifier)

        # Usuń pozostałe niedozwolone znaki, zostaw tylko alfanumeryczne i _
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", identifier)

        # Upewnij się że zaczyna się od litery lub _
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized

        # Jeśli pusty, użyj domyślnej nazwy
        if not sanitized:
            sanitized = "workflow"

        return sanitized
