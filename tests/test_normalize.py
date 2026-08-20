import json
from pathlib import Path

from djen_monitor.classify import classify
from djen_monitor.normalize import normalize_item

FIXTURE = Path(__file__).parent / "fixtures" / "comunicacoes_anonimizadas.json"


def test_normalize_fixture():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pub = normalize_item(payload["items"][0], "123456", "PR")
    assert pub.numero_processo == "0000000-00.2026.8.00.0000"
    assert "ADVOGADO EXEMPLO" in pub.nome_advogado
    assert pub.oab == "123456"
    assert pub.uf_oab == "PR"
    assert "PARTE EXEMPLO" in pub.partes


def test_classification_is_explainable():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pub = classify(normalize_item(payload["items"][0], "123456", "PR"))
    assert pub.classificacao == "POSSIVEL_PRAZO"
    assert "não confirma" in pub.motivo_classificacao.lower()


def test_realistic_nested_advogado_shape():
    raw = {
        "id": 1,
        "numero_processo": "00000012320268260100",
        "destinatarioadvogados": [
            {"advogado": {"nome": "ADVOGADO TESTE", "numero_oab": "123456-O", "uf_oab": "PR"}}
        ],
        "destinatarios": [{"nome": "PARTE TESTE", "polo": "A"}],
        "texto": "conteudo",
    }
    pub = normalize_item(raw, "123456", "PR")
    assert pub.nome_advogado == "ADVOGADO TESTE"
    assert pub.oab == "123456-O"
    assert pub.uf_oab == "PR"
    assert "PARTE TESTE" in pub.partes


def test_original_text_whitespace_is_preserved():
    raw = {"id": 1, "texto": "  <p>Texto original</p>\n", "numero_processo": "1"}
    pub = normalize_item(raw, "123456", "PR")
    assert pub.texto_integral == "  <p>Texto original</p>\n"


def test_missing_advogado_does_not_invent_returned_oab():
    raw = {
        "id": "sem-adv",
        "numero_processo": "123",
        "data_disponibilizacao": "2026-08-19",
        "texto": "Comunicacao sem bloco de advogado",
    }
    pub = normalize_item(raw, "123456", "PR")
    assert pub.oab == ""
    assert pub.uf_oab == ""
    assert pub.oab_consultada == "123456"
    assert pub.uf_consultada == "PR"


def test_generic_motivo_is_not_mistaken_for_cancellation():
    raw = {
        "id": 2, "motivo": "Assunto administrativo", "texto": "conteudo",
        "destinatarioadvogados": [{"advogado": {"nome": "A", "numero_oab": "123456", "uf_oab": "PR"}}],
    }
    pub = normalize_item(raw, "123456", "PR")
    assert pub.motivo_cancelamento == ""


def test_inactive_source_status_is_preserved_and_forces_review():
    raw = {
        "id": 3, "ativo": False, "texto": "conteudo",
        "destinatarioadvogados": [{"advogado": {"nome": "A", "numero_oab": "123456", "uf_oab": "PR"}}],
    }
    pub = classify(normalize_item(raw, "123456", "PR"))
    assert pub.ativo_fonte == "False"
    assert pub.classificacao == "REVISAR"
    assert "inativa" in pub.motivo_classificacao.lower()


def test_nested_generic_id_is_not_used_as_communication_id():
    raw = {
        "numero_processo": "00000012320268260100",
        "destinatarioadvogados": [
            {"advogado": {"id": 999, "nome": "ADVOGADO", "numero_oab": "123456", "uf_oab": "PR"}}
        ],
        "texto": "conteudo",
    }
    pub = normalize_item(raw, "123456", "PR")
    assert pub.source_id == ""
    assert pub.dedupe_key.startswith("sha256:")


def test_source_link_and_generated_portal_link_are_separate():
    raw = {
        "id": 9, "numero_processo": "00000012320268260100",
        "data_disponibilizacao": "2026-08-19", "texto": "conteudo",
        "destinatarioadvogados": [{"advogado": {"nome": "A", "numero_oab": "123456", "uf_oab": "PR"}}],
    }
    pub = normalize_item(raw, "123456", "PR")
    assert pub.link_oficial == ""
    assert pub.link_consulta_djen.startswith("https://comunica.pje.jus.br/consulta?")


def test_document_type_class_status_and_full_medium_are_preserved():
    raw = {
        "id": 10, "tipoDocumento": "Despacho", "nomeClasse": "Procedimento Comum",
        "status": "Processado", "meiocompleto": "Diario de Justica Eletronico Nacional",
        "texto": "conteudo",
        "destinatarioadvogados": [{"advogado": {"nome": "A", "numero_oab": "123456", "uf_oab": "PR"}}],
    }
    pub = normalize_item(raw, "123456", "PR")
    assert pub.tipo_documento == "Despacho"
    assert pub.classe_processual == "Procedimento Comum"
    assert pub.status_fonte == "Processado"
    assert "Diario" in pub.meio_completo


def test_normalize_preserves_configured_oab_name_without_affecting_source_fields():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pub = normalize_item(payload["items"][0], "123456", "PR", target_name="João d\'Ávila")
    assert pub.nome_oab_consultada == "João d\'Ávila"
    assert pub.rotulo_oab_consultada == "João d\'Ávila (123456/PR)"
    assert pub.oab_consultada == "123456"


def test_content_hash_ignores_local_optional_oab_name():
    from djen_monitor.normalize import content_hash

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    without_name = normalize_item(payload["items"][0], "123456", "PR", target_name="")
    with_name = normalize_item(payload["items"][0], "123456", "PR", target_name="João d'Ávila")
    assert content_hash(without_name) == content_hash(with_name)
