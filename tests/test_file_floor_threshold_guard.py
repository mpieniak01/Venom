from __future__ import annotations

from pathlib import Path

from scripts import check_file_coverage_floor as mod


def test_load_thresholds_and_success(tmp_path: Path):
    thresholds = tmp_path / "thresholds.txt"
    thresholds.write_text("a.py,40\n", encoding="utf-8")

    xml_path = tmp_path / "cov.xml"
    xml_path.write_text(
        """
<coverage>
  <packages>
    <package>
      <classes>
        <class filename=\"a.py\" line-rate=\"0.50\" />
      </classes>
    </package>
  </packages>
</coverage>
""".strip(),
        encoding="utf-8",
    )

    loaded = mod._load_thresholds(thresholds)
    assert loaded == [("a.py", 40.0)]

    covered = mod._load_coverage_percent_by_file(xml_path)
    assert covered["a.py"] == 50.0


def test_load_thresholds_rejects_invalid_line(tmp_path: Path):
    thresholds = tmp_path / "thresholds.txt"
    thresholds.write_text("invalid-line\n", encoding="utf-8")

    try:
        mod._load_thresholds(thresholds)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Invalid threshold line" in str(exc)
