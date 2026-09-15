import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import get_settings
from .db import check_connection
from .logging_config import configure_logging

app = typer.Typer(help="Fundação CLI do assistente RAG eSocial.", no_args_is_help=True)
db_app = typer.Typer(help="Comandos de infraestrutura do banco.")
app.add_typer(db_app, name="db")
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
