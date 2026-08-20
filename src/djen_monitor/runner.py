from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .api import DJENAPIError, DJENClient
from .classify import classify
from .config import AppConfig
from .constants import API_BASE_URL, APP_VERSION
from .excel import create_report
from .lock import AlreadyRunningError, SingleRunLock
from .normalize import Publication, normalize_item
from .paths import remember_last_report
from .storage import PublicationStore
from .time_utils import brasilia_now, brasilia_today

logger = logging.getLogger("djen_monitor")


@dataclass
class RunResult:
    report_path: str
    found: int
    new: int
    updated: int
    complete: bool
    requests_made: int
    start_date: str
    end_date: str
    error: str = ""


def run_monitor(cfg: AppConfig, manual: bool = True) -> RunResult:
    del manual  # reservado para futuras diferencas de UX; o motor e o mesmo.
    try:
        with SingleRunLock():
            return _run_monitor_locked(cfg)
    except AlreadyRunningError as exc:
        today = brasilia_today().isoformat()
        return RunResult(
            report_path="", found=0, new=0, updated=0, complete=False, requests_made=0,
            start_date=today, end_date=today, error=str(exc),
        )


def _run_monitor_locked(cfg: AppConfig) -> RunResult:
    started = brasilia_now()
    started_perf = time.monotonic()
    end = brasilia_today()
    configured_start = end - timedelta(days=cfg.janela_dias - 1)
    start = configured_start

    # A janela configurada e o minimo. Se o computador ficou desligado ou a
    # ultima coleta completa e mais antiga, amplia automaticamente a busca ate
    # a data final daquela coleta, com um dia de sobreposicao e deduplicação.
    # Assim uma ausencia maior que a janela não cria um buraco silencioso.
    try:
        with PublicationStore() as history_store:
            last_complete = history_store.last_complete_end_date()
        if last_complete:
            previous_end = date.fromisoformat(last_complete)
            if previous_end < start and previous_end <= end:
                start = previous_end
    except Exception:
        logger.warning("Não foi possível consultar o histórico para ampliar a janela; usando a janela configurada.")

    client = DJENClient(min_interval=cfg.intervalo_requisicoes_segundos)
    raw_total = 0
    publications_by_key: dict[str, Publication] = {}
    complete = True
    error_text = ""

    errors: list[str] = []
    for oab in cfg.oabs:
        logger.info("Consultando OAB %s/%s de %s a %s", oab.numero, oab.uf, start, end)
        try:
            result = client.query_oab(
                numero_oab=oab.numero,
                uf_oab=oab.uf,
                start=start,
                end=end,
                include_variants=cfg.consultar_variantes_oab,
            )
            raw_total += len(result.items)
            complete = complete and result.complete
            if result.errors:
                errors.extend(f"{oab.numero}/{oab.uf}: {message}" for message in result.errors)
            for index, item in enumerate(result.items, start=1):
                try:
                    pub = classify(normalize_item(item, oab.numero, oab.uf, target_name=oab.nome))
                    publications_by_key[pub.dedupe_key] = _merge_publications(
                        publications_by_key.get(pub.dedupe_key), pub
                    )
                except Exception as exc:
                    complete = False
                    item_ref = item.get("id") or item.get("hash") or f"item {index}"
                    message = f"{oab.numero}/{oab.uf}: comunicação {item_ref} não pode ser normalizada: {exc}"
                    errors.append(message)
                    logger.exception("Comunicação malformada; seguindo para os demais itens")
        except DJENAPIError as exc:
            complete = False
            message = f"{oab.numero}/{oab.uf}: {exc}"
            errors.append(message)
            logger.exception("Falha na consulta da OAB %s/%s; seguindo para as demais", oab.numero, oab.uf)
        except Exception as exc:  # nunca interrompe as outras OABs por uma resposta ruim
            complete = False
            message = f"{oab.numero}/{oab.uf}: erro interno ao processar a resposta: {exc}"
            errors.append(message)
            logger.exception("Erro inesperado na OAB %s/%s; seguindo para as demais", oab.numero, oab.uf)

    error_text = " | ".join(errors)

    found = list(publications_by_key.values())
    news: list[Publication] = []
    new_count = 0
    updated_count = 0
    report_path = ""

    finished = brasilia_now()
    execution = {
        "app_version": APP_VERSION,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "configured_start_date": configured_start.isoformat(),
        "catchup_expanded": start < configured_start,
        "oabs": ", ".join(
            f"{o.nome} ({o.numero}/{o.uf})" if o.nome else f"{o.numero}/{o.uf}"
            for o in cfg.oabs
        ),
        "window_days": cfg.janela_dias,
        "variants_enabled": cfg.consultar_variantes_oab,
        "request_interval_seconds": cfg.intervalo_requisicoes_segundos,
        "total_raw": raw_total,
        "total_normalized": len(found),
        "total_new": 0,
        "total_updated": 0,
        "requests_made": client.requests_made,
        "complete": complete and not error_text,
        "duration_seconds": round(time.monotonic() - started_perf, 2),
        "source": f"{API_BASE_URL}/comunicacao",
        "error": error_text,
    }

    try:
        with PublicationStore() as store:
            # Os upserts ficam numa transação pendente ate a planilha ser salva.
            # Se o XLSX falhar (disco cheio, permissao etc.), fazemos rollback para
            # que as publicações ainda aparecam como NOVAS na próxima execução.
            # Publicações de OABs consultadas com sucesso sao persistidas mesmo
            # se outra OAB falhou. A execução fica marcada como incompleta e o
            # agendador tentara novamente, mas não escondemos dados validos.
            for pub in found:
                status = store.upsert(pub, commit=False)
                pub.situacao_coleta = status
                if status == "NOVA":
                    new_count += 1
                    news.append(pub)
                elif status == "ATUALIZADA":
                    updated_count += 1
                    news.append(pub)

            execution["total_new"] = new_count
            execution["total_updated"] = updated_count

            try:
                report_path = str(create_report(found, news, execution))
                try:
                    remember_last_report(report_path)
                except OSError:
                    logger.warning("Não foi possível registrar o atalho para a ultima planilha.")
            except Exception as exc:
                store.rollback()
                error_text = f"Não foi possível gerar a planilha Excel: {exc}"
                execution["error"] = error_text
                execution["complete"] = False
                logger.exception("Falha ao gerar o Excel; deduplicação revertida")
                # Registra a tentativa, mas não marca publicações como consumidas.
                try:
                    store.record_execution(execution, commit=True)
                except Exception:
                    logger.exception("Também não foi possível registrar a execução no SQLite")
                return _result(report_path, found, new_count, updated_count, False, client, start, end, error_text)

            execution["report_path"] = report_path
            store.record_execution(execution, commit=False)
            store.commit()
    except Exception as exc:
        storage_error = f"Falha no armazenamento local: {exc}"
        error_text = " | ".join(part for part in (error_text, storage_error) if part)
        logger.exception("Falha no SQLite")

        # O histórico local e importante para deduplicar, mas nunca deve ser um
        # ponto unico de falha que esconda publicações já coletadas da API. Se o
        # SQLite estiver corrompido/bloqueado, gera uma planilha de emergência
        # com tudo que foi encontrado, explicitamente SEM afirmar que e novo.
        if found and not report_path:
            for pub in found:
                pub.situacao_coleta = "SEM_HISTORICO"
                pub.classificacao = "REVISAR"
                prefix = "Histórico local indisponível; não foi possível confirmar se esta publicação é nova."
                pub.motivo_classificacao = f"{prefix} {pub.motivo_classificacao}".strip()
            execution["total_new"] = 0
            execution["total_updated"] = 0
            execution["complete"] = False
            execution["error"] = error_text
            try:
                report_path = str(create_report(found, found, execution))
                try:
                    remember_last_report(report_path)
                except OSError:
                    logger.warning("Não foi possível registrar o atalho para a planilha de emergência.")
            except Exception as report_exc:
                error_text += f" | Também não foi possível gerar a planilha de emergência: {report_exc}"
                logger.exception("Falha ao gerar planilha de emergência")

        return _result(report_path, found, 0, 0, False, client, start, end, error_text)

    return _result(
        report_path, found, new_count, updated_count,
        complete and not error_text, client, start, end, error_text,
    )


def _result(
    report_path: str,
    found: list[Publication],
    new_count: int,
    updated_count: int,
    complete: bool,
    client: DJENClient,
    start,
    end,
    error_text: str,
) -> RunResult:
    return RunResult(
        report_path=report_path,
        found=len(found),
        new=new_count,
        updated=updated_count,
        complete=complete,
        requests_made=client.requests_made,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        error=error_text,
    )


def _merge_publications(existing: Publication | None, incoming: Publication) -> Publication:
    if existing is None:
        return incoming
    existing_score = sum(bool(getattr(existing, field)) for field in existing.__dataclass_fields__)
    incoming_score = sum(bool(getattr(incoming, field)) for field in incoming.__dataclass_fields__)
    use_incoming = incoming_score >= existing_score
    base = replace(incoming if use_incoming else existing)
    other = existing if use_incoming else incoming

    for field in (
        "nome_advogado", "oab", "uf_oab", "oab_consultada", "uf_consultada",
        "nome_oab_consultada", "rotulo_oab_consultada", "partes",
    ):
        left = str(getattr(base, field) or "")
        right = str(getattr(other, field) or "")
        values = []
        seen = set()
        for part in (left + " | " + right).split(" | "):
            part = part.strip()
            if part and part not in seen:
                seen.add(part)
                values.append(part)
        setattr(base, field, " | ".join(values))

    for field in base.__dataclass_fields__:
        if field in {
            "nome_advogado", "oab", "uf_oab", "oab_consultada", "uf_consultada",
            "nome_oab_consultada", "rotulo_oab_consultada", "partes",
        }:
            continue
        if not getattr(base, field) and getattr(other, field):
            setattr(base, field, getattr(other, field))
    if len(other.texto_integral) > len(base.texto_integral):
        base.texto_integral = other.texto_integral
    return classify(base)
