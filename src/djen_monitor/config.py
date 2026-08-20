from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import DEFAULT_REQUEST_INTERVAL, DEFAULT_TIME, DEFAULT_WINDOW_DAYS
from .paths import config_path

UF_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


@dataclass
class OABConfig:
    numero: str
    uf: str
    nome: str = ""

    def normalized(self) -> "OABConfig":
        numero = normalize_oab_number(self.numero)
        uf = self.uf.strip().upper()
        nome = normalize_oab_name(self.nome)
        if not numero:
            raise ValueError("Número da OAB inválido.")
        if uf not in UF_VALIDAS:
            raise ValueError("UF da OAB inválida.")
        return OABConfig(numero=numero, uf=uf, nome=nome)


@dataclass
class AppConfig:
    oabs: list[OABConfig] = field(default_factory=list)
    janela_dias: int = DEFAULT_WINDOW_DAYS
    horario: str = DEFAULT_TIME
    agendamento_ativo: bool = False
    consultar_variantes_oab: bool = True
    intervalo_requisicoes_segundos: float = DEFAULT_REQUEST_INTERVAL

    def validate(self) -> "AppConfig":
        normalized: list[OABConfig] = []
        seen = set()
        for item in self.oabs:
            n = item.normalized()
            key = (n.numero, n.uf)
            if key not in seen:
                seen.add(key)
                normalized.append(n)
        if not normalized:
            raise ValueError("Cadastre pelo menos uma OAB.")
        if not isinstance(self.janela_dias, int) or self.janela_dias < 1 or self.janela_dias > 3650:
            raise ValueError("A janela de busca deve estar entre 1 e 3650 dias.")
        if not valid_time(self.horario):
            raise ValueError("Horário inválido. Use HH:MM.")
        if self.intervalo_requisicoes_segundos < 0:
            raise ValueError("Intervalo entre requisições inválido.")
        self.oabs = normalized
        return self


def normalize_oab_number(value: str) -> str:
    value = str(value or "").strip().upper().replace(" ", "").replace(".", "")
    value = value.replace("OAB", "")
    # O campo UF e separado, mas usuarios frequentemente colam "123456/PR".
    value = re.sub(r"/[A-Z]{2}$", "", value)
    value = value.replace("/", "")
    match = re.search(r"(\d+)(?:-?([A-Z]))?$", value)
    if not match:
        return ""
    number, suffix = match.groups()
    number = str(int(number)) if number else ""
    return f"{number}-{suffix}" if suffix else number


def normalize_oab_name(value: str) -> str:
    """Normaliza apenas espaços; nomes/apelidos preservam acentos e maiúsculas."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) > 80:
        raise ValueError("O nome/apelido da OAB deve ter no máximo 80 caracteres.")
    return text


def oab_base_digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


def valid_time(value: str) -> bool:
    if not re.fullmatch(r"\d{2}:\d{2}", str(value or "")):
        return False
    hh, mm = map(int, value.split(":"))
    return 0 <= hh <= 23 and 0 <= mm <= 59


def load_config(path: Path | None = None) -> AppConfig | None:
    path = path or config_path()
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = AppConfig(
        oabs=[OABConfig(**item) for item in raw.get("oabs", [])],
        janela_dias=int(raw.get("janela_dias", DEFAULT_WINDOW_DAYS)),
        horario=str(raw.get("horario", DEFAULT_TIME)),
        agendamento_ativo=bool(raw.get("agendamento_ativo", False)),
        consultar_variantes_oab=bool(raw.get("consultar_variantes_oab", True)),
        intervalo_requisicoes_segundos=float(raw.get("intervalo_requisicoes_segundos", DEFAULT_REQUEST_INTERVAL)),
    )
    return cfg.validate()


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    cfg.validate()
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(cfg)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
