import sqlite3
from datetime import date

from djen_monitor.api import QueryResult
from djen_monitor.config import AppConfig, OABConfig
from djen_monitor.runner import run_monitor
from djen_monitor.storage import PublicationStore


RAW = {
    "id": 123,
    "hash": "abc",
    "numero_processo": "00000000020268000000",
    "siglaTribunal": "TJXX",
    "data_disponibilizacao": "2026-08-19",
    "tipoComunicacao": "Intimacao",
    "texto": "Intimado para se manifestar.",
    "destinatarioadvogados": [
        {"advogado": {"nome": "TESTE", "numero_oab": "123456", "uf_oab": "PR"}}
    ],
}


def test_excel_failure_does_not_consume_new_publication(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.requests_made = 1

        def query_oab(self, **kwargs):
            return QueryResult(items=[RAW], announced_count=1, complete=True, requests_made=1)

    monkeypatch.setattr("djen_monitor.runner.DJENClient", FakeClient)
    monkeypatch.setattr("djen_monitor.runner.PublicationStore", lambda: PublicationStore(db))
    monkeypatch.setattr("djen_monitor.runner.create_report", lambda *a, **k: (_ for _ in ()).throw(OSError("disco cheio")))
    monkeypatch.setattr("djen_monitor.runner.brasilia_today", lambda: date(2026, 8, 19))

    cfg = AppConfig(
        oabs=[OABConfig("123456", "PR")],
        janela_dias=1,
        consultar_variantes_oab=False,
        intervalo_requisicoes_segundos=0,
    )
    result = run_monitor(cfg)
    assert result.error
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM publicacoes").fetchone()[0]
    assert count == 0
