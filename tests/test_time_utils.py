from djen_monitor.time_utils import brasilia_now, brasilia_today, format_datetime_ptbr


def test_brasilia_clock_is_timezone_aware():
    now = brasilia_now()
    assert now.tzinfo is not None
    assert now.date() == brasilia_today()
    assert now.utcoffset() is not None


def test_format_datetime_ptbr_iso_with_offset():
    assert format_datetime_ptbr("2026-08-20T09:48:58-03:00") == "20/08/2026 às 09:48"


def test_format_datetime_ptbr_empty_and_invalid():
    assert format_datetime_ptbr(None) == "Nunca executado"
    assert format_datetime_ptbr("") == "Nunca executado"
    assert format_datetime_ptbr("valor-invalido") == "valor-invalido"
