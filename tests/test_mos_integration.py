import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from sqlalchemy import delete, func, select

import rag_esocial.mos_materializer as mos_materializer_module
from rag_esocial.build_service import create_build
from rag_esocial.corpus import (
    freeze_snapshot,
    inventory_zip,
    storage_root,
    verify_snapshot,
)
from rag_esocial.db import session_factory
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
from rag_esocial.mos_materializer import materialize_mos
from rag_esocial.mos_parser import parse_mos_text
from rag_esocial.pdf_text import PdfTextExtractor


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
    payloads[ArtifactRole.LAYOUT_MAIN.value].write_text("<html>fixture</html>")
    payloads[ArtifactRole.LAYOUT_ANNEX_I_DOMAIN_TABLES.value].write_text("Tabela 01")
    payloads[ArtifactRole.LAYOUT_ANNEX_II_VALIDATION_RULES.value].write_text(
        "REGRA_FIXTURE"
    )
    xsd_path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(xsd_path, "w") as archive:
        archive.writestr("evento.xsd", "<schema/>")
        archive.writestr("tipos.xsd", "<schema/>")
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
            session.execute(delete(model).where(model.build_id.in_(ids["builds"])))
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
