"""Testy dla modułu flow_router - routing zadań do flow."""

from unittest.mock import Mock

import pytest

from venom_core.core.flow_router import FlowRouter


class TestFlowRouter:
    """Testy dla FlowRouter."""

    def test_initialization_without_council(self):
        """Test inicjalizacji routera bez council flow."""
        # Arrange & Act
        router = FlowRouter()

        # Assert
        assert router._council_flow is None

    def test_initialization_with_council(self):
        """Test inicjalizacji routera z council flow."""
        # Arrange
        mock_council = Mock()

        # Act
        router = FlowRouter(council_flow=mock_council)

        # Assert
        assert router._council_flow is mock_council

    def test_should_use_council_no_council_flow(self):
        """Test should_use_council gdy brak council flow."""
        # Arrange
        router = FlowRouter()

        # Act
        result = router.should_use_council("test context", "test_intent")

        # Assert
        assert result is False

    def test_should_use_council_with_council_flow_true(self):
        """Test should_use_council gdy council flow zwraca True."""
        # Arrange
        mock_council = Mock()
        mock_council.should_use_council.return_value = True
        router = FlowRouter(council_flow=mock_council)

        # Act
        result = router.should_use_council("complex task", "analyze_code")

        # Assert
        assert result is True
        mock_council.should_use_council.assert_called_once_with(
            "complex task", "analyze_code"
        )

    def test_should_use_council_with_council_flow_false(self):
        """Test should_use_council gdy council flow zwraca False."""
        # Arrange
        mock_council = Mock()
        mock_council.should_use_council.return_value = False
        router = FlowRouter(council_flow=mock_council)

        # Act
        result = router.should_use_council("simple task", "chat")

        # Assert
        assert result is False

    def test_set_council_flow(self):
        """Test ustawiania council flow."""
        # Arrange
        router = FlowRouter()
        mock_council = Mock()

        # Act
        router.set_council_flow(mock_council)

        # Assert
        assert router._council_flow is mock_council

    def test_determine_flow_without_council(self):
        """Test determine_flow bez council."""
        # Arrange
        router = FlowRouter()

        # Act
        flow_name, metadata = router.determine_flow("test context", "chat")

        # Assert
        assert isinstance(flow_name, str)
        assert isinstance(metadata, dict)

    def test_determine_flow_with_council_enabled(self):
        """Test determine_flow z włączonym council."""
        # Arrange
        mock_council = Mock()
        mock_council.should_use_council.return_value = True
        router = FlowRouter(council_flow=mock_council)

        # Act
        flow_name, metadata = router.determine_flow("complex task", "analyze")

        # Assert
        mock_council.should_use_council.assert_called_once()
        assert isinstance(flow_name, str)
        assert isinstance(metadata, dict)

    def test_determine_flow_with_council_disabled(self):
        """Test determine_flow z wyłączonym council."""
        # Arrange
        mock_council = Mock()
        mock_council.should_use_council.return_value = False
        router = FlowRouter(council_flow=mock_council)

        # Act
        flow_name, metadata = router.determine_flow("simple task", "chat")

        # Assert
        assert isinstance(flow_name, str)
        assert isinstance(metadata, dict)
