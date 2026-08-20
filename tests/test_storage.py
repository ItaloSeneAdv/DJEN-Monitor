import json
from pathlib import Path

from djen_monitor.classify import classify
from djen_monitor.normalize import normalize_item
from djen_monitor.storage import PublicationStore

FIXTURE = Path(__file__).parent / "fixtures" / "comunicacoes_anonimizadas.json"


def test_dedup_and_update(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pub = classify(normalize_item(payload["items"][0], "123456", "PR"))
    with PublicationStore(tmp_path / "db.sqlite3") as store:
        assert store.upsert(pub) == "NOVA"
        assert store.upsert(pub) == "JA_CONHECIDA"
        pub.motivo_cancelamento = "Cancelada para reprocessamento"
        assert store.upsert(pub) == "ATUALIZADA"


def test_active_to_inactive_is_detected_as_update(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw = dict(payload["items"][0])
    raw["ativo"] = True
    pub = classify(normalize_item(raw, "123456", "PR"))
    with PublicationStore(tmp_path / "status.sqlite3") as store:
        assert store.upsert(pub) == "NOVA"
        raw["ativo"] = False
        changed = classify(normalize_item(raw, "123456", "PR"))
        assert store.upsert(changed) == "ATUALIZADA"


def test_local_query_metadata_does_not_trigger_source_update(tmp_path):
    from djen_monitor.normalize import content_hash
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pub = classify(normalize_item(payload["items"][0], "123456", "PR"))
    original_hash = content_hash(pub)
    pub.oab_consultada = "123456 | 123456-A"
    pub.uf_consultada = "PR | PR"
    pub.link_consulta_djen = "https://comunica.pje.jus.br/consulta?outra=consulta"
    assert content_hash(pub) == original_hash


def test_stored_payload_contains_actual_collection_status(tmp_path):
    import sqlite3

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pub = classify(normalize_item(payload["items"][0], "123456", "PR"))
    db = tmp_path / "payload.sqlite3"
    with PublicationStore(db) as store:
        assert store.upsert(pub) == "NOVA"
        row = store.conn.execute(
            "SELECT payload_json FROM publicacoes WHERE dedupe_key = ?", (pub.dedupe_key,)
        ).fetchone()
        assert json.loads(row[0])["situacao_coleta"] == "NOVA"
        assert store.upsert(pub) == "JA_CONHECIDA"
        row = store.conn.execute(
            "SELECT payload_json FROM publicacoes WHERE dedupe_key = ?", (pub.dedupe_key,)
        ).fetchone()
        assert json.loads(row[0])["situacao_coleta"] == "JA_CONHECIDA"


def test_last_complete_end_date_ignores_incomplete_runs(tmp_path):
    with PublicationStore(tmp_path / "history.sqlite3") as store:
        base = {
            "started_at": "2026-08-10T08:00:00-03:00",
            "finished_at": "2026-08-10T08:01:00-03:00",
            "start_date": "2026-08-08",
            "end_date": "2026-08-10",
            "total_raw": 0,
            "total_normalized": 0,
            "total_new": 0,
            "total_updated": 0,
            "requests_made": 1,
            "complete": True,
            "report_path": "",
            "error": "",
        }
        store.record_execution(base)
        broken = dict(base, end_date="2026-08-15", complete=False, error="falha")
        store.record_execution(broken)
        assert store.last_complete_end_date() == "2026-08-10"
