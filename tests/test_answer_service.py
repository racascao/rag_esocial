import json
from urllib.error import URLError

import pytest

import rag_esocial.answer_service as answer_service
from rag_esocial.answer_service import ANSWER_JSON_SCHEMA, OllamaAnswerModelClient


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.payload


def test_ollama_generate_uses_native_schema_and_captures_metadata(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response(
            {
                "model": "gemma4:12b",
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 20,
                "message": {
                    "content": json.dumps(
                        {
                            "claims": [
                                {
                                    "claim_id": "C1",
                                    "text": "texto",
                                    "fact_resolution_refs": ["F1"],
                                    "evidence_refs": ["E1"],
                                }
                            ]
                        }
                    )
                },
            }
        )

    monkeypatch.setattr(answer_service, "urlopen", fake_urlopen)
    client = OllamaAnswerModelClient()
    result = client.generate("contexto")
    payload = json.loads(captured["request"].data)
    assert captured["request"].full_url == "http://ollama:11434/api/chat"
    assert payload["format"] == ANSWER_JSON_SCHEMA
    assert payload["think"] is False
    assert payload["options"]["temperature"] == 0
    assert result["claims"][0]["fact_resolution_refs"] == ["F1"]
    assert client.last_metadata["eval_count"] == 20
    assert client.call_count == 1


def test_ollama_generate_converts_transport_and_json_errors(monkeypatch):
    monkeypatch.setattr(
        answer_service,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(RuntimeError, match="OLLAMA_ERROR"):
        OllamaAnswerModelClient().generate("contexto")


def test_ollama_status_checks_runtime_and_exact_model(monkeypatch):
    responses = iter(
        [
            Response({"version": "0.11.10"}),
            Response({"models": [{"name": "gemma4:12b"}]}),
        ]
    )
    monkeypatch.setattr(
        answer_service, "urlopen", lambda *args, **kwargs: next(responses)
    )
    status = OllamaAnswerModelClient().status()
    assert status["reachable"] is True
    assert status["runtime_version"] == "0.11.10"
    assert status["model_available"] is True


def test_ollama_status_reports_unreachable_without_raising(monkeypatch):
    monkeypatch.setattr(
        answer_service,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    status = OllamaAnswerModelClient().status()
    assert status["reachable"] is False
    assert status["model_available"] is False
