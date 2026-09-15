import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from . import __version__
from .config import get_settings
from .corpus import (
    freeze_snapshot,
    inventory_zip,
    sha256_file,
    storage_root,
    verify_snapshot,
)
from .db import check_connection, session_factory
from .logging_config import configure_logging
from .models.corpus import (
    CorpusSnapshot,
    DocumentArtifact,
    DocumentVersion,
    SnapshotMember,
)

app = typer.Typer(help="Fundação CLI do assistente RAG eSocial.", no_args_is_help=True)
db_app = typer.Typer(help="Comandos de infraestrutura do banco.")
app.add_typer(db_app, name="db")
corpus_app = typer.Typer(help="Aquisição, provenance e snapshots do corpus.")
app.add_typer(corpus_app, name="corpus")
artifact_app = typer.Typer(help="Importação manual genérica de artefatos oficiais.")
corpus_app.add_typer(artifact_app, name="artifact")
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
