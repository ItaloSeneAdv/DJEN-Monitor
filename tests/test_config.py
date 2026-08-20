from djen_monitor.config import AppConfig, OABConfig, load_config, normalize_oab_number, valid_time


def test_normalize_oab():
    assert normalize_oab_number("OAB/PR 123456") == "123456"
    assert normalize_oab_number("00123456-A") == "123456-A"


def test_config_validation():
    cfg = AppConfig(oabs=[OABConfig("123456", "pr")], janela_dias=3, horario="08:00")
    cfg.validate()
    assert cfg.oabs[0].uf == "PR"
    assert valid_time("23:59")
    assert not valid_time("25:00")


def test_normalize_oab_with_thousands_separator():
    assert normalize_oab_number("123.456") == "123456"


def test_normalize_oab_accepts_number_slash_uf_format():
    from djen_monitor.config import normalize_oab_number
    assert normalize_oab_number("123.456/PR") == "123456"


def test_oab_optional_name_preserves_accents():
    item = OABConfig("123456", "pr", "  Ítalo   João de Sêne  ").normalized()
    assert item.nome == "Ítalo João de Sêne"


def test_old_config_without_name_remains_compatible(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"oabs":[{"numero":"123456","uf":"PR"}],"janela_dias":3,"horario":"08:00"}', encoding="utf-8")
    cfg = load_config(path)
    assert cfg is not None
    assert cfg.oabs[0].nome == ""
