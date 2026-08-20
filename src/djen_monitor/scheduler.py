from __future__ import annotations

import base64
import getpass
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from .constants import LAUNCHD_LABEL_MACOS, TASK_NAME_WINDOWS
from .paths import app_data_dir, log_dir, stable_bin_dir


class SchedulerError(RuntimeError):
    pass


def refresh_scheduled_binary() -> None:
    """Atualiza a cópia estável usada pelo agendador sem recriar a tarefa."""
    if not bool(getattr(sys, "frozen", False)):
        return
    if platform.system() in {"Windows", "Darwin"}:
        _stable_command()


def install_daily_schedule(horario: str) -> str:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise SchedulerError("O agendamento automático está disponível no Windows e macOS.")

    command = _stable_command()
    if system == "Windows":
        message = _install_windows(horario, command)
    else:
        message = _install_macos(horario, command)

    _write_marker(horario, system)
    return message


def remove_daily_schedule() -> str:
    system = platform.system()
    if system == "Windows":
        _remove_windows()
    elif system == "Darwin":
        _remove_macos()
    else:
        raise SchedulerError("O agendamento automático está disponível no Windows e macOS.")

    _remove_marker()
    return "Agendamento removido."


def schedule_exists() -> bool:
    system = platform.system()
    if system == "Windows":
        try:
            task = _ps_single_quote(TASK_NAME_WINDOWS)
            result = _run_hidden([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                f"if (Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
            ])
            return result.returncode == 0
        except Exception:
            # O marcador nunca substitui a verificação real quando o PowerShell
            # respondeu. Ele serve apenas como fallback se o próprio PowerShell
            # não puder ser iniciado.
            return _marker_path().exists()

    if system == "Darwin":
        plist = _macos_plist_path()
        if not plist.exists():
            return False
        try:
            result = subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL_MACOS}"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except OSError:
            # Se launchctl não puder ser invocado, a presença do plist é o
            # melhor fallback local disponível.
            return plist.exists()

    return False


def _stable_command() -> list[str]:
    frozen = bool(getattr(sys, "frozen", False))
    system = platform.system()
    if frozen:
        source = Path(sys.executable).resolve()
        filename = "DJEN Monitor.exe" if system == "Windows" else "DJEN Monitor"
        target = stable_bin_dir() / filename
        try:
            if source != target.resolve():
                temp = target.with_name(target.name + ".novo")
                shutil.copy2(source, temp)
                if system == "Darwin":
                    temp.chmod(0o755)
                os.replace(temp, target)
        except OSError as exc:
            raise SchedulerError(f"Não foi possível instalar a cópia usada pelo agendamento: {exc}") from exc
        return [str(target), "--automatico"]

    # Modo de desenvolvimento. As Releases usam binário empacotado.
    return [sys.executable, "-m", "djen_monitor", "--automatico"]


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL_MACOS}.plist"


def _install_macos(horario: str, command: list[str]) -> str:
    hh, mm = [int(value) for value in horario.split(":")]
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    logs = log_dir()
    payload = {
        "Label": LAUNCHD_LABEL_MACOS,
        "ProgramArguments": command,
        "StartCalendarInterval": {"Hour": hh, "Minute": mm},
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "launchd.out.log"),
        "StandardErrorPath": str(logs / "launchd.err.log"),
    }
    temp = plist.with_suffix(".plist.tmp")

    try:
        with temp.open("wb") as handle:
            plistlib.dump(payload, handle, sort_keys=False)
        os.replace(temp, plist)

        domain = f"gui/{os.getuid()}"
        # bootout pode falhar legitimamente quando não havia tarefa carregada.
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist)],
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            ["launchctl", "bootstrap", domain, str(plist)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SchedulerError((result.stderr or result.stdout or "launchctl bootstrap falhou").strip())
        if not schedule_exists():
            raise SchedulerError("O macOS não confirmou o carregamento do agendamento.")
        return f"Consulta diária agendada para {horario}."
    except OSError as exc:
        raise SchedulerError(f"Não foi possível configurar o launchd: {exc}") from exc
    finally:
        temp.unlink(missing_ok=True)


def _remove_macos() -> None:
    plist = _macos_plist_path()
    domain = f"gui/{os.getuid()}"
    if plist.exists():
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist)],
            capture_output=True,
            text=True,
        )
        try:
            plist.unlink()
        except OSError as exc:
            raise SchedulerError(f"Não foi possível remover o agendamento do macOS: {exc}") from exc


def _build_windows_registration_script(horario: str, command: list[str], result_file: Path) -> str:
    exe = command[0]
    args = " ".join(command[1:])
    user = _windows_current_user()
    hh, mm = [int(value) for value in horario.split(":")]
    task = _ps_single_quote(TASK_NAME_WINDOWS)
    exe_q = _ps_single_quote(exe)
    args_q = _ps_single_quote(args)
    user_q = _ps_single_quote(user)
    result_q = _ps_single_quote(str(result_file))

    # Explicitamos bateria, execução atrasada, reinício após falha e instância
    # única. A rede é tratada pelo próprio cliente HTTP; não condicionamos a
    # tarefa a um perfil de rede do Windows.
    return f'''$ErrorActionPreference = "Stop"
try {{
  $action = New-ScheduledTaskAction -Execute '{exe_q}' -Argument '{args_q}'
  $at = [datetime]::Today.AddHours({hh}).AddMinutes({mm})
  $trigger = New-ScheduledTaskTrigger -Daily -At $at
  $principal = New-ScheduledTaskPrincipal -UserId '{user_q}' -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
  Register-ScheduledTask -TaskName '{task}' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

  $check = Get-ScheduledTask -TaskName '{task}' -ErrorAction Stop
  $actualExe = [string]$check.Actions[0].Execute
  $actualArgs = [string]$check.Actions[0].Arguments
  if ($actualExe -ne '{exe_q}') {{ throw "Executavel registrado difere do esperado: $actualExe" }}
  if ($actualArgs -ne '{args_q}') {{ throw "Argumentos registrados diferem do esperado: $actualArgs" }}

  Set-Content -LiteralPath '{result_q}' -Value "OK" -Encoding UTF8
}} catch {{
  Set-Content -LiteralPath '{result_q}' -Value ("ERRO: " + $_.Exception.Message) -Encoding UTF8
  exit 1
}}
'''


def _install_windows(horario: str, command: list[str]) -> str:
    result_file = app_data_dir() / "agendamento_windows.result"
    result_file.unlink(missing_ok=True)
    script = _build_windows_registration_script(horario, command, result_file)

    # Primeiro tenta no contexto normal do usuário. Se o Windows negar a
    # criação, repete com UAC. Nenhuma senha é lida ou armazenada pelo app.
    direct = _run_powershell_direct(script)
    status = _read_result_file(result_file)
    if direct.returncode != 0 or not status.startswith("OK"):
        result_file.unlink(missing_ok=True)
        _run_powershell_elevated(script)
        status = _read_result_file(result_file)
    result_file.unlink(missing_ok=True)
    if not status.startswith("OK"):
        raise SchedulerError(status or "O Windows não confirmou a criação do agendamento.")
    return f"Consulta diária agendada para {horario}."


def _build_windows_removal_script(result_file: Path) -> str:
    task = _ps_single_quote(TASK_NAME_WINDOWS)
    result_q = _ps_single_quote(str(result_file))
    return f'''$ErrorActionPreference = "Stop"
try {{
  Unregister-ScheduledTask -TaskName '{task}' -Confirm:$false -ErrorAction SilentlyContinue
  Set-Content -LiteralPath '{result_q}' -Value "OK" -Encoding UTF8
}} catch {{
  Set-Content -LiteralPath '{result_q}' -Value ("ERRO: " + $_.Exception.Message) -Encoding UTF8
  exit 1
}}
'''


def _remove_windows() -> None:
    result_file = app_data_dir() / "agendamento_windows.result"
    result_file.unlink(missing_ok=True)
    script = _build_windows_removal_script(result_file)
    direct = _run_powershell_direct(script)
    status = _read_result_file(result_file)
    if direct.returncode != 0 or not status.startswith("OK"):
        result_file.unlink(missing_ok=True)
        _run_powershell_elevated(script)
        status = _read_result_file(result_file)
    result_file.unlink(missing_ok=True)
    if not status.startswith("OK"):
        raise SchedulerError(status or "O Windows não confirmou a remoção do agendamento.")


def _windows_current_user() -> str:
    domain = os.environ.get("USERDOMAIN", "").strip()
    username = os.environ.get("USERNAME", "").strip() or getpass.getuser().strip()
    if domain and username:
        return f"{domain}\\{username}"
    if username:
        return username
    raise SchedulerError("Não foi possível identificar o usuário atual do Windows.")


def _run_powershell_direct(script: str) -> subprocess.CompletedProcess[str]:
    payload = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return _run_hidden([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", payload,
    ])


def _run_powershell_elevated(script: str) -> None:
    payload = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    outer = (
        "$p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru "
        f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','{payload}'); "
        "exit $p.ExitCode"
    )
    result = _run_hidden([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", outer,
    ])
    if result.returncode != 0:
        raise SchedulerError(
            (result.stderr or result.stdout or "A elevação do Windows foi cancelada ou falhou.").strip()
        )


def _run_hidden(command: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs = {"capture_output": True, "text": True}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(command, **kwargs)  # type: ignore[arg-type]


def _read_result_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace").strip()


def _ps_single_quote(value: str) -> str:
    return str(value).replace("'", "''")


def _marker_path() -> Path:
    return app_data_dir() / "agendamento.json"


def _write_marker(horario: str, system: str) -> None:
    _marker_path().write_text(
        json.dumps({"horario": horario, "sistema": system}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remove_marker() -> None:
    _marker_path().unlink(missing_ok=True)
