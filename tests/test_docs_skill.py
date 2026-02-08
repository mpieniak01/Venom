"""Testy dla DocsSkill."""

import pytest

from venom_core.execution.skills.docs_skill import DocsSkill


@pytest.fixture
def docs_skill(tmp_path):
    """Fixture dla DocsSkill z tymczasowym katalogiem."""
    return DocsSkill(workspace_root=str(tmp_path))


def test_docs_skill_initialization(docs_skill):
    """Test inicjalizacji DocsSkill."""
    assert docs_skill is not None
    assert docs_skill.docs_dir.exists()


@pytest.mark.asyncio
async def test_generate_mkdocs_config(docs_skill):
    """Test generowania pliku mkdocs.yml."""
    result = await docs_skill.generate_mkdocs_config(
        site_name="Test Project",
        theme="material",
    )

    assert "✅" in result
    assert "mkdocs.yml" in result

    # Sprawdź czy plik został utworzony
    config_path = docs_skill.workspace_root / "mkdocs.yml"
    assert config_path.exists()

    # Sprawdź zawartość
    content = config_path.read_text()
    assert "site_name: Test Project" in content
    assert "name: material" in content


@pytest.mark.asyncio
async def test_check_docs_structure_empty(docs_skill):
    """Test sprawdzania pustej struktury docs."""
    result = await docs_skill.check_docs_structure()

    assert "📂" in result
    assert "Plików Markdown: 0" in result


@pytest.mark.asyncio
async def test_check_docs_structure_with_files(docs_skill):
    """Test sprawdzania struktury z plikami."""
    # Utwórz przykładowe pliki
    (docs_skill.docs_dir / "index.md").write_text("# Welcome")
    (docs_skill.docs_dir / "guide.md").write_text("# Guide")

    result = await docs_skill.check_docs_structure()

    assert "Plików Markdown: 2" in result
    assert "✅ Strona główna: index.md" in result


def test_generate_nav_structure(docs_skill):
    """Test generowania struktury nawigacji."""
    # Utwórz pliki testowe
    (docs_skill.docs_dir / "index.md").write_text("# Home")
    (docs_skill.docs_dir / "about.md").write_text("# About")

    # Utwórz podkatalog
    guide_dir = docs_skill.docs_dir / "guide"
    guide_dir.mkdir()
    (guide_dir / "intro.md").write_text("# Intro")

    # Generuj nawigację
    nav = docs_skill._generate_nav_structure()

    assert len(nav) > 0
    # Sprawdź czy zawiera podstawowe elementy
    nav_text = "\n".join(nav)
    assert "index.md" in nav_text or "Strona główna" in nav_text


@pytest.mark.asyncio
async def test_build_docs_without_config(docs_skill):
    """Test budowania bez pliku konfiguracyjnego."""
    result = await docs_skill.build_docs_site()

    assert "❌" in result
    assert "mkdocs.yml" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_docs_workflow(docs_skill):
    """Test pełnego workflow generowania dokumentacji."""
    # 1. Utwórz dokumentację
    (docs_skill.docs_dir / "index.md").write_text("# Welcome to Test Project")
    (docs_skill.docs_dir / "guide.md").write_text("# User Guide\n\nSome content")

    # 2. Generuj konfigurację
    config_result = await docs_skill.generate_mkdocs_config(
        site_name="Test Project", theme="material"
    )
    assert "✅" in config_result

    # 3. Sprawdź strukturę
    structure_result = await docs_skill.check_docs_structure()
    assert "Plików Markdown: 2" in structure_result

    # Uwaga: build_docs_site wymaga zainstalowanego mkdocs
    # Ten test jest pomijany w środowiskach bez mkdocs
