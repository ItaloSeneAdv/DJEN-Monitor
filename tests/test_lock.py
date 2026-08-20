import pytest

from djen_monitor.lock import AlreadyRunningError, SingleRunLock


def test_single_run_lock(tmp_path):
    path = tmp_path / "run.lock"
    with SingleRunLock(path):
        with pytest.raises(AlreadyRunningError):
            with SingleRunLock(path):
                pass
