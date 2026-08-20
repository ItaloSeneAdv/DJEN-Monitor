from djen_monitor.normalize import Publication
from djen_monitor.runner import _merge_publications


def make_pub(oab, uf, nome, text="texto", rotulo=""):
    return Publication(
        dedupe_key="id:1", source_id="1", source_hash="h", tribunal="T", sigla_tribunal="TJ",
        orgao_julgador="Vara", data_disponibilizacao="2026-08-19", data_publicacao="",
        tipo_comunicacao="Intimacao", meio="D", numero_processo="123", nome_advogado=nome,
        oab=oab, uf_oab=uf, oab_consultada=oab, uf_consultada=uf, partes="PARTE", texto_integral=text,
        link_oficial="https://example.invalid", link_consulta_djen="https://comunica.pje.jus.br/consulta",
        motivo_cancelamento="", status_fonte="", ativo_fonte="True", tipo_documento="Despacho",
        classe_processual="Procedimento", meio_completo="DJEN", coletado_em="2026-08-19T08:00:00-03:00",
        nome_oab_consultada=nome, rotulo_oab_consultada=rotulo or f"{nome} ({oab}/{uf})",
    )


def test_merge_same_communication_preserves_multiple_registrations():
    a = make_pub("123456", "PR", "ADVOGADO")
    b = make_pub("999999", "SP", "ADVOGADO")
    merged = _merge_publications(a, b)
    assert set(merged.oab.split(" | ")) == {"123456", "999999"}
    assert set(merged.uf_oab.split(" | ")) == {"PR", "SP"}
    assert set(merged.oab_consultada.split(" | ")) == {"123456", "999999"}
    assert set(merged.uf_consultada.split(" | ")) == {"PR", "SP"}


def test_merge_preserves_oab_labels_even_when_one_has_no_optional_name():
    a = make_pub("123456", "PR", "", rotulo="123456/PR")
    b = make_pub("654321", "PR", "Isabella José", rotulo="Isabella José (654321/PR)")
    merged = _merge_publications(a, b)
    assert set(merged.rotulo_oab_consultada.split(" | ")) == {"123456/PR", "Isabella José (654321/PR)"}
