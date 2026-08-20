from __future__ import annotations

from .normalize import Publication, strip_html

ATTENTION_TERMS = [
    "intim", "citaç", "citacao", "citado", "prazo", "manifest", "contest", "contrarraz",
    "recurso", "recorrer", "embargos", "agravo", "apelaç", "apelacao", "comparec", "audiência",
    "audiencia", "cumpr", "pagar", "pagamento", "emendar", "regularizar", "impugnar", "responder",
    "sentença", "sentenca", "decisão", "decisao", "despacho", "vista", "ciência", "ciencia",
]
ROUTINE_TERMS = ["juntada", "certidão", "certidao", "distribuição", "distribuicao", "remessa", "baixa", "arquiv"]


def classify(pub: Publication) -> Publication:
    plain = strip_html(pub.texto_integral).lower()
    meta = " ".join([pub.tipo_comunicacao, pub.tipo_documento, pub.status_fonte, pub.motivo_cancelamento]).lower()
    haystack = f"{meta} {plain}"

    missing = []
    if not pub.numero_processo:
        missing.append("número do processo")
    if not pub.texto_integral:
        missing.append("texto")
    if not pub.data_disponibilizacao:
        missing.append("data de disponibilização")
    if not pub.nome_advogado:
        missing.append("identificação do advogado")

    if pub.motivo_cancelamento:
        pub.classificacao = "REVISAR"
        pub.motivo_classificacao = "A comunicação informa cancelamento ou alteração e precisa de conferência humana."
        return pub

    if str(pub.ativo_fonte).strip().lower() in {"false", "0", "nao", "não"}:
        pub.classificacao = "REVISAR"
        pub.motivo_classificacao = "A fonte marcou a comunicação como inativa; exige conferência humana."
        return pub

    status_lower = str(pub.status_fonte or "").strip().lower()
    if any(term in status_lower for term in ("cancel", "inativ", "anulad", "reprocess")):
        pub.classificacao = "REVISAR"
        pub.motivo_classificacao = f"Status informado pela fonte exige conferência humana: {pub.status_fonte}."
        return pub

    matches = [term for term in ATTENTION_TERMS if term in haystack]
    if matches:
        pub.classificacao = "POSSIVEL_PRAZO"
        pub.motivo_classificacao = (
            "Termos de atenção encontrados: " + ", ".join(matches[:6])
            + ". A classificação não confirma a existência de prazo."
        )
        return pub

    if missing:
        pub.classificacao = "REVISAR"
        pub.motivo_classificacao = "Campos ausentes ou incompletos: " + ", ".join(missing) + "."
        return pub

    routine_matches = [term for term in ROUTINE_TERMS if term in haystack]
    if routine_matches:
        pub.classificacao = "ROTINA"
        pub.motivo_classificacao = (
            "Termos provavelmente informativos encontrados: " + ", ".join(routine_matches[:5])
            + ". Ainda exige revisão profissional."
        )
        return pub

    pub.classificacao = "REVISAR"
    pub.motivo_classificacao = "Não houve regra suficientemente clara para classificar automaticamente."
    return pub
