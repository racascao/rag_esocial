from typer.testing import CliRunner

import rag_esocial.cli as cli
from rag_esocial.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Fundação" in result.stdout


def test_answer_and_llm_commands_are_exposed() -> None:
    assert runner.invoke(app, ["answer", "--help"]).exit_code == 0
    assert runner.invoke(app, ["answer", "generate", "--help"]).exit_code == 0
    assert runner.invoke(app, ["answer", "show", "--help"]).exit_code == 0
    assert runner.invoke(app, ["llm", "--help"]).exit_code == 0


def test_llm_status_cli(monkeypatch) -> None:
    class Client:
        def __init__(self, **kwargs):
            pass

        def status(self):
            return {
                "provider": "ollama",
                "base_url": "http://ollama:11434",
                "reachable": True,
                "model": "gemma4:12b",
                "model_available": True,
            }

    monkeypatch.setattr(cli, "OllamaAnswerModelClient", Client)
    result = runner.invoke(app, ["llm", "status"])
    assert result.exit_code == 0
    assert '"model_available": true' in result.stdout
