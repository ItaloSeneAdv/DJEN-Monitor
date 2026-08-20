from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .normalize import Publication, content_hash
from .paths import database_path
from .time_utils import format_datetime_ptbr


class PublicationStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=5.0)
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publicacoes (
                dedupe_key TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                source_hash TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execucoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_raw INTEGER NOT NULL,
                total_normalized INTEGER NOT NULL,
                total_new INTEGER NOT NULL,
                total_updated INTEGER NOT NULL,
                requests_made INTEGER NOT NULL,
                complete INTEGER NOT NULL,
                report_path TEXT,
                error TEXT
            )
            """
        )
        self.conn.commit()

    def upsert(self, pub: Publication, *, commit: bool = True) -> str:
        h = content_hash(pub)
        row = self.conn.execute(
            "SELECT content_hash FROM publicacoes WHERE dedupe_key = ?", (pub.dedupe_key,)
        ).fetchone()
        if row is None:
            status = "NOVA"
            pub.situacao_coleta = status
            payload = json.dumps(asdict(pub), ensure_ascii=False, sort_keys=True)
            self.conn.execute(
                "INSERT INTO publicacoes (dedupe_key, content_hash, first_seen, last_seen, source_hash, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (pub.dedupe_key, h, pub.coletado_em, pub.coletado_em, pub.source_hash, payload),
            )
            if commit:
                self.conn.commit()
            return status

        old_hash = row[0]
        status = "ATUALIZADA" if old_hash != h else "JA_CONHECIDA"
        pub.situacao_coleta = status
        payload = json.dumps(asdict(pub), ensure_ascii=False, sort_keys=True)
        self.conn.execute(
            "UPDATE publicacoes SET content_hash = ?, last_seen = ?, source_hash = ?, payload_json = ? WHERE dedupe_key = ?",
            (h, pub.coletado_em, pub.source_hash, payload, pub.dedupe_key),
        )
        if commit:
            self.conn.commit()
        return status

    def record_execution(self, data: dict, *, commit: bool = True) -> None:
        self.conn.execute(
            """
            INSERT INTO execucoes (
                started_at, finished_at, start_date, end_date, total_raw, total_normalized,
                total_new, total_updated, requests_made, complete, report_path, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("started_at", ""), data.get("finished_at", ""), data.get("start_date", ""),
                data.get("end_date", ""), int(data.get("total_raw", 0)), int(data.get("total_normalized", 0)),
                int(data.get("total_new", 0)), int(data.get("total_updated", 0)), int(data.get("requests_made", 0)),
                1 if data.get("complete", False) else 0, data.get("report_path", ""), data.get("error", ""),
            ),
        )
        if commit:
            self.conn.commit()

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def last_execution(self) -> dict | None:
        row = self.conn.execute(
            "SELECT started_at, finished_at, start_date, end_date, total_raw, total_normalized, total_new, total_updated, requests_made, complete, report_path, error FROM execucoes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        keys = [
            "started_at", "finished_at", "start_date", "end_date", "total_raw", "total_normalized",
            "total_new", "total_updated", "requests_made", "complete", "report_path", "error",
        ]
        result = dict(zip(keys, row))
        # Este valor é usado apenas para exibição no menu. O banco continua
        # preservando o timestamp ISO original para rastreabilidade.
        result["finished_at"] = format_datetime_ptbr(result.get("finished_at"))
        return result

    def last_complete_end_date(self) -> str | None:
        row = self.conn.execute(
            "SELECT end_date FROM execucoes WHERE complete = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row and row[0] else None

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "PublicationStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
