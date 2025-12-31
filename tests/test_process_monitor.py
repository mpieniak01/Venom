"""Testy dla modułu process_monitor - monitorowanie procesów."""

import os
from unittest.mock import Mock, patch

import psutil

from venom_core.services.process_monitor import ProcessMonitor


class TestProcessMonitor:
    """Testy dla ProcessMonitor."""

    def test_initialization(self, tmp_path):
        """Test inicjalizacji monitora."""
        # Arrange & Act
        monitor = ProcessMonitor(tmp_path)

        # Assert
        assert monitor.project_root == tmp_path

    def test_read_pid_from_file_exists(self, tmp_path):
        """Test odczytu PID z istniejącego pliku."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("12345")

        # Act
        result = monitor.read_pid_from_file(pid_file)

        # Assert
        assert result == 12345

    def test_read_pid_from_file_not_exists(self, tmp_path):
        """Test odczytu PID gdy plik nie istnieje."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        pid_file = tmp_path / "nonexistent.pid"

        # Act
        result = monitor.read_pid_from_file(pid_file)

        # Assert
        assert result is None

    def test_read_pid_from_file_empty(self, tmp_path):
        """Test odczytu PID z pustego pliku."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        pid_file = tmp_path / "empty.pid"
        pid_file.write_text("")

        # Act
        result = monitor.read_pid_from_file(pid_file)

        # Assert
        assert result is None

    def test_read_pid_from_file_invalid(self, tmp_path):
        """Test odczytu PID z nieprawidłowego pliku."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        pid_file = tmp_path / "invalid.pid"
        pid_file.write_text("not_a_number")

        # Act
        result = monitor.read_pid_from_file(pid_file)

        # Assert
        assert result is None

    def test_read_last_log_line_exists(self, tmp_path):
        """Test odczytu ostatniej linii logu."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        log_file = tmp_path / "test.log"
        log_file.write_text("Line 1\nLine 2\nLine 3")

        # Act
        result = monitor.read_last_log_line(log_file, max_lines=2)

        # Assert
        assert result == "Line 2 | Line 3"

    def test_read_last_log_line_not_exists(self, tmp_path):
        """Test odczytu logu gdy plik nie istnieje."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        log_file = tmp_path / "nonexistent.log"

        # Act
        result = monitor.read_last_log_line(log_file)

        # Assert
        assert result is None

    def test_read_last_log_line_empty(self, tmp_path):
        """Test odczytu pustego pliku logu."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        log_file = tmp_path / "empty.log"
        log_file.write_text("")

        # Act
        result = monitor.read_last_log_line(log_file)

        # Assert
        assert result is None

    def test_is_process_running_current_process(self, tmp_path):
        """Test sprawdzania czy bieżący proces działa."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        current_pid = os.getpid()

        # Act
        result = monitor.is_process_running(current_pid)

        # Assert
        assert result is True

    def test_is_process_running_nonexistent(self, tmp_path):
        """Test sprawdzania nieistniejącego procesu."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        # Użyj bardzo wysokiego PID który prawdopodobnie nie istnieje
        fake_pid = 999999

        # Act
        result = monitor.is_process_running(fake_pid)

        # Assert
        assert result is False

    @patch("psutil.Process")
    def test_get_process_info_success(self, mock_process_class, tmp_path):
        """Test pobierania informacji o procesie (success)."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.cpu_percent.return_value = 25.5
        mock_memory = Mock()
        mock_memory.rss = 100 * 1024 * 1024  # 100 MB
        mock_process.memory_info.return_value = mock_memory
        mock_process.create_time.return_value = 1000.0
        mock_process_class.return_value = mock_process

        # Mock time.time
        with patch("time.time", return_value=2000.0):
            # Act
            result = monitor.get_process_info(12345)

        # Assert
        assert result is not None
        assert result["cpu_percent"] == 25.5
        assert result["memory_mb"] == 100.0
        assert result["uptime_seconds"] == 1000

    @patch("psutil.Process")
    def test_get_process_info_not_running(self, mock_process_class, tmp_path):
        """Test pobierania informacji o procesie który nie działa."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        mock_process = Mock()
        mock_process.is_running.return_value = False
        mock_process_class.return_value = mock_process

        # Act
        result = monitor.get_process_info(12345)

        # Assert
        assert result is None

    @patch("psutil.Process")
    def test_get_process_info_no_such_process(self, mock_process_class, tmp_path):
        """Test pobierania informacji gdy proces nie istnieje."""
        # Arrange
        monitor = ProcessMonitor(tmp_path)
        mock_process_class.side_effect = psutil.NoSuchProcess(12345)

        # Act
        result = monitor.get_process_info(12345)

        # Assert
        assert result is None
