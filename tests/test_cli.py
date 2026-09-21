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
    assert runner.invoke(app, ["complete", "--help"]).exit_code == 0
    assert runner.invoke(app, ["complete", "generate", "--help"]).exit_code == 0
    assert runner.invoke(app, ["complete", "show", "--help"]).exit_code == 0


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


def test_complete_cli_generate_and_show_use_structured_boundary(
    monkeypatch, tmp_path
) -> None:
    class SessionContext:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def rollback(self):
            pass

    class Factory:
        def __call__(self):
            return SessionContext()

    class Build:
        build_digest = "b" * 64

    class Run:
        run_key = "run-key"

    class Result:
        run = Run()
        payload = {"run_key": run.run_key, "status": "ANSWERED"}

    monkeypatch.setattr(cli, "session_factory", lambda: Factory())
    monkeypatch.setattr(cli, "resolve_build", lambda _session, _value: Build())
    monkeypatch.setattr(cli, "load_complete_input", lambda _path: {"question": "Q"})
    monkeypatch.setattr(
        cli,
        "execute_complete",
        lambda *_args, **_kwargs: Result(),
    )
    input_file = tmp_path / "complete.json"
    input_file.write_text("{}", encoding="utf-8")
    generated = runner.invoke(
        app, ["complete", "generate", "--build", "build", "--input", str(input_file)]
    )
    assert generated.exit_code == 0, generated.stdout
    assert '"run_key": "run-key"' in generated.stdout

    monkeypatch.setattr(
        cli,
        "complete_show_payload",
        lambda _session, _run: {"run_key": "run-key", "status": "ANSWERED"},
    )
    shown = runner.invoke(app, ["complete", "show", "--run", "run-key"])
    assert shown.exit_code == 0, shown.stdout
    assert '"status": "ANSWERED"' in shown.stdout


def test_complete_evaluation_cli_is_exposed() -> None:
    result = runner.invoke(app, ["eval", "complete", "--help"])
    assert result.exit_code == 0
    assert "fake" in result.stdout
    assert runner.invoke(app, ["eval", "complete-review", "--help"]).exit_code == 0
