import types
from pathlib import Path

import djen_monitor.scheduler as scheduler


def test_powershell_quote_handles_apostrophe():
    assert scheduler._ps_single_quote("C:/Users/D'Ávila/DJEN Monitor") == "C:/Users/D''Ávila/DJEN Monitor"


def test_schedule_exists_checks_native_scheduler_even_without_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Windows")
    monkeypatch.setattr(scheduler, "_marker_path", lambda: tmp_path / "missing-marker.json")
    monkeypatch.setattr(
        scheduler,
        "_run_hidden",
        lambda command: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert scheduler.schedule_exists() is True


def test_windows_registration_script_has_reliability_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "Usuario")
    script = scheduler._build_windows_registration_script(
        "08:15", [r"C:\Users\Usuario\AppData\Local\DJEN Monitor\bin\DJEN Monitor.exe", "--automatico"],
        tmp_path / "resultado.txt",
    )
    assert "-AllowStartIfOnBatteries" in script
    assert "-DontStopIfGoingOnBatteries" in script
    assert "-StartWhenAvailable" in script
    assert "-RunOnlyIfNetworkAvailable" not in script
    assert "-MultipleInstances IgnoreNew" in script
    assert "-RestartCount 3" in script
    assert "-RestartInterval" in script
    assert "--automatico" in script
    assert "08:15" not in script  # horario e convertido em horas/minutos, sem string fragil
    assert "AddHours(8).AddMinutes(15)" in script


def test_scheduler_is_windows_only(monkeypatch):
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Linux")
    assert scheduler.schedule_exists() is False
    try:
        scheduler.install_daily_schedule("08:00")
    except scheduler.SchedulerError as exc:
        assert "Windows" in str(exc)
    else:
        raise AssertionError("Deveria recusar agendamento fora do Windows")
