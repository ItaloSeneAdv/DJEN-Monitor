from __future__ import annotations

import json
import logging
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import certifi

from .constants import (
    API_BASE_URL, API_PAGE_SIZE, API_RESULT_CAP, DEFAULT_REQUEST_INTERVAL, DEFAULT_TIMEOUT,
    STANDARD_OAB_SUFFIXES, USER_AGENT,
)
from .config import oab_base_digits
from .normalize import extract_advogados

logger = logging.getLogger("djen_monitor")


class DJENAPIError(RuntimeError):
    pass


@dataclass
class QueryResult:
    items: list[dict[str, Any]]
    announced_count: int | None
    complete: bool
    requests_made: int
    errors: list[str] = field(default_factory=list)


class DJENClient:
    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        min_interval: float = DEFAULT_REQUEST_INTERVAL,
        requester: Callable[[str], tuple[dict[str, Any], dict[str, str]]] | None = None,
    ) -> None:
        self.timeout = timeout
        self.min_interval = max(0.0, float(min_interval))
        self._last_request_at = 0.0
        self._custom_requester = requester
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.requests_made = 0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _request_json(self, url: str) -> tuple[dict[str, Any], dict[str, str]]:
        if self._custom_requester is not None:
            self.requests_made += 1
            self._last_request_at = time.monotonic()
            payload, headers = self._custom_requester(url)
            if not isinstance(payload, dict):
                raise DJENAPIError("Formato inesperado da resposta do DJEN.")
            _raise_if_payload_error(payload)
            return payload, headers

        attempts = 4
        transient_status = {408, 429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            self._throttle()
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                method="GET",
            )
            try:
                self.requests_made += 1
                with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_context) as response:
                    self._last_request_at = time.monotonic()
                    raw = response.read()
                    headers = {k.lower(): v for k, v in response.headers.items()}
                    if response.status != 200:
                        raise DJENAPIError(f"DJEN respondeu HTTP {response.status}.")
                    try:
                        payload = json.loads(raw.decode("utf-8-sig"))
                    except Exception as exc:
                        raise DJENAPIError("O DJEN respondeu algo que não é JSON válido.") from exc
                    if not isinstance(payload, dict):
                        raise DJENAPIError("Formato inesperado da resposta do DJEN.")
                    _raise_if_payload_error(payload)
                    return payload, headers
            except urllib.error.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                if exc.code == 403:
                    raise DJENAPIError(
                        "O DJEN recusou a conexão com HTTP 403. A API pode restringir acessos conforme a origem da rede."
                    ) from exc
                if exc.code not in transient_status or attempt == attempts:
                    raise DJENAPIError(f"DJEN respondeu HTTP {exc.code}.") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = _retry_delay(attempt, retry_after)
                logger.warning("Falha temporária HTTP %s. Nova tentativa em %.1fs.", exc.code, delay)
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                if attempt == attempts:
                    break
                delay = _retry_delay(attempt, None)
                logger.warning("Falha de rede. Nova tentativa em %.1fs: %s", delay, exc)
                time.sleep(delay)

        raise DJENAPIError(f"Não foi possível conectar ao DJEN: {last_error}")

    def query_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        start: date,
        end: date,
        include_variants: bool = True,
    ) -> QueryResult:
        variants = oab_variants(numero_oab) if include_variants else [numero_oab]
        all_items: list[dict[str, Any]] = []
        counts: list[int] = []
        complete = True
        start_requests = self.requests_made

        errors: list[str] = []
        successful_variants = 0
        for variant in variants:
            try:
                result = self._query_with_cap_split(variant, uf_oab, start, end)
            except DJENAPIError as exc:
                # Uma variante com falha não apaga resultados validos que ja
                # vieram das demais. A coleta fica incompleta e o erro e
                # exposto ao usuário/Excel para nova tentativa automatica.
                complete = False
                message = f"variante {variant}/{uf_oab}: {exc}"
                errors.append(message)
                logger.warning("Falha em %s; seguindo para as demais variantes", message)
                continue

            successful_variants += 1
            rejected = 0
            unverified = 0
            for item in result.items:
                match = _matches_target_oab(item, numero_oab, uf_oab)
                if match is False:
                    rejected += 1
                    continue
                if match is None:
                    unverified += 1
                all_items.append(item)
            if rejected:
                complete = False
                message = (
                    f"variante {variant}/{uf_oab}: {rejected} item(ns) retornado(s) "
                    f"com OAB explicita diferente de {numero_oab}/{uf_oab}"
                )
                errors.append(message)
                logger.warning(message)
            if unverified:
                complete = False
                message = (
                    f"variante {variant}/{uf_oab}: {unverified} item(ns) sem OAB/UF "
                    "suficiente para conferencia local; preservados para revisao"
                )
                errors.append(message)
                logger.warning(message)
            if result.announced_count is not None:
                counts.append(result.announced_count)
            if result.errors:
                errors.extend(result.errors)
            complete = complete and result.complete

        if successful_variants == 0 and errors:
            raise DJENAPIError("Todas as variantes consultadas falharam: " + " | ".join(errors))

        deduped = _dedupe_raw_items(all_items)
        announced = sum(counts) if counts else None
        return QueryResult(
            items=deduped,
            announced_count=announced,
            complete=complete,
            requests_made=self.requests_made - start_requests,
            errors=errors,
        )

    def _query_with_cap_split(self, numero_oab: str, uf_oab: str, start: date, end: date) -> QueryResult:
        result = self._query_exact_oab(numero_oab, uf_oab, start, end)
        # Em producao o count pode ficar limitado em torno de 10 mil. Para uma
        # janela grande, divide automaticamente por data em vez de declarar uma
        # coleta potencialmente truncada como completa.
        if result.announced_count is not None and result.announced_count >= API_RESULT_CAP:
            if start >= end:
                result.complete = False
                return result
            span_days = (end - start).days
            mid = start + timedelta(days=span_days // 2)
            left = self._query_with_cap_split(numero_oab, uf_oab, start, mid)
            right = self._query_with_cap_split(numero_oab, uf_oab, mid + timedelta(days=1), end)
            items = _dedupe_raw_items(left.items + right.items)
            count = None
            if left.announced_count is not None and right.announced_count is not None:
                count = left.announced_count + right.announced_count
            return QueryResult(
                items=items, announced_count=count,
                complete=left.complete and right.complete, requests_made=0,
                errors=left.errors + right.errors,
            )
        return result

    def _query_exact_oab(self, numero_oab: str, uf_oab: str, start: date, end: date) -> QueryResult:
        page_size = API_PAGE_SIZE
        first_url = self._build_url(numero_oab, uf_oab, start, end, page=1, page_size=page_size)
        first_payload, first_headers = self._request_json(first_url)
        items_acc = list(_extract_items(first_payload))
        count = _extract_count(first_payload)
        if items_acc and count == 0:
            count = None
        if count is not None and count >= API_RESULT_CAP and start < end:
            # Devolve cedo para que _query_with_cap_split particione a janela
            # antes de baixar milhares de itens que serao consultados de novo.
            return QueryResult(items=items_acc, announced_count=count, complete=False, requests_made=0)

        logger.debug(
            "Consulta %s/%s: primeira pagina=%s itens, count=%s, page_size=%s, rate_limit=%s",
            numero_oab, uf_oab, len(items_acc), count, page_size,
            first_headers.get("x-ratelimit-limit"),
        )

        if not items_acc:
            # count=0 e um zero explicito. Sem count, uma pagina vazia pode ser
            # resposta transiente/malformada; nunca a tratamos imediatamente
            # como prova de que não existem publicacoes.
            if count == 0:
                return QueryResult(items=[], announced_count=0, complete=True, requests_made=0)
            for retry in range(1, 3):
                time.sleep(float(retry))
                payload, _ = self._request_json(first_url)
                items_acc = list(_extract_items(payload))
                retry_count = _extract_count(payload)
                if retry_count is not None:
                    count = retry_count
                if items_acc:
                    break
                if count == 0:
                    return QueryResult(items=[], announced_count=0, complete=True, requests_made=0)
            if not items_acc:
                return QueryResult(items=[], announced_count=count, complete=False, requests_made=0)

        max_pages = max(1, API_RESULT_CAP // page_size)
        page = 2
        empty_retries = 0
        while page <= max_pages:
            if count is not None and count > 0 and len(items_acc) >= count:
                break
            url = self._build_url(numero_oab, uf_oab, start, end, page=page, page_size=page_size)
            payload, _ = self._request_json(url)
            page_items = _extract_items(payload)
            page_count = _extract_count(payload)
            if count is None and page_count is not None:
                count = page_count

            if not page_items:
                # Uma pagina vazia depois de uma pagina cheia pode ser o fim
                # legitimo, mas tambem pode ser uma resposta transiente. Fazemos
                # duas reconferencias antes de aceitar o fim quando nao existe
                # count confiavel.
                definitely_done = count is not None and len(items_acc) >= count
                if definitely_done:
                    break
                if empty_retries < 2:
                    empty_retries += 1
                    time.sleep(float(empty_retries))
                    continue
                if count is None:
                    break
                return QueryResult(items=items_acc, announced_count=count, complete=False, requests_made=0)

            empty_retries = 0
            items_acc.extend(page_items)
            # Com count confiavel podemos encerrar assim que atingimos o total.
            # Sem count, não presumimos que a API respeitou itensPorPagina=50;
            # seguimos ate observar uma pagina realmente vazia.
            if count is not None and len(items_acc) >= count:
                break
            page += 1

        # Se consumimos todas as 200 paginas permitidas sem observar um fim
        # legitimo, nunca declaramos a coleta como completa. Ao sinalizar o
        # teto, _query_with_cap_split divide a janela por data quando possível.
        if page > max_pages:
            announced_for_split = max(count or 0, API_RESULT_CAP)
            return QueryResult(
                items=items_acc, announced_count=announced_for_split, complete=False, requests_made=0
            )

        complete = not (count is not None and count > 0 and len(items_acc) < count)
        return QueryResult(items=items_acc, announced_count=count, complete=complete, requests_made=0)

    @staticmethod
    def _build_url(numero_oab: str, uf_oab: str, start: date, end: date, page: int, page_size: int | None) -> str:
        params = {
            "numeroOab": numero_oab,
            "ufOab": uf_oab.upper(),
            "dataDisponibilizacaoInicio": start.isoformat(),
            "dataDisponibilizacaoFim": end.isoformat(),
            "pagina": str(page),
        }
        if page_size is not None:
            params["itensPorPagina"] = str(page_size)
        return f"{API_BASE_URL}/comunicacao?{urllib.parse.urlencode(params)}"


def oab_variants(numero_oab: str) -> list[str]:
    base = oab_base_digits(numero_oab)
    if not base:
        return [numero_oab]
    variants = [f"{base}{suffix}" for suffix in STANDARD_OAB_SUFFIXES]
    explicit = str(numero_oab).strip().upper()
    if explicit and explicit not in variants:
        variants.insert(0, explicit)
    return list(dict.fromkeys(variants))


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "comunicacoes", "resultados", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_count(payload: dict[str, Any]) -> int | None:
    for key in ("count", "total", "totalItems", "total_items"):
        value = payload.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _raw_identity(item: dict[str, Any]) -> str:
    candidates = [
        item.get("id"), item.get("hash"), item.get("numeroComunicacao"), item.get("numero_comunicacao"),
    ]
    for value in candidates:
        if value not in (None, ""):
            return str(value)
    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return repr(item)


def _dedupe_raw_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = _raw_identity(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _matches_target_oab(item: dict[str, Any], target_oab: str, target_uf: str) -> bool | None:
    advogados = extract_advogados(item)
    if not advogados:
        return None  # campo pode estar ausente; nao escondemos a publicacao
    digits = oab_base_digits(target_oab)
    uf = target_uf.upper()
    found_same_number_without_uf = False
    for advogado in advogados:
        if oab_base_digits(advogado.get("oab", "")) != digits:
            continue
        item_uf = str(advogado.get("uf", "")).upper().strip()
        if item_uf == uf:
            return True
        if not item_uf:
            found_same_number_without_uf = True
    return None if found_same_number_without_uf else False



def _raise_if_payload_error(payload: dict[str, Any]) -> None:
    status = str(payload.get("status", "") or "").strip().lower()
    if status in {"error", "erro", "failed", "failure", "falha"}:
        message = str(payload.get("message", "") or payload.get("mensagem", "") or "Erro informado pela API.")
        raise DJENAPIError(f"O DJEN informou erro na resposta: {message}")
    # Uma resposta de consulta normal deve expor pelo menos items ou count.
    # Se vier apenas uma mensagem/estado desconhecido, nao convertemos isso em
    # um falso zero de publicacoes.
    if not any(key in payload for key in ("items", "comunicacoes", "resultados", "data", "count", "total", "totalItems", "total_items")):
        if payload.get("message") or payload.get("mensagem") or payload.get("status"):
            message = str(payload.get("message", "") or payload.get("mensagem", "") or payload.get("status", ""))
            raise DJENAPIError(f"Resposta inesperada do DJEN: {message}")

def _retry_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(60.0, max(1.0, float(retry_after)))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(retry_after)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                seconds = (parsed - datetime.now(timezone.utc)).total_seconds()
                return min(60.0, max(1.0, seconds))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(30.0, (2 ** (attempt - 1)) + random.uniform(0.0, 0.5))
