# ruff: noqa: E501
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from sqlalchemy import delete, func, select

import rag_esocial.layout_materializer as layout_materializer_module
import rag_esocial.mos_materializer as mos_materializer_module
import rag_esocial.xsd_materializer as xsd_materializer_module
from rag_esocial.build_service import create_build
from rag_esocial.corpus import (
    freeze_snapshot,
    inventory_zip,
    storage_root,
    verify_snapshot,
)
from rag_esocial.db import session_factory
from rag_esocial.layout_materializer import materialize_layout
from rag_esocial.layout_parser import parse_layout_html
from rag_esocial.models.build import (
    CitationTarget,
    CorpusBuild,
    CorpusBuildCitationTarget,
)
from rag_esocial.models.corpus import (
    ArchiveMember,
    ArtifactRole,
    CorpusSnapshot,
    DocumentArtifact,
    DocumentFamily,
    DocumentVersion,
    SnapshotMember,
)
from rag_esocial.models.layout import (
    LayoutDocument,
    LayoutEvent,
    LayoutField,
    LayoutGroup,
)
from rag_esocial.models.mos import (
    ContentBlock,
    EventMetadataBlock,
    ExplicitReference,
    MosDocument,
    MosEventSection,
    MosEventSubitem,
    MosEventTopic,
    MosTopic,
)
from rag_esocial.models.xsd import (
    XsdElement,
    XsdEnumeration,
    XsdEventSchema,
    XsdPackageDocument,
    XsdSharedType,
)
from rag_esocial.mos_materializer import materialize_mos
from rag_esocial.mos_parser import parse_mos_text
from rag_esocial.pdf_text import PdfTextExtractor
from rag_esocial.xsd_materializer import materialize_xsd
from rag_esocial.xsd_parser import parse_xsd_package


def make_integration_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    lines = [
        "CAP III",
        "S-9999 Evento de Teste",
        "Conceito",
        "Consultar S-1210 {ideDmDev}",
        "Quem está obrigado",
        "Empregadores.",
        "Prazo de envio",
        "Até o prazo aplicável.",
        "Pré-requisitos",
        "REGRA_EXEMPLO [infoPerAnt] Tabela 05",
        "Informações adicionais",
        "1 Tópico com S-1210",
        "1.1 Subitem com {perApur} e REGRA_SUBITEM",
    ]
    commands = ["BT /F1 12 Tf 40 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -18 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = StreamObject()
    stream._data = " ".join(commands).encode()
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


def count_rows(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def build_fixture(tmp_path: Path):
    mos_pdf = tmp_path / "mos-fixture.pdf"
    make_integration_pdf(mos_pdf)
    payloads = {
        ArtifactRole.MOS_MAIN.value: mos_pdf,
        ArtifactRole.LAYOUT_MAIN.value: tmp_path / "layout.html",
        ArtifactRole.LAYOUT_ANNEX_I_DOMAIN_TABLES.value: tmp_path / "annex-i.txt",
        ArtifactRole.LAYOUT_ANNEX_II_VALIDATION_RULES.value: tmp_path / "annex-ii.txt",
    }
    payloads[ArtifactRole.LAYOUT_MAIN.value].write_text(
        """<section data-kind='event' code='S-9999' title='Evento Layout Fixture'>
<div data-kind='group' name='info' level='1' description='Grupo raiz'>
<div data-kind='group' name='dados' level='2' description='Grupo aninhado'>
<div data-kind='group' name='detalhe' level='3'>
<p data-kind='field' name='aliqRat' type='N' occurrence='1-1' size='5'
condition='REGRA_LAYOUT'>Descrição REGRA_LAYOUT e Tabela 05</p>
</div></div></div></section>"""
    )
    payloads[ArtifactRole.LAYOUT_ANNEX_I_DOMAIN_TABLES.value].write_text("Tabela 01")
    payloads[ArtifactRole.LAYOUT_ANNEX_II_VALIDATION_RULES.value].write_text(
        "REGRA_FIXTURE"
    )
    xsd_path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(xsd_path, "w") as archive:
        archive.writestr(
            "evento_fixture.xsd",
            """<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema' targetNamespace='urn:fixture:1.0'>
<xs:element name='evtFixture'><xs:annotation><xs:documentation>REGRA_EXEMPLO Tabela 05</xs:documentation></xs:annotation>
<xs:complexType><xs:sequence><xs:element name='id' type='ts:TS_Id' minOccurs='1' maxOccurs='unbounded'/>
<xs:element name='code' minOccurs='0' maxOccurs='1'><xs:simpleType><xs:restriction base='xs:string'><xs:pattern value='[A-Z]+'/>
<xs:enumeration value='A'><xs:annotation><xs:documentation>Alpha</xs:documentation></xs:annotation></xs:enumeration>
</xs:restriction></xs:simpleType></xs:element></xs:sequence></xs:complexType></xs:element>
<xs:include schemaLocation='tipos.xsd'/></xs:schema>""",
        )
        archive.writestr(
            "tipos.xsd",
            """<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema' targetNamespace='urn:fixture:1.0'>
<xs:simpleType name='TS_Id'><xs:annotation><xs:documentation>CHAVE_GRUPO: id</xs:documentation></xs:annotation>
<xs:restriction base='xs:string'><xs:minLength value='2'/></xs:restriction></xs:simpleType>
<xs:complexType name='T_Group'><xs:sequence><xs:element name='child'/></xs:sequence></xs:complexType></xs:schema>""",
        )
        archive.writestr(
            "xmldsig-core-schema.xsd",
            "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>",
        )
    payloads[ArtifactRole.XSD_PACKAGE.value] = xsd_path

    session = session_factory()()
    ids = {"snapshots": [], "builds": [], "versions": [], "artifacts": []}
    try:
        versions = {}
        for family, label in [
            (DocumentFamily.MOS.value, "MOS fixture"),
            (DocumentFamily.LAYOUT.value, "Layout fixture"),
            (DocumentFamily.XSD.value, "XSD fixture"),
        ]:
            version = DocumentVersion(
                id=str(uuid.uuid4()),
                document_family=family,
                version_label=label,
                title=label,
                created_at=datetime.now(timezone.utc),
            )
            session.add(version)
            session.flush()
            versions[family] = version
            ids["versions"].append(version.id)
        artifacts = {}
        for role, source in payloads.items():
            family = (
                DocumentFamily.MOS.value
                if role == ArtifactRole.MOS_MAIN.value
                else DocumentFamily.XSD.value
                if role == ArtifactRole.XSD_PACKAGE.value
                else DocumentFamily.LAYOUT.value
            )
            destination = storage_root() / f"integration-{uuid.uuid4()}-{source.name}"
            shutil.copyfile(source, destination)
            artifact = DocumentArtifact(
                id=str(uuid.uuid4()),
                document_version_id=versions[family].id,
                artifact_role=role,
                official_url=f"https://fixture.invalid/{source.name}",
                original_filename=source.name,
                media_type="application/pdf"
                if role == ArtifactRole.MOS_MAIN.value
                else "application/octet-stream",
                storage_path=destination.name,
                sha256=__import__(
                    "rag_esocial.corpus", fromlist=["sha256_file"]
                ).sha256_file(destination),
                size_bytes=destination.stat().st_size,
                retrieved_at=datetime.now(timezone.utc),
                capture_method="test_fixture",
                created_at=datetime.now(timezone.utc),
            )
            session.add(artifact)
            session.flush()
            if role == ArtifactRole.XSD_PACKAGE.value:
                inventory_zip(artifact, session)
            artifacts[role] = artifact
            ids["artifacts"].append(artifact.id)
        snapshot = CorpusSnapshot(
            id=str(uuid.uuid4()),
            slug=f"test-esocial-{uuid.uuid4()}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)
        session.flush()
        ids["snapshots"].append(snapshot.id)
        role_version = {
            ArtifactRole.MOS_MAIN.value: versions[DocumentFamily.MOS.value].id,
            ArtifactRole.LAYOUT_MAIN.value: versions[DocumentFamily.LAYOUT.value].id,
            ArtifactRole.LAYOUT_ANNEX_I_DOMAIN_TABLES.value: versions[
                DocumentFamily.LAYOUT.value
            ].id,
            ArtifactRole.LAYOUT_ANNEX_II_VALIDATION_RULES.value: versions[
                DocumentFamily.LAYOUT.value
            ].id,
            ArtifactRole.XSD_PACKAGE.value: versions[DocumentFamily.XSD.value].id,
        }
        for role, version_id in role_version.items():
            session.add(
                SnapshotMember(
                    id=str(uuid.uuid4()),
                    snapshot_id=snapshot.id,
                    artifact_role=role,
                    document_version_id=version_id,
                )
            )
        session.commit()
        assert verify_snapshot(snapshot) == []
        freeze_snapshot(session, snapshot)
        assert snapshot.frozen_at and snapshot.manifest_sha256
        session.refresh(snapshot)
        build = create_build(session, snapshot.slug, "mos-parser-test-v1", {})
        return (
            session,
            snapshot,
            build,
            versions[DocumentFamily.MOS.value],
            artifacts[ArtifactRole.MOS_MAIN.value],
            ids,
        )
    except Exception:
        session.rollback()
        session.close()
        raise


def cleanup(session, ids):
    for model in [
        XsdEnumeration,
        XsdElement,
        XsdSharedType,
        XsdEventSchema,
        XsdPackageDocument,
        LayoutField,
        LayoutGroup,
        LayoutEvent,
        LayoutDocument,
        XsdEnumeration,
        XsdElement,
        XsdEventSchema,
        XsdPackageDocument,
        XsdSharedType,
        ExplicitReference,
        ContentBlock,
        MosEventSubitem,
        MosEventTopic,
        EventMetadataBlock,
        MosEventSection,
        MosTopic,
        MosDocument,
        CorpusBuildCitationTarget,
        CitationTarget,
        CorpusBuild,
        ArchiveMember,
        SnapshotMember,
        DocumentArtifact,
        DocumentVersion,
        CorpusSnapshot,
    ]:
        if model is CorpusBuildCitationTarget:
            session.execute(delete(model))
        elif model in (DocumentArtifact, DocumentVersion, CorpusSnapshot):
            key = {
                DocumentArtifact: "artifacts",
                DocumentVersion: "versions",
                CorpusSnapshot: "snapshots",
            }[model]
            session.execute(delete(model).where(model.id.in_(ids[key])))
        else:
            session.execute(delete(model))
    session.commit()


def test_mos_postgres_harness_e2e_idempotency_and_two_builds(tmp_path: Path) -> None:
    session, snapshot, build, version, artifact, ids = build_fixture(tmp_path)
    try:
        pages = PdfTextExtractor().extract(storage_root() / artifact.storage_path).pages
        result = parse_mos_text("\n".join(page.text for page in pages))
        document, created = materialize_mos(session, build, version, artifact, result)
        session.commit()
        ids["builds"].append(build.id)
        assert created
        assert verify_snapshot(snapshot) == []
        refs = session.scalars(
            select(ExplicitReference).where(
                ExplicitReference.corpus_build_id == build.id
            )
        ).all()
        assert refs and all(ref.resolution_status == "UNRESOLVED" for ref in refs)
        assert any(
            "metadata" in paths_by_origin.source_local_stable_path
            for ref in refs
            if (
                paths_by_origin := session.get(
                    CitationTarget, ref.origin_citation_target_id
                )
            )
        )
        before = {
            model.__name__: count_rows(session, model)
            for model in [
                MosDocument,
                MosEventSection,
                EventMetadataBlock,
                MosEventTopic,
                MosEventSubitem,
                ContentBlock,
                ExplicitReference,
                CitationTarget,
                CorpusBuildCitationTarget,
            ]
        }
        _, created_again = materialize_mos(session, build, version, artifact, result)
        session.commit()
        after = {
            model.__name__: count_rows(session, model)
            for model in [
                MosDocument,
                MosEventSection,
                EventMetadataBlock,
                MosEventTopic,
                MosEventSubitem,
                ContentBlock,
                ExplicitReference,
                CitationTarget,
                CorpusBuildCitationTarget,
            ]
        }
        assert not created_again and before == after
        build2 = create_build(session, snapshot.slug, "mos-parser-test-v2", {})
        ids["builds"].append(build2.id)
        second, created_second = materialize_mos(
            session, build2, version, artifact, result
        )
        session.commit()
        assert created_second and second.id != document.id
        first_target = session.scalar(
            select(CitationTarget).where(
                CitationTarget.source_local_stable_path == "MOS/CapIII/S-9999/1.1"
            )
        )
        assert (
            first_target
            and len(
                session.scalars(
                    select(CorpusBuildCitationTarget).where(
                        CorpusBuildCitationTarget.citation_target_id == first_target.id
                    )
                ).all()
            )
            == 2
        )
        assert first_target.locator_metadata["page"] == 1
    finally:
        cleanup(session, ids)
        session.close()


def test_xsd_postgres_e2e_idempotency_rollback_and_two_builds(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    xsd_artifact = session.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.artifact_role == ArtifactRole.XSD_PACKAGE.value,
            DocumentArtifact.document_version_id.in_(
                select(SnapshotMember.document_version_id).where(
                    SnapshotMember.snapshot_id == snapshot.id
                )
            ),
        )
    )
    xsd_version = session.get(DocumentVersion, xsd_artifact.document_version_id)
    result = parse_xsd_package(storage_root() / xsd_artifact.storage_path)
    try:
        package = materialize_xsd(session, build, xsd_version, xsd_artifact, result)
        session.commit()
        session.close()
        session = session_factory()()
        counts = {
            model: count_rows(session, model)
            for model in [
                XsdPackageDocument,
                XsdEventSchema,
                XsdElement,
                XsdSharedType,
                XsdEnumeration,
                ExplicitReference,
                CitationTarget,
                CorpusBuildCitationTarget,
            ]
        }
        assert session.get(XsdPackageDocument, package.id)
        assert {
            row.schema_kind for row in session.scalars(select(XsdEventSchema)).all()
        } == {"EVENT_SCHEMA", "SHARED_TYPES_SCHEMA", "AUXILIARY_SCHEMA"}
        element = session.scalar(select(XsdElement).where(XsdElement.name == "id"))
        assert (
            element
            and element.type_qname == "ts:TS_Id"
            and element.max_occurs == "unbounded"
        )
        code = session.scalar(select(XsdElement).where(XsdElement.name == "code"))
        assert code and code.min_occurs == "0" and code.parent_element_id
        assert session.scalar(select(XsdEnumeration).where(XsdEnumeration.value == "A"))
        refs = session.scalars(
            select(ExplicitReference).where(
                ExplicitReference.corpus_build_id == build.id
            )
        ).all()
        assert refs and all(ref.resolution_status == "UNRESOLVED" for ref in refs)
        assert any(ref.reference_kind == "SCHEMA_INCLUDE" for ref in refs)
        origin = session.get(
            CitationTarget,
            next(
                ref.origin_citation_target_id
                for ref in refs
                if ref.reference_kind == "SCHEMA_INCLUDE"
            ),
        )
        assert origin and "/schema/evento_fixture" in origin.source_local_stable_path
        session.expunge_all()
        materialize_xsd(session, build, xsd_version, xsd_artifact, result)
        session.commit()
        assert counts == {model: count_rows(session, model) for model in counts}
        build2 = create_build(session, snapshot.slug, "xsd-parser-test-v2", {})
        ids["builds"].append(build2.id)
        materialize_xsd(session, build2, xsd_version, xsd_artifact, result)
        session.commit()
        assert count_rows(session, XsdPackageDocument) >= 2
        b1 = session.scalar(
            select(XsdElement).where(
                XsdElement.package_document_id == package.id, XsdElement.name == "id"
            )
        )
        b2 = session.scalar(
            select(XsdElement).where(
                XsdElement.package_document_id != package.id, XsdElement.name == "id"
            )
        )
        assert (
            b1
            and b2
            and b1.id != b2.id
            and b1.source_local_stable_path == b2.source_local_stable_path
        )
        targets = session.scalars(
            select(CitationTarget).where(
                CitationTarget.source_local_stable_path == b1.source_local_stable_path,
                CitationTarget.document_version_id == xsd_version.id,
            )
        ).all()
        assert len(targets) == 1
        assert (
            len(
                session.scalars(
                    select(CorpusBuildCitationTarget).where(
                        CorpusBuildCitationTarget.citation_target_id == targets[0].id
                    )
                ).all()
            )
            == 2
        )
        build3 = create_build(session, snapshot.slug, "xsd-parser-test-v3", {})
        ids["builds"].append(build3.id)
        build3_id = build3.id
        original = xsd_materializer_module.associate_citation_target
        calls = 0

        def fail_after_partial(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected xsd failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(
            xsd_materializer_module, "associate_citation_target", fail_after_partial
        )
        try:
            materialize_xsd(session, build3, xsd_version, xsd_artifact, result)
        except RuntimeError:
            session.rollback()
        else:
            raise AssertionError("rollback failure was not injected")
        session.close()
        session = session_factory()()
        assert not session.scalar(
            select(XsdPackageDocument).where(
                XsdPackageDocument.corpus_build_id == build3_id
            )
        )
        assert session.get(CorpusSnapshot, snapshot.id).frozen_at
        assert session.get(DocumentArtifact, xsd_artifact.id)
    finally:
        cleanup(session, ids)
        session.close()


def test_mos_materialization_rolls_back_after_intermediate_failure(
    tmp_path: Path, monkeypatch
) -> None:
    session, snapshot, build, version, artifact, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    build_id = build.id
    snapshot_id = snapshot.id
    artifact_id = artifact.id
    try:
        pages = PdfTextExtractor().extract(storage_root() / artifact.storage_path).pages
        result = parse_mos_text("\n".join(page.text for page in pages))
        preexisting = CitationTarget(
            id=str(uuid.uuid4()),
            stable_key=f"{version.id}|MOS|MOS/CapIII/S-9999",
            document_version_id=version.id,
            document_family="MOS",
            target_kind="event_section",
            source_local_stable_path="MOS/CapIII/S-9999",
            locator_metadata={"page": 1},
            created_at=datetime.now(timezone.utc),
        )
        session.add(preexisting)
        session.commit()
        preexisting_id = preexisting.id
        calls = 0
        original = mos_materializer_module.associate_citation_target

        def fail_after_partial(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected integration failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(
            mos_materializer_module, "associate_citation_target", fail_after_partial
        )
        try:
            materialize_mos(session, build, version, artifact, result)
        except RuntimeError as error:
            assert str(error) == "injected integration failure"
            session.rollback()
        else:
            raise AssertionError("the injected failure was not observed")
        session.close()
        session = session_factory()()
        assert (
            session.scalar(
                select(MosDocument.id).where(MosDocument.corpus_build_id == build_id)
            )
            is None
        )
        assert session.scalar(select(MosEventSection.id)) is None
        assert (
            session.scalar(
                select(ExplicitReference.id).where(
                    ExplicitReference.corpus_build_id == build_id
                )
            )
            is None
        )
        assert (
            session.scalar(
                select(CitationTarget.id).where(CitationTarget.id == preexisting_id)
            )
            == preexisting_id
        )
        assert session.get(CorpusSnapshot, snapshot_id).frozen_at is not None
        assert session.get(CorpusBuild, build_id) is not None
        assert session.get(DocumentArtifact, artifact_id) is not None
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()


def test_layout_postgres_e2e_idempotency_origins_two_builds_and_rollback(
    tmp_path: Path, monkeypatch
) -> None:
    session, snapshot, build, _mos_version, _mos_artifact, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    build_id = build.id
    snapshot_id = snapshot.id
    layout_artifact = session.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.artifact_role == ArtifactRole.LAYOUT_MAIN.value,
            DocumentArtifact.document_version_id.in_(
                select(SnapshotMember.document_version_id).where(
                    SnapshotMember.snapshot_id == snapshot.id
                )
            ),
        )
    )
    layout_version = session.get(DocumentVersion, layout_artifact.document_version_id)
    try:
        html = (storage_root() / layout_artifact.storage_path).read_text()
        result = parse_layout_html(html)
        document, created = materialize_layout(
            session, build, layout_version, layout_artifact, result
        )
        session.commit()
        assert created
        session.expunge_all()
        persisted = session.scalar(
            select(LayoutDocument).where(LayoutDocument.id == document.id)
        )
        assert persisted and persisted.corpus_build_id == build_id
        event = session.scalar(
            select(LayoutEvent).where(LayoutEvent.layout_document_id == document.id)
        )
        groups = session.scalars(
            select(LayoutGroup).where(LayoutGroup.layout_event_id == event.id)
        ).all()
        field = session.scalar(
            select(LayoutField).where(LayoutField.technical_name == "aliqRat")
        )
        assert event.event_code == "S-9999"
        assert len(groups) == 3 and field.source_local_stable_path.endswith("/aliqRat")
        targets = session.scalars(
            select(CitationTarget).where(CitationTarget.document_family == "LAYOUT")
        ).all()
        target_by_path = {target.source_local_stable_path: target for target in targets}
        assert (
            target_by_path["LAYOUT/S-9999/info/dados/detalhe/aliqRat"].locator_metadata[
                "source"
            ]
            == "html"
        )
        refs = session.scalars(
            select(ExplicitReference).where(
                ExplicitReference.corpus_build_id == build_id
            )
        ).all()
        assert refs and all(ref.resolution_status == "UNRESOLVED" for ref in refs)
        assert {
            session.get(
                CitationTarget, ref.origin_citation_target_id
            ).source_local_stable_path
            for ref in refs
        } == {"LAYOUT/S-9999/info/dados/detalhe/aliqRat"}
        before = {
            model.__name__: count_rows(session, model)
            for model in [
                LayoutDocument,
                LayoutEvent,
                LayoutGroup,
                LayoutField,
                ExplicitReference,
                CitationTarget,
                CorpusBuildCitationTarget,
            ]
        }
        _, created_again = materialize_layout(
            session, build, layout_version, layout_artifact, result
        )
        session.commit()
        after = {
            model.__name__: count_rows(session, model)
            for model in [
                LayoutDocument,
                LayoutEvent,
                LayoutGroup,
                LayoutField,
                ExplicitReference,
                CitationTarget,
                CorpusBuildCitationTarget,
            ]
        }
        assert not created_again and before == after
        build2 = create_build(session, snapshot.slug, "layout-parser-test-v2", {})
        ids["builds"].append(build2.id)
        document2, created2 = materialize_layout(
            session, build2, layout_version, layout_artifact, result
        )
        session.commit()
        assert created2 and document2.id != document.id
        shared = session.scalars(
            select(CitationTarget).where(
                CitationTarget.stable_key
                == target_by_path["LAYOUT/S-9999/info/dados/detalhe/aliqRat"].stable_key
            )
        ).all()
        assert len(shared) == 1
        assert (
            len(
                session.scalars(
                    select(CorpusBuildCitationTarget).where(
                        CorpusBuildCitationTarget.citation_target_id == shared[0].id
                    )
                ).all()
            )
            == 2
        )
        preexisting_id = shared[0].id
        session.close()
        session = session_factory()()
        calls = 0
        original = layout_materializer_module.associate_citation_target

        def fail_after_partial(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected layout failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(
            layout_materializer_module, "associate_citation_target", fail_after_partial
        )
        build3 = create_build(session, snapshot.slug, "layout-parser-test-v3", {})
        ids["builds"].append(build3.id)
        build3_id = build3.id
        result3 = parse_layout_html(html)
        try:
            materialize_layout(
                session, build3, layout_version, layout_artifact, result3
            )
        except RuntimeError:
            session.rollback()
        else:
            raise AssertionError("injected layout failure was not observed")
        session.close()
        session = session_factory()()
        assert (
            session.scalar(
                select(LayoutDocument.id).where(
                    LayoutDocument.corpus_build_id == build3_id
                )
            )
            is None
        )
        assert (
            session.scalar(
                select(CitationTarget.id).where(CitationTarget.id == preexisting_id)
            )
            == preexisting_id
        )
        assert session.get(CorpusSnapshot, snapshot_id).frozen_at is not None
        assert session.get(CorpusBuild, build_id) is not None
        assert session.get(DocumentArtifact, layout_artifact.id) is not None
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()
