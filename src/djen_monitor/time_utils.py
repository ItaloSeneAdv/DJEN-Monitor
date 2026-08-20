from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python >= 3.11 is required
    ZoneInfo = None  # type: ignore[assignment]


def brasilia_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/Sao_Paulo")
        except Exception:
            pass
    # Fallback conservador para ambientes quebrados. O pacote tzdata faz com que
    # o caminho normal funcione também no Windows.
    return timezone(timedelta(hours=-3), name="America/Sao_Paulo")


def brasilia_now() -> datetime:
    return datetime.now(brasilia_tz())


def brasilia_today() -> date:
    return brasilia_now().date()


def format_datetime_ptbr(value: str | datetime | None) -> str:
    """Formata data/hora para exibição humana no padrão brasileiro."""
    if value is None or value == "":
        return "Nunca executado"

    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return str(value)

    if dt.tzinfo is not None:
        dt = dt.astimezone(brasilia_tz())
    return dt.strftime("%d/%m/%Y às %H:%M")
