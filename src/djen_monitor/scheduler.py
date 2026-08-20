from __future__ import annotations

import base64
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .constants import TASK_NAME_WINDOWS
from .paths import app_data_dir, stable_bin_dir


class SchedulerError(RuntimeError):
    pass


def refresh_scheduled_binary() -> None:
    """Atualiza a cópia estavel usada pelo Agendador sem recriar a tarefa."""
    if platform.system() != "Windows" or not bool(getattr(sys, "frozen", False)):
        return
    _stable_command()


def install_daily_schedule(horario: str) -> str:
    if platform.system() != "Windows":
        raise SchedulerError("O agendamento automatico desta versão esta disponivel somente no Windows.")
    command = _stable_command()
    message = _install_windows(horario, command)
    _write_marker(horario)
    return message


def remove_daily_schedule() -> str:
    if platform.system() != "Windows":
        raise SchedulerError("O agendamento automatico desta versão esta disponivel somente no Windows.")
    _remove_windows()
    _remove_marker()
    return "Agendamento removido."


def schedule_exists() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        task = _ps_single_quote(TASK_NAME_WINDOWS)
        result = _run_hidden([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"if (Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ])
        return result.returncode == 0
    except Exception:
        # O marcador nunca substitui a verificacao real quando o PowerShell
        # respondeu. Ele serve apenas como fallback se o próprio PowerShell
        # nao puder ser iniciado.
        return _marker_path().exists()


def _stable_command() -> list[str]:
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        source = Path(sys.executable).resolve()
        target = stable_bin_dir() / "DJEN Monitor.exe"
        try:
            if source != target.resolve():
                temp = target.with_name(target.name + ".novo")
                shutil.copy2(source, temp)
                os.replace(temp, target)
        except OSError as exc:
            raise SchedulerError(f"Não foi possível instalar a cópia usada pelo agendamento: {exc}") from exc
        return [str(target), "--automatico"]

    # Modo de desenvolvimento. A Release para o usuário sempre usa o .exe.
    return [sys.executable, "-m", "djen_monitor", "--automatico"]


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

    # Explicitamos bateria, execução atrasada, reinicio apos falha e instancia
    # única. A rede e tratada pelo próprio cliente HTTP; não condicionamos a
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
    # criação, repete com UAC. Nenhuma senha e lida ou armazenada pelo app.
    direct = _run_powershell_direct(script)
    status = _read_result_file(result_file)
    if direct.returncode != 0 or not status.startswith("OK"):
        result_file.unlink(missing_ok=True)
        _run_powershell_elevated(script)
        status = _read_result_file(result_file)
    result_file.unlink(missing_ok=True)
    if not status.startswith("OK"):
        raise SchedulerError(status or "O Windows nao confirmou a criação do agendamento.")
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
        raise SchedulerError(status or "O Windows nao confirmou a remoção do agendamento.")


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


def _write_marker(horario: str) -> None:
    _marker_path().write_text(
        json.dumps({"horario": horario, "sistema": "Windows"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remove_marker() -> None:
    _marker_path().unlink(missing_ok=True)
