from pathlib import Path

import djen_monitor.paths as paths


def test_windows_app_data_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    result = paths.app_data_dir()
    assert result == tmp_path / "LocalAppData" / "DJEN Monitor"
    assert result.is_dir()


def test_macos_app_data_uses_application_support(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    result = paths.app_data_dir()
    assert result == tmp_path / "Library" / "Application Support" / "DJEN Monitor"
    assert result.is_dir()


def test_macos_reports_use_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    result = paths.reports_dir()
    assert result == tmp_path / "Documents" / "DJEN Monitor"
    assert result.is_dir()
