from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from .config import oab_base_digits
from .constants import PORTAL_URL
from .time_utils import brasilia_now


@dataclass
class Publication:
    dedupe_key: str
    source_id: str
    source_hash: str
    tribunal: str
    sigla_tribunal: str
    orgao_julgador: str
    data_disponibilizacao: str
    data_publicacao: str
    tipo_comunicacao: str
    meio: str
    numero_processo: str
    nome_advogado: str
    oab: str
    uf_oab: str
    oab_consultada: str
    uf_consultada: str
    partes: str
    texto_integral: str
    link_oficial: str
    link_consulta_djen: str
    motivo_cancelamento: str
    status_fonte: str
    ativo_fonte: str
    tipo_documento: str
    classe_processual: str
    meio_completo: str
    coletado_em: str
    nome_oab_consultada: str = ""
    rotulo_oab_consultada: str = ""
    classificacao: str = "REVISAR"
    motivo_classificacao: str = "Classificação ainda não executada."
    situacao_coleta: str = "NOVA"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


KEYS = {
    "id": ["id", "numeroComunicacao", "numero_comunicacao", "idComunicacao", "id_comunicacao"],
    "hash": ["hash", "hashComunicacao", "hash_comunicacao"],
    "tribunal": ["tribunal", "nomeTribunal", "nome_tribunal"],
    "sigla": ["siglaTribunal", "sigla_tribunal", "tribunalSigla", "tribunal_sigla"],
    "orgao": ["nomeOrgao", "nome_orgao", "orgaoJulgador", "orgao_julgador", "orgao", "unidade"],
    "disp": ["dataDisponibilizacao", "data_disponibilizacao", "dataDisponibilizacaoDiario", "data_disponibilizacao_diario"],
    "pub": ["dataPublicacao", "data_publicacao", "dataPublicacaoDiario", "data_publicacao_diario"],
    "tipo": ["tipoComunicacao", "tipo_comunicacao", "tipo", "descricaoTipoComunicacao"],
    "meio": ["meio", "tipoMeio", "tipo_meio"],
    "meio_completo": ["meiocompleto", "meioCompleto", "meio_completo"],
    "processo": ["numeroProcesso", "numero_processo", "processo", "numeroProcessoComMascara"],
    "texto": ["texto", "textoComunicacao", "texto_comunicacao", "conteudo", "inteiroTeor", "inteiro_teor"],
    "link": ["link", "url", "linkInteiroTeor", "link_inteiro_teor", "urlInteiroTeor", "url_inteiro_teor"],
    "cancelamento": ["motivoCancelamento", "motivo_cancelamento", "cancelamento"],
    "status": ["status", "statusComunicacao", "status_comunicacao", "situacao"],
    "ativo": ["ativo", "active"],
    "tipo_documento": ["tipoDocumento", "tipo_documento"],
    "classe": ["nomeClasse", "nome_classe", "classeProcessual", "classe_processual"],
}


def normalize_item(
    raw: dict[str, Any],
    target_oab: str,
    target_uf: str,
    collected_at: datetime | None = None,
    target_name: str = "",
) -> Publication:
    collected_at = collected_at or brasilia_now()
    # Identificadores genericos como "id" nunca sao procurados recursivamente:
    # um id de advogado/parte nao pode virar id da comunicacao.
    source_id = text_value(find_root_value(raw, KEYS["id"]))
    source_hash = text_value(find_root_value(raw, KEYS["hash"]))
    tribunal = text_value(find_value(raw, KEYS["tribunal"]))
    sigla = text_value(find_value(raw, KEYS["sigla"]))
    orgao = text_value(find_value(raw, KEYS["orgao"]))
    disp = date_text(find_value(raw, KEYS["disp"]))
    pub = date_text(find_value(raw, KEYS["pub"]))
    tipo = text_value(find_value(raw, KEYS["tipo"]))
    meio = text_value(find_value(raw, KEYS["meio"]))
    meio_completo = text_value(find_value(raw, KEYS["meio_completo"]))
    processo = text_value(find_value(raw, KEYS["processo"]))
    texto = text_value(find_value(raw, KEYS["texto"]), preserve_html=True)
    link = text_value(find_value(raw, KEYS["link"]))
    cancelamento = text_value(find_value(raw, KEYS["cancelamento"]))
    status_fonte = text_value(find_root_value(raw, KEYS["status"]))
    ativo_fonte = text_value(find_root_value(raw, KEYS["ativo"]))
    tipo_documento = text_value(find_value(raw, KEYS["tipo_documento"]))
    classe_processual = text_value(find_value(raw, KEYS["classe"]))

    advogados = extract_advogados(raw)
    target_digits = oab_base_digits(target_oab)
    matched = [
        a for a in advogados
        if oab_base_digits(a.get("oab", "")) == target_digits
        and (not str(a.get("uf", "")).strip() or str(a.get("uf", "")).upper() == target_uf.upper())
    ]
    use_advogados = matched or advogados
    nomes = join_unique(a.get("nome", "") for a in use_advogados)
    # Nunca transforma o filtro usado na consulta em dado retornado pela fonte.
    # Se o item nao trouxer advogado/OAB, os campos confirmados ficam vazios e
    # a OAB usada na busca permanece separada em oab_consultada/uf_consultada.
    oabs = join_unique(a.get("oab", "") for a in use_advogados)
    ufs = join_unique(a.get("uf", "") for a in use_advogados)

    partes = extract_partes(raw)
    link_consulta_djen = build_portal_link(processo, target_oab, target_uf, disp)

    dedupe_key = build_dedupe_key(raw, source_id, source_hash, sigla, processo, disp, tipo, texto)
    return Publication(
        dedupe_key=dedupe_key,
        source_id=source_id,
        source_hash=source_hash,
        tribunal=tribunal,
        sigla_tribunal=sigla,
        orgao_julgador=orgao,
        data_disponibilizacao=disp,
        data_publicacao=pub,
        tipo_comunicacao=tipo,
        meio=meio,
        numero_processo=processo,
        nome_advogado=nomes,
        oab=oabs,
        uf_oab=ufs,
        oab_consultada=target_oab,
        uf_consultada=target_uf.upper(),
        nome_oab_consultada=str(target_name or "").strip(),
        rotulo_oab_consultada=(
            f"{str(target_name).strip()} ({target_oab}/{target_uf.upper()})"
            if str(target_name or "").strip() else f"{target_oab}/{target_uf.upper()}"
        ),
        partes=partes,
        texto_integral=texto,
        link_oficial=link,
        link_consulta_djen=link_consulta_djen,
        motivo_cancelamento=cancelamento,
        status_fonte=status_fonte,
        ativo_fonte=ativo_fonte,
        tipo_documento=tipo_documento,
        classe_processual=classe_processual,
        meio_completo=meio_completo,
        coletado_em=collected_at.isoformat(timespec="seconds"),
    )


def find_root_value(raw: dict[str, Any], candidate_keys: list[str]) -> Any:
    """Busca apenas no objeto da comunicacao, nunca em filhos genericos."""
    wanted = {normalize_key(k) for k in candidate_keys}
    for key, value in raw.items():
        if normalize_key(str(key)) in wanted and value not in (None, "", [], {}):
            return value
    # Tolera um envelope explicito {"comunicacao": {...}}, mas nao percorre
    # partes/advogados/destinatarios em busca de ids genericos.
    for envelope_key in ("comunicacao", "communication"):
        nested = raw.get(envelope_key)
        if isinstance(nested, dict):
            for key, value in nested.items():
                if normalize_key(str(key)) in wanted and value not in (None, "", [], {}):
                    return value
    return ""


def find_value(obj: Any, candidate_keys: list[str]) -> Any:
    wanted = {normalize_key(k) for k in candidate_keys}
    queue = [obj]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if isinstance(current, (dict, list)):
            obj_id = id(current)
            if obj_id in seen:
                continue
            seen.add(obj_id)
        if isinstance(current, dict):
            for key, value in current.items():
                if normalize_key(str(key)) in wanted and value not in (None, "", [], {}):
                    return value
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            for value in current:
                if isinstance(value, (dict, list)):
                    queue.append(value)
    return ""


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def text_value(value: Any, preserve_html: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value if preserve_html else value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " | ".join(text_value(v, preserve_html=preserve_html) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        if preserve_html:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return " | ".join(f"{k}: {text_value(v)}" for k, v in value.items() if v not in (None, ""))
    return str(value)


def date_text(value: Any) -> str:
    raw = text_value(value)
    if not raw:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        return raw


def extract_advogados(raw: dict[str, Any]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for node in walk(raw):
        if not isinstance(node, dict):
            continue
        keys = {normalize_key(str(k)): k for k in node.keys()}
        oab_key = next((keys[k] for k in keys if k in {"numerooab", "oab", "inscricaooab", "numeroinscricao"}), None)
        uf_key = next((keys[k] for k in keys if k in {"ufoab", "uf", "seccional", "siglauf"}), None)
        nome_key = next((keys[k] for k in keys if k in {"nomeadvogado", "nome", "advogado"}), None)
        if not oab_key:
            continue
        oab = text_value(node.get(oab_key))
        uf = text_value(node.get(uf_key)).upper() if uf_key else ""
        nome_value = node.get(nome_key) if nome_key else ""
        if isinstance(nome_value, dict):
            nome = text_value(find_value(nome_value, ["nome", "nomeAdvogado"]))
        else:
            nome = text_value(nome_value)
        if oab:
            results.append({"nome": nome, "oab": oab, "uf": uf})
    return unique_dicts(results, ("nome", "oab", "uf"))


def extract_partes(raw: dict[str, Any]) -> str:
    candidates = []
    for node in walk(raw):
        if not isinstance(node, dict):
            continue
        normalized = {normalize_key(str(k)): k for k in node}
        if any(k in normalized for k in ("nomeparte", "polo", "tipoparte")):
            nome_key = normalized.get("nomeparte") or normalized.get("nome")
            polo_key = normalized.get("polo") or normalized.get("tipoparte")
            nome = text_value(node.get(nome_key)) if nome_key else ""
            polo = text_value(node.get(polo_key)) if polo_key else ""
            if nome:
                candidates.append(f"{polo}: {nome}" if polo else nome)
    if candidates:
        return join_unique(candidates)

    direct = find_value(raw, ["partes", "destinatarios", "destinatario"])
    return text_value(direct)


def walk(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, dict):
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def unique_dicts(items: list[dict[str, str]], fields: tuple[str, ...]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for item in items:
        key = tuple(item.get(field, "") for field in fields)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def join_unique(values: Iterable[str]) -> str:
    result = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return " | ".join(result)


def build_portal_link(processo: str, oab: str, uf: str, disp: str) -> str:
    params: dict[str, str] = {"numeroOab": oab_base_digits(oab), "ufOab": uf.lower()}
    digits = "".join(ch for ch in processo if ch.isdigit())
    if digits:
        params["numeroProcesso"] = digits
    if disp and re.fullmatch(r"\d{4}-\d{2}-\d{2}", disp):
        params["dataDisponibilizacaoInicio"] = disp
        params["dataDisponibilizacaoFim"] = disp
    return f"{PORTAL_URL}?{urllib.parse.urlencode(params)}"


def build_dedupe_key(raw: dict[str, Any], source_id: str, source_hash: str, tribunal: str, processo: str, disp: str, tipo: str, texto: str) -> str:
    if source_id:
        return f"id:{source_id}"
    if source_hash:
        return f"hash:{source_hash}"
    # Sem id/hash oficial nao existe chave natural segura. Hasheamos o item
    # inteiro para evitar fundir duas comunicacoes diferentes apenas porque
    # compartilham processo/data/tipo e o mesmo inicio de texto.
    stable = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(stable.encode("utf-8", errors="replace")).hexdigest()


def content_hash(pub: Publication) -> str:
    payload = pub.to_dict().copy()
    for local_field in (
        "coletado_em", "situacao_coleta", "classificacao", "motivo_classificacao",
        "oab_consultada", "uf_consultada", "nome_oab_consultada", "rotulo_oab_consultada", "link_consulta_djen",
    ):
        payload.pop(local_field, None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def strip_html(value: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", value or "")
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
