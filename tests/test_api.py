import urllib.parse
from datetime import date

from djen_monitor.api import DJENClient, QueryResult, oab_variants


def test_variants():
    variants = oab_variants("123456")
    assert variants[0] == "123456"
    assert "123456-O" in variants
    assert "123456-A" in variants
    assert len(variants) == 7


def test_uses_production_safe_page_size_50():
    calls = []

    def fake(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        calls.append(q)
        assert q["itensPorPagina"] == ["50"]
        assert q["pagina"] == ["1"]
        assert q["numeroOab"] == ["123456"]
        assert q["ufOab"] == ["PR"]
        assert q["dataDisponibilizacaoInicio"] == ["2026-08-18"]
        assert q["dataDisponibilizacaoFim"] == ["2026-08-19"]
        return {"count": 2, "items": [{"id": 1}, {"id": 2}]}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client._query_exact_oab("123456", "PR", date(2026, 8, 18), date(2026, 8, 19))
    assert len(result.items) == 2
    assert len(calls) == 1


def test_retries_transient_empty_first_page(monkeypatch):
    monkeypatch.setattr("djen_monitor.api.time.sleep", lambda _seconds: None)
    calls = 0

    def fake(url):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"count": 1, "items": []}, {}
        return {"count": 1, "items": [{"id": 1}]}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client._query_exact_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19))
    assert result.complete
    assert [i["id"] for i in result.items] == [1]
    assert calls == 2


def test_nested_advogado_matches_target_and_wrong_oab_is_rejected():
    items = [
        {
            "id": 1,
            "destinatarioadvogados": [
                {"advogado": {"nome": "ALVO", "numero_oab": "123456-O", "uf_oab": "PR"}}
            ],
        },
        {
            "id": 2,
            "destinatarioadvogados": [
                {"advogado": {"nome": "OUTRO", "numero_oab": "999999", "uf_oab": "PR"}}
            ],
        },
    ]

    def fake(_url):
        return {"count": 2, "items": items}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client.query_oab(
        "123456", "PR", date(2026, 8, 19), date(2026, 8, 19), include_variants=False
    )
    assert [i["id"] for i in result.items] == [1]
    assert not result.complete  # houve retorno explicitamente incompatível


def test_large_window_is_split_before_10k_download(monkeypatch):
    client = DJENClient(min_interval=0, requester=lambda _url: ({}, {}))
    calls = []

    def fake_exact(numero, uf, start, end):
        calls.append((start, end))
        if start != end:
            return QueryResult(items=[{"id": "first-page"}], announced_count=10000, complete=False, requests_made=0)
        return QueryResult(items=[{"id": start.isoformat()}], announced_count=1, complete=True, requests_made=0)

    monkeypatch.setattr(client, "_query_exact_oab", fake_exact)
    result = client._query_with_cap_split("123456", "PR", date(2026, 8, 18), date(2026, 8, 19))
    assert result.complete
    assert {i["id"] for i in result.items} == {"2026-08-18", "2026-08-19"}
    assert calls == [
        (date(2026, 8, 18), date(2026, 8, 19)),
        (date(2026, 8, 18), date(2026, 8, 18)),
        (date(2026, 8, 19), date(2026, 8, 19)),
    ]


def test_item_without_lawyer_is_preserved_but_marks_collection_incomplete():
    def requester(url):
        return ({
            "count": 1,
            "items": [{"id": "x", "texto": "sem identificacao de advogado"}],
        }, {})

    client = DJENClient(min_interval=0, requester=requester)
    result = client.query_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19), include_variants=False)
    assert len(result.items) == 1
    assert result.complete is False


def test_http_200_payload_error_is_not_treated_as_zero_results():
    import pytest
    from djen_monitor.api import DJENAPIError

    client = DJENClient(min_interval=0, requester=lambda _url: ({"status": "error", "message": "falha interna"}, {}))
    with pytest.raises(DJENAPIError, match="falha interna"):
        client.query_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19), include_variants=False)


def test_same_oab_number_without_uf_is_preserved_but_unverified():
    item = {
        "id": 3,
        "destinatarioadvogados": [
            {"advogado": {"nome": "ALVO", "numero_oab": "123456-O"}}
        ],
    }
    client = DJENClient(min_interval=0, requester=lambda _url: ({"count": 1, "items": [item]}, {}))
    result = client.query_oab(
        "123456", "PR", date(2026, 8, 19), date(2026, 8, 19), include_variants=False
    )
    assert len(result.items) == 1
    assert result.complete is False


def test_page_limit_without_count_is_never_declared_complete(monkeypatch):
    monkeypatch.setattr("djen_monitor.api.time.sleep", lambda _seconds: None)

    def fake(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        page = int(q["pagina"][0])
        # Simula API sem count que continua entregando pagina cheia ate o teto.
        items = [{"id": page * 1000 + i} for i in range(50)]
        return {"items": items}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client._query_exact_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19))
    assert len(result.items) == 10000
    assert result.complete is False
    assert result.announced_count == 10000


def test_retry_after_http_date_is_supported(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from djen_monitor.api import _retry_delay

    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    delay = _retry_delay(1, future)
    assert 1 <= delay <= 60


def test_empty_first_page_without_count_is_retried_and_not_false_zero(monkeypatch):
    monkeypatch.setattr("djen_monitor.api.time.sleep", lambda _seconds: None)
    calls = 0

    def fake(_url):
        nonlocal calls
        calls += 1
        return {"items": []}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client._query_exact_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19))
    assert calls == 3
    assert result.items == []
    assert result.announced_count is None
    assert result.complete is False


def test_failure_in_one_oab_variant_preserves_other_variant_results(monkeypatch):
    from djen_monitor.api import DJENAPIError

    calls = []

    def fake_split(self, numero, uf, start, end):
        calls.append(numero)
        if numero.endswith("-A"):
            raise DJENAPIError("falha temporaria simulada")
        if numero == "123456":
            return QueryResult(
                items=[{
                    "id": 44,
                    "destinatarioadvogados": [
                        {"advogado": {"nome": "ALVO", "numero_oab": "123456", "uf_oab": "PR"}}
                    ],
                }],
                announced_count=1,
                complete=True,
                requests_made=0,
            )
        return QueryResult(items=[], announced_count=0, complete=True, requests_made=0)

    monkeypatch.setattr(DJENClient, "_query_with_cap_split", fake_split)
    client = DJENClient(min_interval=0, requester=lambda _url: ({}, {}))
    result = client.query_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19), include_variants=True)
    assert [item["id"] for item in result.items] == [44]
    assert result.complete is False
    assert any("123456-A/PR" in error for error in result.errors)
    assert len(calls) == 7


def test_empty_later_page_without_count_is_retried_before_accepting_end(monkeypatch):
    monkeypatch.setattr("djen_monitor.api.time.sleep", lambda _seconds: None)
    calls = []

    def fake(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        page = int(q["pagina"][0])
        calls.append(page)
        if page == 1:
            return {"items": [{"id": i} for i in range(50)]}, {}
        return {"items": []}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client._query_exact_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19))
    assert len(result.items) == 50
    assert result.complete is True
    assert calls == [1, 2, 2, 2]


def test_without_count_does_not_assume_server_honored_requested_page_size(monkeypatch):
    monkeypatch.setattr("djen_monitor.api.time.sleep", lambda _seconds: None)
    calls = []

    def fake(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        page = int(q["pagina"][0])
        calls.append(page)
        pages = {
            1: [{"id": i} for i in range(1, 6)],
            2: [{"id": i} for i in range(6, 11)],
            3: [{"id": 11}, {"id": 12}],
        }
        return {"items": pages.get(page, [])}, {}

    client = DJENClient(min_interval=0, requester=fake)
    result = client._query_exact_oab("123456", "PR", date(2026, 8, 19), date(2026, 8, 19))
    assert [item["id"] for item in result.items] == list(range(1, 13))
    assert result.complete is True
    assert calls == [1, 2, 3, 4, 4, 4]
