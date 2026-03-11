"""Testy dla DocsSkill."""

import subprocess

import pytest

import venom_core.execution.skills.docs_skill as docs_skill_module
from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.docs_skill import DocsSkill


@pytest.fixture
def docs_skill(tmp_path):
    """Fixture dla DocsSkill z tymczasowym katalogiem."""
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(40)
    try:
        yield DocsSkill(workspace_root=str(tmp_path))
    finally:
        permission_guard.set_level(previous_level)


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
async def test_generate_mkdocs_config_rejects_invalid_input(docs_skill):
    empty_name = await docs_skill.generate_mkdocs_config(site_name="", theme="material")
    invalid_theme = await docs_skill.generate_mkdocs_config(
        site_name="Test", theme="invalid"
    )

    assert "site_name nie może być pusty" in empty_name
    assert "Nieprawidłowy motyw MkDocs" in invalid_theme


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


@pytest.mark.asyncio
async def test_build_docs_blocked_without_shell_permission(tmp_path):
    skill = DocsSkill(workspace_root=str(tmp_path))
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(0)
    try:
        result = await skill.build_docs_site()
    finally:
        permission_guard.set_level(previous_level)

    assert "AutonomyViolation" in result
    assert "Brak uprawnień do shella" in result


@pytest.mark.asyncio
async def test_build_docs_mkdocs_not_installed(docs_skill, monkeypatch):
    (docs_skill.workspace_root / "mkdocs.yml").write_text("site_name: Test")

    def _raise_not_found(*_args, **_kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(docs_skill_module.subprocess, "run", _raise_not_found)
    result = await docs_skill.build_docs_site()
    assert "MkDocs nie jest zainstalowany" in result


@pytest.mark.asyncio
async def test_build_docs_build_error_propagates_stderr(docs_skill, monkeypatch):
    (docs_skill.workspace_root / "mkdocs.yml").write_text("site_name: Test")

    calls = {"count": 0}

    def _run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok")
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="", stderr="mkdocs build failed"
        )

    monkeypatch.setattr(docs_skill_module.subprocess, "run", _run)
    result = await docs_skill.build_docs_site(clean=False)
    assert "Błąd podczas budowania" in result
    assert "mkdocs build failed" in result


def test_serve_docs_validations_and_success_hint(docs_skill):
    invalid_port = docs_skill.serve_docs(port=0)
    assert "Nieprawidłowy port" in invalid_port

    missing_cfg = docs_skill.serve_docs(port=8000)
    assert "Brak pliku mkdocs.yml" in missing_cfg

    (docs_skill.workspace_root / "mkdocs.yml").write_text("site_name: Test")
    ok = docs_skill.serve_docs(port=8001)
    assert "mkdocs serve -a 0.0.0.0:8001" in ok
    assert "http://localhost:8001" in ok


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
