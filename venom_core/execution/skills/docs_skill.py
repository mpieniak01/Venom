"""Moduł: docs_skill - umiejętność generowania dokumentacji."""

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils import helpers
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)

ALLOWED_MKDOCS_THEMES = {"material", "readthedocs"}
MKDOCS_CONFIG_FILE = "mkdocs.yml"
INDEX_DOC_FILE = "index.md"


class DocsSkill:
    """
    Skill do generowania dokumentacji przy użyciu MkDocs.

    Umożliwia agentom tworzenie statycznych stron HTML z dokumentacji
    w formacie Markdown.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja DocsSkill.

        Args:
            workspace_root: Katalog roboczy (domyślnie z SETTINGS)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.docs_dir = self.workspace_root / "docs"
        self.site_dir = self.workspace_root / "site"

        # Upewnij się że katalog docs istnieje
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        logger.info("DocsSkill zainicjalizowany")

    @kernel_function(
        name="generate_mkdocs_config",
        description=f"Generuje plik konfiguracyjny {MKDOCS_CONFIG_FILE} dla dokumentacji. "
        "Użyj przed budowaniem strony dokumentacji.",
    )
    def generate_mkdocs_config(
        self,
        site_name: Annotated[str, "Nazwa projektu/strony (np. 'My Project')"],
        theme: Annotated[
            str, "Motyw MkDocs: 'material' lub 'readthedocs' (domyślnie 'material')"
        ] = "material",
        repo_url: Annotated[Optional[str], "URL repozytorium (opcjonalne)"] = None,
    ) -> str:
        """
        Generuje plik konfiguracji MkDocs.

        Args:
            site_name: Nazwa projektu
            theme: Motyw dokumentacji
            repo_url: URL repozytorium

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            if not site_name or not site_name.strip():
                return "❌ site_name nie może być pusty"
            if theme not in ALLOWED_MKDOCS_THEMES:
                return (
                    "❌ Nieprawidłowy motyw MkDocs. "
                    f"Dozwolone wartości: {', '.join(sorted(ALLOWED_MKDOCS_THEMES))}"
                )

            logger.info(f"Generowanie {MKDOCS_CONFIG_FILE} dla projektu: {site_name}")

            # Przygotuj konfigurację
            config_lines = [
                f"site_name: {site_name.strip()}",
                "theme:",
                f"  name: {theme}",
            ]

            if theme == "material":
                config_lines.extend(
                    [
                        "  features:",
                        "    - navigation.tabs",
                        "    - navigation.sections",
                        "    - toc.integrate",
                        "    - search.suggest",
                        "    - search.highlight",
                        "  palette:",
                        "    - scheme: default",
                        "      primary: indigo",
                        "      accent: indigo",
                    ]
                )

            if repo_url:
                config_lines.append(f"repo_url: {repo_url}")

            # Automatycznie wykryj strukturę docs/
            nav = self._generate_nav_structure()
            if nav:
                config_lines.append("\nnav:")
                config_lines.extend(nav)

            # Dodaj podstawowe pluginy
            config_lines.extend(
                [
                    "\nplugins:",
                    "  - search",
                    "\nmarkdown_extensions:",
                    "  - pymdownx.highlight",
                    "  - pymdownx.superfences",
                    "  - admonition",
                    "  - toc:",
                    "      permalink: true",
                ]
            )

            # Zapisz plik używając helpers (Venom Standard Library)
            config_path = self.workspace_root / MKDOCS_CONFIG_FILE
            config_content = "\n".join(config_lines)

            if not helpers.write_file(
                config_path, config_content, raise_on_error=False
            ):
                raise IOError(f"Nie udało się zapisać pliku {config_path}")

            logger.info(f"Plik {MKDOCS_CONFIG_FILE} utworzony: {config_path}")
            return (
                f"✅ Plik konfiguracyjny utworzony: {config_path}\n\n{config_content}"
            )

        except Exception as e:
            error_msg = f"❌ Błąd podczas generowania {MKDOCS_CONFIG_FILE}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def _generate_nav_structure(self) -> list[str]:
        """
        Generuje strukturę nawigacji na podstawie zawartości docs/.

        Returns:
            Lista linii konfiguracji nav
        """
        nav_lines = []

        try:
            # Szukaj pliku index.md lub README.md jako strona główna
            index_file = None
            for name in [INDEX_DOC_FILE, "README.md", "readme.md"]:
                if (self.docs_dir / name).exists():
                    index_file = name
                    break

            if index_file:
                nav_lines.append(f"  - Strona główna: {index_file}")

            # Dodaj wszystkie pliki .md (poza index/readme)
            md_files = sorted(self.docs_dir.glob("*.md"))
            for md_file in md_files:
                if md_file.name.lower() not in [INDEX_DOC_FILE, "readme.md"]:
                    # Utwórz czytelny tytuł z nazwy pliku
                    title = md_file.stem.replace("_", " ").replace("-", " ").title()
                    nav_lines.append(f"  - {title}: {md_file.name}")

            # Sprawdź czy istnieją podkatalogi
            for subdir in sorted(self.docs_dir.iterdir()):
                if subdir.is_dir() and not subdir.name.startswith((".", "_")):
                    subdir_files = list(subdir.glob("*.md"))
                    if subdir_files:
                        # Dodaj sekcję dla podkatalogu
                        section_name = (
                            subdir.name.replace("_", " ").replace("-", " ").title()
                        )
                        nav_lines.append(f"  - {section_name}:")
                        for md_file in sorted(subdir_files):
                            title = (
                                md_file.stem.replace("_", " ").replace("-", " ").title()
                            )
                            rel_path = f"{subdir.name}/{md_file.name}"
                            nav_lines.append(f"    - {title}: {rel_path}")

        except Exception as e:
            logger.warning(f"Nie można wygenerować automatycznej nawigacji: {e}")

        return nav_lines

    def _list_visible_subdirs(self) -> list[Path]:
        return [
            directory
            for directory in self.docs_dir.iterdir()
            if directory.is_dir() and not directory.name.startswith((".", "_"))
        ]

    def _resolve_homepage_name(self) -> str | None:
        has_index = (self.docs_dir / INDEX_DOC_FILE).exists()
        if has_index:
            return INDEX_DOC_FILE
        has_readme = (self.docs_dir / "README.md").exists()
        if has_readme:
            return "README.md"
        return None

    def _build_docs_sample_lines(
        self, md_files: list[Path], limit: int = 10
    ) -> list[str]:
        if not md_files:
            return []
        lines = ["\n📋 Przykładowe pliki:"]
        for md_file in md_files[:limit]:
            rel_path = md_file.relative_to(self.docs_dir)
            lines.append(f"  - {rel_path}")
        if len(md_files) > limit:
            lines.append(f"  ... i {len(md_files) - limit} więcej")
        return lines

    @kernel_function(
        name="build_docs_site",
        description="Buduje statyczną stronę HTML z dokumentacji Markdown. "
        f"Użyj po wygenerowaniu {MKDOCS_CONFIG_FILE}.",
    )
    async def build_docs_site(
        self,
        clean: Annotated[
            bool, "Czy wyczyścić poprzednią wersję przed budowaniem (domyślnie True)"
        ] = True,
    ) -> str:
        """
        Buduje stronę dokumentacji za pomocą MkDocs.

        Args:
            clean: Czy wyczyścić poprzednią wersję

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            logger.info("Budowanie strony dokumentacji...")

            # Sprawdź czy mkdocs.yml istnieje
            config_path = self.workspace_root / MKDOCS_CONFIG_FILE
            if not config_path.exists():
                return f"❌ Brak pliku {MKDOCS_CONFIG_FILE}. Użyj najpierw generate_mkdocs_config."

            # Sprawdź czy mkdocs jest zainstalowany
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["mkdocs", "--version"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.SubprocessError, FileNotFoundError):
                return "❌ MkDocs nie jest zainstalowany. Zainstaluj: pip install mkdocs mkdocs-material"

            # Wyczyść poprzednią wersję jeśli wymagane
            if clean and self.site_dir.exists():
                shutil.rmtree(self.site_dir)
                logger.info("Wyczyszczono poprzednią wersję strony")

            # Buduj stronę
            result = await asyncio.to_thread(
                subprocess.run,
                ["mkdocs", "build"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                # Sprawdź czy site/ został utworzony
                if self.site_dir.exists():
                    # Policz pliki HTML
                    html_files = list(self.site_dir.rglob("*.html"))
                    logger.info(
                        f"Strona dokumentacji zbudowana: {len(html_files)} plików HTML"
                    )

                    return (
                        f"✅ Strona dokumentacji zbudowana pomyślnie!\n\n"
                        f"📁 Lokalizacja: {self.site_dir}\n"
                        f"📄 Plików HTML: {len(html_files)}\n\n"
                        f"Możesz otworzyć: {self.site_dir / 'index.html'}"
                    )
                else:
                    return "❌ Budowanie zakończone, ale katalog site/ nie został utworzony"
            else:
                error_output = result.stderr or result.stdout
                return f"❌ Błąd podczas budowania:\n{error_output}"

        except subprocess.TimeoutExpired:
            return "❌ Budowanie przekroczyło limit czasu (60s)"
        except Exception as e:
            error_msg = f"❌ Nieoczekiwany błąd podczas budowania: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="serve_docs",
        description="Uruchamia lokalny serwer deweloperski MkDocs z live-reload. "
        "Użyj do podglądu dokumentacji podczas pracy.",
    )
    def serve_docs(
        self,
        port: Annotated[int, "Port serwera (domyślnie 8000)"] = 8000,
    ) -> str:
        """
        Uruchamia serwer deweloperski MkDocs.

        UWAGA: Ta funkcja startuje serwer w tle. Użyj z ostrożnością.

        Args:
            port: Port HTTP

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            if port < 1 or port > 65535:
                return "❌ Nieprawidłowy port. Dozwolony zakres: 1-65535"

            logger.info(f"Uruchamianie serwera dokumentacji na porcie {port}...")

            # Sprawdź czy mkdocs.yml istnieje
            config_path = self.workspace_root / MKDOCS_CONFIG_FILE
            if not config_path.exists():
                return f"❌ Brak pliku {MKDOCS_CONFIG_FILE}. Użyj najpierw generate_mkdocs_config."

            # Informacja dla użytkownika
            info = (
                f"ℹ️ Aby uruchomić serwer deweloperski MkDocs, wykonaj:\n\n"
                f"cd {self.workspace_root}\n"
                f"mkdocs serve -a 0.0.0.0:{port}\n\n"
                f"Serwer będzie dostępny pod: {build_http_url('localhost', port)}"
            )

            logger.info(info)
            return info

        except Exception as e:
            error_msg = f"❌ Błąd: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="check_docs_structure",
        description="Sprawdza strukturę katalogu docs/ i raportuje co zostało znalezione. "
        "Użyj przed generowaniem dokumentacji.",
    )
    def check_docs_structure(self) -> str:
        """
        Sprawdza strukturę dokumentacji.

        Returns:
            Raport o strukturze docs/
        """
        try:
            logger.info("Sprawdzanie struktury dokumentacji...")

            if not self.docs_dir.exists():
                return f"❌ Katalog docs/ nie istnieje: {self.docs_dir}"

            # Zbierz statystyki
            md_files = list(self.docs_dir.rglob("*.md"))
            subdirs = self._list_visible_subdirs()

            # Przygotuj raport
            report_lines = [
                f"📂 Struktura dokumentacji: {self.docs_dir}\n",
                f"📄 Plików Markdown: {len(md_files)}",
            ]

            if subdirs:
                report_lines.append(f"📁 Podkatalogów: {len(subdirs)}")
                for subdir in subdirs:
                    subdir_files = list(subdir.glob("*.md"))
                    report_lines.append(
                        f"  - {subdir.name}/ ({len(subdir_files)} plików)"
                    )

            homepage_name = self._resolve_homepage_name()
            if homepage_name:
                report_lines.append(f"\n✅ Strona główna: {homepage_name}")
            else:
                report_lines.append(
                    f"\n⚠️ Brak strony głównej ({INDEX_DOC_FILE} lub README.md)"
                )

            report_lines.extend(self._build_docs_sample_lines(md_files))

            return "\n".join(report_lines)

        except Exception as e:
            error_msg = f"❌ Błąd podczas sprawdzania struktury: {str(e)}"
            logger.error(error_msg)
            return error_msg
