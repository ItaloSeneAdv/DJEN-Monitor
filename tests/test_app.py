from types import SimpleNamespace
import djen_monitor.app as app


def test_automatic_mode_returns_failure_for_incomplete_collection(monkeypatch):
    monkeypatch.setattr(app, "setup_logging", lambda **_kwargs: None)
    monkeypatch.setattr(app, "load_config", lambda: object())
    monkeypatch.setattr(
        app,
        "run_monitor",
        lambda _cfg, manual=False: SimpleNamespace(error="", complete=False),
    )
    assert app.main(["--automatico"]) == 1


def test_automatic_mode_returns_success_only_when_complete(monkeypatch):
    monkeypatch.setattr(app, "setup_logging", lambda **_kwargs: None)
    monkeypatch.setattr(app, "load_config", lambda: object())
    monkeypatch.setattr(
        app,
        "run_monitor",
        lambda _cfg, manual=False: SimpleNamespace(error="", complete=True),
    )
    assert app.main(["--automatico"]) == 0
