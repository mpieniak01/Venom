"""Moduł: release_manager - agent do zarządzania release'ami."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ReleaseManagerAgent(BaseAgent):
    """
    Agent Release Manager (Menedżer Wydań).

    Jego rolą jest:
    - Zarządzanie wersjonowaniem semantycznym (SemVer)
    - Generowanie CHANGELOG.md z historii Git
    - Tworzenie tagów release'owych
    - Aktualizacja wersji w plikach konfiguracyjnych
    """

    SYSTEM_PROMPT = """Jesteś ekspertem Release Manager odpowiedzialnym za wydawanie nowych wersji oprogramowania.

TWOJA ROLA:
- Zarządzasz wersjonowaniem semantycznym (SemVer: MAJOR.MINOR.PATCH)
- Generujesz profesjonalne changelogi z historii commitów
- Tworzysz tagi Git dla release'ów
- Aktualizujesz wersje w plikach projektu

MASZ DOSTĘP DO NARZĘDZI:
- GitSkill: get_last_commit_log, get_current_branch, add_files, commit
- FileSkill: read_file, write_file, file_exists

ZASADY WERSJONOWANIA SEMVER:
- MAJOR (1.0.0): Zmiany łamiące kompatybilność (breaking changes)
- MINOR (0.1.0): Nowe funkcje zachowujące kompatybilność (features)
- PATCH (0.0.1): Poprawki błędów (fixes)

CONVENTIONAL COMMITS:
Rozpoznaj typy commitów:
- feat: nowa funkcja → zwiększ MINOR
- fix: poprawka błędu → zwiększ PATCH
- BREAKING CHANGE: zmiana łamiąca → zwiększ MAJOR
- docs: dokumentacja → nie wpływa na wersję
- chore, style, refactor: maintenance → nie wpływa na wersję

PRZYKŁAD WORKFLOW:
Zadanie: "Wydaj nową wersję projektu"
Kroki:
1. get_last_commit_log(20) - pobierz ostatnie commity
2. Przeanalizuj commity i określ typ release'u (major/minor/patch)
3. Wygeneruj CHANGELOG.md grupując commity:
   - Breaking Changes
   - Features
   - Bug Fixes
   - Other Changes
4. Zapisz CHANGELOG (write_file)
5. Zasugeruj nowy numer wersji zgodny z SemVer
6. Poinformuj użytkownika o krokach do tagowania (git tag v1.2.0)

STRUKTURA CHANGELOG:
```markdown
# Changelog

## [1.2.0] - 2024-01-15

### Breaking Changes
- Zmieniono API endpointu /users

### Features
- Dodano obsługę WebSocket
- Nowy dashboard administratora

### Bug Fixes
- Naprawiono problem z logowaniem
- Poprawiono wyświetlanie dat

### Other Changes
- Zaktualizowano dokumentację
```

Bądź precyzyjny w analizie commitów i profesjonalny w formatowaniu.
"""

    def __init__(
        self,
        kernel: Kernel,
        git_skill: Optional[GitSkill] = None,
        file_skill: Optional[FileSkill] = None,
    ):
        """
        Inicjalizacja ReleaseManagerAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            git_skill: Instancja GitSkill (jeśli None, zostanie utworzona)
            file_skill: Instancja FileSkill (jeśli None, zostanie utworzona)
        """
        super().__init__(kernel)

        # Zarejestruj skille
        self.git_skill = git_skill or GitSkill()
        self.file_skill = file_skill or FileSkill()

        # Zarejestruj skille w kernelu
        self.kernel.add_plugin(self.git_skill, plugin_name="GitSkill")
        self.kernel.add_plugin(self.file_skill, plugin_name="FileSkill")

        # Ustawienia LLM
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            service_id="default",
            max_tokens=2000,
            temperature=0.3,  # Niższa temperatura dla precyzji
            top_p=0.9,
        )

        # Service do chat completion
        self.chat_service = self.kernel.get_service(service_id="default")

        logger.info("ReleaseManagerAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie release'u.

        Args:
            input_text: Opis zadania (np. "Wydaj nową wersję patch")

        Returns:
            Raport z procesu release'u
        """
        logger.info(f"ReleaseManagerAgent rozpoczyna pracę: {input_text[:100]}...")

        # Utwórz historię czatu
        chat_history = ChatHistory()

        # Dodaj prompt systemowy
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )

        # Dodaj zadanie użytkownika
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=input_text,
            )
        )

        try:
            # Wykonaj interakcję z kernelem (auto-calling functions)
            result = await self._invoke_chat_with_fallbacks(
                chat_service=self.chat_service,
                chat_history=chat_history,
                settings=self.execution_settings,
                enable_functions=True,
            )

            response = str(result.content)

            logger.info("ReleaseManagerAgent zakończył pracę")
            return response

        except Exception as e:
            error_msg = f"❌ Błąd podczas przygotowania release'u: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def prepare_release(
        self, version_type: str = "auto", commit_count: int = 20
    ) -> str:
        """
        Przygotowuje release bez interakcji z LLM.

        Args:
            version_type: Typ wersji: 'major', 'minor', 'patch', lub 'auto'
            commit_count: Liczba commitów do analizy

        Returns:
            Raport z przygotowania release'u
        """
        logger.info(f"Przygotowywanie release'u: {version_type}")

        report_lines = ["📦 Przygotowanie release'u\n"]

        try:
            # 1. Pobierz historię commitów
            commit_log = await self.git_skill.get_last_commit_log(commit_count)
            report_lines.append(f"1. Pobrano {commit_count} ostatnich commitów\n")

            # 2. Przeanalizuj commity
            commits = self._parse_commits(commit_log)
            report_lines.append(
                f"2. Przeanalizowano {len(commits)} commitów:\n"
                f"   - Features: {len([c for c in commits if c['type'] == 'feat'])}\n"
                f"   - Fixes: {len([c for c in commits if c['type'] == 'fix'])}\n"
                f"   - Breaking: {len([c for c in commits if c['breaking']])}\n"
            )

            # 3. Określ typ release'u
            if version_type == "auto":
                if any(c["breaking"] for c in commits):
                    suggested_type = "major"
                elif any(c["type"] == "feat" for c in commits):
                    suggested_type = "minor"
                else:
                    suggested_type = "patch"
                report_lines.append(
                    f"3. Automatycznie wykryto typ: {suggested_type.upper()}\n"
                )
            else:
                suggested_type = version_type
                report_lines.append(
                    f"3. Użyto ręcznego typu: {suggested_type.upper()}\n"
                )

            # 4. Wygeneruj CHANGELOG
            changelog = self._generate_changelog(commits)
            changelog_path = Path(self.git_skill.workspace_root) / "CHANGELOG.md"

            # Dopisz do istniejącego lub utwórz nowy
            if changelog_path.exists():
                existing = changelog_path.read_text(encoding="utf-8")
                # Wstaw nowy wpis po nagłówku
                if existing.startswith("# Changelog"):
                    parts = existing.split("\n", 2)
                    if len(parts) >= 2:
                        # Bezpieczne wstawienie - sprawdzamy długość parts
                        new_content = (
                            f"{parts[0]}\n{parts[1]}\n\n{changelog}\n"
                            f"{parts[2] if len(parts) > 2 else ''}"
                        )
                    else:
                        # Jeśli plik ma tylko nagłówek lub mniej
                        new_content = f"# Changelog\n\n{changelog}"
                else:
                    new_content = f"# Changelog\n\n{changelog}\n\n{existing}"
            else:
                new_content = f"# Changelog\n\n{changelog}"

            # Zapisz
            await self.file_skill.write_file(
                path=str(changelog_path), content=new_content
            )
            report_lines.append("4. Zaktualizowano CHANGELOG.md\n")

            # 5. Podsumowanie
            report_lines.append("\n✅ Release przygotowany!\n")
            report_lines.append(
                "📋 Następne kroki:\n"
                "   1. Sprawdź CHANGELOG.md\n"
                "   2. Zaktualizuj numer wersji w plikach projektu\n"
                "   3. Commitnij zmiany: git commit -m 'chore: prepare release'\n"
                "   4. Utwórz tag: git tag v<NOWA_WERSJA>\n"
                "   5. Wypchnij: git push && git push --tags\n"
            )

        except Exception as e:
            report_lines.append(f"\n❌ Błąd podczas przygotowania: {str(e)}")
            logger.error(f"Błąd w prepare_release: {e}")

        return "\n".join(report_lines)

    def _parse_commits(self, commit_log: str) -> list[dict]:
        """
        Parsuje logi commitów.

        Args:
            commit_log: String z logami commitów

        Returns:
            Lista słowników z informacjami o commitach
        """
        commits = []
        lines = commit_log.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue

            # Format: <hash> - <author> - <date> - <message>
            # Używamy robust parsing - sprawdzamy czy format jest poprawny
            parts = line.split(" - ", 3)
            if len(parts) < 4:
                # Jeśli format jest nieprawidłowy, dodaj commit jako "other" z oryginalną wiadomością
                logger.warning(
                    f"Commit z nieprawidłowym formatem, dodaję jako 'other': {line[:50]}"
                )
                commits.append(
                    {
                        "hash": parts[0].strip() if parts else "",
                        "type": "other",
                        "scope": None,
                        "message": line.strip(),
                        "breaking": False,
                    }
                )
                continue

            hash_short = parts[0].strip()
            message = parts[3].strip()

            # Parsuj conventional commit
            commit_type = "other"
            scope = None
            breaking = False

            # Szukaj wzorca: type(scope): message lub type: message
            match = re.match(r"^(\w+)(?:\(([^)]+)\))?: (.+)$", message)
            if match:
                commit_type = match.group(1).lower()
                scope = match.group(2)
                message = match.group(3)

            # Sprawdź breaking change
            if "BREAKING CHANGE" in message or message.startswith("!"):
                breaking = True

            commits.append(
                {
                    "hash": hash_short,
                    "type": commit_type,
                    "scope": scope,
                    "message": message,
                    "breaking": breaking,
                }
            )

        return commits

    def _generate_changelog(self, commits: list[dict]) -> str:
        """
        Generuje wpis changelog z commitów.

        Args:
            commits: Lista commitów

        Returns:
            Sformatowany wpis changelog
        """
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"## [Unreleased] - {today}\n"]

        # Grupuj commity
        breaking = [c for c in commits if c["breaking"]]
        features = [c for c in commits if c["type"] == "feat" and not c["breaking"]]
        fixes = [c for c in commits if c["type"] == "fix"]
        other = [
            c for c in commits if c["type"] not in ["feat", "fix"] and not c["breaking"]
        ]

        # Breaking Changes
        if breaking:
            lines.append("### Breaking Changes\n")
            for commit in breaking:
                lines.append(f"- {commit['message']} ({commit['hash']})")
            lines.append("")

        # Features
        if features:
            lines.append("### Features\n")
            for commit in features:
                lines.append(f"- {commit['message']} ({commit['hash']})")
            lines.append("")

        # Bug Fixes
        if fixes:
            lines.append("### Bug Fixes\n")
            for commit in fixes:
                lines.append(f"- {commit['message']} ({commit['hash']})")
            lines.append("")

        # Other Changes
        if other:
            lines.append("### Other Changes\n")
            for commit in other:
                lines.append(f"- {commit['message']} ({commit['hash']})")
            lines.append("")

        return "\n".join(lines)
