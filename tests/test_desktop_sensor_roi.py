from venom_core.perception.desktop_sensor import DesktopSensor, PrivacyFilter


def test_privacy_filter_blocks_sensitive():
    assert PrivacyFilter.is_sensitive("password=secret") is True
    assert PrivacyFilter.sanitize("password=secret") == ""


def test_privacy_filter_truncates_long_text():
    text = "x" * 1100
    sanitized = PrivacyFilter.sanitize(text, max_length=1000)
    assert sanitized.endswith("...")
    assert len(sanitized) == 1003


def test_desktop_sensor_status_fields():
    sensor = DesktopSensor(privacy_filter=False)
    sensor._last_clipboard_content = "hello"
    sensor._last_active_window = "Editor"
    status = sensor.get_status()
    assert status["privacy_filter"] is False
    assert status["last_clipboard_length"] == 5
    assert status["last_active_window"] == "Editor"
