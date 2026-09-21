# ruff: noqa: E501
import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from typer.testing import CliRunner

import rag_esocial.cli as cli_module
import rag_esocial.layout_materializer as layout_materializer_module
import rag_esocial.mos_materializer as mos_materializer_module
import rag_esocial.xsd_materializer as xsd_materializer_module
from rag_esocial.answer_service import (
    FakeAnswerModelClient,
    create_answer_request,
    execute_answer,
    preflight_answer,
    validate_answer_contract,
)
from rag_esocial.build_service import create_build
from rag_esocial.complete_answer_service import (
    SOURCE_ORDER,
    CompleteBuildMismatchError,
    CompleteDuplicateMembershipError,
    CompleteIdentityError,
    CompleteMembershipError,
    CompleteRequestedAspectSpec,
    CompleteSourceInputSpec,
    create_complete_answer_request,
    create_complete_answer_run,
    inspect_complete_run,
    mark_complete_run_failed,
    register_complete_source_run,
)
from rag_esocial.complete_application_service import (
    complete_show_payload,
    execute_complete,
)
from rag_esocial.config import get_settings
from rag_esocial.corpus import (
    freeze_snapshot,
    inventory_zip,
    storage_root,
    verify_snapshot,
)
from rag_esocial.cross_source_service import (
    CrossSourceSupportError,
    aggregate_cross_source,
    serialize_cross_source_context,
)
from rag_esocial.db import session_factory
from rag_esocial.evaluation_service import (
    evaluate_fact_resolution_status,
    evaluate_retrieval_evidence,
    write_report,
)
from rag_esocial.evidence_service import assemble_evidence
from rag_esocial.fact_resolution_service import requested_fact, resolve_requested_fact
from rag_esocial.facts_service import build_facts
from rag_esocial.layout_materializer import materialize_layout
from rag_esocial.layout_parser import parse_layout_html
from rag_esocial.models.answer import (
    AnswerCitation,
    AnswerClaim,
    AnswerClaimFact,
    AnswerRequest,
    AnswerRequestFactResolution,
    AnswerRun,
    AnswerRunStatus,
)
from rag_esocial.models.build import (
    CanonicalEntity,
    CitationTarget,
    CorpusBuild,
    CorpusBuildCitationTarget,
)
from rag_esocial.models.complete_answer import (
    CompleteAnswerCitation,
    CompleteAnswerClaim,
    CompleteAnswerClaimComparison,
    CompleteAnswerClaimFact,
    CompleteAnswerRequest,
    CompleteAnswerRequestedAspect,
    CompleteAnswerRequestSource,
    CompleteAnswerRun,
    CompleteAnswerSourceInput,
    CompleteAnswerSourceRun,
    CompleteRunExecutionState,
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
from rag_esocial.models.cross_source import (
    CrossSourceComparison,
    CrossSourceComparisonMember,
)
from rag_esocial.models.evidence import EvidenceSet, EvidenceSetItem, EvidenceUnit
from rag_esocial.models.fact_resolution import (
    FactResolution,
    FactResolutionSupport,
    RequestedFact,
    RuntimeStatus,
)
from rag_esocial.models.facts import (
    EntityRelation,
    ReferenceResolution,
    ResolvedFact,
    SourceFact,
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
from rag_esocial.models.search import (
    SearchProjection,
    SearchUnit,
    SearchUnitCitationTarget,
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
from rag_esocial.q14_service import (
    DeterministicQ14Client,
    evaluate_q14,
    validate_q14,
)
from rag_esocial.search_service import materialize_projection, search
from rag_esocial.synthesis_service import (
    SYNTHESIS_CONTRACT_REVISION,
    build_synthesis_context,
    execute_complete_synthesis,
    validate_synthesis_output,
)
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
        CompleteAnswerClaimComparison,
        CompleteAnswerCitation,
        CompleteAnswerClaimFact,
        CompleteAnswerClaim,
        CrossSourceComparisonMember,
        CrossSourceComparison,
        CompleteAnswerSourceRun,
        CompleteAnswerRun,
        CompleteAnswerSourceInput,
        CompleteAnswerRequestedAspect,
        CompleteAnswerRequestSource,
        CompleteAnswerRequest,
        AnswerCitation,
        AnswerClaimFact,
        AnswerClaim,
        AnswerRun,
        AnswerRequestFactResolution,
        AnswerRequest,
        FactResolutionSupport,
        FactResolution,
        RequestedFact,
        EvidenceSetItem,
        EvidenceUnit,
        EvidenceSet,
        SearchUnitCitationTarget,
        SearchUnit,
        SearchProjection,
        XsdEnumeration,
        XsdElement,
        XsdSharedType,
        XsdEventSchema,
        XsdPackageDocument,
        SourceFact,
        ReferenceResolution,
        EntityRelation,
        ResolvedFact,
        SearchUnitCitationTarget,
        SearchUnit,
        SearchProjection,
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


def materialize_phase4_fixture(session, build, snapshot):
    mos_artifact = session.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.artifact_role == ArtifactRole.MOS_MAIN.value,
            DocumentArtifact.document_version_id.in_(
                select(SnapshotMember.document_version_id).where(
                    SnapshotMember.snapshot_id == snapshot.id
                )
            ),
        )
    )
    mos_version = session.get(DocumentVersion, mos_artifact.document_version_id)
    pages = PdfTextExtractor().extract(storage_root() / mos_artifact.storage_path).pages
    materialize_mos(
        session,
        build,
        mos_version,
        mos_artifact,
        parse_mos_text("\n".join(page.text for page in pages)),
    )
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
    materialize_layout(
        session,
        build,
        layout_version,
        layout_artifact,
        parse_layout_html((storage_root() / layout_artifact.storage_path).read_text()),
    )
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
    materialize_xsd(
        session,
        build,
        xsd_version,
        xsd_artifact,
        parse_xsd_package(storage_root() / xsd_artifact.storage_path),
    )


def test_facts_e2e_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        build_facts(session, build)
        session.commit()
        session.close()
        session = session_factory()()
        facts = session.scalars(
            select(SourceFact).where(SourceFact.corpus_build_id == build.id)
        ).all()
        assert facts and {fact.extraction_kind for fact in facts} <= {"D1", "D2"}
        assert any(fact.fact_type == "LAYOUT_TYPE" for fact in facts)
        assert any(
            fact.fact_type == "XSD_MAX_OCCURS" and fact.string_value == "unbounded"
            for fact in facts
        )
        assert session.scalars(
            select(ReferenceResolution).where(
                ReferenceResolution.corpus_build_id == build.id
            )
        ).all()
    finally:
        cleanup(session, ids)
        session.close()


def test_facts_idempotency_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        build_facts(session, build)
        session.commit()
        before = {
            model: count_rows(session, model)
            for model in (SourceFact, ReferenceResolution, EntityRelation, ResolvedFact)
        }
        build_facts(session, build)
        session.commit()
        assert before == {model: count_rows(session, model) for model in before}
    finally:
        cleanup(session, ids)
        session.close()


def test_facts_rollback_postgresql(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    build_id = build.id
    snapshot_id = snapshot.id
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        import rag_esocial.facts_service as facts_module

        original = facts_module._fact
        calls = 0

        def fail_after_partial(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("facts rollback")
            return original(*args, **kwargs)

        monkeypatch.setattr(facts_module, "_fact", fail_after_partial)
        try:
            build_facts(session, build)
        except RuntimeError:
            session.rollback()
        session.close()
        session = session_factory()()
        assert not session.scalars(
            select(SourceFact).where(SourceFact.corpus_build_id == build_id)
        ).all()
        assert session.get(CorpusSnapshot, snapshot_id).frozen_at
    finally:
        cleanup(session, ids)
        session.close()


def test_facts_two_builds_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        build_facts(session, build)
        session.commit()
        build2 = create_build(session, snapshot.slug, "facts-parser-v2", {})
        ids["builds"].append(build2.id)
        materialize_phase4_fixture(session, build2, snapshot)
        build_facts(session, build2)
        session.commit()
        entity = session.scalar(
            select(CanonicalEntity).where(CanonicalEntity.stable_key == "EVENT:S-9999")
        )
        assert entity
        assert session.scalar(
            select(func.count())
            .select_from(SourceFact)
            .where(SourceFact.corpus_build_id == build.id)
        )
        assert session.scalar(
            select(func.count())
            .select_from(SourceFact)
            .where(SourceFact.corpus_build_id == build2.id)
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_search_projection_fts_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        digest = build.build_digest
        projection, created = materialize_projection(session, build, "LAYOUT_FIELD")
        session.commit()
        session.close()
        session = session_factory()()
        assert created and session.get(SearchProjection, projection.id)
        assert session.scalar(
            select(func.count())
            .select_from(SearchUnit)
            .where(SearchUnit.search_projection_id == projection.id)
        )
        rows = search(session, session.get(SearchProjection, projection.id), "aliqRat")
        assert rows and rows[0]["source_local_stable_path"].endswith("aliqRat")
        assert session.get(CorpusBuild, build.id).build_digest == digest
    finally:
        cleanup(session, ids)
        session.close()


def test_search_projection_idempotency_and_multiple_profiles(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        projection, created = materialize_projection(session, build, "XSD_ELEMENT")
        session.commit()
        before = count_rows(session, SearchUnit)
        same, created_again = materialize_projection(session, build, "XSD_ELEMENT")
        session.commit()
        assert before == count_rows(session, SearchUnit)
        other, other_created = materialize_projection(session, build, "LAYOUT_FIELD")
        session.commit()
        assert (
            created
            and not created_again
            and same.id == projection.id
            and other_created
            and other.id != projection.id
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_search_projection_rolls_back_postgresql(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    build_id = build.id
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        import rag_esocial.search_service as search_module

        original = search_module._target
        calls = 0

        def fail_after_partial(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("search projection rollback")
            return original(*args, **kwargs)

        monkeypatch.setattr(search_module, "_target", fail_after_partial)
        try:
            materialize_projection(session, build, "XSD_ELEMENT")
        except RuntimeError:
            session.rollback()
        else:
            raise AssertionError("rollback failure was not injected")
        session.close()
        session = session_factory()()
        assert not session.scalars(
            select(SearchProjection).where(SearchProjection.corpus_build_id == build_id)
        ).all()
        assert not session.scalars(
            select(SearchUnit)
            .join(SearchProjection)
            .where(SearchProjection.corpus_build_id == build_id)
        ).all()
    finally:
        cleanup(session, ids)
        session.close()


def test_search_projection_two_builds_are_specific_and_targets_transversal(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        build_facts(session, build)
        session.commit()
        first, _ = materialize_projection(session, build, "LAYOUT_FIELD")
        session.commit()
        build2 = create_build(session, snapshot.slug, "search-projection-test-v2", {})
        ids["builds"].append(build2.id)
        materialize_phase4_fixture(session, build2, snapshot)
        build_facts(session, build2)
        session.commit()
        second, _ = materialize_projection(session, build2, "LAYOUT_FIELD")
        session.commit()
        one = session.scalar(
            select(SearchUnit).where(SearchUnit.search_projection_id == first.id)
        )
        two = session.scalar(
            select(SearchUnit).where(SearchUnit.search_projection_id == second.id)
        )
        assert one and two and one.id != two.id
        assert one.source_local_stable_path == two.source_local_stable_path
        assert one.root_citation_target_id == two.root_citation_target_id
        assert session.scalar(
            select(CanonicalEntity).where(CanonicalEntity.stable_key == "EVENT:S-9999")
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_evidence_assembly_postgresql_and_idempotency(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        projection, _ = materialize_projection(session, build, "LAYOUT_FIELD")
        session.commit()
        evidence_set, created = assemble_evidence(session, build, projection, "aliqRat")
        session.commit()
        session.close()
        session = session_factory()()
        items = session.scalars(
            select(EvidenceSetItem).where(
                EvidenceSetItem.evidence_set_id == evidence_set.id
            )
        ).all()
        unit = session.get(EvidenceUnit, items[0].evidence_unit_id)
        assert created and items and "aliqRat" in unit.rendered_content
        assert (
            unit.rendered_content
            != session.get(SearchUnit, items[0].source_search_unit_id).search_text
        )
        same, created_again = assemble_evidence(
            session,
            session.get(CorpusBuild, build.id),
            session.get(SearchProjection, projection.id),
            "aliqRat",
        )
        session.commit()
        assert not created_again and same.id == evidence_set.id
    finally:
        cleanup(session, ids)
        session.close()


def test_evidence_rollback_and_two_builds_postgresql(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        projection, _ = materialize_projection(session, build, "LAYOUT_FIELD")
        session.commit()
        import rag_esocial.evidence_service as evidence_module

        original = evidence_module._render

        def fail_after_retrieval(*args, **kwargs):
            raise RuntimeError("evidence rollback")

        monkeypatch.setattr(evidence_module, "_render", fail_after_retrieval)
        try:
            assemble_evidence(session, build, projection, "aliqRat")
        except RuntimeError:
            session.rollback()
        assert not session.scalars(
            select(EvidenceSet).where(EvidenceSet.corpus_build_id == build.id)
        ).all()
        monkeypatch.setattr(evidence_module, "_render", original)
        build2 = create_build(session, snapshot.slug, "evidence-test-v2", {})
        ids["builds"].append(build2.id)
        materialize_phase4_fixture(session, build2, snapshot)
        session.commit()
        projection2, _ = materialize_projection(session, build2, "LAYOUT_FIELD")
        session.commit()
        first, _ = assemble_evidence(session, build, projection, "aliqRat")
        second, _ = assemble_evidence(session, build2, projection2, "aliqRat")
        session.commit()
        one = session.scalar(
            select(EvidenceUnit)
            .join(EvidenceSetItem)
            .where(EvidenceSetItem.evidence_set_id == first.id)
        )
        two = session.scalar(
            select(EvidenceUnit)
            .join(EvidenceSetItem)
            .where(EvidenceSetItem.evidence_set_id == second.id)
        )
        assert one.id != two.id and one.citation_target_id == two.citation_target_id
    finally:
        cleanup(session, ids)
        session.close()


def test_dev_retrieval_evidence_evaluation_is_deterministic(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        dataset = Path("evaluation/dev/retrieval_evidence_v1.json")
        first = evaluate_retrieval_evidence(session, build, dataset)
        session.commit()
        projection_state = session.execute(
            select(
                SearchProjection.id,
                SearchProjection.profile,
                SearchProjection.projection_config_digest,
                SearchProjection.text_search_config,
            ).where(SearchProjection.corpus_build_id == build.id)
        ).all()
        second = evaluate_retrieval_evidence(session, build, dataset)
        session.commit()
        assert (
            projection_state
            == session.execute(
                select(
                    SearchProjection.id,
                    SearchProjection.profile,
                    SearchProjection.projection_config_digest,
                    SearchProjection.text_search_config,
                ).where(SearchProjection.corpus_build_id == build.id)
            ).all()
        )
        first_path = tmp_path / "report-one.json"
        second_path = tmp_path / "report-two.json"
        write_report(first, first_path)
        write_report(second, second_path)
        assert first == second
        assert first_path.read_bytes() == second_path.read_bytes()
        assert len(first["results"]) >= 6
        assert first["aggregates"]
        assert first["dataset_kind"] == "DEV_NOT_BLIND_HOLDOUT"
        assert all("mrr" in item["metrics"] for item in first["results"])
    finally:
        cleanup(session, ids)
        session.close()


def _resolution_fixture(session, snapshot, build):
    materialize_phase4_fixture(session, build, snapshot)
    build_facts(session, build)
    session.flush()
    mos, _ = materialize_projection(session, build, "MOS_EVENT_SECTION")
    layout, _ = materialize_projection(session, build, "LAYOUT_FIELD")
    xsd, _ = materialize_projection(session, build, "XSD_ELEMENT")
    return (
        assemble_evidence(session, build, mos, "S-9999")[0],
        assemble_evidence(session, build, layout, "S-9999")[0],
        assemble_evidence(session, build, xsd, "evtFixture")[0],
    )


def test_fact_resolution_e2e_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        mos_evidence, layout_evidence, xsd_evidence = _resolution_fixture(
            session, snapshot, build
        )
        immutable_state = {
            "build_digest": build.build_digest,
            "projections": session.execute(
                select(
                    SearchProjection.id,
                    SearchProjection.projection_config_digest,
                    SearchProjection.text_search_config,
                ).where(SearchProjection.corpus_build_id == build.id)
            ).all(),
            "units": session.execute(
                select(
                    SearchUnit.id,
                    SearchUnit.search_projection_id,
                    SearchUnit.search_text,
                )
            ).all(),
            "evidence_sets": session.execute(
                select(EvidenceSet.id, EvidenceSet.assembly_config_digest).where(
                    EvidenceSet.corpus_build_id == build.id
                )
            ).all(),
            "evidence_units": session.execute(
                select(EvidenceUnit.id, EvidenceUnit.rendered_content_sha256).where(
                    EvidenceUnit.corpus_build_id == build.id
                )
            ).all(),
        }
        mos_request, _ = requested_fact(
            session, build, "EVENT_CONCEITO", "EVENT", "S-9999"
        )
        mos, _ = resolve_requested_fact(session, mos_request, "MOS", mos_evidence)
        layout_request, _ = requested_fact(
            session, build, "LAYOUT_TYPE", "EVENT", "S-9999"
        )
        layout, _ = resolve_requested_fact(
            session, layout_request, "LAYOUT", layout_evidence
        )
        fact = session.scalar(
            select(SourceFact).where(
                SourceFact.corpus_build_id == build.id,
                SourceFact.fact_type == "XSD_MAX_OCCURS",
            )
        )
        path = session.get(
            CitationTarget, fact.citation_target_id
        ).source_local_stable_path
        xsd_request, _ = requested_fact(session, build, "XSD_MAX_OCCURS", "FIELD", path)
        xsd, _ = resolve_requested_fact(session, xsd_request, "XSD", xsd_evidence)
        session.commit()
        assert build.build_digest == immutable_state["build_digest"]
        assert (
            immutable_state["projections"]
            == session.execute(
                select(
                    SearchProjection.id,
                    SearchProjection.projection_config_digest,
                    SearchProjection.text_search_config,
                ).where(SearchProjection.corpus_build_id == build.id)
            ).all()
        )
        assert (
            immutable_state["units"]
            == session.execute(
                select(
                    SearchUnit.id,
                    SearchUnit.search_projection_id,
                    SearchUnit.search_text,
                )
            ).all()
        )
        assert (
            immutable_state["evidence_sets"]
            == session.execute(
                select(EvidenceSet.id, EvidenceSet.assembly_config_digest).where(
                    EvidenceSet.corpus_build_id == build.id
                )
            ).all()
        )
        assert (
            immutable_state["evidence_units"]
            == session.execute(
                select(EvidenceUnit.id, EvidenceUnit.rendered_content_sha256).where(
                    EvidenceUnit.corpus_build_id == build.id
                )
            ).all()
        )
        session.close()
        session = session_factory()()
        assert [mos.runtime_status, layout.runtime_status, xsd.runtime_status] == [
            RuntimeStatus.RESOLVED.value,
            RuntimeStatus.RESOLVED.value,
            RuntimeStatus.RESOLVED.value,
        ], [mos.provenance, layout.provenance, xsd.provenance]
        assert mos.resolved_value["value"].startswith("Consultar S-1210 {ideDmDev}")
        assert layout.resolved_value == {"value": "N"}
        assert xsd.resolved_value == {"value": fact.string_value}
        for resolution in (mos, layout, xsd):
            assert session.scalars(
                select(FactResolutionSupport).where(
                    FactResolutionSupport.fact_resolution_id == resolution.id
                )
            ).all()
    finally:
        cleanup(session, ids)
        session.close()


def test_fact_resolution_statuses_and_no_bypass_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        mos_evidence, layout_evidence, _ = _resolution_fixture(session, snapshot, build)
        request, _ = requested_fact(session, build, "LAYOUT_TYPE", "EVENT", "S-9999")
        not_applicable, _ = resolve_requested_fact(session, request, "MOS")
        miss, _ = resolve_requested_fact(session, request, "LAYOUT", mos_evidence)
        unsupported_request, _ = requested_fact(
            session, build, "LAYOUT_TYPE", "EVENT", "S-UNKNOWN"
        )
        unsupported, _ = resolve_requested_fact(
            session, unsupported_request, "LAYOUT", layout_evidence
        )
        aspect_request, _ = requested_fact(
            session, build, "XSD_MAX_OCCURS", "EVENT", "S-9999"
        )
        aspect, _ = resolve_requested_fact(session, aspect_request, "XSD")
        assert (
            not_applicable.runtime_status == RuntimeStatus.SOURCE_NOT_APPLICABLE.value
        )
        assert miss.runtime_status == RuntimeStatus.NO_RELEVANT_EVIDENCE.value
        assert miss.resolved_value is None
        assert unsupported.runtime_status == RuntimeStatus.UNSUPPORTED.value
        assert aspect.runtime_status == RuntimeStatus.ASPECT_NOT_COVERED.value
    finally:
        cleanup(session, ids)
        session.close()


def test_fact_resolution_idempotency_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        _, evidence, _ = _resolution_fixture(session, snapshot, build)
        request, _ = requested_fact(session, build, "LAYOUT_TYPE", "EVENT", "S-9999")
        first, _ = resolve_requested_fact(session, request, "LAYOUT", evidence)
        session.commit()
        before = tuple(
            count_rows(session, model)
            for model in (RequestedFact, FactResolution, FactResolutionSupport)
        )
        same_request, created = requested_fact(
            session, build, "LAYOUT_TYPE", "EVENT", "S-9999"
        )
        second, created_resolution = resolve_requested_fact(
            session, same_request, "LAYOUT", evidence
        )
        session.commit()
        assert not created and not created_resolution and first.id == second.id
        assert before == tuple(
            count_rows(session, model)
            for model in (RequestedFact, FactResolution, FactResolutionSupport)
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_fact_resolution_rollback_postgresql(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        build_id = build.id
        _, evidence, _ = _resolution_fixture(session, snapshot, build)
        session.commit()
        import rag_esocial.fact_resolution_service as module

        original = module.FactResolutionSupport

        class FailingSupport(original):
            def __init__(self, *args, **kwargs):
                raise RuntimeError("injected resolution failure")

        monkeypatch.setattr(module, "FactResolutionSupport", FailingSupport)
        request, _ = requested_fact(session, build, "LAYOUT_TYPE", "EVENT", "S-9999")
        try:
            resolve_requested_fact(session, request, "LAYOUT", evidence)
        except RuntimeError:
            session.rollback()
        session.close()
        session = session_factory()()
        assert not session.scalars(
            select(RequestedFact).where(RequestedFact.corpus_build_id == build_id)
        ).all()
        assert not session.scalars(
            select(FactResolution)
            .join(RequestedFact)
            .where(RequestedFact.corpus_build_id == build_id)
        ).all()
        assert session.scalars(
            select(EvidenceSet).where(EvidenceSet.corpus_build_id == build_id)
        ).all()
    finally:
        cleanup(session, ids)
        session.close()


def test_fact_resolution_two_builds_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        _, evidence, _ = _resolution_fixture(session, snapshot, build)
        request, _ = requested_fact(session, build, "LAYOUT_TYPE", "EVENT", "S-9999")
        first, _ = resolve_requested_fact(session, request, "LAYOUT", evidence)
        session.commit()
        build2 = create_build(session, snapshot.slug, "fact-resolution-v2", {})
        ids["builds"].append(build2.id)
        _, evidence2, _ = _resolution_fixture(session, snapshot, build2)
        request2, _ = requested_fact(session, build2, "LAYOUT_TYPE", "EVENT", "S-9999")
        second, _ = resolve_requested_fact(session, request2, "LAYOUT", evidence2)
        session.commit()
        first_support = session.scalar(
            select(FactResolutionSupport).where(
                FactResolutionSupport.fact_resolution_id == first.id
            )
        )
        second_support = session.scalar(
            select(FactResolutionSupport).where(
                FactResolutionSupport.fact_resolution_id == second.id
            )
        )
        assert (
            request.id != request2.id
            and request.request_digest == request2.request_digest
        )
        assert first.id != second.id
        assert first_support.id != second_support.id
        assert (
            session.get(EvidenceUnit, first_support.evidence_unit_id).citation_target_id
            == session.get(
                EvidenceUnit, second_support.evidence_unit_id
            ).citation_target_id
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_fact_resolution_evaluation_report_is_deterministic(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        _resolution_fixture(session, snapshot, build)
        session.commit()
        dataset = Path("evaluation/dev/fact_resolution_status_v1.json")
        first = evaluate_fact_resolution_status(session, build, dataset)
        session.commit()
        second = evaluate_fact_resolution_status(session, build, dataset)
        session.commit()
        one, two = tmp_path / "facts-one.json", tmp_path / "facts-two.json"
        write_report(first, one)
        write_report(second, two)
        assert first == second and one.read_bytes() == two.read_bytes()
        assert first["aggregates"]["RuntimeStatusExactMatch"] == 1
        assert first["aggregates"]["NoRelevantEvidenceRateOnCovered"] == 0.25
    finally:
        cleanup(session, ids)
        session.close()


def _answer_fixture(session, snapshot, build):
    mos_evidence, layout_evidence, _ = _resolution_fixture(session, snapshot, build)
    resolved_request, _ = requested_fact(
        session, build, "LAYOUT_TYPE", "EVENT", "S-9999"
    )
    resolved, _ = resolve_requested_fact(
        session, resolved_request, "LAYOUT", layout_evidence
    )
    missing_request, _ = requested_fact(
        session, build, "LAYOUT_SIZE", "EVENT", "S-UNKNOWN"
    )
    negative, _ = resolve_requested_fact(
        session, missing_request, "LAYOUT", mos_evidence
    )
    return resolved, negative


def _valid_answer(text="O campo possui tipo numérico."):
    return {
        "claims": [
            {
                "claim_id": "C1",
                "text": text,
                "fact_resolution_refs": ["F1"],
                "evidence_refs": ["E1"],
            }
        ]
    }


def test_answer_contract_e2e_postgresql_new_session(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolution, _ = _answer_fixture(session, snapshot, build)
        request, created = create_answer_request(
            session, build, "LAYOUT", "Qual é o tipo do campo?", [resolution]
        )
        client = FakeAnswerModelClient([_valid_answer()])
        run = execute_answer(session, request, client)
        session.commit()
        run_id = run.id
        request_id = request.id
        session.close()
        session = session_factory()()
        stored = session.get(AnswerRun, run_id)
        assert created and stored.status == AnswerRunStatus.ANSWERED.value
        assert stored.rendered_answer.startswith("O campo possui tipo numérico.")
        assert client.call_count == 1
        assert count_rows(session, AnswerClaim) == 1
        assert count_rows(session, AnswerClaimFact) == 1
        assert count_rows(session, AnswerCitation) == 1
        same, created_again = create_answer_request(
            session,
            session.get(CorpusBuild, build.id),
            "LAYOUT",
            "Qual é o tipo do campo?",
            [session.get(FactResolution, resolution.id)],
        )
        assert not created_again and same.id == request_id
        second = execute_answer(
            session, same, FakeAnswerModelClient([_valid_answer("Outra formulação.")])
        )
        session.commit()
        assert second.id != run_id and count_rows(session, AnswerRun) == 2
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_abstained_zero_calls_and_partial(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolved, negative = _answer_fixture(session, snapshot, build)
        abstain_request, _ = create_answer_request(
            session, build, "LAYOUT", "Pergunta sem cobertura", [negative]
        )
        abstain_client = FakeAnswerModelClient([])
        abstained = execute_answer(session, abstain_request, abstain_client)
        assert abstained.status == AnswerRunStatus.ABSTAINED.value
        assert abstain_client.call_count == 0
        partial_request, _ = create_answer_request(
            session,
            build,
            "LAYOUT",
            "Pergunta parcialmente coberta",
            [resolved, negative],
        )
        partial_client = FakeAnswerModelClient([_valid_answer()])
        partial = execute_answer(session, partial_request, partial_client)
        assert partial.status == AnswerRunStatus.PARTIAL.value
        context = __import__("json").loads(partial_client.contexts[0])
        assert list(context["facts"]) == ["F1"]
        assert partial.validation_summary["limitations"]
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_validator_rejects_unauthorized_and_orphan_claims(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolved, _ = _answer_fixture(session, snapshot, build)
        outputs = [
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "x",
                        "fact_resolution_refs": ["F9"],
                        "evidence_refs": ["E1"],
                    }
                ]
            },
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "x",
                        "fact_resolution_refs": ["F1"],
                        "evidence_refs": ["E9"],
                    }
                ]
            },
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "x",
                        "fact_resolution_refs": [],
                        "evidence_refs": ["E1"],
                    }
                ]
            },
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "x",
                        "fact_resolution_refs": ["F1"],
                        "evidence_refs": [],
                    }
                ]
            },
        ]
        for index, output in enumerate(outputs):
            request, _ = create_answer_request(
                session, build, "LAYOUT", f"Inválida {index}", [resolved]
            )
            run = execute_answer(session, request, FakeAnswerModelClient([output]))
            assert run.status == AnswerRunStatus.VALIDATION_FAILED.value
            assert run.rendered_answer is None
        request, _ = create_answer_request(
            session, build, "LAYOUT", "Cadeia de suporte inválida", [resolved]
        )
        _, fact_map, unit_map, _, _ = preflight_answer(session, request)
        assert validate_answer_contract(_valid_answer(), fact_map, unit_map, set()) == [
            "SUPPORT_MISMATCH"
        ]
        with_extra_field = _valid_answer()
        with_extra_field["claims"][0]["outside_contract"] = True
        assert "INVALID_CLAIM_SCHEMA" in validate_answer_contract(
            with_extra_field,
            fact_map,
            unit_map,
            {(resolved.id, next(iter(unit_map.values())).id)},
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_structured_output_retry_and_model_error(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolved, _ = _answer_fixture(session, snapshot, build)
        repaired_request, _ = create_answer_request(
            session, build, "LAYOUT", "Retry válido", [resolved]
        )
        repaired = execute_answer(
            session,
            repaired_request,
            FakeAnswerModelClient([{"invalid": True}, _valid_answer()]),
        )
        assert repaired.status == AnswerRunStatus.ANSWERED.value
        assert repaired.attempt_count == 2
        failed_request, _ = create_answer_request(
            session, build, "LAYOUT", "Retry inválido", [resolved]
        )
        failed = execute_answer(
            session,
            failed_request,
            FakeAnswerModelClient([{"invalid": True}, {"still": "invalid"}]),
        )
        assert failed.status == AnswerRunStatus.MODEL_ERROR.value
        assert failed.attempt_count == 2
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_contract_rollback_postgresql(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolved, _ = _answer_fixture(session, snapshot, build)
        session.commit()
        import rag_esocial.answer_service as module

        original = module.AnswerCitation

        class FailingCitation(original):
            def __init__(self, *args, **kwargs):
                raise RuntimeError("injected answer persistence failure")

        monkeypatch.setattr(module, "AnswerCitation", FailingCitation)
        request, _ = create_answer_request(
            session, build, "LAYOUT", "Rollback", [resolved]
        )
        resolved_id = resolved.id
        try:
            execute_answer(session, request, FakeAnswerModelClient([_valid_answer()]))
        except RuntimeError:
            session.rollback()
        session.close()
        session = session_factory()()
        assert count_rows(session, AnswerRun) == 0
        assert count_rows(session, AnswerClaim) == 0
        assert count_rows(session, AnswerClaimFact) == 0
        assert count_rows(session, AnswerCitation) == 0
        assert session.get(FactResolution, resolved_id)
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_contract_two_builds_postgresql(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        first_resolution, _ = _answer_fixture(session, snapshot, build)
        first_request, _ = create_answer_request(
            session, build, "LAYOUT", "B1/B2", [first_resolution]
        )
        first_run = execute_answer(
            session, first_request, FakeAnswerModelClient([_valid_answer()])
        )
        session.commit()
        build2 = create_build(session, snapshot.slug, "answer-contract-v2", {})
        ids["builds"].append(build2.id)
        second_resolution, _ = _answer_fixture(session, snapshot, build2)
        second_request, _ = create_answer_request(
            session, build2, "LAYOUT", "B1/B2", [second_resolution]
        )
        second_run = execute_answer(
            session, second_request, FakeAnswerModelClient([_valid_answer()])
        )
        session.commit()
        assert first_request.id != second_request.id
        assert first_run.id != second_run.id
        first_citation = session.scalar(
            select(AnswerCitation)
            .join(AnswerClaim)
            .where(AnswerClaim.answer_run_id == first_run.id)
        )
        second_citation = session.scalar(
            select(AnswerCitation)
            .join(AnswerClaim)
            .where(AnswerClaim.answer_run_id == second_run.id)
        )
        assert (
            session.get(
                EvidenceUnit, first_citation.evidence_unit_id
            ).citation_target_id
            == session.get(
                EvidenceUnit, second_citation.evidence_unit_id
            ).citation_target_id
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_contract_preserves_upstream_materializations(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolved, _ = _answer_fixture(session, snapshot, build)
        session.flush()
        before = {
            "build_digest": build.build_digest,
            "search_projections": count_rows(session, SearchProjection),
            "search_units": count_rows(session, SearchUnit),
            "evidence_sets": count_rows(session, EvidenceSet),
            "evidence_units": count_rows(session, EvidenceUnit),
            "fact_resolutions": count_rows(session, FactResolution),
            "supports": count_rows(session, FactResolutionSupport),
        }
        request, _ = create_answer_request(
            session, build, "LAYOUT", "Imutabilidade upstream", [resolved]
        )
        execute_answer(session, request, FakeAnswerModelClient([_valid_answer()]))
        session.flush()
        after = {
            "build_digest": build.build_digest,
            "search_projections": count_rows(session, SearchProjection),
            "search_units": count_rows(session, SearchUnit),
            "evidence_sets": count_rows(session, EvidenceSet),
            "evidence_units": count_rows(session, EvidenceUnit),
            "fact_resolutions": count_rows(session, FactResolution),
            "supports": count_rows(session, FactResolutionSupport),
        }
        assert before == after
    finally:
        cleanup(session, ids)
        session.close()


def test_answer_cli_generate_and_show_against_postgresql(tmp_path, monkeypatch):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        resolved, _ = _answer_fixture(session, snapshot, build)
        session.commit()
        client = FakeAnswerModelClient([_valid_answer()])
        monkeypatch.setattr(
            cli_module, "OllamaAnswerModelClient", lambda **kwargs: client
        )
        runner = CliRunner()
        generated = runner.invoke(
            cli_module.app,
            [
                "answer",
                "generate",
                "--build",
                build.id,
                "--source",
                "LAYOUT",
                "--question",
                "Qual é o tipo?",
                "--resolution",
                resolved.id,
            ],
        )
        assert generated.exit_code == 0, generated.output
        session.expire_all()
        run = session.scalar(
            select(AnswerRun).order_by(AnswerRun.created_at.desc()).limit(1)
        )
        assert run.status == AnswerRunStatus.ANSWERED.value
        shown = runner.invoke(cli_module.app, ["answer", "show", "--run", run.id])
        assert shown.exit_code == 0, shown.output
        assert run.id in shown.output
        assert "O campo possui tipo numérico." in shown.output
    finally:
        cleanup(session, ids)
        session.close()


def test_q14_fake_14_of_14_is_deterministic_and_frozen(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    dataset = Path("evaluation/q14/q14_v1.json")
    try:
        _resolution_fixture(session, snapshot, build)
        session.commit()
        data, digest = validate_q14(dataset)
        assert len(data["cases"]) == 14
        assert (
            digest == "30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7"
        )
        first = evaluate_q14(
            session, build, dataset, DeterministicQ14Client, "fake-deterministic"
        )
        session.commit()
        upstream = {
            "build_digest": build.build_digest,
            "projections": count_rows(session, SearchProjection),
            "search_units": count_rows(session, SearchUnit),
            "evidence_sets": count_rows(session, EvidenceSet),
            "evidence_units": count_rows(session, EvidenceUnit),
        }
        second = evaluate_q14(
            session, build, dataset, DeterministicQ14Client, "fake-deterministic"
        )
        session.commit()
        assert first == second
        assert upstream == {
            "build_digest": build.build_digest,
            "projections": count_rows(session, SearchProjection),
            "search_units": count_rows(session, SearchUnit),
            "evidence_sets": count_rows(session, EvidenceSet),
            "evidence_units": count_rows(session, EvidenceUnit),
        }
        one, two = tmp_path / "q14-one.json", tmp_path / "q14-two.json"
        write_report(first, one)
        write_report(second, two)
        assert one.read_bytes() == two.read_bytes()
        assert sum(x["observed_status"] == "ANSWERED" for x in first["results"]) == 8, [
            (x["case_id"], x["expected_status"], x["observed_status"])
            for x in first["results"]
        ]
        assert sum(x["observed_status"] == "PARTIAL" for x in first["results"]) == 3
        abstained = [x for x in first["results"] if x["observed_status"] == "ABSTAINED"]
        assert len(abstained) == 3
        assert all(x["model_call_count"] == 0 for x in abstained)
        assert first["aggregates"]["AnswerRunSuccessRate"] == 1
        assert first["aggregates"]["CitationMembershipValidity"] == 1
        assert first["aggregates_by_family"] == [
            {"family": "MOS", "case_count": 5, "status_exact_match_rate": 1.0},
            {"family": "LAYOUT", "case_count": 5, "status_exact_match_rate": 1.0},
            {"family": "XSD", "case_count": 4, "status_exact_match_rate": 1.0},
        ]
        cli_report = tmp_path / "q14-cli.json"
        cli_result = CliRunner().invoke(
            cli_module.app,
            [
                "eval",
                "q14",
                "--build",
                build.id,
                "--fake",
                "--output",
                str(cli_report),
            ],
        )
        assert cli_result.exit_code == 0, cli_result.output
        assert (
            json.loads(cli_report.read_text())["aggregates"]["AnswerRunSuccessRate"]
            == 1
        )
    finally:
        cleanup(session, ids)
        session.close()


def _phase9a_source_fixture(session, snapshot, build, question="Complete fixture"):
    mos_evidence, layout_evidence, xsd_evidence = _resolution_fixture(
        session, snapshot, build
    )
    definitions = (
        (
            "event.concept",
            "EVENT_CONCEITO",
            "EVENT",
            "S-9999",
            DocumentFamily.MOS.value,
            "MOS_EVENT_SECTION",
            "S-9999",
            mos_evidence,
        ),
        (
            "layout.field-type",
            "LAYOUT_TYPE",
            "EVENT",
            "S-9999",
            DocumentFamily.LAYOUT.value,
            "LAYOUT_FIELD",
            "aliqRat",
            layout_evidence,
        ),
        (
            "xsd.max-occurs",
            "XSD_MAX_OCCURS",
            "FIELD",
            "XSD/urn:fixture:1.0/schema/evento_fixture/evtFixture/id",
            DocumentFamily.XSD.value,
            "XSD_ELEMENT",
            "TS_Id",
            xsd_evidence,
        ),
    )
    aspects = []
    resolutions = {}
    for (
        aspect_key,
        fact_type,
        subject_kind,
        subject_key,
        family,
        profile,
        query,
        evidence,
    ) in definitions:
        fact, _ = requested_fact(session, build, fact_type, subject_kind, subject_key)
        resolution, _ = resolve_requested_fact(session, fact, family, evidence)
        assert resolution.runtime_status == RuntimeStatus.RESOLVED.value
        aspects.append(
            CompleteRequestedAspectSpec(
                aspect_key=aspect_key,
                subject_kind=subject_kind,
                subject_key=subject_key,
                canonical_entity=(
                    session.get(CanonicalEntity, fact.canonical_entity_id)
                    if fact.canonical_entity_id
                    else None
                ),
                source_inputs=(
                    CompleteSourceInputSpec(
                        document_family=family,
                        requested_fact=fact,
                        retrieval_profile=profile,
                        query=query,
                        top_k=5,
                    ),
                ),
            )
        )
        resolutions[family] = resolution
    complete_request, created = create_complete_answer_request(
        session,
        build,
        question,
        SOURCE_ORDER,
        tuple(aspects),
        orchestration_config={"source_run_policy": "ALWAYS_NEW"},
    )
    source_requests = {}
    source_runs = {}
    for family in SOURCE_ORDER:
        source_request, _ = create_answer_request(
            session, build, family, question, [resolutions[family]]
        )
        source_requests[family] = source_request
        source_runs[family] = execute_answer(
            session,
            source_request,
            FakeAnswerModelClient([_valid_answer(f"Resposta {family}.")]),
        )
    return complete_request, created, tuple(aspects), source_requests, source_runs


def _register_phase9a_sources(session, complete_run, source_requests, source_runs):
    memberships = {}
    for family in SOURCE_ORDER:
        membership, created = register_complete_source_run(
            session,
            complete_run,
            family,
            source_requests[family],
            source_runs[family],
            {"answer_status": source_runs[family].status},
        )
        assert created
        memberships[family] = membership
    return memberships


def test_phase9a_e2e_new_session_idempotency_multiple_runs_and_sources(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, created, aspects, source_requests, source_runs = (
            _phase9a_source_fixture(session, snapshot, build)
        )
        same, created_again = create_complete_answer_request(
            session,
            build,
            request.question,
            tuple(reversed(SOURCE_ORDER)),
            tuple(reversed(aspects)),
            orchestration_config={"source_run_policy": "ALWAYS_NEW"},
        )
        assert created and not created_again
        assert same.id == request.id and same.request_digest == request.request_digest
        changed, changed_created = create_complete_answer_request(
            session,
            build,
            request.question,
            SOURCE_ORDER,
            aspects,
            orchestration_config={"source_run_policy": "ALWAYS_NEW", "revision": 2},
        )
        assert changed_created and changed.id != request.id

        first_run = create_complete_answer_run(session, request)
        memberships = _register_phase9a_sources(
            session, first_run, source_requests, source_runs
        )
        repeated, repeated_created = register_complete_source_run(
            session,
            first_run,
            DocumentFamily.MOS.value,
            source_requests[DocumentFamily.MOS.value],
            source_runs[DocumentFamily.MOS.value],
        )
        assert not repeated_created and repeated.id == memberships["MOS"].id

        second_source_runs = {
            family: execute_answer(
                session,
                source_requests[family],
                FakeAnswerModelClient([_valid_answer(f"Segunda {family}.")]),
            )
            for family in SOURCE_ORDER
        }
        second_run = create_complete_answer_run(session, request)
        _register_phase9a_sources(
            session, second_run, source_requests, second_source_runs
        )
        assert first_run.id != second_run.id
        session.commit()
        first_id, request_id = first_run.id, request.id
        session.close()

        session = session_factory()()
        stored = session.get(CompleteAnswerRun, first_id)
        inspected = inspect_complete_run(session, stored)
        assert stored.complete_answer_request_id == request_id
        assert stored.execution_state == CompleteRunExecutionState.RUNNING.value
        assert [item["document_family"] for item in inspected["sources"]] == list(
            SOURCE_ORDER
        )
        assert all(item["answer_run_id"] for item in inspected["sources"])
        assert stored.request.id == request_id
        assert all(
            item.answer_run.answer_request_id == item.answer_request.id
            for item in stored.source_runs
        )
        assert count_rows(session, CompleteAnswerRequest) == 2
        assert count_rows(session, CompleteAnswerRun) == 2
        assert count_rows(session, CompleteAnswerSourceRun) == 6
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9a_source_membership_negative_matrix(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, aspects, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        with pytest.raises(CompleteIdentityError, match="duplicate"):
            create_complete_answer_request(
                session,
                build,
                "duplicate",
                ("MOS", "MOS", "XSD"),
                aspects,
            )
        with pytest.raises(CompleteIdentityError, match="requires"):
            create_complete_answer_request(
                session,
                build,
                "unknown",
                ("MOS", "LAYOUT", "UNKNOWN"),
                aspects,
            )

        run = create_complete_answer_run(session, request)
        with pytest.raises(CompleteMembershipError, match="unknown"):
            register_complete_source_run(
                session,
                run,
                "UNKNOWN",
                source_requests["MOS"],
                source_runs["MOS"],
            )
        with pytest.raises(CompleteMembershipError, match="wrong family"):
            register_complete_source_run(
                session,
                run,
                "MOS",
                source_requests["LAYOUT"],
                source_runs["LAYOUT"],
            )
        with pytest.raises(CompleteMembershipError, match="other answer request"):
            register_complete_source_run(
                session,
                run,
                "MOS",
                source_requests["MOS"],
                source_runs["LAYOUT"],
            )
        mos_resolution = session.scalar(
            select(FactResolution)
            .join(AnswerRequestFactResolution)
            .where(
                AnswerRequestFactResolution.answer_request_id
                == source_requests["MOS"].id
            )
        )
        wrong_request, _ = create_answer_request(
            session, build, "MOS", "Outra pergunta", [mos_resolution]
        )
        wrong_request_run = execute_answer(
            session,
            wrong_request,
            FakeAnswerModelClient([_valid_answer("wrong request")]),
        )
        with pytest.raises(CompleteMembershipError, match="wrong question"):
            register_complete_source_run(
                session, run, "MOS", wrong_request, wrong_request_run
            )
        register_complete_source_run(
            session,
            run,
            "MOS",
            source_requests["MOS"],
            source_runs["MOS"],
        )
        replacement = execute_answer(
            session,
            source_requests["MOS"],
            FakeAnswerModelClient([_valid_answer("replacement")]),
        )
        with pytest.raises(CompleteDuplicateMembershipError, match="already has"):
            register_complete_source_run(
                session, run, "MOS", source_requests["MOS"], replacement
            )
        another_run = create_complete_answer_run(session, request)
        with pytest.raises(CompleteDuplicateMembershipError, match="already belongs"):
            register_complete_source_run(
                session,
                another_run,
                "MOS",
                source_requests["MOS"],
                source_runs["MOS"],
            )
        failed = mark_complete_run_failed(
            session, another_run, "TEST_FAILURE", {"stage": "9A"}
        )
        assert failed.execution_state == CompleteRunExecutionState.FAILED.value
        assert failed.status is None and failed.failure_code == "TEST_FAILURE"
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9a_wrong_build_and_b1_b2(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request1, _, aspects1, requests1, runs1 = _phase9a_source_fixture(
            session, snapshot, build
        )
        run1 = create_complete_answer_run(session, request1)
        _register_phase9a_sources(session, run1, requests1, runs1)
        session.commit()

        build2 = create_build(session, snapshot.slug, "complete-answer-b2", {})
        ids["builds"].append(build2.id)
        request2, _, _, requests2, runs2 = _phase9a_source_fixture(
            session, snapshot, build2
        )
        run2 = create_complete_answer_run(session, request2)
        _register_phase9a_sources(session, run2, requests2, runs2)
        session.commit()
        assert request1.id != request2.id
        assert run1.id != run2.id
        assert {
            item.id
            for item in session.scalars(
                select(CompleteAnswerSourceRun).where(
                    CompleteAnswerSourceRun.complete_answer_run_id == run1.id
                )
            )
        }.isdisjoint(
            {
                item.id
                for item in session.scalars(
                    select(CompleteAnswerSourceRun).where(
                        CompleteAnswerSourceRun.complete_answer_run_id == run2.id
                    )
                )
            }
        )

        third_run = create_complete_answer_run(session, request1)
        with pytest.raises(CompleteBuildMismatchError, match="other build"):
            register_complete_source_run(
                session, third_run, "MOS", requests2["MOS"], runs2["MOS"]
            )
        savepoint = session.begin_nested()
        now = datetime.now(timezone.utc)
        session.add(
            CompleteAnswerRun(
                id=str(uuid.uuid4()),
                complete_answer_request_id=request1.id,
                corpus_build_id=build2.id,
                run_key=str(uuid.uuid4()),
                execution_state=CompleteRunExecutionState.RUNNING.value,
                status=None,
                context_digest=None,
                failure_code=None,
                failure_details=None,
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        savepoint.rollback()
        wrong_fact_aspect = CompleteRequestedAspectSpec(
            aspect_key="wrong-build",
            subject_kind=aspects1[0].subject_kind,
            subject_key=aspects1[0].subject_key,
            source_inputs=(
                CompleteSourceInputSpec(
                    document_family="MOS",
                    requested_fact=session.get(
                        RequestedFact,
                        session.scalar(
                            select(CompleteAnswerSourceInput.requested_fact_id)
                            .join(CompleteAnswerRequestSource)
                            .where(
                                CompleteAnswerRequestSource.complete_answer_request_id
                                == request2.id,
                                CompleteAnswerRequestSource.document_family == "MOS",
                            )
                        ),
                    ),
                    retrieval_profile="MOS_EVENT_SECTION",
                    query="S-9999",
                    top_k=5,
                ),
            ),
        )
        with pytest.raises(CompleteBuildMismatchError, match="requested fact"):
            create_complete_answer_request(
                session,
                build,
                "wrong build",
                SOURCE_ORDER,
                (wrong_fact_aspect,),
            )

        target1 = session.scalar(
            select(SourceFact.citation_target_id).where(
                SourceFact.corpus_build_id == build.id,
                SourceFact.fact_type == "LAYOUT_TYPE",
            )
        )
        target2 = session.scalar(
            select(SourceFact.citation_target_id).where(
                SourceFact.corpus_build_id == build2.id,
                SourceFact.fact_type == "LAYOUT_TYPE",
            )
        )
        assert target1 == target2
        assert aspects1[0].canonical_entity.id == session.scalar(
            select(CanonicalEntity.id).where(
                CanonicalEntity.stable_key == aspects1[0].canonical_entity.stable_key
            )
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9a_rollback_preserves_request_and_phase8_runs(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        session.commit()
        request_id = request.id
        answer_run_ids = {item.id for item in source_runs.values()}

        run = create_complete_answer_run(session, request)
        memberships = _register_phase9a_sources(
            session, run, source_requests, source_runs
        )
        run_id = run.id
        mos = memberships["MOS"]
        session.add(
            CompleteAnswerSourceRun(
                id=str(uuid.uuid4()),
                complete_answer_run_id=run.id,
                complete_answer_request_id=request.id,
                request_source_id=mos.request_source_id,
                answer_request_id=mos.answer_request_id,
                answer_run_id=mos.answer_run_id,
                document_family=mos.document_family,
                source_order=mos.source_order,
                availability=mos.availability,
                outcome_summary={},
                created_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        session.close()

        session = session_factory()()
        assert session.get(CompleteAnswerRequest, request_id)
        assert session.get(CompleteAnswerRun, run_id) is None
        assert count_rows(session, CompleteAnswerSourceRun) == 0
        assert answer_run_ids == {
            item.id
            for item in session.scalars(
                select(AnswerRun).where(AnswerRun.id.in_(answer_run_ids))
            )
        }
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9a_preserves_all_upstream_and_q14(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        session.commit()
        models = (
            CorpusSnapshot,
            CorpusBuild,
            SearchProjection,
            SearchUnit,
            EvidenceSet,
            EvidenceUnit,
            SourceFact,
            ResolvedFact,
            RequestedFact,
            FactResolution,
            FactResolutionSupport,
            AnswerRequest,
            AnswerRun,
            AnswerClaim,
            AnswerClaimFact,
            AnswerCitation,
        )
        q14_path = Path("evaluation/q14/q14_v1.json")
        _, q14_digest = validate_q14(q14_path)
        report_hashes = {
            path.name: __import__("hashlib").sha256(path.read_bytes()).hexdigest()
            for path in Path("evaluation/q14").glob("*report.json")
        }
        before = {model.__name__: count_rows(session, model) for model in models}
        before["build_digest"] = build.build_digest

        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()

        after = {model.__name__: count_rows(session, model) for model in models}
        after["build_digest"] = session.get(CorpusBuild, build.id).build_digest
        assert before == after
        assert validate_q14(q14_path)[1] == q14_digest
        assert (
            q14_digest
            == "30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7"
        )
        assert report_hashes == {
            path.name: __import__("hashlib").sha256(path.read_bytes()).hexdigest()
            for path in Path("evaluation/q14").glob("*report.json")
        }
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9b_aggregation_is_deterministic_new_session_and_source_qualified(
    tmp_path,
):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, aspects, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()

        first, first_digest = aggregate_cross_source(session, run)
        session.commit()
        assert first_digest == run.context_digest
        assert [item["ref"] for item in first["facts"]] == [
            "MOS:F1",
            "LAYOUT:F1",
            "XSD:F1",
        ]
        assert [item["ref"] for item in first["evidence"]] == [
            "MOS:E1",
            "LAYOUT:E1",
            "XSD:E1",
        ]
        assert all(
            item["status"] == "SOURCE_NOT_APPLICABLE"
            for coverage in first["coverage"]
            for item in coverage["sources"]
            if item["source"]
            != next(
                aspect.source_inputs[0].document_family
                for aspect in aspects
                if aspect.aspect_key == coverage["aspect_key"]
            )
        )
        assert [item["kind"] for item in first["comparisons"]] == [
            "SINGLE_SOURCE",
            "SINGLE_SOURCE",
            "SINGLE_SOURCE",
        ]
        serialized = serialize_cross_source_context(first)
        assert "complete_answer_run_id" not in serialized
        assert "answer_run_id" not in serialized
        assert len(session.scalars(select(CrossSourceComparison)).all()) == 3
        assert len(session.scalars(select(CrossSourceComparisonMember)).all()) == 3

        session.close()
        session = session_factory()()
        persisted_run = session.get(CompleteAnswerRun, run.id)
        second, second_digest = aggregate_cross_source(session, persisted_run)
        assert second == first
        assert second_digest == first_digest
        assert serialize_cross_source_context(second) == serialized
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9b_support_chain_failure_and_rollback_are_local(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()
        support = session.scalar(select(FactResolutionSupport))
        session.delete(support)
        session.commit()
        with pytest.raises(CrossSourceSupportError):
            aggregate_cross_source(session, run)
        session.rollback()
        assert session.scalars(select(CrossSourceComparison)).all() == []
        assert session.scalars(select(CrossSourceComparisonMember)).all() == []
        assert session.get(AnswerRun, source_runs["MOS"].id) is not None
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9c_three_source_synthesis_context_claim_ledger_and_reload(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()
        context = build_synthesis_context(session, run)
        assert context.payload["revision"] == SYNTHESIS_CONTRACT_REVISION
        assert {item["ref"] for item in context.payload["facts"]} == {
            "MOS:F1",
            "LAYOUT:F1",
            "XSD:F1",
        }
        assert "rendered_answer" not in context.payload
        assert "AnswerClaim" not in context.serialize()
        output = {
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Achado consolidado pelas fontes autorizadas.",
                    "fact_refs": ["MOS:F1", "LAYOUT:F1", "XSD:F1"],
                    "evidence_refs": ["MOS:E1", "LAYOUT:E1", "XSD:E1"],
                    "comparison_refs": ["X1", "X2", "X3"],
                }
            ]
        }
        assert validate_synthesis_output(output, context) == []
        client = FakeAnswerModelClient([output])
        result = execute_complete_synthesis(session, run, client)
        session.commit()
        assert result.status == "ANSWERED"
        assert result.execution_state == "FINALIZED"
        assert client.call_count == 1
        assert result.synthesis_attempt_count == 1
        assert count_rows(session, CompleteAnswerClaim) == 1
        assert count_rows(session, CompleteAnswerClaimFact) == 3
        assert count_rows(session, CompleteAnswerCitation) == 3
        assert count_rows(session, CompleteAnswerClaimComparison) == 3
        assert result.synthesis_rendered_answer

        session.close()
        session = session_factory()()
        reloaded = session.get(CompleteAnswerRun, run.id)
        assert reloaded.status == "ANSWERED"
        assert (
            session.scalars(
                select(CompleteAnswerClaim).where(
                    CompleteAnswerClaim.complete_answer_run_id == run.id
                )
            )
            .one()
            .claim_key
            == "C1"
        )
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9c_retry_validation_failure_and_no_fact_zero_call(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()
        assert build_synthesis_context(session, run).aggregation_digest
        good = {
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Fato autorizado.",
                    "fact_refs": ["MOS:F1", "LAYOUT:F1"],
                    "evidence_refs": ["MOS:E1", "LAYOUT:E1"],
                    "comparison_refs": ["X1", "X2"],
                }
            ]
        }
        retry_client = FakeAnswerModelClient([{"bad": True}, good])
        result = execute_complete_synthesis(session, run, retry_client)
        session.commit()
        assert result.status == "ANSWERED"
        assert retry_client.call_count == 2
        assert result.synthesis_attempt_count == 2

        for resolution in session.scalars(select(FactResolution)).all():
            resolution.runtime_status = RuntimeStatus.UNSUPPORTED.value
            resolution.resolved_value = None
        session.commit()
        no_source_runs = {
            family: execute_answer(
                session,
                source_requests[family],
                FakeAnswerModelClient([]),
            )
            for family in SOURCE_ORDER
        }
        no_fact_run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, no_fact_run, source_requests, no_source_runs)
        session.commit()
        no_call_client = FakeAnswerModelClient([RuntimeError("must not call")])
        result = execute_complete_synthesis(session, no_fact_run, no_call_client)
        session.commit()
        assert result.status == "ABSTAINED"
        assert result.synthesis_attempt_count == 0
        assert no_call_client.call_count == 0
        assert count_rows(session, CompleteAnswerClaim) == 1
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9c_validator_rejects_closed_world_and_support_violations(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()
        context = build_synthesis_context(session, run)
        base = {
            "claim_id": "C1",
            "text": "Claim.",
            "fact_refs": ["MOS:F1"],
            "evidence_refs": ["MOS:E1"],
            "comparison_refs": [],
        }
        cases = (
            ({**base, "fact_refs": ["MOS:F9"]}, "UNAUTHORIZED_FACT_REFERENCE"),
            ({**base, "evidence_refs": ["MOS:E9"]}, "UNAUTHORIZED_EVIDENCE_REFERENCE"),
            ({**base, "comparison_refs": ["X9"]}, "UNAUTHORIZED_COMPARISON_REFERENCE"),
            ({**base, "fact_refs": ["BAD:F1"]}, "UNAUTHORIZED_FACT_REFERENCE"),
            ({**base, "evidence_refs": ["LAYOUT:E1"]}, "SUPPORT_MISMATCH"),
            ({**base, "comparison_refs": ["X2"]}, "COMPARISON_MEMBER_MISMATCH"),
            (
                {
                    **base,
                    "fact_refs": ["MOS:F1", "LAYOUT:F1"],
                    "evidence_refs": ["MOS:E1", "LAYOUT:E1"],
                },
                "MISSING_COMPARISON_REFERENCE",
            ),
            ({**base, "fact_refs": []}, "CLAIM_WITHOUT_FACT_REFS"),
            ({**base, "evidence_refs": []}, "CLAIM_WITHOUT_EVIDENCE_REFS"),
        )
        for claim, expected in cases:
            assert expected in validate_synthesis_output({"claims": [claim]}, context)
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9c_source_failure_is_limitation_and_single_source_skips_synthesis(
    tmp_path,
):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        source_runs["MOS"].status = "MODEL_ERROR"
        run = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()
        output = {
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Fatos autorizados.",
                    "fact_refs": ["MOS:F1", "LAYOUT:F1", "XSD:F1"],
                    "evidence_refs": ["MOS:E1", "LAYOUT:E1", "XSD:E1"],
                    "comparison_refs": ["X1", "X2", "X3"],
                }
            ]
        }
        client = FakeAnswerModelClient([output])
        result = execute_complete_synthesis(session, run, client)
        session.commit()
        assert result.status == "PARTIAL"
        assert client.call_count == 1
        assert any(
            item["kind"] == "MODEL_ERROR"
            for item in result.synthesis_validation_summary["limitations"]
        )

        for resolution in session.scalars(select(FactResolution)).all():
            if resolution.document_family != DocumentFamily.MOS.value:
                resolution.runtime_status = RuntimeStatus.ASPECT_NOT_COVERED.value
                resolution.resolved_value = None
        session.commit()
        single_source_runs = {
            family: execute_answer(
                session,
                source_requests[family],
                FakeAnswerModelClient(
                    [_valid_answer("Resposta MOS.")]
                    if family == DocumentFamily.MOS.value
                    else []
                ),
            )
            for family in SOURCE_ORDER
        }
        single = create_complete_answer_run(session, request)
        _register_phase9a_sources(session, single, source_requests, single_source_runs)
        session.commit()
        no_synthesis = FakeAnswerModelClient([RuntimeError("must not call")])
        result = execute_complete_synthesis(session, single, no_synthesis)
        session.commit()
        assert no_synthesis.call_count == 0
        assert result.status == "PARTIAL"
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9c_rollback_keeps_9b_and_removes_final_ledger(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        request, _, _, source_requests, source_runs = _phase9a_source_fixture(
            session, snapshot, build
        )
        run = create_complete_answer_run(session, request)
        run_id = run.id
        _register_phase9a_sources(session, run, source_requests, source_runs)
        session.commit()
        aggregate_cross_source(session, run)
        session.commit()
        comparisons_before = count_rows(session, CrossSourceComparison)
        output = {
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Claim válida.",
                    "fact_refs": ["MOS:F1", "LAYOUT:F1"],
                    "evidence_refs": ["MOS:E1", "LAYOUT:E1"],
                    "comparison_refs": ["X1", "X2"],
                }
            ]
        }
        execute_complete_synthesis(session, run, FakeAnswerModelClient([output]))
        session.rollback()
        session.close()
        session = session_factory()()
        assert count_rows(session, CompleteAnswerClaim) == 0
        assert count_rows(session, CompleteAnswerClaimFact) == 0
        assert count_rows(session, CompleteAnswerCitation) == 0
        assert count_rows(session, CompleteAnswerClaimComparison) == 0
        assert count_rows(session, CrossSourceComparison) == comparisons_before
        assert session.get(CompleteAnswerRun, run_id).status is None
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9d_application_e2e_new_session_idempotency_and_read_only_show(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    source_clients = {}

    class FakeSynthesisClient:
        model = "fake-synthesis"

        def __init__(self):
            self.call_count = 0

        def generate(self, prompt):
            self.call_count += 1
            context = json.loads(prompt)["context"]
            facts = context["facts"]
            evidence = context["evidence"]
            comparisons = context["comparisons"]
            return {
                "claims": [
                    {
                        "claim_id": "C1",
                        "text": "Síntese Complete determinística.",
                        "fact_refs": [item["ref"] for item in facts],
                        "evidence_refs": [item["ref"] for item in evidence],
                        "comparison_refs": [item["ref"] for item in comparisons],
                    }
                ]
            }

    synthesis_clients = []

    def source_factory(family):
        client = FakeAnswerModelClient([_valid_answer(f"Resposta {family}.")])
        source_clients[family] = client
        return client

    def synthesis_factory():
        client = FakeSynthesisClient()
        synthesis_clients.append(client)
        return client

    try:
        _phase9a_source_fixture(session, snapshot, build)
        facts = {
            item.fact_type: item
            for item in session.scalars(
                select(RequestedFact).where(RequestedFact.corpus_build_id == build.id)
            )
        }
        data = {
            "question": "Como o mesmo aspecto é representado nas fontes?",
            "aspects": [
                {
                    "aspect_key": "event.concept",
                    "subject_kind": facts["EVENT_CONCEITO"].subject_kind,
                    "subject_key": facts["EVENT_CONCEITO"].subject_key,
                    "source_inputs": [
                        {
                            "source": "MOS",
                            "requested_fact_id": facts["EVENT_CONCEITO"].id,
                            "profile": "MOS_EVENT_SECTION",
                            "query": "S-9999",
                        }
                    ],
                },
                {
                    "aspect_key": "layout.field-type",
                    "subject_kind": facts["LAYOUT_TYPE"].subject_kind,
                    "subject_key": facts["LAYOUT_TYPE"].subject_key,
                    "source_inputs": [
                        {
                            "source": "LAYOUT",
                            "requested_fact_id": facts["LAYOUT_TYPE"].id,
                            "profile": "LAYOUT_FIELD",
                            "query": "aliqRat",
                        }
                    ],
                },
                {
                    "aspect_key": "xsd.max-occurs",
                    "subject_kind": facts["XSD_MAX_OCCURS"].subject_kind,
                    "subject_key": facts["XSD_MAX_OCCURS"].subject_key,
                    "source_inputs": [
                        {
                            "source": "XSD",
                            "requested_fact_id": facts["XSD_MAX_OCCURS"].id,
                            "profile": "XSD_ELEMENT",
                            "query": "TS_Id",
                        }
                    ],
                },
            ],
        }
        first = execute_complete(
            session,
            build,
            data,
            get_settings(),
            source_client_factory=source_factory,
            synthesis_client_factory=synthesis_factory,
        )
        first_key = first.run.run_key
        assert first.payload["status"] == "ANSWERED"
        assert first.payload["claims"][0]["comparison_refs"]
        assert sum(client.call_count for client in source_clients.values()) == 3
        assert synthesis_clients[-1].call_count == 1

        second = execute_complete(
            session,
            build,
            data,
            get_settings(),
            source_client_factory=source_factory,
            synthesis_client_factory=synthesis_factory,
        )
        assert second.request.id == first.request.id
        assert second.run.run_key != first_key
        assert second.payload["status"] == "ANSWERED"

        session.commit()
        before = {
            "runs": session.scalar(select(func.count()).select_from(CompleteAnswerRun)),
            "claims": session.scalar(
                select(func.count()).select_from(CompleteAnswerClaim)
            ),
        }
        session.close()
        session = session_factory()()
        shown = complete_show_payload(session, first_key)
        assert shown["run_key"] == first_key
        assert shown["status"] == "ANSWERED"
        assert shown["citations"]
        assert synthesis_clients[-1].call_count == 1
        after = {
            "runs": session.scalar(select(func.count()).select_from(CompleteAnswerRun)),
            "claims": session.scalar(
                select(func.count()).select_from(CompleteAnswerClaim)
            ),
        }
        assert after == before
    finally:
        cleanup(session, ids)
        session.close()


def test_phase9d_all_no_fact_abstains_without_model_calls(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    source_clients = []
    synthesis_calls = []

    class NoCallClient:
        model = "must-not-call"

        def generate(self, _prompt):
            raise AssertionError("provider não deve ser chamado")

    try:
        data = {
            "question": "Pergunta sem evidência.",
            "aspects": [
                {
                    "aspect_key": "missing",
                    "subject_kind": "EVENT",
                    "subject_key": "UNKNOWN",
                    "source_inputs": [
                        {
                            "source": family,
                            "requested_fact": {
                                "fact_type": "UNSUPPORTED_FACT",
                                "subject_kind": "EVENT",
                                "subject_key": "UNKNOWN",
                            },
                            "profile": profile,
                            "query": "text-that-does-not-exist",
                        }
                        for family, profile in (
                            ("MOS", "MOS_EVENT_SECTION"),
                            ("LAYOUT", "LAYOUT_FIELD"),
                            ("XSD", "XSD_ELEMENT"),
                        )
                    ],
                }
            ],
        }

        def source_factory(_family):
            client = NoCallClient()
            client.call_count = 0
            source_clients.append(client)
            return client

        def synthesis_factory():
            synthesis_calls.append(True)
            return NoCallClient()

        result = execute_complete(
            session,
            build,
            data,
            get_settings(),
            source_client_factory=source_factory,
            synthesis_client_factory=synthesis_factory,
        )
        assert result.payload["status"] == "ABSTAINED"
        assert all(client.call_count == 0 for client in source_clients)
        assert synthesis_calls == [True]
        assert result.payload["answer"]
    finally:
        cleanup(session, ids)
        session.close()
