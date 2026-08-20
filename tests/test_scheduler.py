import plistlib
import types

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
        "08:15",
        [r"C:\Users\Usuario\AppData\Local\DJEN Monitor\bin\DJEN Monitor.exe", "--automatico"],
        tmp_path / "resultado.txt",
    )
    assert "-AllowStartIfOnBatteries" in script
    assert "-DontStopIfGoingOnBatteries" in script
    assert "-StartWhenAvailable" in script
    assert "-RunOnlyIfNetworkAvailable" not in script
    assert "-MultipleInstances IgnoreNew" in script
    assert "-RestartCount 3" in script
    assert "--automatico" in script
    assert "AddHours(8).AddMinutes(15)" in script


def test_macos_install_writes_valid_launchagent(tmp_path, monkeypatch):
    plist = tmp_path / "Library" / "LaunchAgents" / "br.italosene.djenmonitor.plist"
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(scheduler, "_macos_plist_path", lambda: plist)
    monkeypatch.setattr(scheduler, "log_dir", lambda: logs)
    monkeypatch.setattr(scheduler.os, "getuid", lambda: 501, raising=False)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    monkeypatch.setattr(scheduler, "schedule_exists", lambda: True)
    message = scheduler._install_macos("08:15", ["/tmp/DJEN Monitor", "--automatico"])
    assert "08:15" in message
    with plist.open("rb") as handle:
        data = plistlib.load(handle)
    assert data["Label"] == "br.italosene.djenmonitor"
    assert data["ProgramArguments"] == ["/tmp/DJEN Monitor", "--automatico"]
    assert data["StartCalendarInterval"] == {"Hour": 8, "Minute": 15}
    # launchd assume RunAtLoad=false quando a chave é omitida.
    assert data.get("RunAtLoad", False) is False
    assert any(cmd[:2] == ["launchctl", "bootstrap"] for cmd in calls)


def test_macos_schedule_exists_uses_launchctl(tmp_path, monkeypatch):
    plist = tmp_path / "agent.plist"
    plist.write_text("x", encoding="utf-8")
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(scheduler, "_macos_plist_path", lambda: plist)
    monkeypatch.setattr(scheduler.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert scheduler.schedule_exists() is True


def test_linux_scheduler_is_rejected(monkeypatch):
    monkeypatch.setattr(scheduler.platform, "system", lambda: "Linux")
    assert scheduler.schedule_exists() is False
    try:
        scheduler.install_daily_schedule("08:00")
    except scheduler.SchedulerError as exc:
        assert "Windows e macOS" in str(exc)
    else:
        raise AssertionError("Deveria recusar agendamento no Linux")
