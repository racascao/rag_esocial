import hashlib
import json
import uuid
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy import select

from .identity import canonical_json, parser_config_digest
from .models.answer import (
    AnswerCitation,
    AnswerClaim,
    AnswerClaimFact,
    AnswerRequest,
    AnswerRequestFactResolution,
    AnswerRun,
    AnswerRunStatus,
)
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.corpus import DocumentFamily
from .models.evidence import EvidenceSetItem, EvidenceUnit
from .models.fact_resolution import (
    FactResolution,
    FactResolutionSupport,
    RequestedFact,
    RuntimeStatus,
)

CONTRACT_REVISION = "answer-contract-v1"
PROMPT_REVISION = "answer-prompt-v1"
MODEL_CONFIG = {
    "provider": "ollama",
    "temperature": 0,
    "seed": 42,
    "num_ctx": 8192,
    "num_predict": 256,
    "timeout_seconds": 300,
}
MAX_CLAIMS = 32
MAX_CLAIM_TEXT_LENGTH = 4000
MAX_REFS_PER_CLAIM = 32
ANSWER_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_CLAIMS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "claim_id",
                    "text",
                    "fact_resolution_refs",
                    "evidence_refs",
                ],
                "properties": {
                    "claim_id": {"type": "string", "minLength": 1},
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_CLAIM_TEXT_LENGTH,
                    },
                    "fact_resolution_refs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_REFS_PER_CLAIM,
                        "items": {"type": "string"},
                    },
                    "evidence_refs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_REFS_PER_CLAIM,
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


class FakeAnswerModelClient:
    """Deterministic provider boundary used only by tests and benchmark dry-runs."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.call_count = 0
        self.contexts = []

    def generate(self, context):
        self.call_count += 1
        self.contexts.append(context)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class OllamaAnswerModelClient:
    def __init__(self, base_url="http://ollama:11434", model="gemma4:12b"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.call_count = 0
        self.last_metadata = {}
        self.last_invalid_content = None

    def status(self):
        try:
            with urlopen(f"{self.base_url}/api/version", timeout=10) as response:
                version = json.loads(response.read()).get("version")
            with urlopen(f"{self.base_url}/api/tags", timeout=10) as response:
                payload = json.loads(response.read())
                models = [item["name"] for item in payload["models"]]
        except (URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
            return {
                "provider": "ollama",
                "base_url": self.base_url,
                "reachable": False,
                "model": self.model,
                "model_available": False,
                "error": str(error),
            }
        return {
            "provider": "ollama",
            "base_url": self.base_url,
            "reachable": True,
            "runtime_version": version,
            "model": self.model,
            "model_available": self.model in models,
            "models": sorted(models),
        }

    def generate(self, context):
        self.call_count += 1
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [{"role": "user", "content": context}],
            "format": ANSWER_JSON_SCHEMA,
            "options": {
                key: value
                for key, value in MODEL_CONFIG.items()
                if key not in {"provider", "timeout_seconds"}
            },
        }
        try:
            request = Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=MODEL_CONFIG["timeout_seconds"]) as response:
                envelope = json.loads(response.read())
                self.last_metadata = {
                    key: envelope[key]
                    for key in (
                        "model",
                        "created_at",
                        "done_reason",
                        "total_duration",
                        "load_duration",
                        "prompt_eval_count",
                        "prompt_eval_duration",
                        "eval_count",
                        "eval_duration",
                    )
                    if key in envelope
                }
                content = envelope["message"]["content"]
        except (
            URLError,
            TimeoutError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(f"OLLAMA_ERROR:{error}") from error
        try:
            return json.loads(content)
        except (TypeError, json.JSONDecodeError):
            self.last_invalid_content = content
            return content


def create_answer_request(
    session, build, source, question, resolutions, model_id="gemma4:12b", config=None
):
    if source not in {item.value for item in DocumentFamily}:
        raise ValueError("invalid document family")
    if not question.strip() or not resolutions:
        raise ValueError("question and fact resolutions are required")
    for resolution in resolutions:
        requested = session.get(RequestedFact, resolution.requested_fact_id)
        if (
            not requested
            or requested.corpus_build_id != build.id
            or resolution.document_family != source
        ):
            raise ValueError("fact resolution outside build/source")
    config = config or MODEL_CONFIG
    ids = sorted(item.id for item in resolutions)
    digest = hashlib.sha256(
        canonical_json(
            {
                "source": source,
                "question": question,
                "resolutions": ids,
                "contract": CONTRACT_REVISION,
                "prompt": PROMPT_REVISION,
                "model": model_id,
                "config": config,
            }
        ).encode()
    ).hexdigest()
    item = session.scalar(
        select(AnswerRequest).where(
            AnswerRequest.corpus_build_id == build.id,
            AnswerRequest.request_digest == digest,
        )
    )
    if item:
        return item, False
    item = AnswerRequest(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        document_family=source,
        question=question,
        question_digest=hashlib.sha256(question.encode()).hexdigest(),
        answer_contract_revision=CONTRACT_REVISION,
        prompt_revision=PROMPT_REVISION,
        model_id=model_id,
        model_config=config,
        model_config_digest=parser_config_digest(config),
        request_digest=digest,
        created_at=datetime.now(timezone.utc),
    )
    session.add(item)
    session.flush()
    for order, resolution in enumerate(sorted(resolutions, key=lambda value: value.id)):
        session.add(
            AnswerRequestFactResolution(
                answer_request_id=item.id,
                fact_resolution_id=resolution.id,
                request_order=order,
            )
        )
    session.flush()
    return item, True


def preflight_answer(session, request):
    resolutions = session.scalars(
        select(FactResolution)
        .join(AnswerRequestFactResolution)
        .where(AnswerRequestFactResolution.answer_request_id == request.id)
        .order_by(AnswerRequestFactResolution.request_order)
    ).all()
    if not resolutions:
        raise ValueError("answer request has no fact resolutions")
    for resolution in resolutions:
        requested = session.get(RequestedFact, resolution.requested_fact_id)
        if (
            not requested
            or requested.corpus_build_id != request.corpus_build_id
            or resolution.document_family != request.document_family
        ):
            raise ValueError("answer request crosses build/source boundary")
    resolved = [
        item
        for item in resolutions
        if item.runtime_status == RuntimeStatus.RESOLVED.value
    ]
    support_rows = (
        session.execute(
            select(FactResolutionSupport, EvidenceUnit)
            .join(
                EvidenceUnit, EvidenceUnit.id == FactResolutionSupport.evidence_unit_id
            )
            .where(
                FactResolutionSupport.fact_resolution_id.in_(
                    [item.id for item in resolved]
                )
            )
            .order_by(
                FactResolutionSupport.fact_resolution_id,
                FactResolutionSupport.support_order,
            )
        ).all()
        if resolved
        else []
    )
    resolution_by_id = {item.id: item for item in resolved}
    authorized_rows = []
    for support, unit in support_rows:
        resolution = resolution_by_id[support.fact_resolution_id]
        target = session.get(CitationTarget, unit.citation_target_id)
        membership = session.get(
            CorpusBuildCitationTarget,
            {
                "build_id": request.corpus_build_id,
                "citation_target_id": unit.citation_target_id,
            },
        )
        evidence_membership = session.get(
            EvidenceSetItem,
            {
                "evidence_set_id": resolution.evidence_set_id,
                "evidence_unit_id": unit.id,
            },
        )
        if (
            unit.corpus_build_id != request.corpus_build_id
            or unit.document_family != request.document_family
            or not target
            or target.document_family != request.document_family
            or not membership
            or not evidence_membership
        ):
            raise ValueError("evidence outside authorized build/source/support chain")
        authorized_rows.append((support, unit))
    support_rows = authorized_rows
    supported_resolution_ids = {
        support.fact_resolution_id for support, _ in support_rows
    }
    resolved = [item for item in resolved if item.id in supported_resolution_ids]
    fact_map = {f"F{index}": item for index, item in enumerate(resolved, 1)}
    unit_by_id = {}
    for support, unit in support_rows:
        if support.fact_resolution_id not in supported_resolution_ids:
            continue
        unit_by_id.setdefault(unit.id, unit)
    unit_map = {
        f"E{index}": unit
        for index, unit in enumerate(
            sorted(
                unit_by_id.values(), key=lambda value: value.source_local_stable_path
            ),
            1,
        )
    }
    support_pairs = {
        (support.fact_resolution_id, support.evidence_unit_id)
        for support, _ in support_rows
    }
    negatives = [
        item for item in resolutions if item.id not in {x.id for x in resolved}
    ]
    return resolutions, fact_map, unit_map, support_pairs, negatives


def validate_answer_contract(output, fact_map, unit_map, support_pairs):
    if not isinstance(output, dict) or set(output) != {"claims"}:
        return ["INVALID_SCHEMA"]
    claims = output["claims"]
    if not isinstance(claims, list) or not claims or len(claims) > MAX_CLAIMS:
        return ["INVALID_SCHEMA"]
    errors = []
    claim_ids = []
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("INVALID_CLAIM")
            continue
        if set(claim) != {
            "claim_id",
            "text",
            "fact_resolution_refs",
            "evidence_refs",
        }:
            errors.append("INVALID_CLAIM_SCHEMA")
        claim_id = claim.get("claim_id")
        text = claim.get("text")
        fact_refs = claim.get("fact_resolution_refs")
        evidence_refs = claim.get("evidence_refs")
        if not isinstance(claim_id, str) or not claim_id.strip():
            errors.append("INVALID_CLAIM_ID")
        else:
            claim_ids.append(claim_id)
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > MAX_CLAIM_TEXT_LENGTH
        ):
            errors.append("EMPTY_CLAIM")
        if (
            not isinstance(fact_refs, list)
            or not fact_refs
            or len(fact_refs) > MAX_REFS_PER_CLAIM
            or any(not isinstance(ref, str) for ref in fact_refs)
        ):
            errors.append("CLAIM_WITHOUT_FACT")
            continue
        if (
            not isinstance(evidence_refs, list)
            or not evidence_refs
            or len(evidence_refs) > MAX_REFS_PER_CLAIM
            or any(not isinstance(ref, str) for ref in evidence_refs)
        ):
            errors.append("CLAIM_WITHOUT_CITATION")
            continue
        if len(fact_refs) != len(set(fact_refs)) or len(evidence_refs) != len(
            set(evidence_refs)
        ):
            errors.append("DUPLICATE_REFERENCE")
        facts = [fact_map.get(ref) for ref in fact_refs]
        units = [unit_map.get(ref) for ref in evidence_refs]
        if any(item is None for item in facts):
            errors.append("UNAUTHORIZED_FACT_REFERENCE")
            continue
        if any(item is None for item in units):
            errors.append("UNAUTHORIZED_CITATION")
            continue
        for unit in units:
            if not any((fact.id, unit.id) in support_pairs for fact in facts):
                errors.append("SUPPORT_MISMATCH")
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("DUPLICATE_CLAIM_ID")
    return sorted(set(errors))


def _limitations(negatives):
    return [
        {
            "fact_resolution_id": item.id,
            "runtime_status": item.runtime_status,
            "reason_code": item.reason_code,
        }
        for item in negatives
    ]


def render_answer(session, claims, unit_map, limitations):
    lines = []
    for claim in claims:
        labels = []
        for ref in claim["evidence_refs"]:
            unit = unit_map[ref]
            target = session.get(CitationTarget, unit.citation_target_id)
            label = target.human_label or target.source_local_stable_path
            labels.append(f"{target.document_family}: {label}")
        lines.append(f"{claim['text']} " + "".join(f"[{label}]" for label in labels))
    if limitations:
        lines.append("Limitações:")
        for item in limitations:
            lines.append(
                f"- {item['runtime_status']}: "
                f"{item['reason_code'] or 'sem detalhe adicional'}"
            )
    return "\n".join(lines)


def execute_answer(session, request, client):
    resolutions, fact_map, unit_map, support_pairs, negatives = preflight_answer(
        session, request
    )
    run = AnswerRun(
        id=str(uuid.uuid4()),
        answer_request_id=request.id,
        run_key=str(uuid.uuid4()),
        status=AnswerRunStatus.ABSTAINED.value,
        provider="ollama",
        model_id=request.model_id,
        model_config=request.model_config,
        model_config_digest=request.model_config_digest,
        provider_metadata={},
        attempt_count=0,
        raw_response=None,
        rendered_answer=None,
        validation_summary={},
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    if not fact_map:
        limitations = _limitations(negatives)
        run.rendered_answer = render_answer(session, [], {}, limitations)
        run.validation_summary = {
            "model_call_count": 0,
            "limitations": limitations,
            "errors": [],
        }
        session.flush()
        return run
    context = canonical_json(
        {
            "question": request.question,
            "source": request.document_family,
            "facts": {key: value.resolved_value for key, value in fact_map.items()},
            "evidence": {
                key: value.rendered_content for key, value in unit_map.items()
            },
            "instruction": (
                "Return only the JSON claim ledger required by the schema. Use "
                "only provided identifiers. Prefer one concise claim covering "
                "all provided facts; every claim requires fact_resolution_refs "
                "and evidence_refs. Never add outside knowledge."
            ),
        }
    )
    rejected_attempts = []
    try:
        output = client.generate(context)
        run.attempt_count = 1
        if not isinstance(output, dict) or not isinstance(output.get("claims"), list):
            rejected_attempts.append(output)
            output = client.generate(context)
            run.attempt_count = 2
    except RuntimeError as error:
        run.status = AnswerRunStatus.MODEL_ERROR.value
        run.provider_metadata = getattr(client, "last_metadata", {})
        run.validation_summary = {
            "error": str(error),
            "rejected_attempts": rejected_attempts,
        }
        session.flush()
        return run
    claims = output.get("claims") if isinstance(output, dict) else None
    if not isinstance(claims, list):
        run.status = AnswerRunStatus.MODEL_ERROR.value
        run.raw_response = output if isinstance(output, dict) else None
        run.provider_metadata = getattr(client, "last_metadata", {})
        run.validation_summary = {
            "error": "INVALID_STRUCTURED_OUTPUT",
            "rejected_attempts": rejected_attempts,
        }
        session.flush()
        return run
    errors = validate_answer_contract(output, fact_map, unit_map, support_pairs)
    if errors:
        run.status = AnswerRunStatus.VALIDATION_FAILED.value
        run.raw_response = output
        run.provider_metadata = getattr(client, "last_metadata", {})
        run.validation_summary = {
            "errors": errors,
            "rejected_attempts": rejected_attempts,
        }
        session.flush()
        return run
    run.raw_response = output
    run.provider_metadata = getattr(client, "last_metadata", {})
    run.status = (
        AnswerRunStatus.ANSWERED.value
        if not negatives
        else AnswerRunStatus.PARTIAL.value
    )
    for order, claim in enumerate(claims, 1):
        stored = AnswerClaim(
            id=str(uuid.uuid4()),
            answer_run_id=run.id,
            claim_key=claim["claim_id"],
            claim_order=order,
            text=claim["text"],
            text_sha256=hashlib.sha256(claim["text"].encode()).hexdigest(),
            validation_state="VALID",
        )
        session.add(stored)
        session.flush()
        for ref in claim["fact_resolution_refs"]:
            session.add(
                AnswerClaimFact(
                    answer_claim_id=stored.id, fact_resolution_id=fact_map[ref].id
                )
            )
        for citation_order, ref in enumerate(claim["evidence_refs"], 1):
            session.add(
                AnswerCitation(
                    answer_claim_id=stored.id,
                    evidence_unit_id=unit_map[ref].id,
                    citation_order=citation_order,
                )
            )
    limitations = _limitations(negatives)
    run.rendered_answer = render_answer(session, claims, unit_map, limitations)
    run.validation_summary = {
        "model_call_count": run.attempt_count,
        "errors": [],
        "limitations": limitations,
        "rejected_attempts": rejected_attempts,
    }
    session.flush()
    return run
