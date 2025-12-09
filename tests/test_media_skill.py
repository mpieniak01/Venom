"""Testy jednostkowe dla MediaSkill."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from venom_core.execution.skills.media_skill import MediaSkill


@pytest.fixture
def temp_assets_dir():
    """Fixture dla tymczasowego katalogu assets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_media_skill_initialization(temp_assets_dir):
    """Test inicjalizacji MediaSkill."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    assert skill.assets_dir == Path(temp_assets_dir)
    assert skill.assets_dir.exists()
    assert skill.service in ["placeholder", "openai", "local-sd"]


@pytest.mark.asyncio
async def test_generate_placeholder_image(temp_assets_dir):
    """Test generowania placeholdera obrazu."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    skill.service = "placeholder"  # Force placeholder mode

    result = await skill.generate_image(
        prompt="Test logo for app",
        size="512x512",
        filename="test_logo.png",
    )

    # Sprawdź czy plik został utworzony
    assert Path(result).exists()
    assert "test_logo.png" in result

    # Sprawdź czy to prawidłowy obraz
    img = Image.open(result)
    assert img.size == (512, 512)
    assert img.mode == "RGB"


@pytest.mark.asyncio
async def test_generate_image_invalid_size(temp_assets_dir):
    """Test generowania obrazu z nieprawidłowym rozmiarem."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    skill.service = "placeholder"

    result = await skill.generate_image(
        prompt="Test", size="invalid", filename="test.png"
    )

    # Powinien użyć domyślnego rozmiaru 1024x1024
    assert Path(result).exists()
    img = Image.open(result)
    assert img.size == (1024, 1024)


@pytest.mark.asyncio
async def test_resize_image(temp_assets_dir):
    """Test zmiany rozmiaru obrazu."""
    skill = MediaSkill(assets_dir=temp_assets_dir)

    # Najpierw stwórz testowy obraz
    test_img_path = Path(temp_assets_dir) / "original.png"
    img = Image.new("RGB", (1000, 1000), color="red")
    img.save(test_img_path)

    # Zmień rozmiar
    result = await skill.resize_image(
        image_path=str(test_img_path),
        width=500,
        height=500,
        output_name="resized.png",
    )

    # Sprawdź rezultat
    assert Path(result).exists()
    resized_img = Image.open(result)
    assert resized_img.size == (500, 500)


@pytest.mark.asyncio
async def test_resize_nonexistent_image(temp_assets_dir):
    """Test zmiany rozmiaru nieistniejącego obrazu."""
    skill = MediaSkill(assets_dir=temp_assets_dir)

    with pytest.raises(FileNotFoundError):
        await skill.resize_image(
            image_path="/nonexistent/image.png",
            width=100,
            height=100,
        )


@pytest.mark.asyncio
async def test_list_assets(temp_assets_dir):
    """Test listowania assetów."""
    skill = MediaSkill(assets_dir=temp_assets_dir)

    # Stwórz kilka testowych plików
    (Path(temp_assets_dir) / "logo.png").write_text("test")
    (Path(temp_assets_dir) / "icon.png").write_text("test")

    result = await skill.list_assets()

    assert "logo.png" in result
    assert "icon.png" in result
    assert "KB" in result


@pytest.mark.asyncio
async def test_list_assets_empty_dir(temp_assets_dir):
    """Test listowania pustego katalogu."""
    skill = MediaSkill(assets_dir=temp_assets_dir)

    result = await skill.list_assets()
    assert "Brak wygenerowanych assetów" in result


@pytest.mark.asyncio
async def test_generate_image_with_dalle_fallback(temp_assets_dir):
    """Test generowania obrazu z DALL-E z fallbackiem."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    skill.service = "openai"
    skill.openai_available = False  # Symuluj brak OpenAI

    # Powinien użyć fallback (placeholder)
    result = await skill.generate_image(
        prompt="Test logo",
        size="512x512",
        filename="dalle_test.png",
    )

    assert Path(result).exists()
    assert "png" in result


@pytest.mark.asyncio
async def test_generate_image_auto_filename(temp_assets_dir):
    """Test generowania obrazu z automatyczną nazwą pliku."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    skill.service = "placeholder"

    result = await skill.generate_image(
        prompt="Test",
        size="256x256",
        filename="",  # Brak nazwy - użyj timestampu
    )

    assert Path(result).exists()
    assert "placeholder_" in result or "dalle_" in result
    assert result.endswith(".png")


@pytest.mark.asyncio
async def test_resize_image_auto_output_name(temp_assets_dir):
    """Test zmiany rozmiaru z automatyczną nazwą."""
    skill = MediaSkill(assets_dir=temp_assets_dir)

    # Stwórz testowy obraz
    test_img_path = Path(temp_assets_dir) / "test.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(test_img_path)

    # Zmień rozmiar bez podania nazwy wyjściowej
    result = await skill.resize_image(
        image_path=str(test_img_path),
        width=50,
        height=50,
        output_name="",
    )

    assert Path(result).exists()
    assert "50x50" in result


@pytest.mark.asyncio
async def test_stable_diffusion_unavailable_fallback(temp_assets_dir):
    """Test fallbacku gdy Stable Diffusion jest niedostępny."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    skill.service = "local-sd"
    skill.openai_available = False  # Wyłącz DALL-E

    # SD jest niedostępny, więc powinien użyć placeholder
    result = await skill.generate_image(
        prompt="Test image",
        size="256x256",
        filename="sd_test.png",
    )

    assert Path(result).exists()
    # Powinien wygenerować placeholder
    img = Image.open(result)
    assert img.size == (256, 256)


@pytest.mark.asyncio
async def test_generate_image_service_priority(temp_assets_dir):
    """Test priorytetu serwisów generowania (Local First)."""
    skill = MediaSkill(assets_dir=temp_assets_dir)
    skill.service = "local-sd"  # Priorytet: Stable Diffusion
    skill.openai_available = False

    result = await skill.generate_image(
        prompt="Priority test",
        size="512x512",
        filename="priority_test.png",
    )

    # Powinien spróbować SD (ale fallback do placeholder bo SD niedostępny)
    assert Path(result).exists()
    assert result.endswith(".png")


@pytest.mark.asyncio
async def test_stable_diffusion_method_returns_none_on_error(temp_assets_dir):
    """Test że _generate_with_stable_diffusion zwraca None przy błędzie."""
    skill = MediaSkill(assets_dir=temp_assets_dir)

    # Wywołaj bezpośrednio metodę SD (która nie ma dostępu do API)
    result = await skill._generate_with_stable_diffusion(
        "test prompt", "512x512", "test.png"
    )

    # Powinien zwrócić None bo API niedostępny
    assert result is None
