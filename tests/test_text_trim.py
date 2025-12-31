"""Testy dla modułu text - pomocnicze funkcje tekstowe."""

import pytest

from venom_core.utils.text import trim_to_char_limit


class TestTrimToCharLimit:
    """Testy dla funkcji trim_to_char_limit."""

    def test_trim_below_limit(self):
        """Test obcinania gdy tekst jest krótszy niż limit."""
        # Arrange
        text = "Krótki tekst"
        limit = 100

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == text
        assert was_trimmed is False

    def test_trim_exact_limit(self):
        """Test gdy tekst ma dokładnie limit znaków."""
        # Arrange
        text = "12345"
        limit = 5

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == text
        assert was_trimmed is False

    def test_trim_above_limit(self):
        """Test obcinania gdy tekst jest dłuższy niż limit."""
        # Arrange
        text = "To jest bardzo długi tekst który przekracza limit"
        limit = 20

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == "To jest bardzo długi"
        assert len(result) == 20
        assert was_trimmed is True

    def test_trim_zero_limit(self):
        """Test z limitem równym zero."""
        # Arrange
        text = "Jakiś tekst"
        limit = 0

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == ""
        assert was_trimmed is True

    def test_trim_negative_limit(self):
        """Test z limitem ujemnym."""
        # Arrange
        text = "Jakiś tekst"
        limit = -5

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == ""
        assert was_trimmed is True

    def test_trim_empty_text(self):
        """Test z pustym tekstem."""
        # Arrange
        text = ""
        limit = 100

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == ""
        assert was_trimmed is False

    def test_trim_none_text(self):
        """Test z None jako tekstem."""
        # Arrange
        text = None
        limit = 100

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result is None
        assert was_trimmed is False

    def test_trim_unicode_text(self):
        """Test z tekstem zawierającym znaki unicode."""
        # Arrange
        text = "Zażółć gęślą jaźń 🎉"
        limit = 10

        # Act
        result, was_trimmed = trim_to_char_limit(text, limit)

        # Assert
        assert result == "Zażółć gęś"
        assert len(result) == 10
        assert was_trimmed is True
