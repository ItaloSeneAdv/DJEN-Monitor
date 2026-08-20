from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timedelta

import djen_monitor.scheduler as scheduler


def main() -> int:
    if platform.system() != "Windows":
        print("Smoke do Agendador: ignorado fora do Windows.")
        return 0

    original_name = scheduler.TASK_NAME_WINDOWS
    scheduler.TASK_NAME_WINDOWS = f"DJEN Monitor CI Smoke {os.getpid()}"
    result_file = scheduler.app_data_dir() / f"scheduler-ci-{os.getpid()}.result"
    try:
        command = [sys.executable, "-m", "djen_monitor", "--automatico"]
        future = datetime.now() + timedelta(minutes=10)
        horario = future.strftime("%H:%M")
        script = scheduler._build_windows_registration_script(horario, command, result_file)
        result = scheduler._run_powershell_direct(script)
        status = scheduler._read_result_file(result_file)
        if result.returncode != 0 or not status.startswith("OK"):
            raise RuntimeError(f"Falha ao registrar tarefa de teste: {status or result.stderr or result.stdout}")
        if not scheduler.schedule_exists():
            raise RuntimeError("A tarefa foi registrada, mas nao foi encontrada pelo Get-ScheduledTask.")

        result_file.unlink(missing_ok=True)
        removal = scheduler._build_windows_removal_script(result_file)
        result = scheduler._run_powershell_direct(removal)
        status = scheduler._read_result_file(result_file)
        if result.returncode != 0 or not status.startswith("OK"):
            raise RuntimeError(f"Falha ao remover tarefa de teste: {status or result.stderr or result.stdout}")
        if scheduler.schedule_exists():
            raise RuntimeError("A tarefa de teste continuou registrada apos a remocao.")
        print("Smoke do Agendador do Windows: OK")
        return 0
    finally:
        result_file.unlink(missing_ok=True)
        # Melhor esforco para nunca deixar lixo no runner se uma assercao falhar.
        try:
            removal = scheduler._build_windows_removal_script(result_file)
            scheduler._run_powershell_direct(removal)
        except Exception:
            pass
        result_file.unlink(missing_ok=True)
        scheduler.TASK_NAME_WINDOWS = original_name


if __name__ == "__main__":
    raise SystemExit(main())
