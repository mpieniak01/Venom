"""Testy dla modułu code_generation_utils - narzędzia do generowania kodu."""

from venom_core.utils.code_generation_utils import escape_string_for_code


class TestEscapeStringForCode:
    """Testy dla funkcji escape_string_for_code."""

    def test_escape_simple_string(self):
        """Test eskejpowania prostego stringa."""
        # Arrange
        value = "hello"

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "'hello'"

    def test_escape_string_with_single_quote(self):
        """Test eskejpowania stringa z pojedynczym cudzysłowem."""
        # Arrange
        value = "it's"

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == '"it\'s"'

    def test_escape_string_with_double_quote(self):
        """Test eskejpowania stringa z podwójnym cudzysłowem."""
        # Arrange
        value = 'say "hello"'

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "'say \"hello\"'"

    def test_escape_potential_injection(self):
        """Test eskejpowania potencjalnej iniekcji kodu."""
        # Arrange
        value = 'test"; drop table'

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "'test\"; drop table'"
        # Upewnij się że wynik jest poprawnym literalem Pythona i odtwarza oryginalny string
        assert eval(result) == value

    def test_escape_backslash(self):
        """Test eskejpowania backslasha."""
        # Arrange
        value = "path\\to\\file"

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "'path\\\\to\\\\file'"

    def test_escape_newline(self):
        """Test eskejpowania znaku nowej linii."""
        # Arrange
        value = "line1\nline2"

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "'line1\\nline2'"

    def test_escape_tab(self):
        """Test eskejpowania tabulatora."""
        # Arrange
        value = "col1\tcol2"

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "'col1\\tcol2'"

    def test_escape_unicode(self):
        """Test eskejpowania znaków unicode."""
        # Arrange
        value = "Zażółć gęślą jaźń 🎉"

        # Act
        result = escape_string_for_code(value)

        # Assert
        # Python repr() zachowuje znaki Unicode jeśli są printable
        assert result == "'Zażółć gęślą jaźń 🎉'"
        assert result.startswith("'")
        assert result.endswith("'")

    def test_escape_empty_string(self):
        """Test eskejpowania pustego stringa."""
        # Arrange
        value = ""

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert result == "''"

    def test_escape_multiline_string(self):
        """Test eskejpowania wieloliniowego stringa."""
        # Arrange
        value = "line1\nline2\nline3"

        # Act
        result = escape_string_for_code(value)

        # Assert
        assert "\\n" in result
        assert result.startswith("'") or result.startswith('"')
