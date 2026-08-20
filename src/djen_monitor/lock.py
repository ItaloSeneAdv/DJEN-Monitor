from __future__ import annotations

import os
from pathlib import Path

from .paths import app_data_dir


class AlreadyRunningError(RuntimeError):
    pass


class SingleRunLock:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "execucao.lock")
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")

        if os.name == "nt":
            import msvcrt
            try:
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                self.file.close()
                self.file = None
                raise AlreadyRunningError("Ja existe uma consulta do DJEN Monitor em andamento.") from exc
        else:
            import fcntl
            try:
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self.file.close()
                self.file = None
                raise AlreadyRunningError("Ja existe uma consulta do DJEN Monitor em andamento.") from exc

        # Only touch file contents once we're confirmed to hold the lock.
        self.file.seek(0)
        if self.file.read(1) == b"":
            self.file.seek(0)
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)

        return self

    def __exit__(self, exc_type, exc, tb):
        if self.file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None
