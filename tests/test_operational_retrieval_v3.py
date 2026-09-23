from contextlib import contextmanager

import pytest
from sqlalchemy import delete, func, select
from test_layout_official_hotfix import _event, _s1005
from test_mos_integration import build_fixture, cleanup, materialize_phase4_fixture

from rag_esocial.build_service import create_build
from rag_esocial.evidence_service import _render
from rag_esocial.models.build import CitationTarget
from rag_esocial.models.runtime import ActiveRuntime
from rag_esocial.models.search import (
    SearchProjection,
    SearchUnit,
    SearchUnitCitationTarget,
)
from rag_esocial.operational_query import analyze_query
from rag_esocial.runtime_defaults import DEFAULT_PARSER_CONFIG, DEFAULT_PARSER_REVISION
from rag_esocial.runtime_service import (
    activate_runtime,
    get_active_runtime,
    is_build_ready,
)
from rag_esocial.search_service import PROFILES, materialize_projection, search
from rag_esocial.setup_service import prepare_runtime


def _schema(root, parent, children, *, facets=False):
    items = "".join(
        f"<xs:element name='{name}' type='xs:string'/>" for name in children
    )
    restricted = (
        "<xs:element name='restricted'><xs:simpleType><xs:restriction "
        "base='xs:string'><xs:pattern value='[A-Z]+'/><xs:enumeration "
        "value='A'/></xs:restriction></xs:simpleType></xs:element>"
        if facets
        else ""
    )
    return (
        "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema' "
        "targetNamespace='urn:operational:test'>"
        "<xs:element name='eSocial'><xs:complexType><xs:sequence>"
        f"<xs:element name='{root}'><xs:complexType><xs:sequence>"
        f"<xs:element name='{parent}'><xs:complexType><xs:sequence>"
        f"{items}</xs:sequence></xs:complexType></xs:element>"
        "</xs:sequence></xs:complexType></xs:element>"
        f"</xs:sequence></xs:complexType></xs:element>{restricted}</xs:schema>"
    )


@pytest.mark.parametrize(
    ("question", "event", "attributes", "relationship", "families"),
    [
        ("ocorrência de alpha no S-1000", "S-1000", ("occurrence",), None, ()),
        ("condição de beta no S-1200", "S-1200", ("condition",), None, ()),
        ("decimais do campo gamma S-9999", "S-9999", ("decimals",), None, ()),
        ("ocorrência de alpha no S-7777", "S-7777", ("occurrence",), None, ()),
        ("condição de beta no S-8888", "S-8888", ("condition",), None, ()),
        ("tipo e tamanho de campo gamma", None, ("type", "size"), None, ()),
        (
            "filhos de alpha no XSD S-7777",
            "S-7777",
            ("children",),
            "CHILDREN",
            ("XSD",),
        ),
        (
            "compare evidências de alpha S-7777 no MOS, Leiaute e XSD",
            "S-7777",
            (),
            None,
            ("MOS", "LAYOUT", "XSD"),
        ),
    ],
)
def test_query_analysis_is_schema_based(
    question, event, attributes, relationship, families
):
    intent = analyze_query(question, {"alpha", "beta", "gamma"})
    assert intent.event_codes == ((event,) if event else ())
    assert intent.requested_attributes == attributes
    assert intent.relationship == relationship
    assert intent.requested_families == families
    assert (
        "alpha" in intent.technical_tokens
        or "beta" in intent.technical_tokens
        or "gamma" in intent.technical_tokens
    )


def _generic_layout():
    return """<section data-kind='event' code='S-7777' title='Omega'>
<div data-kind='group' name='evtOmega' level='1'>
<div data-kind='group' name='alpha' level='2' occurrence='1' condition='O'>
<p data-kind='field' name='first' type='N' occurrence='1' size='4' decimals='2'></p>
<p data-kind='field' name='second' type='C' occurrence='1' size='8'></p>
</div></div></section>
<section data-kind='event' code='S-8888' title='Sigma'>
<div data-kind='group' name='evtSigma' level='1'>
<div data-kind='group' name='alpha' level='2' occurrence='0-1' condition='OC'
description='Referência textual a S-7777 e alpha'>
<p data-kind='field' name='foreign' type='C' occurrence='1' size='9'></p>
</div></div></section>""" + "".join(
        "<section data-kind='event' code='S-{code}' title='Noise'>"
        "<div data-kind='group' name='evtNoise{index}' level='1' "
        "description='S-7777 alpha first second'></div></section>".format(
            code=9000 + index, index=index
        )
        for index in range(20)
    )


def test_generic_event_attribute_children_xsd_and_cross_source(tmp_path, monkeypatch):
    import rag_esocial.cli as cli_module

    session, snapshot, build, _, _, ids = build_fixture(
        tmp_path,
        event_code="S-7777",
        layout_html=_generic_layout(),
        extra_xsd_members={
            "evtOmega.xsd": _schema(
                "evtOmega", "alpha", ("first", "second"), facets=True
            ),
            "evtSigma.xsd": _schema("evtSigma", "alpha", ("foreign",)),
        },
        mos_subject="alpha",
    )
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        projections = {
            family: materialize_projection(
                session, build, f"{family}_ALL", "fts-baseline-v3"
            )[0]
            for family in ("MOS", "LAYOUT", "XSD")
        }
        session.commit()
        children = search(
            session,
            projections["LAYOUT"],
            "quais campos pertencem ao grupo alpha do S-7777?",
            5,
        )
        assert {row["source_local_stable_path"] for row in children} == {
            "LAYOUT/S-7777/evtOmega/alpha/first",
            "LAYOUT/S-7777/evtOmega/alpha/second",
        }
        occurrence = search(
            session, projections["LAYOUT"], "qual a ocorrência do grupo alpha S-7777?"
        )
        assert [row["source_local_stable_path"] for row in occurrence] == [
            "LAYOUT/S-7777/evtOmega/alpha"
        ]
        target = session.get(CitationTarget, occurrence[0]["root_citation_target_id"])
        assert "Occurrence: 1" in _render(session, build, target)
        condition = search(
            session, projections["LAYOUT"], "condição do grupo alpha S-8888?"
        )
        assert [row["source_local_stable_path"] for row in condition] == [
            "LAYOUT/S-8888/evtSigma/alpha"
        ]
        assert "Condition: OC" in _render(
            session,
            build,
            session.get(CitationTarget, condition[0]["root_citation_target_id"]),
        )
        field_type = search(
            session, projections["LAYOUT"], "tipo do campo first S-7777"
        )
        assert len(field_type) == 1 and field_type[0][
            "source_local_stable_path"
        ].endswith("/first")
        field_size = search(
            session, projections["LAYOUT"], "tamanho do campo second S-7777"
        )
        assert len(field_size) == 1 and "tamanho 8" in field_size[0]["search_text"]
        field_decimals = search(
            session, projections["LAYOUT"], "decimais do campo first S-7777"
        )
        assert len(field_decimals) == 1
        assert "decimais 2" in field_decimals[0]["search_text"]
        assert (
            search(session, projections["LAYOUT"], "condição do campo first S-7777")
            == []
        )
        xsd = search(
            session,
            projections["XSD"],
            "quais elementos filhos de alpha no XSD do S-7777?",
        )
        assert {row["source_local_stable_path"].rsplit("/", 1)[-1] for row in xsd} == {
            "first",
            "second",
        }
        assert all("evtOmega" in row["source_local_stable_path"] for row in xsd)
        xsd_type = search(
            session, projections["XSD"], "tipo do elemento first no XSD S-7777"
        )
        assert len(xsd_type) == 1 and "tipo xs:string" in xsd_type[0]["search_text"]
        assert (
            search(session, projections["XSD"], "tipo do elemento first no XSD")
            == xsd_type
        )
        xsd_parent = search(
            session, projections["XSD"], "pai do elemento first no XSD S-7777"
        )
        assert len(xsd_parent) == 1 and xsd_parent[0][
            "source_local_stable_path"
        ].endswith("/alpha")
        pattern = search(
            session, projections["XSD"], "padrão do elemento restricted XSD S-7777"
        )
        assert len(pattern) == 1 and "[A-Z]+" in pattern[0]["search_text"]
        enumeration = search(
            session, projections["XSD"], "enumeração do elemento restricted XSD S-7777"
        )
        assert len(enumeration) == 1
        assert "Enumerations: A" in _render(
            session,
            build,
            session.get(CitationTarget, enumeration[0]["root_citation_target_id"]),
        )
        factual = analyze_query(
            "compare evidências disponíveis sobre alpha S-7777 no MOS, Leiaute e XSD"
        ).normalized_text
        assert factual == "alpha S-7777"
        assert all(
            search(session, projection, factual) for projection in projections.values()
        )
        mos_concept = search(session, projections["MOS"], "conceito do evento S-7777")
        assert (
            mos_concept[0]["source_local_stable_path"]
            == "MOS/CapIII/S-7777/metadata/conceito"
        )
        assert len(children) == 2  # top_k is a maximum, not padding.
        activate_runtime(session, build, projections["LAYOUT"])
        session.commit()

        @contextmanager
        def current_session():
            yield session

        monkeypatch.setattr(cli_module, "session_factory", lambda: current_session)
        output = []
        monkeypatch.setattr(
            cli_module.console, "print", lambda value, **_kw: output.append(str(value))
        )
        monkeypatch.setattr(
            cli_module.typer,
            "prompt",
            lambda *_args, **_kw: (
                "compare evidências sobre alpha S-7777 no MOS, Leiaute e XSD"
            ),
        )
        cli_module._query_active("CROSS_SOURCE")
        assert all(
            f"{family}: AVAILABLE" in output for family in ("MOS", "LAYOUT", "XSD")
        )
        output.clear()
        monkeypatch.setattr(
            cli_module.typer,
            "prompt",
            lambda *_args, **_kw: (
                "compare evidências sobre first S-7777 no MOS, Leiaute e XSD"
            ),
        )
        cli_module._query_active("CROSS_SOURCE")
        assert "MOS: NO_AUTHORIZED_EVIDENCE" in output
        assert "LAYOUT: AVAILABLE" in output
        assert "XSD: AVAILABLE" in output
        assert not any("Abstenção:" in line for line in output)
        assert not any("grupo_pai " in line or "event_code " in line for line in output)
        output.clear()
        monkeypatch.setattr(
            cli_module.typer,
            "prompt",
            lambda *_args, **_kw: "compare evidências sobre inexistente S-7777",
        )
        cli_module._query_active("CROSS_SOURCE")
        assert all(
            f"{family}: NO_AUTHORIZED_EVIDENCE" in output
            for family in ("MOS", "LAYOUT", "XSD")
        )
        assert any("Abstenção:" in line for line in output)
        output.clear()
        monkeypatch.setattr(
            cli_module.typer,
            "prompt",
            lambda *_args, **_kw: "condição do grupo alpha S-8888",
        )
        cli_module._query_active("LAYOUT_ALL")
        assert any("Condition: OC" in line for line in output)
    finally:
        session.rollback()
        session.execute(delete(ActiveRuntime))
        session.commit()
        cleanup(session, ids)
        session.close()


def test_real_regressions_on_official_table_shape(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(
        tmp_path,
        event_code="S-1000",
        layout_html=_event("S-1000", "evtInfoEmpregador", "inclusao") + _s1005(),
        extra_xsd_members={
            "evtInfoEmpregador.xsd": _schema(
                "evtInfoEmpregador", "ideEmpregador", ("tpInsc", "nrInsc")
            ),
        },
    )
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        projections = {
            family: materialize_projection(
                session, build, f"{family}_ALL", "fts-baseline-v3"
            )[0]
            for family in ("MOS", "LAYOUT", "XSD")
        }
        session.commit()
        mos = search(session, projections["MOS"], "qual é o conceito do evento S-1000?")
        assert (
            mos[0]["source_local_stable_path"] == "MOS/CapIII/S-1000/metadata/conceito"
        )
        children = search(
            session,
            projections["LAYOUT"],
            "quais campos pertencem ao grupo ideEmpregador do evento S-1000?",
        )
        assert {row["source_local_stable_path"] for row in children} == {
            "LAYOUT/S-1000/ideEmpregador/tpInsc",
            "LAYOUT/S-1000/ideEmpregador/nrInsc",
        }
        occurrence = search(
            session,
            projections["LAYOUT"],
            "qual é a ocorrência do grupo ideEmpregador no evento S-1000?",
        )
        assert len(occurrence) == 1 and "ocorrencia 1" in occurrence[0]["search_text"]
        condition = search(
            session,
            projections["LAYOUT"],
            "qual é a condição do grupo infoCadastro na inclusão do S-1000?",
        )
        assert len(condition) == 1
        assert (
            condition[0]["source_local_stable_path"]
            == "LAYOUT/S-1000/infoEmpregador/inclusao/infoCadastro"
        )
        assert "condicao N (se procEmi" in condition[0]["search_text"]
        xsd = search(
            session,
            projections["XSD"],
            "quais elementos filhos existem em ideEmpregador no XSD do S-1000?",
        )
        assert {row["source_local_stable_path"].rsplit("/", 1)[-1] for row in xsd} == {
            "tpInsc",
            "nrInsc",
        }
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()


def test_search_v3_reindexes_same_complete_build_without_http_or_parser(
    tmp_path, monkeypatch
):
    import rag_esocial.search_service as search_module
    import rag_esocial.setup_service as setup_module

    session, snapshot, _old, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(_old.id)
    build = create_build(
        session, snapshot.slug, DEFAULT_PARSER_REVISION, dict(DEFAULT_PARSER_CONFIG)
    )
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        old_projections = {
            profile: materialize_projection(session, build, profile, "fts-baseline-v2")[
                0
            ]
            for profile in PROFILES
        }
        build.status = "COMPLETE"
        active = activate_runtime(session, build, old_projections["LAYOUT_ALL"])
        session.commit()
        generation = active.generation
        build_id = build.id
        old_id = old_projections["LAYOUT_ALL"].id
        old_units = session.scalar(
            select(func.count(SearchUnit.id)).where(
                SearchUnit.search_projection_id == old_id
            )
        )

        class NoNetwork:
            def download(self, *_args, **_kwargs):
                raise AssertionError("HTTP forbidden during local reindex")

        def no_parser(_html):
            raise AssertionError("parser forbidden during search-only reindex")

        original_target = search_module._target
        monkeypatch.setattr(setup_module, "parse_layout_html", no_parser)
        monkeypatch.setattr(
            search_module,
            "_target",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("index failure")),
        )
        with pytest.raises(RuntimeError, match="index failure"):
            prepare_runtime(session, downloader=NoNetwork())
        session.rollback()
        assert get_active_runtime(session).search_projection_id == old_id
        assert get_active_runtime(session).generation == generation
        monkeypatch.setattr(search_module, "_target", original_target)
        result = prepare_runtime(session, downloader=NoNetwork())
        assert result["build"].id == build_id
        assert result["snapshot"].id == snapshot.id
        assert result["runtime"].search_projection_id != old_id
        assert result["runtime"].generation == generation + 1
        assert is_build_ready(session, build, tuple(PROFILES))
        assert (
            session.get(SearchProjection, old_id).projection_revision
            == "fts-baseline-v2"
        )
        assert (
            session.scalar(
                select(func.count(SearchUnit.id)).where(
                    SearchUnit.search_projection_id == old_id
                )
            )
            == old_units
        )
        again = prepare_runtime(session, downloader=NoNetwork())
        assert again["same_version"] and again["runtime"].generation == generation + 1
        v3 = result["runtime"].projection
        one_unit = session.scalar(
            select(SearchUnit.id).where(SearchUnit.search_projection_id == v3.id)
        )
        session.execute(
            delete(SearchUnitCitationTarget).where(
                SearchUnitCitationTarget.search_unit_id == one_unit
            )
        )
        session.commit()
        repaired, created = materialize_projection(
            session, build, "LAYOUT_ALL", "fts-baseline-v3"
        )
        assert created and repaired.id == v3.id
        assert (
            session.get(SearchProjection, old_id).projection_revision
            == "fts-baseline-v2"
        )
    finally:
        session.rollback()
        session.execute(delete(ActiveRuntime))
        session.commit()
        cleanup(session, ids)
        session.close()
