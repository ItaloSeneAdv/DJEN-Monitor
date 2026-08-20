from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .api import DJENAPIError, DJENClient
from .config import AppConfig, OABConfig, load_config, save_config, valid_time
from .constants import APP_NAME, APP_VERSION, DEFAULT_TIME, DEFAULT_WINDOW_DAYS
from .logging_setup import setup_logging
from .paths import config_path, last_report_path, log_dir, reports_dir
from .runner import run_monitor
from .scheduler import (
    SchedulerError,
    install_daily_schedule,
    refresh_scheduled_binary,
    remove_daily_schedule,
    schedule_exists,
)
from .storage import PublicationStore
from .time_utils import brasilia_now, brasilia_today, format_datetime_ptbr


def format_oab(item: OABConfig) -> str:
    base = f"{item.numero}/{item.uf}"
    return f"{item.nome} ({base})" if item.nome else base


def interactive_main() -> int:
    setup_logging(verbose_console=False)
    try:
        cfg = load_config()
    except Exception as exc:
        cfg_file = config_path()
        backup = cfg_file.with_name(f"config_corrompida_{brasilia_now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            cfg_file.replace(backup)
            clear_screen()
            print(f"A configuração estava inválida e foi preservada em:\n{backup}")
            print(f"Detalhe: {exc}")
            pause("Pressione ENTER para refazer a configuração.")
        except Exception:
            pass
        cfg = None

    if cfg is None:
        cfg = first_run_setup()
    elif schedule_exists():
        try:
            refresh_scheduled_binary()
        except SchedulerError as exc:
            clear_screen()
            print("ATENÇÃO: o agendamento está ativo, mas a cópia automática não pôde ser atualizada.")
            print(f"Detalhe: {exc}")
            print("Use a opção AGENDAMENTO para reativar/atualizar a tarefa.")
            pause()

    while True:
        clear_screen()
        print_header(cfg)
        print(" [1] CONSULTAR AGORA")
        print(" [2] CONFIGURAÇÕES")
        print(" [3] AGENDAMENTO")
        print(" [4] ABRIR PLANILHAS")
        print(" [5] AJUDA / DIAGNÓSTICO")
        print(" [0] SAIR")
        print()
        option = input("Escolha: ").strip()
        if option == "1":
            do_manual_run(cfg)
        elif option == "2":
            cfg = configuration_menu(cfg)
        elif option == "3":
            cfg = schedule_menu(cfg)
        elif option == "4":
            open_reports_folder()
            pause("Pasta de planilhas aberta. Pressione ENTER para voltar.")
        elif option == "5":
            diagnostics_menu(cfg)
        elif option == "0":
            return 0


def first_run_setup() -> AppConfig:
    clear_screen()
    print("=" * 58)
    print(f" {APP_NAME}")
    print(" Configuração inicial")
    print("=" * 58)
    print()
    oabs: list[OABConfig] = []
    while True:
        numero = input("Número da OAB: ").strip()
        uf = input("UF da OAB: ").strip().upper()
        nome = input("Nome/apelido desta OAB (opcional, ENTER para pular): ").strip()
        try:
            item = OABConfig(numero=numero, uf=uf, nome=nome).normalized()
            if any(existing.numero == item.numero and existing.uf == item.uf for existing in oabs):
                print(f"OAB {format_oab(item)} já estava cadastrada nesta configuração.")
            else:
                oabs.append(item)
                print(f"OAB {format_oab(item)} adicionada.")
        except ValueError as exc:
            print(f"Erro: {exc}")
            continue
        if input("Adicionar outra OAB? [s/N]: ").strip().lower() not in {"s", "sim", "y", "yes"}:
            break

    janela = ask_int(f"Janela de busca em dias [{DEFAULT_WINDOW_DAYS}]: ", DEFAULT_WINDOW_DAYS, 1, 3650)
    horario = ask_time(f"Horário diário [{DEFAULT_TIME}]: ", DEFAULT_TIME)
    cfg = AppConfig(oabs=oabs, janela_dias=janela, horario=horario, agendamento_ativo=False)
    save_config(cfg)

    wants_schedule = input("Deseja ativar a consulta automática diária agora? [S/n]: ").strip().lower()
    if wants_schedule not in {"n", "não", "nao", "no"}:
        try:
            install_daily_schedule(horario)
            cfg.agendamento_ativo = True
            save_config(cfg)
            print(f"Agendamento criado para {horario}.")
        except SchedulerError as exc:
            print(f"Não foi possível criar o agendamento: {exc}")
            print("Você pode tentar novamente pelo menu Agendamento.")
    pause("Configuração salva. Pressione ENTER para abrir o menu.")
    return cfg


def print_header(cfg: AppConfig) -> None:
    oabs = ", ".join(format_oab(o) for o in cfg.oabs)
    status = f"ATIVO às {cfg.horario}" if schedule_exists() else "DESATIVADO"
    last_text = "Nunca executado"
    try:
        with PublicationStore() as store:
            last = store.last_execution()
        if last:
            finished_at = format_datetime_ptbr(last.get("finished_at"))
            last_text = f"{finished_at} | novas: {last['total_new']} | atualizadas: {last['total_updated']}"
    except Exception:
        pass

    print("=" * 72)
    print(f" {APP_NAME} v{APP_VERSION}")
    print(f" OABs: {oabs}")
    print(f" Busca: últimos {cfg.janela_dias} dia(s) no mínimo")
    print(f" Automático: {status}")
    print(f" Última consulta: {last_text}")
    print("=" * 72)
    print()


def do_manual_run(cfg: AppConfig) -> None:
    clear_screen()
    print("Consultando o DJEN...")
    print("Isso pode levar alguns segundos por OAB porque o programa evita excesso de requisições.")
    print()
    result = run_monitor(cfg, manual=True)
    print()
    print("Consulta concluída." if not result.error else "Consulta concluída com falha parcial/erro.")
    print(f"Período: {result.start_date} a {result.end_date}")
    print(f"Publicações encontradas na janela: {result.found}")
    print(f"Novas publicações: {result.new}")
    print(f"Publicações atualizadas/reprocessadas: {result.updated}")
    print(f"Requisições ao DJEN: {result.requests_made}")
    if result.error:
        print("ATENÇÃO:")
        print(result.error)
    if not result.complete:
        print("ATENÇÃO: a coleta pode estar incompleta. Confira o RESUMO da planilha e a mensagem acima.")
    if result.report_path:
        print(f"Planilha: {result.report_path}")
    pause()


def configuration_menu(cfg: AppConfig) -> AppConfig:
    while True:
        clear_screen()
        print("CONFIGURAÇÕES")
        print()
        for idx, item in enumerate(cfg.oabs, 1):
            print(f" OAB {idx}: {format_oab(item)}")
        print()
        print(" [1] Adicionar OAB")
        print(" [2] Alterar nome/apelido de uma OAB")
        print(" [3] Remover OAB")
        print(" [4] Alterar janela de busca")
        print(" [5] Ativar/desativar variantes de OAB")
        print(" [6] Ver arquivo de configuração")
        print(" [0] Voltar")
        option = input("Escolha: ").strip()

        if option == "1":
            numero = input("Número da OAB: ").strip()
            uf = input("UF: ").strip().upper()
            nome = input("Nome/apelido (opcional, ENTER para pular): ").strip()
            try:
                item = OABConfig(numero=numero, uf=uf, nome=nome).normalized()
                if any(existing.numero == item.numero and existing.uf == item.uf for existing in cfg.oabs):
                    pause(f"OAB {item.numero}/{item.uf} já está cadastrada. Pressione ENTER.")
                    continue
                cfg.oabs.append(item)
                cfg.validate()
                save_config(cfg)
                pause(f"OAB {format_oab(item)} adicionada. Pressione ENTER.")
            except ValueError as exc:
                pause(f"Erro: {exc}\nPressione ENTER.")

        elif option == "2":
            idx = ask_int("Número da OAB que deseja renomear (0 cancela): ", 0, 0, len(cfg.oabs))
            if idx == 0:
                continue
            item = cfg.oabs[idx - 1]
            atual = item.nome or "sem nome"
            novo = input(f"Nome/apelido atual: {atual}\nNovo nome (ENTER remove/deixa em branco): ").strip()
            try:
                cfg.oabs[idx - 1] = OABConfig(item.numero, item.uf, novo).normalized()
                save_config(cfg)
                pause(f"OAB atualizada: {format_oab(cfg.oabs[idx - 1])}. Pressione ENTER.")
            except ValueError as exc:
                pause(f"Erro: {exc}\nPressione ENTER.")

        elif option == "3":
            if len(cfg.oabs) <= 1:
                pause("É necessário manter pelo menos uma OAB. Pressione ENTER.")
                continue
            idx = ask_int("Número da OAB a remover (0 cancela): ", 0, 0, len(cfg.oabs))
            if idx == 0:
                continue
            removed = cfg.oabs.pop(idx - 1)
            save_config(cfg)
            pause(f"OAB {format_oab(removed)} removida. Pressione ENTER.")

        elif option == "4":
            cfg.janela_dias = ask_int("Nova janela em dias: ", cfg.janela_dias, 1, 3650)
            save_config(cfg)

        elif option == "5":
            cfg.consultar_variantes_oab = not cfg.consultar_variantes_oab
            save_config(cfg)
            state = "ativada" if cfg.consultar_variantes_oab else "desativada"
            pause(f"Busca por variantes {state}. Pressione ENTER.")

        elif option == "6":
            print(config_path())
            try:
                print(config_path().read_text(encoding="utf-8"))
            except Exception as exc:
                print(exc)
            pause()

        elif option == "0":
            return cfg


def schedule_menu(cfg: AppConfig) -> AppConfig:
    while True:
        clear_screen()
        active = schedule_exists()
        print("AGENDAMENTO")
        print(f"Status: {'ATIVO' if active else 'DESATIVADO'}")
        print(f"Horário configurado: {cfg.horario}")
        print()
        print(" [1] Ativar/atualizar agendamento")
        print(" [2] Alterar horário")
        print(" [3] Desativar agendamento")
        print(" [0] Voltar")
        option = input("Escolha: ").strip()
        try:
            if option == "1":
                message = install_daily_schedule(cfg.horario)
                cfg.agendamento_ativo = True
                save_config(cfg)
                pause(message + " Pressione ENTER.")
            elif option == "2":
                novo_horario = ask_time("Novo horário HH:MM: ", cfg.horario)
                if active:
                    install_daily_schedule(novo_horario)
                cfg.horario = novo_horario
                save_config(cfg)
                pause(f"Horário alterado para {cfg.horario}. Pressione ENTER.")
            elif option == "3":
                message = remove_daily_schedule()
                cfg.agendamento_ativo = False
                save_config(cfg)
                pause(message + " Pressione ENTER.")
            elif option == "0":
                return cfg
        except SchedulerError as exc:
            pause(f"Falha no agendamento: {exc}\nPressione ENTER.")


def diagnostics_menu(cfg: AppConfig) -> None:
    while True:
        clear_screen()
        print("AJUDA / DIAGNÓSTICO")
        print()
        print(" [1] Testar conexão com a API do DJEN")
        print(" [2] Abrir pasta de logs")
        print(" [3] Mostrar pastas usadas pelo programa")
        print(" [4] Mostrar versão")
        print(" [0] Voltar")
        option = input("Escolha: ").strip()
        if option == "1":
            oab = cfg.oabs[0]
            print(f"Testando com {format_oab(oab)}...")
            try:
                client = DJENClient(min_interval=0)
                today = brasilia_today()
                result = client.query_oab(oab.numero, oab.uf, today, today, include_variants=False)
                if result.complete:
                    print("Conexão OK e resposta validada.")
                else:
                    print("A API respondeu, mas a validação da coleta ficou INCOMPLETA.")
                print(f"Itens retornados hoje: {len(result.items)}")
                print(f"Requisições: {client.requests_made}")
                for warning in result.errors:
                    print(f"Aviso: {warning}")
            except DJENAPIError as exc:
                print(f"Falha: {exc}")
            pause()
        elif option == "2":
            open_path(log_dir())
            pause()
        elif option == "3":
            print(f"Configuração: {config_path()}")
            print(f"Planilhas: {reports_dir()}")
            print(f"Logs: {log_dir()}")
            pause()
        elif option == "4":
            pause(f"{APP_NAME} v{APP_VERSION}\nPressione ENTER.")
        elif option == "0":
            return


def open_reports_folder() -> None:
    target = reports_dir()
    remembered = last_report_path()
    if remembered and remembered.exists():
        target = remembered.parent
    else:
        try:
            with PublicationStore() as store:
                last = store.last_execution()
            if last and last.get("report_path"):
                report = Path(str(last["report_path"]))
                if report.exists():
                    target = report.parent
        except Exception:
            pass
    open_path(target)


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(path)], check=True)
        else:
            raise OSError("A abertura automática de pastas é suportada no Windows e macOS.")
    except Exception:
        print(f"Abra manualmente: {path}")


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause(message: str = "Pressione ENTER para voltar.") -> None:
    input(message)


def ask_int(prompt: str, default: int, minimum: int, maximum: int) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            value = int(raw)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f"Digite um número entre {minimum} e {maximum}.")


def ask_time(prompt: str, default: str) -> str:
    while True:
        raw = input(prompt).strip() or default
        if valid_time(raw):
            return raw
        print("Horário inválido. Use HH:MM, por exemplo 08:00.")
