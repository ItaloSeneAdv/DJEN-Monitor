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
from .scheduler import SchedulerError, install_daily_schedule, refresh_scheduled_binary, remove_daily_schedule, schedule_exists
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
            cfg_file.replace(backup); clear_screen(); print(f"A configuração estava inválida e foi preservada em:\n{backup}"); print(f"Detalhe: {exc}"); pause("Pressione ENTER para refazer a configuração.")
        except Exception:
            pass
        cfg = None
    if cfg is None:
        cfg = first_run_setup()
    elif schedule_exists():
        try:
            refresh_scheduled_binary()
        except SchedulerError as exc:
            clear_screen(); print("ATENÇÃO: o agendamento está ativo, mas a cópia automática não pôde ser atualizada."); print(f"Detalhe: {exc}"); print("Use a opção AGENDAMENTO para reativar/atualizar a tarefa."); pause()
    while True:
        clear_screen(); print_header(cfg)
        print(" [1] CONSULTAR AGORA\n [2] CONFIGURAÇÕES\n [3] AGENDAMENTO\n [4] ABRIR PLANILHAS\n [5] AJUDA / DIAGNÓSTICO\n [0] SAIR\n")
        option = input("Escolha: ").strip()
        if option == "1": do_manual_run(cfg)
        elif option == "2": cfg = configuration_menu(cfg)
        elif option == "3": cfg = schedule_menu(cfg)
        elif option == "4": open_reports_folder(); pause("Pasta de planilhas aberta. Pressione ENTER para voltar.")
        elif option == "5": diagnostics_menu(cfg)
        elif option == "0": return 0


def first_run_setup() -> AppConfig:
    clear_screen(); print("=" * 58); print(f" {APP_NAME}\n Configuração inicial"); print("=" * 58); print()
    oabs: list[OABConfig] = []
    while True:
        numero = input("Número da OAB: ").strip(); uf = input("UF da OAB: ").strip().upper(); nome = input("Nome/apelido desta OAB (opcional, ENTER para pular): ").strip()
        try:
            item = OABConfig(numero=numero, uf=uf, nome=nome).normalized()
            if any(existing.numero == item.numero and existing.uf == item.uf for existing in oabs): print(f"OAB {format_oab(item)} já estava cadastrada nesta configuração.")
            else: oabs.append(item); print(f"OAB {format_oab(item)} adicionada.")
        except ValueError as exc:
            print(f"Erro: {exc}"); continue
        if input("Adicionar outra OAB? [s/N]: ").strip().lower() not in {"s", "sim", "y", "yes"}: break
    janela = ask_int(f"Janela de busca em dias [{DEFAULT_WINDOW_DAYS}]: ", DEFAULT_WINDOW_DAYS, 1, 3650); horario = ask_time(f"Horário diário [{DEFAULT_TIME}]: ", DEFAULT_TIME)
    cfg = AppConfig(oabs=oabs, janela_dias=janela, horario=horario, agendamento_ativo=False); save_config(cfg)
    if input("Deseja ativar a consulta automática diária agora? [S/n]: ").strip().lower() not in {"n", "não", "nao", "no"}:
        try:
            install_daily_schedule(horario); cfg.agendamento_ativo = True; save_config(cfg); print(f"Agendamento criado para {horario}.")
        except SchedulerError as exc:
            print(f"Não foi possível criar o agendamento: {exc}\nVocê pode tentar novamente pelo menu Agendamento.")
    pause("Configuração salva. Pressione ENTER para abrir o menu."); return cfg


def print_header(cfg: AppConfig) -> None:
    oabs = ", ".join(format_oab(o) for o in cfg.oabs); status = f"ATIVO às {cfg.horario}" if schedule_exists() else "DESATIVADO"; last_text = "Nunca executado"
    try:
        with PublicationStore() as store: last = store.last_execution()
        if last: last_text = f"{format_datetime_ptbr(last.get('finished_at'))} | novas: {last['total_new']} | atualizadas: {last['total_updated']}"
    except Exception: pass
    print("=" * 72); print(f" {APP_NAME} v{APP_VERSION}\n OABs: {oabs}\n Busca: últimos {cfg.janela_dias} dia(s) no mínimo\n Automático: {status}\n Última consulta: {last_text}"); print("=" * 72); print()


def do_manual_run(cfg: AppConfig) -> None:
    clear_screen(); print("Consultando o DJEN...\nIsso pode levar alguns segundos por OAB porque o programa evita excesso de requisições.\n"); result = run_monitor(cfg, manual=True); print(); print("Consulta concluída." if not result.error else "Consulta concluída com falha parcial/erro."); print(f"Período: {result.start_date} a {result.end_date}\nPublicações encontradas na janela: {result.found}\nNovas publicações: {result.new}\nPublicações atualizadas/reprocessadas: {result.updated}\nRequisições ao DJEN: {result.requests_made}")
    if result.error: print("ATENÇÃO:"); print(result.error)
    if not result.complete: print("ATENÇÃO: a coleta pode estar incompleta. Confira o RESUMO da planilha e a mensagem acima.")
    if result.report_path: print(f"Planilha: {result.report_path}")
    pause()


def configuration_menu(cfg: AppConfig) -> AppConfig:
    while True:
        clear_screen(); print("CONFIGURAÇÕES\n"); [print(f" OAB {idx}: {format_oab(item)}") for idx, item in enumerate(cfg.oabs, 1)]; print("\n [1] Adicionar OAB\n [2] Alterar nome/apelido de uma OAB\n [3] Remover OAB\n [4] Alterar janela de busca\n [5] Ativar/desativar variantes de OAB\n [6] Ver arquivo de configuração\n [0] Voltar")
        option = input("Escolha: ").strip()
        if option == "1":
            try:
                item = OABConfig(input("Número da OAB: ").strip(), input("UF: ").strip().upper(), input("Nome/apelido (opcional, ENTER para pular): ").strip()).normalized()
                if any(e.numero == item.numero and e.uf == item.uf for e in cfg.oabs): pause(f"OAB {item.numero}/{item.uf} já está cadastrada. Pressione ENTER."); continue
                cfg.oabs.append(item); cfg.validate(); save_config(cfg); pause(f"OAB {format_oab(item)} adicionada. Pressione ENTER.")
            except ValueError as exc: pause(f"Erro: {exc}\nPressione ENTER.")
        elif option == "2":
            idx = ask_int("Número da OAB que deseja renomear (0 cancela): ", 0, 0, len(cfg.oabs))
            if idx:
                item = cfg.oabs[idx-1]; novo = input(f"Nome/apelido atual: {item.nome or 'sem nome'}\nNovo nome (ENTER remove/deixa em branco): ").strip(); cfg.oabs[idx-1] = OABConfig(item.numero, item.uf, novo).normalized(); save_config(cfg)
        elif option == "3":
            if len(cfg.oabs) <= 1: pause("É necessário manter pelo menos uma OAB. Pressione ENTER."); continue
            idx = ask_int("Número da OAB a remover (0 cancela): ", 0, 0, len(cfg.oabs))
            if idx: removed = cfg.oabs.pop(idx-1); save_config(cfg); pause(f"OAB {format_oab(removed)} removida. Pressione ENTER.")
        elif option == "4": cfg.janela_dias = ask_int("Nova janela em dias: ", cfg.janela_dias, 1, 3650); save_config(cfg)
        elif option == "5": cfg.consultar_variantes_oab = not cfg.consultar_variantes_oab; save_config(cfg); pause(f"Busca por variantes {'ativada' if cfg.consultar_variantes_oab else 'desativada'}. Pressione ENTER.")
        elif option == "6": print(config_path()); print(config_path().read_text(encoding="utf-8")); pause()
        elif option == "0": return cfg


def schedule_menu(cfg: AppConfig) -> AppConfig:
    while True:
        clear_screen(); active = schedule_exists(); print(f"AGENDAMENTO\nStatus: {'ATIVO' if active else 'DESATIVADO'}\nHorário configurado: {cfg.horario}\n\n [1] Ativar/atualizar agendamento\n [2] Alterar horário\n [3] Desativar agendamento\n [0] Voltar")
        option = input("Escolha: ").strip()
        try:
            if option == "1": cfg.agendamento_ativo = True; pause(install_daily_schedule(cfg.horario) + " Pressione ENTER."); save_config(cfg)
            elif option == "2":
                novo = ask_time("Novo horário HH:MM: ", cfg.horario)
                if active: install_daily_schedule(novo)
                cfg.horario = novo; save_config(cfg); pause(f"Horário alterado para {novo}. Pressione ENTER.")
            elif option == "3": cfg.agendamento_ativo = False; pause(remove_daily_schedule() + " Pressione ENTER."); save_config(cfg)
            elif option == "0": return cfg
        except SchedulerError as exc: pause(f"Falha no agendamento: {exc}\nPressione ENTER.")


def diagnostics_menu(cfg: AppConfig) -> None:
    while True:
        clear_screen(); print("AJUDA / DIAGNÓSTICO\n\n [1] Testar conexão com a API do DJEN\n [2] Abrir pasta de logs\n [3] Mostrar pastas usadas pelo programa\n [4] Mostrar versão\n [0] Voltar"); option = input("Escolha: ").strip()
        if option == "1":
            oab = cfg.oabs[0]; print(f"Testando com {format_oab(oab)}...")
            try:
                client = DJENClient(min_interval=0); today = brasilia_today(); result = client.query_oab(oab.numero, oab.uf, today, today, include_variants=False); print("Conexão OK e resposta validada." if result.complete else "A API respondeu, mas a validação da coleta ficou INCOMPLETA."); print(f"Itens retornados hoje: {len(result.items)}\nRequisições: {client.requests_made}"); [print(f"Aviso: {w}") for w in result.errors]
            except DJENAPIError as exc: print(f"Falha: {exc}")
            pause()
        elif option == "2": open_path(log_dir()); pause()
        elif option == "3": print(f"Configuração: {config_path()}\nPlanilhas: {reports_dir()}\nLogs: {log_dir()}"); pause()
        elif option == "4": pause(f"{APP_NAME} v{APP_VERSION}\nPressione ENTER.")
        elif option == "0": return


def open_reports_folder() -> None:
    target = reports_dir(); remembered = last_report_path()
    if remembered and remembered.exists(): target = remembered.parent
    else:
        try:
            with PublicationStore() as store: last = store.last_execution()
            if last and last.get("report_path"):
                report = Path(str(last["report_path"])); target = report.parent if report.exists() else target
        except Exception: pass
    open_path(target)


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt": os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin": subprocess.run(["open", str(path)], check=True)
        else: subprocess.run(["xdg-open", str(path)], check=True)
    except Exception: print(f"Abra manualmente: {path}")


def clear_screen() -> None: os.system("cls" if os.name == "nt" else "clear")
def pause(message: str = "Pressione ENTER para voltar.") -> None: input(message)

def ask_int(prompt: str, default: int, minimum: int, maximum: int) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw: return default
        try:
            value = int(raw)
            if minimum <= value <= maximum: return value
        except ValueError: pass
        print(f"Digite um número entre {minimum} e {maximum}.")

def ask_time(prompt: str, default: str) -> str:
    while True:
        raw = input(prompt).strip() or default
        if valid_time(raw): return raw
        print("Horário inválido. Use HH:MM, por exemplo 08:30.")
