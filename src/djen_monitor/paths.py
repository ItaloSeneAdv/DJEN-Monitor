from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path

from .constants import APP_NAME


def app_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / APP_NAME
    elif system == "Darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "djen-monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _windows_documents_dir() -> Path | None:
    if platform.system() != "Windows":
        return None
    try:
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
        guid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        raw_ptr = ctypes.c_void_p()
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None
        result = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(raw_ptr))
        if result != 0 or not raw_ptr.value:
            return None
        try:
            return Path(ctypes.wstring_at(raw_ptr.value))
        finally:
            ole32.CoTaskMemFree(raw_ptr)
    except Exception:
        return None


def reports_dir() -> Path:
    documents = _windows_documents_dir() or (Path.home() / "Documents")
    path = documents / APP_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        return fallback_reports_dir()


def config_path() -> Path:
    return app_data_dir() / "config.json"


def database_path() -> Path:
    return app_data_dir() / "dados.sqlite3"


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stable_bin_dir() -> Path:
    path = app_data_dir() / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fallback_reports_dir() -> Path:
    path = app_data_dir() / "Planilhas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def last_report_marker_path() -> Path:
    return app_data_dir() / "ultima_planilha.txt"


def remember_last_report(path: Path | str) -> None:
    marker = last_report_marker_path()
    temp = marker.with_suffix(".tmp")
    temp.write_text(str(Path(path).resolve()), encoding="utf-8")
    temp.replace(marker)


def last_report_path() -> Path | None:
    marker = last_report_marker_path()
    try:
        if not marker.exists():
            return None
        value = marker.read_text(encoding="utf-8").strip()
        return Path(value) if value else None
    except OSError:
        return None
