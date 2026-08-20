from __future__ import annotations

import argparse
import ctypes
import os
import sys
import logging

from .config import load_config
from .logging_setup import setup_logging
from .runner import run_monitor
from .selftest import run_packaged_self_test, run_stable_copy_self_test
from .ui import interactive_main


def _ensure_windows_console() -> None:
    """Prepara o terminal do Windows para português/UTF-8, inclusive acentos na entrada."""
    if os.name != "nt" or "--automatico" in sys.argv:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow() == 0:
            kernel32.AllocConsole()

        # Não depende do code page herdado do CMD/PowerShell. Isso permite
        # digitar e exibir normalmente nomes como "Ítalo", "João" e "Sêne".
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleTitleW("DJEN Monitor")

        if sys.stdin is None:
            sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        elif hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")

        if sys.stdout is None:
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        elif hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

        if sys.stderr is None:
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        elif hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        # Se um host de terminal exótico não aceitar reconfiguração, o menu
        # continua funcionando com a codificação fornecida pelo próprio host.
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--automatico", action="store_true", help="Executa a consulta sem menu, para o agendador do sistema.")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test-console", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test-stable-copy", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.self_test_console:
        _ensure_windows_console()
        if sys.stdin is None or sys.stdout is None or sys.stderr is None:
            return 91
        try:
            stdin_encoding = str(getattr(sys.stdin, "encoding", "") or "").lower()
            stdout_encoding = str(getattr(sys.stdout, "encoding", "") or "").lower()
            if "utf" not in stdin_encoding or "utf" not in stdout_encoding:
                return 95
            sys.stdout.write("DJEN Monitor console self-test: configuração, João, Ítalo, Sêne, ação.\n")
            sys.stdout.flush()
            run_packaged_self_test()
            return 0
        except Exception:
            return 92

    if args.self_test:
        try:
            run_packaged_self_test()
            return 0
        except Exception:
            return 93

    if args.self_test_stable_copy:
        try:
            run_stable_copy_self_test()
            return 0
        except Exception:
            return 94

    if args.automatico:
        setup_logging(verbose_console=False)
        try:
            cfg = load_config()
        except Exception:
            logging.getLogger("djen_monitor").exception("Configuração inválida na execução automatica")
            return 2
        if cfg is None:
            logging.getLogger("djen_monitor").error("Execução automatica sem configuração cadastrada.")
            return 2
        result = run_monitor(cfg, manual=False)
        return 0 if (not result.error and result.complete) else 1

    _ensure_windows_console()
    if sys.stdin is None or sys.stdout is None or sys.stderr is None:
        return 3
    return interactive_main()
