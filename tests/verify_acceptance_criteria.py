"""
Skrypt weryfikacji Kryteriów Akceptacji dla External Discovery v1.0
Zadanie: Integracja GitHub & Hugging Face
"""

from pathlib import Path
from unittest.mock import MagicMock

from venom_core.execution.skills.github_skill import GitHubSkill
from venom_core.execution.skills.huggingface_skill import HuggingFaceSkill


def _ensure(condition: bool, message: str) -> None:
    """Raise AssertionError with a helpful message."""
    if not condition:
        raise AssertionError(message)


def _read_requirements_files(files: list[str]) -> dict[str, str]:
    contents: dict[str, str] = {}
    for file_name in files:
        path = Path(file_name)
        if path.exists():
            contents[file_name] = path.read_text(encoding="utf-8")
    return contents


def test_kryteria_akceptacji():
    """
    Weryfikacja wszystkich kryteriów akceptacji (DoD):
    - [ ] Agent zapytany "Znajdź popularne biblioteki Python do PDF" zwraca listę linków do GitHub z liczbą gwiazdek.
    - [ ] Agent zapytany "Poszukaj lekkiego modelu do sentymentu" zwraca listę modeli z Hugging Face.
    - [ ] Biblioteki PyGithub i huggingface_hub są zadeklarowane w profilach zależności.
    """

    print("\n" + "=" * 80)
    print("WERYFIKACJA KRYTERIÓW AKCEPTACJI - External Discovery v1.0")
    print("=" * 80)

    # Kryterium 1: Agent może wyszukać biblioteki Python do PDF na GitHub
    print("\n[1/3] Test: Agent może znaleźć biblioteki Python do PDF na GitHub")
    print("-" * 80)

    github_skill = GitHubSkill()

    # Mock API dla demonstracji
    mock_repo1 = MagicMock()
    mock_repo1.full_name = "pymupdf/PyMuPDF"
    mock_repo1.description = "PyMuPDF - a Python binding for MuPDF"
    mock_repo1.stargazers_count = 4500
    mock_repo1.forks_count = 500
    mock_repo1.html_url = "https://github.com/pymupdf/PyMuPDF"
    mock_repo1.language = "Python"

    mock_repo2 = MagicMock()
    mock_repo2.full_name = "py-pdf/pypdf"
    mock_repo2.description = "A pure-python PDF library"
    mock_repo2.stargazers_count = 7000
    mock_repo2.forks_count = 1200
    mock_repo2.html_url = "https://github.com/py-pdf/pypdf"
    mock_repo2.language = "Python"

    github_skill.github.search_repositories = MagicMock(
        return_value=[mock_repo2, mock_repo1]  # sorted by stars
    )

    result = github_skill.search_repos(
        query="Python PDF", language="Python", sort="stars"
    )

    print("Wynik zapytania: 'Znajdź biblioteki Python do PDF'")
    print(result)

    # Weryfikacja
    _ensure("py-pdf/pypdf" in result, "Brak biblioteki pypdf w wynikach")
    _ensure("pymupdf/PyMuPDF" in result, "Brak biblioteki PyMuPDF w wynikach")
    _ensure("7,000" in result or "7000" in result, "Brak liczby gwiazdek")
    _ensure("github.com" in result, "Brak linków do GitHub")

    print("\n✅ SUKCES: Agent zwraca listę bibliotek z GitHub z gwiazdkami i linkami")

    # Kryterium 2: Agent może wyszukać lekki model do sentymentu na Hugging Face
    print("\n[2/3] Test: Agent może znaleźć lekki model do sentymentu na Hugging Face")
    print("-" * 80)

    hf_skill = HuggingFaceSkill()

    # Mock modeli
    mock_model1 = MagicMock()
    mock_model1.id = "distilbert-base-uncased-finetuned-sst-2-english"
    mock_model1.pipeline_tag = "text-classification"
    mock_model1.downloads = 1000000
    mock_model1.likes = 500
    mock_model1.tags = ["pytorch", "transformers", "text-classification"]

    mock_model2 = MagicMock()
    mock_model2.id = "distilbert-sentiment-onnx"
    mock_model2.pipeline_tag = "text-classification"
    mock_model2.downloads = 50000
    mock_model2.likes = 100
    mock_model2.tags = ["onnx", "text-classification", "sentiment"]

    hf_skill.api.list_models = MagicMock(return_value=[mock_model1, mock_model2])

    result = hf_skill.search_models(
        task="text-classification", query="sentiment", sort="downloads"
    )

    print("Wynik zapytania: 'Poszukaj lekkiego modelu do sentymentu'")
    print(result)

    # Weryfikacja
    _ensure("distilbert" in result.lower(), "Brak modeli distilbert w wynikach")
    _ensure("text-classification" in result, "Brak informacji o zadaniu")
    _ensure("huggingface.co" in result, "Brak linków do Hugging Face")
    _ensure("✅ ONNX" in result, "Nie preferuje modeli ONNX (lekkich)")

    print(
        "\n✅ SUKCES: Agent zwraca listę modeli z Hugging Face z preferencją dla ONNX"
    )

    # Kryterium 3: Weryfikacja zależności w plikach profilowych requirements
    print(
        "\n[3/3] Test: Biblioteki PyGithub i huggingface_hub są zadeklarowane w profilach"
    )
    print("-" * 80)

    requirement_files = [
        "requirements.txt",
        "requirements-profile-api.txt",
        "requirements-docker-minimal.txt",
        "requirements-full.txt",
        "requirements-ci-lite.txt",
    ]
    contents_by_file = _read_requirements_files(requirement_files)
    _ensure(
        len(contents_by_file) > 0,
        "Nie znaleziono żadnych plików requirements do weryfikacji",
    )

    def _find_dependency(dep_name: str) -> list[str]:
        return [
            file_name
            for file_name, content in contents_by_file.items()
            if dep_name in content
        ]

    pygithub_in = _find_dependency("PyGithub")
    hfhub_in = _find_dependency("huggingface_hub")

    _ensure(
        len(pygithub_in) > 0,
        "PyGithub nie jest zadeklarowany w żadnym aktywnym profilu requirements",
    )
    print(f"✅ PyGithub zadeklarowany w: {', '.join(pygithub_in)}")

    _ensure(
        len(hfhub_in) > 0,
        "huggingface_hub nie jest zadeklarowany w żadnym aktywnym profilu requirements",
    )
    print(f"✅ huggingface_hub zadeklarowany w: {', '.join(hfhub_in)}")

    # Sprawdź czy można je zaimportować
    try:
        import importlib

        github_module = importlib.import_module("github")
        _ = getattr(github_module, "__version__", "unknown")
        print("✅ PyGithub można zaimportować")
    except ImportError as exc:
        raise AssertionError("Nie można zaimportować PyGithub") from exc

    try:
        import huggingface_hub

        print(
            f"✅ huggingface_hub można zaimportować (wersja: {huggingface_hub.__version__})"
        )
    except ImportError:
        raise AssertionError("Nie można zaimportować huggingface_hub")

    print("\n✅ SUKCES: Wszystkie zależności są poprawnie zainstalowane")

    # Podsumowanie
    print("\n" + "=" * 80)
    print("PODSUMOWANIE WERYFIKACJI")
    print("=" * 80)
    print("✅ [1/3] Agent może wyszukać biblioteki Python do PDF na GitHub")
    print("✅ [2/3] Agent może wyszukać lekkie modele do sentymentu na Hugging Face")
    print("✅ [3/3] Biblioteki PyGithub i huggingface_hub są zadeklarowane w profilach")
    print("\n🎉 WSZYSTKIE KRYTERIA AKCEPTACJI SPEŁNIONE!")
    print("=" * 80)


if __name__ == "__main__":
    test_kryteria_akceptacji()
