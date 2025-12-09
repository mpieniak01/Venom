"""Moduł: skill_manager - dynamiczne zarządzanie umiejętnościami (plugins)."""

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from semantic_kernel import Kernel

from venom_core.config import SETTINGS
from venom_core.utils import helpers
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class SkillValidationError(Exception):
    """Wyjątek rzucany gdy skill nie przechodzi walidacji."""

    pass


class SkillManager:
    """
    Menedżer Umiejętności - zarządza cyklem życia dynamicznych pluginów.

    Odpowiada za:
    - Dynamiczne ładowanie pluginów z katalogu custom/
    - Hot-reload pluginów bez restartu aplikacji
    - Walidację bezpieczeństwa pluginów przed załadowaniem
    - Rejestrację pluginów w Semantic Kernel
    """

    def __init__(
        self,
        kernel: Kernel,
        custom_skills_dir: Optional[str] = None,
        event_broadcaster: Optional[Any] = None,
    ):
        """
        Inicjalizacja SkillManager.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            custom_skills_dir: Ścieżka do katalogu z custom skills
                              (domyślnie venom_core/execution/skills/custom/)
            event_broadcaster: Opcjonalny broadcaster eventów WebSocket (EventBroadcaster)
        """
        self.kernel = kernel
        self.event_broadcaster = event_broadcaster

        # Ustaw ścieżkę do katalogu custom skills
        if custom_skills_dir:
            self.custom_skills_dir = Path(custom_skills_dir).resolve()
        else:
            # Domyślna ścieżka: znajdź katalog względem workspace/custom
            # (SkillManager oczekuje że FileSkill zapisuje do workspace/custom)
            workspace_root = Path(SETTINGS.WORKSPACE_ROOT).resolve()
            self.custom_skills_dir = workspace_root / "custom"

        # Upewnij się że katalog istnieje
        self.custom_skills_dir.mkdir(parents=True, exist_ok=True)

        # Rejestr załadowanych skills: {skill_name: module}
        self.loaded_skills: Dict[str, Any] = {}

        logger.info(
            f"SkillManager zainicjalizowany z katalogiem: {self.custom_skills_dir}"
        )

    def load_skills_from_dir(self, path: Optional[str] = None) -> List[str]:
        """
        Dynamicznie importuje wszystkie pliki .py z katalogu custom skills.

        Args:
            path: Opcjonalna ścieżka do katalogu (domyślnie self.custom_skills_dir)

        Returns:
            Lista nazw załadowanych skills

        Raises:
            SkillValidationError: Jeśli skill nie przechodzi walidacji
        """
        target_dir = Path(path) if path else self.custom_skills_dir
        loaded_skills = []

        logger.info(f"Szukam skills w katalogu: {target_dir}")

        # Znajdź wszystkie pliki .py (ignoruj __init__.py i pliki zaczynające się od _)
        skill_files = [
            f
            for f in target_dir.glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith("_")
        ]

        if not skill_files:
            logger.info(f"Nie znaleziono żadnych skills w {target_dir}")
            return loaded_skills

        for skill_file in skill_files:
            try:
                logger.info(f"Próba załadowania skill: {skill_file.name}")

                # Waliduj plik przed załadowaniem
                self.validate_skill(str(skill_file))

                # Załaduj moduł
                skill_name = skill_file.stem  # Nazwa bez rozszerzenia
                module = self._load_module(skill_name, skill_file)

                # Zarejestruj w kernelu
                self._register_skill_in_kernel(skill_name, module)

                # Zapisz w rejestrze
                self.loaded_skills[skill_name] = module
                loaded_skills.append(skill_name)

                logger.info(f"✅ Załadowano skill: {skill_name}")

            except SkillValidationError as e:
                logger.error(f"❌ Walidacja nieudana dla {skill_file.name}: {e}")
                continue
            except Exception as e:
                logger.error(f"❌ Błąd ładowania {skill_file.name}: {e}")
                continue

        logger.info(
            f"Załadowano {len(loaded_skills)} skills: {', '.join(loaded_skills)}"
        )
        return loaded_skills

    def reload_skill(self, skill_name: str) -> bool:
        """
        Przeładowuje moduł skill (hot-reload) bez restartu aplikacji.

        Args:
            skill_name: Nazwa skill do przeładowania

        Returns:
            True jeśli przeładowanie udane, False w przeciwnym razie
        """
        try:
            logger.info(f"Przeładowywanie skill: {skill_name}")

            # Sprawdź czy skill był wcześniej załadowany
            if skill_name not in self.loaded_skills:
                logger.warning(
                    f"Skill {skill_name} nie był wcześniej załadowany - ładuję po raz pierwszy"
                )
                # Spróbuj załadować
                skill_file = self.custom_skills_dir / f"{skill_name}.py"
                if not skill_file.exists():
                    logger.error(f"Plik {skill_file} nie istnieje")
                    return False

                # Waliduj
                self.validate_skill(str(skill_file))

                # Załaduj
                module = self._load_module(skill_name, skill_file)
                self._register_skill_in_kernel(skill_name, module)
                self.loaded_skills[skill_name] = module

                logger.info(f"✅ Załadowano nowy skill: {skill_name}")
                return True

            # Przeładuj istniejący moduł
            old_module = self.loaded_skills[skill_name]

            # Waliduj przed przeładowaniem
            skill_file = self.custom_skills_dir / f"{skill_name}.py"
            try:
                self.validate_skill(str(skill_file))
            except SkillValidationError as e:
                logger.error(f"Walidacja nie powiodła się: {e}")
                return False

            # Użyj importlib.reload z obsługą błędów
            try:
                reloaded_module = importlib.reload(old_module)
            except Exception as e:
                logger.error(f"Błąd podczas reload: {e}")
                # Pozostaw stary moduł załadowany
                return False

            # Zarejestruj ponownie w kernelu (nadpisz)
            self._register_skill_in_kernel(skill_name, reloaded_module)

            # Zaktualizuj rejestr
            self.loaded_skills[skill_name] = reloaded_module

            logger.info(f"✅ Przeładowano skill: {skill_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Błąd podczas przeładowywania {skill_name}: {e}")
            return False

    def validate_skill(self, file_path: str) -> bool:
        """
        Sprawdza statycznie (AST), czy kod jest bezpieczny.

        Sprawdza:
        - Czy plik zawiera klasę skill
        - Czy klasa ma przynajmniej jedną metodę z dekoratorem @kernel_function
        - Czy kod nie zawiera niebezpiecznych konstrukcji (eval, exec, __import__)

        Args:
            file_path: Ścieżka do pliku do walidacji

        Returns:
            True jeśli walidacja przeszła

        Raises:
            SkillValidationError: Jeśli walidacja nie przeszła
        """
        try:
            # Odczytaj plik używając helpers (Venom Standard Library)
            source_code = helpers.read_file(file_path, raise_on_error=True)
            if source_code is None:
                raise SkillValidationError(f"Nie można odczytać pliku: {file_path}")

            # Parsuj kod do AST
            tree = ast.parse(source_code, filename=file_path)

            # Sprawdź niebezpieczne konstrukcje
            dangerous_nodes = []
            for node in ast.walk(tree):
                # Sprawdź eval, exec, compile
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ["eval", "exec", "compile", "__import__"]:
                            dangerous_nodes.append(node.func.id)

            if dangerous_nodes:
                raise SkillValidationError(
                    f"Kod zawiera niebezpieczne funkcje: {', '.join(set(dangerous_nodes))}"
                )

            # Sprawdź czy jest przynajmniej jedna klasa
            classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
            if not classes:
                raise SkillValidationError("Plik nie zawiera żadnej klasy skill")

            # Sprawdź czy przynajmniej jedna klasa ma metodę z dekoratorem
            has_kernel_function = False
            for class_node in classes:
                for item in class_node.body:
                    if isinstance(item, ast.FunctionDef):
                        # Sprawdź dekoratory
                        for decorator in item.decorator_list:
                            # Dekorator może być Name lub Call
                            decorator_name = None
                            if isinstance(decorator, ast.Name):
                                decorator_name = decorator.id
                            elif isinstance(decorator, ast.Call):
                                if isinstance(decorator.func, ast.Name):
                                    decorator_name = decorator.func.id

                            if decorator_name == "kernel_function":
                                has_kernel_function = True
                                break

                    if has_kernel_function:
                        break

                if has_kernel_function:
                    break

            if not has_kernel_function:
                raise SkillValidationError(
                    "Żadna metoda nie ma dekoratora @kernel_function"
                )

            logger.info(f"✅ Walidacja przeszła dla: {file_path}")
            return True

        except SyntaxError as e:
            raise SkillValidationError(f"Błąd składni w pliku: {e}") from e
        except Exception as e:
            if isinstance(e, SkillValidationError):
                raise
            raise SkillValidationError(f"Błąd podczas walidacji: {e}") from e

    def _load_module(self, skill_name: str, skill_file: Path) -> Any:
        """
        Ładuje moduł Python ze ścieżki.

        Args:
            skill_name: Nazwa modułu
            skill_file: Ścieżka do pliku

        Returns:
            Załadowany moduł
        """
        # Użyj prefixu aby uniknąć konfliktów z innymi modułami
        module_name = f"venom_custom_{skill_name}"

        # Utwórz spec modułu
        spec = importlib.util.spec_from_file_location(module_name, skill_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Nie można utworzyć spec dla {skill_file}")

        # Załaduj moduł
        module = importlib.util.module_from_spec(spec)

        # Dodaj do sys.modules aby można było go później przeładować
        sys.modules[module_name] = module

        # Wykonaj moduł
        spec.loader.exec_module(module)

        return module

    def _register_skill_in_kernel(self, skill_name: str, module: Any) -> None:
        """
        Rejestruje skill w Semantic Kernel.

        Szuka wszystkich klas w module i próbuje je zarejestrować jako pluginy.

        Args:
            skill_name: Nazwa skill
            module: Załadowany moduł
        """
        # Znajdź wszystkie klasy w module
        classes = [
            getattr(module, name)
            for name in dir(module)
            if isinstance(getattr(module, name), type)
        ]

        if not classes:
            logger.warning(f"Moduł {skill_name} nie zawiera żadnych klas")
            return

        # Moduł name z prefixem
        module_full_name = f"venom_custom_{skill_name}"

        # Zarejestruj każdą klasę jako plugin
        for cls in classes:
            # Pomiń klasy zaimportowane z innych modułów
            # Sprawdź czy klasa należy do tego modułu (z prefixem)
            if (
                not cls.__module__.endswith(skill_name)
                and cls.__module__ != module_full_name
            ):
                continue

            try:
                # Utwórz instancję klasy
                instance = cls()

                # Zarejestruj w kernelu
                self.kernel.add_plugin(instance, plugin_name=cls.__name__)

                logger.info(
                    f"Zarejestrowano plugin: {cls.__name__} z modułu {skill_name}"
                )

            except Exception as e:
                logger.warning(f"Nie udało się zarejestrować klasy {cls.__name__}: {e}")

    def get_loaded_skills(self) -> List[str]:
        """
        Zwraca listę nazw załadowanych skills.

        Returns:
            Lista nazw skills
        """
        return list(self.loaded_skills.keys())

    def unload_skill(self, skill_name: str) -> bool:
        """
        Usuwa skill z rejestru (nie usuwa z kernela - to wymaga restartowania kernela).

        Args:
            skill_name: Nazwa skill do usunięcia

        Returns:
            True jeśli usunięto, False jeśli skill nie był załadowany
        """
        if skill_name in self.loaded_skills:
            del self.loaded_skills[skill_name]
            logger.info(f"Usunięto skill z rejestru: {skill_name}")
            return True

        logger.warning(f"Skill {skill_name} nie był załadowany")
        return False

    async def broadcast_skill_event(
        self, event_type: str, skill_name: str, action: str = "", is_external: bool = False
    ):
        """
        Emituje event WebSocket o wykonaniu skilla.

        Args:
            event_type: Typ eventu - należy używać EventType.SKILL_STARTED, 
                       EventType.SKILL_COMPLETED lub EventType.SKILL_FAILED
            skill_name: Nazwa skilla
            action: Opcjonalnie akcja wykonywana przez skill
            is_external: Czy skill komunikuje się z zewnętrznymi API
        
        Note:
            Ta metoda musi być wywołana przez kod używający skills aby 
            emitować eventy. Przykład użycia znajduje się w dokumentacji.
        """
        if self.event_broadcaster:
            try:
                await self.event_broadcaster.broadcast_event(
                    event_type=event_type,
                    message=f"Skill: {skill_name}" + (f" - {action}" if action else ""),
                    agent="SkillManager",
                    data={
                        "skill": skill_name,
                        "action": action,
                        "is_external": is_external,
                    },
                )
            except Exception as e:
                logger.warning(f"Nie udało się wysłać eventu skill: {e}")
