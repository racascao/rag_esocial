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
from .models.layout import LayoutDocument
from .models.mos import MosDocument
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
