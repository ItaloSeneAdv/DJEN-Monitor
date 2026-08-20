from djen_monitor.config import AppConfig, OABConfig
import djen_monitor.ui as ui


def test_failed_schedule_time_change_does_not_change_saved_time(monkeypatch):
    cfg = AppConfig(oabs=[OABConfig("123456", "PR")], horario="08:00")
    answers = iter(["2", "09:15", "", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(ui, "clear_screen", lambda: None)
    monkeypatch.setattr(ui, "schedule_exists", lambda: True)
    monkeypatch.setattr(ui, "save_config", lambda _cfg: (_ for _ in ()).throw(AssertionError("não deveria salvar")))
    monkeypatch.setattr(
        ui,
        "install_daily_schedule",
        lambda _h: (_ for _ in ()).throw(ui.SchedulerError("falha simulada")),
    )
    result = ui.schedule_menu(cfg)
    assert result.horario == "08:00"


def test_first_run_setup_is_single_guided_flow_with_optional_name(monkeypatch):
    answers = iter(["123.456", "pr", "Ítalo José", "n", "", "", "n", ""])
    saved = []
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(ui, "clear_screen", lambda: None)
    monkeypatch.setattr(ui, "save_config", lambda cfg: saved.append(cfg))
    cfg = ui.first_run_setup()
    assert [(item.numero, item.uf, item.nome) for item in cfg.oabs] == [("123456", "PR", "Ítalo José")]
    assert cfg.janela_dias == 3
    assert cfg.horario == "08:00"
    assert cfg.agendamento_ativo is False
    assert saved


def test_first_run_name_is_truly_optional(monkeypatch):
    answers = iter(["123456", "PR", "", "n", "", "", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(ui, "clear_screen", lambda: None)
    monkeypatch.setattr(ui, "save_config", lambda _cfg: None)
    cfg = ui.first_run_setup()
    assert cfg.oabs[0].nome == ""
    assert ui.format_oab(cfg.oabs[0]) == "123456/PR"
