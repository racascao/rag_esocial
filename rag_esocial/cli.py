import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from . import __version__
from .build_service import create_build
from .config import get_settings
from .corpus import (
    freeze_snapshot,
    inventory_zip,
    sha256_file,
    storage_root,
    verify_snapshot,
)
from .db import check_connection, session_factory
from .evaluation_service import (
    evaluate_fact_resolution_status,
    evaluate_retrieval_evidence,
    write_report,
)
from .evidence_service import assemble_evidence
from .fact_resolution_service import requested_fact, resolve_requested_fact
from .facts_service import build_facts
from .layout_materializer import materialize_layout
from .layout_parser import parse_layout_html
from .logging_config import configure_logging
from .models.build import CorpusBuild
from .models.corpus import (
    CorpusSnapshot,
    DocumentArtifact,
    DocumentVersion,
    SnapshotMember,
)
from .models.evidence import EvidenceSet, EvidenceSetItem, EvidenceUnit
from .models.fact_resolution import FactResolution, FactResolutionSupport, RequestedFact
from .models.facts import EntityRelation, ReferenceResolution, ResolvedFact, SourceFact
from .models.layout import LayoutDocument
from .models.mos import MosDocument
from .models.search import SearchProjection, SearchUnit
from .models.xsd import (
    XsdElement,
    XsdEnumeration,
    XsdEventSchema,
    XsdPackageDocument,
    XsdSharedType,
)
from .mos_materializer import materialize_mos
from .mos_parser import parse_mos_text
from .pdf_text import PdfTextExtractor
from .search_service import materialize_projection, search
from .xsd_materializer import parse_and_materialize_xsd

app = typer.Typer(help="Fundação CLI do assistente RAG eSocial.", no_args_is_help=True)
db_app = typer.Typer(help="Comandos de infraestrutura do banco.")
app.add_typer(db_app, name="db")
corpus_app = typer.Typer(help="Aquisição, provenance e snapshots do corpus.")
app.add_typer(corpus_app, name="corpus")
artifact_app = typer.Typer(help="Importação manual genérica de artefatos oficiais.")
corpus_app.add_typer(artifact_app, name="artifact")
build_app = typer.Typer(help="Materializações reproduzíveis de snapshots congelados.")
app.add_typer(build_app, name="build")
mos_app = typer.Typer(help="Parser estrutural do MOS.")
app.add_typer(mos_app, name="mos")
layout_app = typer.Typer(help="Parser estrutural do Leiaute.")
app.add_typer(layout_app, name="layout")
xsd_app = typer.Typer(help="Parser estrutural do pacote XSD.")
app.add_typer(xsd_app, name="xsd")
facts_app = typer.Typer(help="Fatos determinísticos e resolução de referências.")
app.add_typer(facts_app, name="facts")
search_app = typer.Typer(help="Projeções experimentais e busca lexical FTS.")
app.add_typer(search_app, name="search")
evidence_app = typer.Typer(help="Retrieval FTS e montagem de evidência autorizada.")
app.add_typer(evidence_app, name="evidence")
eval_app = typer.Typer(help="Avaliação DEV de retrieval e evidence assembly.")
app.add_typer(eval_app, name="eval")
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"rag-esocial {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=version_callback, is_eager=True
    ),
) -> None:
    configure_logging(get_settings().log_level)


@db_app.command("status")
def db_status() -> None:
    settings = get_settings()
    table = Table(title="eSocial — banco")
    table.add_column("Item")
    table.add_column("Valor")
    table.add_row("Ambiente", settings.environment)
    table.add_row("Banco", "conectado" if check_connection() else "indisponível")
    table.add_row("LLM declarativo", settings.llm_model)
    console.print(table)


def current_snapshot(session) -> CorpusSnapshot | None:
    return session.scalar(
        select(CorpusSnapshot).where(CorpusSnapshot.slug == "esocial-s1.3-snapshot-001")
    )


@corpus_app.command("init")
def corpus_init() -> None:
    with session_factory()() as session:
        snapshot = current_snapshot(session)
        if snapshot:
            console.print(f"Snapshot já existe: {snapshot.slug}")
            return
        snapshot = CorpusSnapshot(
            id=str(uuid.uuid4()),
            slug="esocial-s1.3-snapshot-001",
            created_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)
        session.commit()
        console.print(f"Snapshot criado: {snapshot.slug}")


@corpus_app.command("status")
def corpus_status() -> None:
    with session_factory()() as session:
        snapshot = current_snapshot(session)
        if not snapshot:
            console.print("Nenhum snapshot inicializado. Execute: esocial corpus init")
            raise typer.Exit(code=1)
        console.print(f"Snapshot: {snapshot.slug}")
        console.print(f"Status: {'FROZEN' if snapshot.frozen_at else 'DRAFT'}")
        console.print(f"Membros: {len(snapshot.members)}")
        if snapshot.manifest_sha256:
            console.print(f"Manifest SHA-256: {snapshot.manifest_sha256}")


@corpus_app.command("verify")
def corpus_verify() -> None:
    with session_factory()() as session:
        snapshot = current_snapshot(session)
        if not snapshot:
            console.print("INVALID: snapshot não inicializado")
            raise typer.Exit(code=1)
        errors = verify_snapshot(snapshot)
        if errors:
            console.print("INVALID")
            for error in errors:
                console.print(f"- {error}")
            raise typer.Exit(code=1)
        console.print(f"VALID: {snapshot.slug}")


@corpus_app.command("freeze")
def corpus_freeze() -> None:
    with session_factory()() as session:
        snapshot = current_snapshot(session)
        if not snapshot:
            console.print("Não há snapshot para congelar")
            raise typer.Exit(code=1)
        try:
            digest = freeze_snapshot(session, snapshot)
        except ValueError as error:
            console.print(f"Freeze recusado: {error}")
            raise typer.Exit(code=1) from error
        console.print(f"Snapshot congelado: {snapshot.slug}")
        console.print(f"Manifest SHA-256: {digest}")


@artifact_app.command("import")
def artifact_import(
    role: str = typer.Option(..., help="ArtifactRole controlado."),
    file: Path = typer.Option(..., exists=True, dir_okay=False),
    official_url: str = typer.Option(...),
    version_label: str = typer.Option(...),
    title: str = typer.Option(...),
    family: str = typer.Option(..., help="DocumentFamily: MOS, LAYOUT ou XSD."),
) -> None:
    """Importa um arquivo fornecido manualmente sem alterar snapshot congelado."""
    filename = file.name
    relative = f"{uuid.uuid4()}-{filename}"
    destination = storage_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file, destination)
    with session_factory()() as session:
        snapshot = current_snapshot(session)
        if not snapshot:
            console.print(
                "Inicialize o snapshot antes da importação: esocial corpus init"
            )
            raise typer.Exit(code=1)
        if snapshot.frozen_at:
            console.print(
                "Importação recusada: snapshot congelado; crie outro snapshot"
            )
            raise typer.Exit(code=1)
        version = DocumentVersion(
            id=str(uuid.uuid4()),
            document_family=family,
            version_label=version_label,
            title=title,
            publisher="gov.br",
        )
        artifact = DocumentArtifact(
            id=str(uuid.uuid4()),
            document_version=version,
            artifact_role=role,
            official_url=official_url,
            original_filename=filename,
            storage_path=relative,
            sha256=sha256_file(destination),
            size_bytes=destination.stat().st_size,
            retrieved_at=datetime.now(timezone.utc),
            capture_method="manual_import",
        )
        session.add(version)
        session.flush()
        if filename.lower().endswith(".zip"):
            inventory_zip(artifact, session)
        session.add(
            SnapshotMember(
                id=str(uuid.uuid4()),
                snapshot_id=snapshot.id,
                artifact_role=role,
                document_version_id=version.id,
            )
        )
        session.commit()
    console.print(f"Artefato importado: {role} ({artifact.sha256})")


@build_app.command("create")
def build_create(
    snapshot: str = typer.Option(...),
    parser_revision: str = typer.Option(...),
    parser_config: Path | None = typer.Option(None, exists=True, dir_okay=False),
) -> None:
    import json

    config = json.loads(parser_config.read_text()) if parser_config else {}
    with session_factory()() as session:
        try:
            build = create_build(session, snapshot, parser_revision, config)
        except ValueError as error:
            console.print(f"Build recusado: {error}")
            raise typer.Exit(code=1) from error
    console.print(f"Build: {build.id}")
    console.print(f"Digest: {build.build_digest}")


@build_app.command("status")
def build_status(snapshot: str = typer.Option(...)) -> None:
    with session_factory()() as session:
        builds = session.scalars(
            select(CorpusBuild)
            .join(CorpusBuild.snapshot)
            .where(CorpusBuild.snapshot.has(slug=snapshot))
        ).all()
        if not builds:
            console.print("Nenhum build encontrado")
            raise typer.Exit(code=1)
        for build in builds:
            console.print(f"{build.id} {build.status} {build.build_digest}")


def resolve_build(session, value: str) -> CorpusBuild | None:
    return session.scalar(
        select(CorpusBuild).where(
            (CorpusBuild.id == value) | (CorpusBuild.build_digest == value)
        )
    )


@mos_app.command("parse")
def mos_parse(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target_build = resolve_build(session, build)
        if not target_build:
            console.print("Build não encontrado")
            raise typer.Exit(code=1)
        artifact = session.scalar(
            select(DocumentArtifact).where(
                DocumentArtifact.document_version_id.in_(
                    select(SnapshotMember.document_version_id).where(
                        SnapshotMember.snapshot_id == target_build.corpus_snapshot_id
                    )
                ),
                DocumentArtifact.artifact_role == "MOS_MAIN",
            )
        )
        version = (
            session.get(DocumentVersion, artifact.document_version_id)
            if artifact
            else None
        )
        if not artifact or not version:
            console.print("MOS_MAIN não encontrado no snapshot do build")
            raise typer.Exit(code=1)
        from .corpus import storage_root

        pages = PdfTextExtractor().extract(storage_root() / artifact.storage_path).pages
        result = parse_mos_text("\n".join(page.text for page in pages))
        try:
            document, created = materialize_mos(
                session, target_build, version, artifact, result
            )
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na materialização: {error}")
            raise typer.Exit(code=1) from error
        console.print(
            f"MOS {'materializado' if created else 'já materializado'}: {document.id}"
        )
        console.print(
            f"Eventos: {len(result.events)} | Warnings: {len(result.diagnostics)}"
        )


@mos_app.command("status")
def mos_status(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target_build = resolve_build(session, build)
        if not target_build:
            console.print("Build não encontrado")
            raise typer.Exit(code=1)
        documents = session.scalars(
            select(MosDocument).where(MosDocument.corpus_build_id == target_build.id)
        ).all()
        console.print(f"Build: {target_build.id}")
        console.print(f"Materializado: {'sim' if documents else 'não'}")


@layout_app.command("parse")
def layout_parse(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target_build = resolve_build(session, build)
        if not target_build:
            console.print("Build não encontrado")
            raise typer.Exit(code=1)
        artifact = session.scalar(
            select(DocumentArtifact).where(
                DocumentArtifact.artifact_role == "LAYOUT_MAIN",
                DocumentArtifact.document_version_id.in_(
                    select(SnapshotMember.document_version_id).where(
                        SnapshotMember.snapshot_id == target_build.corpus_snapshot_id
                    )
                ),
            )
        )
        version = (
            session.get(DocumentVersion, artifact.document_version_id)
            if artifact
            else None
        )
        if not artifact or not version:
            console.print("LAYOUT_MAIN não encontrado no snapshot do build")
            raise typer.Exit(code=1)
        html = (storage_root() / artifact.storage_path).read_text()
        result = parse_layout_html(html)
        try:
            document, created = materialize_layout(
                session, target_build, version, artifact, result
            )
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na materialização: {error}")
            raise typer.Exit(code=1) from error
        status = "materializado" if created else "já materializado"
        console.print(f"Leiaute {status}: {document.id}")
        console.print(
            f"Eventos: {len(result.events)} | Referências: {len(result.references)}"
        )


@layout_app.command("status")
def layout_status(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target_build = resolve_build(session, build)
        if not target_build:
            console.print("Build não encontrado")
            raise typer.Exit(code=1)
        count = session.scalar(
            select(func.count())
            .select_from(LayoutDocument)
            .where(LayoutDocument.corpus_build_id == target_build.id)
        )
        console.print(f"Build: {target_build.id}")
        console.print(f"Materializado: {'sim' if count else 'não'}")


@xsd_app.command("parse")
def xsd_parse(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            console.print("Build não encontrado")
            raise typer.Exit(code=1)
        artifact = session.scalar(
            select(DocumentArtifact).where(
                DocumentArtifact.artifact_role == "XSD_PACKAGE",
                DocumentArtifact.document_version_id.in_(
                    select(SnapshotMember.document_version_id).where(
                        SnapshotMember.snapshot_id == target.corpus_snapshot_id
                    )
                ),
            )
        )
        version = (
            session.get(DocumentVersion, artifact.document_version_id)
            if artifact
            else None
        )
        if not artifact or not version:
            console.print("XSD_PACKAGE não encontrado no snapshot")
            raise typer.Exit(code=1)
        try:
            doc = parse_and_materialize_xsd(session, target, version, artifact)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha no parse XSD: {error}")
            raise typer.Exit(code=1) from error
        console.print(f"XSD materializado: {doc.id}")


@xsd_app.command("status")
def xsd_status(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        doc = session.scalar(
            select(XsdPackageDocument).where(
                XsdPackageDocument.corpus_build_id == target.id
            )
        )
        console.print(f"Build: {target.id}")
        console.print(f"Package: {'sim' if doc else 'não'}")
        if doc:
            for label, model in (
                ("Schemas", XsdEventSchema),
                ("Shared types", XsdSharedType),
                ("Elements", XsdElement),
                ("Enumerations", XsdEnumeration),
            ):
                console.print(
                    f"{label}: "
                    f"{session.scalar(select(func.count()).select_from(model)) or 0}"
                )


@facts_app.command("build")
def facts_build(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        try:
            build_facts(session, target)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na materialização de fatos: {error}")
            raise typer.Exit(code=1) from error
        console.print(f"Fatos materializados para build {target.id}")


@facts_app.command("status")
def facts_status(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        for label, model in (
            ("SourceFacts", SourceFact),
            ("ReferenceResolutions", ReferenceResolution),
            ("EntityRelations", EntityRelation),
            ("ResolvedFacts", ResolvedFact),
        ):
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.corpus_build_id == target.id)
                )
                or 0
            )
            console.print(f"{label}: {count}")


@facts_app.command("resolve")
def facts_resolve(
    build: str = typer.Option(..., "--build"),
    fact_type: str = typer.Option(..., "--fact-type"),
    subject_kind: str = typer.Option(..., "--subject-kind"),
    subject_key: str = typer.Option(..., "--subject-key"),
    source: str = typer.Option(..., "--source"),
    evidence_set: str | None = typer.Option(None, "--evidence-set"),
) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        evidence = session.get(EvidenceSet, evidence_set) if evidence_set else None
        if not target or (evidence_set and not evidence):
            raise typer.Exit(code=1)
        try:
            request, _ = requested_fact(
                session, target, fact_type, subject_kind, subject_key
            )
            resolution, _ = resolve_requested_fact(session, request, source, evidence)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na resolução: {error}")
            raise typer.Exit(code=1) from error
        console.print_json(
            json.dumps(
                {
                    "requested_fact_id": request.id,
                    "resolution_id": resolution.id,
                    "runtime_status": resolution.runtime_status,
                    "resolved_value": resolution.resolved_value,
                },
                ensure_ascii=False,
            )
        )


@facts_app.command("resolution-show")
def facts_resolution_show(resolution: str = typer.Option(..., "--resolution")) -> None:
    with session_factory()() as session:
        item = session.get(FactResolution, resolution)
        if not item:
            raise typer.Exit(code=1)
        supports = session.scalars(
            select(FactResolutionSupport)
            .where(FactResolutionSupport.fact_resolution_id == item.id)
            .order_by(FactResolutionSupport.support_order)
        ).all()
        request = session.get(RequestedFact, item.requested_fact_id)
        console.print_json(
            json.dumps(
                {
                    "requested_fact": request.request_payload,
                    "source": item.document_family,
                    "runtime_status": item.runtime_status,
                    "resolved_value": item.resolved_value,
                    "strategy": item.resolution_strategy,
                    "reason": item.reason_code,
                    "evidence_set_id": item.evidence_set_id,
                    "provenance": item.provenance,
                    "supports": [
                        {
                            "evidence_unit_id": support.evidence_unit_id,
                            "source_fact_id": support.source_fact_id,
                            "resolved_fact_id": support.resolved_fact_id,
                        }
                        for support in supports
                    ],
                },
                ensure_ascii=False,
            )
        )


@search_app.command("build")
def search_build(
    build: str = typer.Option(..., "--build"),
    profile: str = typer.Option(..., "--profile"),
) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        try:
            projection, created = materialize_projection(session, target, profile)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na projeção: {error}")
            raise typer.Exit(code=1) from error
        console.print(
            f"Projeção {'criada' if created else 'existente'}: {projection.id}"
        )


@search_app.command("query")
def search_query(
    projection: str = typer.Option(..., "--projection"),
    query: str = typer.Option(..., "--query"),
) -> None:
    with session_factory()() as session:
        item = session.get(SearchProjection, projection)
        if not item:
            raise typer.Exit(code=1)
        for row in search(session, item, query):
            console.print(
                f"{row['score']:.4f} {row['source_local_stable_path']} {row['title']}"
            )


@search_app.command("status")
def search_status(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        for projection in session.scalars(
            select(SearchProjection).where(
                SearchProjection.corpus_build_id == target.id
            )
        ).all():
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(SearchUnit)
                    .where(SearchUnit.search_projection_id == projection.id)
                )
                or 0
            )
            console.print(f"{projection.profile}: {count}")


@evidence_app.command("assemble")
def evidence_assemble(
    projection: str = typer.Option(..., "--projection"),
    query: str = typer.Option(..., "--query"),
    top_k: int = typer.Option(5, "--top-k"),
) -> None:
    with session_factory()() as session:
        item = session.get(SearchProjection, projection)
        if not item:
            raise typer.Exit(code=1)
        build = session.get(CorpusBuild, item.corpus_build_id)
        try:
            result, created = assemble_evidence(session, build, item, query, top_k)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na evidência: {error}")
            raise typer.Exit(code=1) from error
        console.print(
            f"EvidenceSet {'criado' if created else 'existente'}: {result.id}"
        )


@evidence_app.command("status")
def evidence_status(build: str = typer.Option(..., "--build")) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        for label, model in (
            ("EvidenceSets", EvidenceSet),
            ("EvidenceUnits", EvidenceUnit),
            ("EvidenceItems", EvidenceSetItem),
        ):
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(model)
                    .join(
                        EvidenceSet, EvidenceSet.id == EvidenceSetItem.evidence_set_id
                    )
                    if model is EvidenceSetItem
                    else select(func.count())
                    .select_from(model)
                    .where(model.corpus_build_id == target.id)
                )
                or 0
            )
            console.print(f"{label}: {count}")


@eval_app.command("retrieval")
def eval_retrieval(
    build: str = typer.Option(..., "--build"),
    dataset: Path = typer.Option(
        Path("evaluation/dev/retrieval_evidence_v1.json"), "--dataset"
    ),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        try:
            report = evaluate_retrieval_evidence(session, target, dataset)
            if output:
                write_report(report, output)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na avaliação: {error}")
            raise typer.Exit(code=1) from error
        console.print_json(json.dumps(report, ensure_ascii=False, sort_keys=True))


@eval_app.command("facts")
def eval_facts(
    build: str = typer.Option(..., "--build"),
    dataset: Path = typer.Option(
        Path("evaluation/dev/fact_resolution_status_v1.json"), "--dataset"
    ),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    with session_factory()() as session:
        target = resolve_build(session, build)
        if not target:
            raise typer.Exit(code=1)
        try:
            report = evaluate_fact_resolution_status(session, target, dataset)
            if output:
                write_report(report, output)
            session.commit()
        except Exception as error:
            session.rollback()
            console.print(f"Falha na avaliação de fatos: {error}")
            raise typer.Exit(code=1) from error
        console.print_json(json.dumps(report, ensure_ascii=False, sort_keys=True))
