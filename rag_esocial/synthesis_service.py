"""Evidence-closed synthesis for Complete Mode 9C.

The provider sees a deterministic, source-qualified factual snapshot.  Provider
text is never used to build facts, evidence, comparisons, or support links.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy import select

from .answer_service import OllamaAnswerModelClient
from .cross_source_service import aggregate_cross_source
from .identity import canonical_json, parser_config_digest
from .models.answer import AnswerCitation, AnswerClaim, AnswerClaimFact
from .models.build import CitationTarget
from .models.complete_answer import (
    CompleteAnswerCitation,
    CompleteAnswerClaim,
    CompleteAnswerClaimComparison,
    CompleteAnswerClaimFact,
    CompleteAnswerRun,
    CompleteAnswerStatus,
    CompleteRunExecutionState,
)
from .models.cross_source import CrossSourceComparison
from .models.evidence import EvidenceUnit
from .models.fact_resolution import FactResolution, FactResolutionSupport, RuntimeStatus

SYNTHESIS_CONTRACT_REVISION = "complete-answer-contract-v1"
SYNTHESIS_PROMPT_REVISION = "complete-synthesis-prompt-v1"
SYNTHESIS_RENDERER_REVISION = "complete-answer-renderer-v1"
SYNTHESIS_MODEL_CONFIG = {
    "provider": "ollama",
    "temperature": 0,
    "seed": 42,
    "num_ctx": 8192,
    "num_predict": 2048,
    "timeout_seconds": 600,
}
MAX_SYNTHESIS_CLAIMS = 32
MAX_SYNTHESIS_CLAIM_TEXT = 4000
MAX_SYNTHESIS_REFS = 32
SYNTHESIS_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_SYNTHESIS_CLAIMS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "claim_id",
                    "text",
                    "fact_refs",
                    "evidence_refs",
                    "comparison_refs",
                ],
                "properties": {
                    "claim_id": {"type": "string", "minLength": 1},
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_SYNTHESIS_CLAIM_TEXT,
                    },
                    "fact_refs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_SYNTHESIS_REFS,
                        "items": {"type": "string"},
                    },
                    "evidence_refs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_SYNTHESIS_REFS,
                        "items": {"type": "string"},
                    },
                    "comparison_refs": {
                        "type": "array",
                        "maxItems": MAX_SYNTHESIS_REFS,
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


class SynthesisError(Exception):
    pass


class SynthesisPreflightError(SynthesisError):
    pass


class SynthesisValidationError(SynthesisError):
    pass


@dataclass(frozen=True)
class CompleteSynthesisContext:
    payload: dict
    fact_map: dict
    evidence_map: dict
    comparison_map: dict
    support_pairs: frozenset
    fact_refs_by_resolution: dict
    evidence_refs_by_unit: dict
    comparison_refs_by_id: dict
    aggregation_digest: str

    def serialize(self) -> str:
        return canonical_json(self.payload)


class OllamaSynthesisModelClient(OllamaAnswerModelClient):
    """Ollama transport with the independent 9C schema/config boundary."""

    def generate(self, context):
        self.call_count += 1
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [{"role": "user", "content": context}],
            "format": SYNTHESIS_JSON_SCHEMA,
            "options": {
                key: value
                for key, value in SYNTHESIS_MODEL_CONFIG.items()
                if key not in {"provider", "timeout_seconds"}
            },
        }
        try:
            request = Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(
                request, timeout=SYNTHESIS_MODEL_CONFIG["timeout_seconds"]
            ) as response:
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
            raise RuntimeError(f"OLLAMA_SYNTHESIS_ERROR:{error}") from error
        try:
            return json.loads(content)
        except (TypeError, json.JSONDecodeError):
            self.last_invalid_content = content
            return content


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _ref_number(ref, prefix):
    return int(ref.split(prefix, 1)[1])


def _source_from_ref(ref):
    return ref.split(":", 1)[0] if ":" in ref else None


def _comparison_ref(index):
    return f"X{index + 1}"


def _build_context_payload(run, aggregation, comparisons, limitations):
    aspects = sorted(run.request.aspects, key=lambda item: item.aspect_order)
    return {
        "revision": SYNTHESIS_CONTRACT_REVISION,
        "prompt_revision": SYNTHESIS_PROMPT_REVISION,
        "aggregation_context_digest": run.context_digest,
        "build_digest": run.build.build_digest,
        "request_digest": run.request.request_digest,
        "question": run.request.question,
        "requested_aspects": [
            {
                "aspect_key": aspect.aspect_key,
                "subject_kind": aspect.subject_kind,
                "subject_key": aspect.subject_key,
                "qualifiers": aspect.qualifiers,
            }
            for aspect in aspects
        ],
        "source_coverage": aggregation["coverage"],
        "facts": aggregation["facts"],
        "evidence": aggregation["evidence"],
        "comparisons": comparisons,
        "limitations": limitations,
        "ref_maps": {
            "facts": {
                item["ref"]: {
                    "source": item["source"],
                    "evidence_refs": [],
                }
                for item in aggregation["facts"]
            },
            "evidence": {
                item["ref"]: {
                    "source": item["source"],
                    "stable_path": item["source_local_stable_path"],
                }
                for item in aggregation["evidence"]
            },
            "comparisons": {
                item["ref"]: {"key": item["key"], "kind": item["kind"]}
                for item in comparisons
            },
        },
        "rules": {
            "closed_world": True,
            "no_source_precedence": True,
            "divergence_is_metadata": True,
        },
    }


def _source_limitations(session, run, aggregation):
    limitations = []
    for coverage in aggregation["coverage"]:
        for source in coverage["sources"]:
            if source["status"] == "SOURCE_NOT_APPLICABLE":
                limitations.append(
                    {
                        "kind": "SOURCE_NOT_APPLICABLE",
                        "aspect_key": coverage["aspect_key"],
                        "source": source["source"],
                    }
                )
            for item in source.get("inputs", []):
                if item.get("status") in {
                    RuntimeStatus.ASPECT_NOT_COVERED.value,
                    RuntimeStatus.NO_RELEVANT_EVIDENCE.value,
                    RuntimeStatus.UNSUPPORTED.value,
                }:
                    limitations.append(
                        {
                            "kind": item["status"],
                            "aspect_key": coverage["aspect_key"],
                            "source": source["source"],
                            "reason_code": item.get("reason_code"),
                        }
                    )
    for source_run in run.source_runs:
        if source_run.answer_run and source_run.answer_run.status in {
            "MODEL_ERROR",
            "VALIDATION_FAILED",
        }:
            limitations.append(
                {
                    "kind": source_run.answer_run.status,
                    "source": source_run.document_family,
                    "reason_code": "SOURCE_OUTPUT_EXCLUDED",
                }
            )
    return sorted(
        limitations,
        key=lambda item: canonical_json(item),
    )


def build_synthesis_context(session, run: CompleteAnswerRun):
    if run.execution_state != CompleteRunExecutionState.RUNNING.value:
        raise SynthesisPreflightError("complete run is not running")
    aggregation, aggregation_digest = aggregate_cross_source(session, run)
    if run.context_digest != aggregation_digest:
        raise SynthesisPreflightError("aggregation context digest mismatch")
    comparison_rows = session.scalars(
        select(CrossSourceComparison)
        .where(CrossSourceComparison.complete_answer_run_id == run.id)
        .order_by(CrossSourceComparison.comparison_order)
    ).all()
    comparison_ref_by_id = {
        row.id: _comparison_ref(index) for index, row in enumerate(comparison_rows)
    }
    comparison_map = {
        ref: row
        for row, ref in ((row, comparison_ref_by_id[row.id]) for row in comparison_rows)
    }
    fact_ref_by_resolution = {}
    evidence_ref_by_unit = {}
    for row in comparison_rows:
        for member in sorted(row.members, key=lambda item: item.member_order):
            fact_ref_by_resolution[member.fact_resolution_id] = member.fact_ref
            supports = session.scalars(
                select(FactResolutionSupport).where(
                    FactResolutionSupport.fact_resolution_id
                    == member.fact_resolution_id
                ).order_by(
                    FactResolutionSupport.support_order, FactResolutionSupport.id
                )
            ).all()
            for support, evidence_ref in zip(supports, member.evidence_refs):
                evidence_ref_by_unit[support.evidence_unit_id] = evidence_ref
    # Support rows are the authority for evidence/fact pairing.

    support_pairs = set()
    for resolution_id, fact_ref in fact_ref_by_resolution.items():
        for support in session.scalars(
            select(FactResolutionSupport).where(
                FactResolutionSupport.fact_resolution_id == resolution_id
            ).order_by(FactResolutionSupport.support_order, FactResolutionSupport.id)
        ):
            evidence_ref = evidence_ref_by_unit.get(support.evidence_unit_id)
            if evidence_ref:
                support_pairs.add((fact_ref, evidence_ref))
    fact_map = {}
    evidence_map = {}
    for item in aggregation["facts"]:
        resolution_id = next(
            key for key, value in fact_ref_by_resolution.items() if value == item["ref"]
        )
        fact_map[item["ref"]] = session.get(FactResolution, resolution_id)
    for item in aggregation["evidence"]:
        unit_id = next(
            key for key, value in evidence_ref_by_unit.items() if value == item["ref"]
        )
        evidence_map[item["ref"]] = session.get(EvidenceUnit, unit_id)
    limitations = _source_limitations(session, run, aggregation)
    public_comparisons = [
        {
            **item,
            "ref": comparison_ref_by_id[row.id],
        }
        for row, item in zip(comparison_rows, aggregation["comparisons"])
    ]
    payload = _build_context_payload(run, aggregation, public_comparisons, limitations)
    for fact in payload["facts"]:
        fact["evidence_refs"] = sorted(
            ref for fact_ref, ref in support_pairs if fact_ref == fact["ref"]
        )
        payload["ref_maps"]["facts"][fact["ref"]]["evidence_refs"] = fact[
            "evidence_refs"
        ]
    return CompleteSynthesisContext(
        payload=payload,
        fact_map=fact_map,
        evidence_map=evidence_map,
        comparison_map=comparison_map,
        support_pairs=frozenset(support_pairs),
        fact_refs_by_resolution=fact_ref_by_resolution,
        evidence_refs_by_unit=evidence_ref_by_unit,
        comparison_refs_by_id=comparison_ref_by_id,
        aggregation_digest=aggregation_digest,
    )


def _schema_errors(output):
    if not isinstance(output, dict) or set(output) != {"claims"}:
        return ["INVALID_SCHEMA"]
    claims = output["claims"]
    if not isinstance(claims, list) or not claims or len(claims) > MAX_SYNTHESIS_CLAIMS:
        return ["INVALID_SCHEMA"]
    errors = []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {
            "claim_id",
            "text",
            "fact_refs",
            "evidence_refs",
            "comparison_refs",
        }:
            errors.append("INVALID_CLAIM_SCHEMA")
            continue
        if not isinstance(claim["claim_id"], str) or not claim["claim_id"].strip():
            errors.append("INVALID_CLAIM_ID")
        if not isinstance(claim["text"], str) or not claim["text"].strip():
            errors.append("EMPTY_CLAIM")
        if len(claim.get("text", "")) > MAX_SYNTHESIS_CLAIM_TEXT:
            errors.append("CLAIM_TOO_LONG")
        for field, required in (("fact_refs", True), ("evidence_refs", True)):
            refs = claim.get(field)
            if not isinstance(refs, list) or (required and not refs):
                errors.append(f"CLAIM_WITHOUT_{field.upper()}")
            elif len(refs) > MAX_SYNTHESIS_REFS or any(
                not isinstance(ref, str) for ref in refs
            ):
                errors.append("INVALID_REFERENCE_LIST")
        refs = claim.get("comparison_refs")
        if not isinstance(refs, list) or len(refs) > MAX_SYNTHESIS_REFS:
            errors.append("INVALID_COMPARISON_LIST")
    ids = [claim.get("claim_id") for claim in claims if isinstance(claim, dict)]
    if ids != [f"C{index}" for index in range(1, len(ids) + 1)]:
        errors.append("NON_SEQUENTIAL_CLAIM_IDS")
    return sorted(set(errors))


def validate_synthesis_output(output, context: CompleteSynthesisContext):
    errors = _schema_errors(output)
    if errors:
        return errors
    errors = []
    for claim in output["claims"]:
        facts = claim["fact_refs"]
        evidence = claim["evidence_refs"]
        comparisons = claim["comparison_refs"]
        if len(facts) != len(set(facts)) or len(evidence) != len(set(evidence)):
            errors.append("DUPLICATE_REFERENCE")
        if len(comparisons) != len(set(comparisons)):
            errors.append("DUPLICATE_COMPARISON_REFERENCE")
        if any(ref not in context.fact_map for ref in facts):
            errors.append("UNAUTHORIZED_FACT_REFERENCE")
            continue
        if any(ref not in context.evidence_map for ref in evidence):
            errors.append("UNAUTHORIZED_EVIDENCE_REFERENCE")
            continue
        if any(ref not in context.comparison_map for ref in comparisons):
            errors.append("UNAUTHORIZED_COMPARISON_REFERENCE")
            continue
        if any(
            not any(
                (fact_ref, evidence_ref) in context.support_pairs
                for evidence_ref in evidence
            )
            for fact_ref in facts
        ):
            errors.append("SUPPORT_MISMATCH")
        families = {_source_from_ref(ref) for ref in facts}
        if len(families) > 1 and not comparisons:
            errors.append("MISSING_COMPARISON_REFERENCE")
        for comparison_ref in comparisons:
            comparison = context.comparison_map[comparison_ref]
            member_refs = {member.fact_ref for member in comparison.members}
            if not member_refs.issubset(set(facts)):
                errors.append("COMPARISON_MEMBER_MISMATCH")
    return sorted(set(errors))


def _source_claim_output(session, run, context):
    usable = [
        source_run
        for source_run in run.source_runs
        if source_run.answer_run
        and source_run.answer_run.status in {"ANSWERED", "PARTIAL"}
        and any(
            fact["source"] == source_run.document_family
            for fact in context.payload["facts"]
        )
    ]
    if len(usable) != 1:
        return None
    source_run = usable[0]
    claims = session.scalars(
        select(AnswerClaim).where(AnswerClaim.answer_run_id == source_run.answer_run_id)
    ).all()
    result = []
    for index, claim in enumerate(sorted(claims, key=lambda item: item.claim_order), 1):
        fact_ids = session.scalars(
            select(AnswerClaimFact.fact_resolution_id).where(
                AnswerClaimFact.answer_claim_id == claim.id
            )
        ).all()
        evidence_ids = session.scalars(
            select(AnswerCitation.evidence_unit_id).where(
                AnswerCitation.answer_claim_id == claim.id
            )
        ).all()
        fact_refs = [
            context.fact_refs_by_resolution[item]
            for item in fact_ids
            if item in context.fact_refs_by_resolution
        ]
        evidence_refs = [
            context.evidence_refs_by_unit[item]
            for item in evidence_ids
            if item in context.evidence_refs_by_unit
        ]
        if fact_refs and evidence_refs:
            result.append(
                {
                    "claim_id": f"C{index}",
                    "text": claim.text,
                    "fact_refs": fact_refs,
                    "evidence_refs": evidence_refs,
                    "comparison_refs": [],
                }
            )
    if result:
        return {"claims": result}
    return None


def _fallback_claims(context):
    claims = []
    for index, fact in enumerate(context.payload["facts"], 1):
        evidence_refs = context.payload["ref_maps"]["facts"][fact["ref"]][
            "evidence_refs"
        ]
        claims.append(
            {
                "claim_id": f"C{index}",
                "text": f"{fact['fact_type']}: {canonical_json(fact['value'])}",
                "fact_refs": [fact["ref"]],
                "evidence_refs": evidence_refs,
                "comparison_refs": [],
            }
        )
    return {"claims": claims}


def _prompt(context):
    rules = (
        "Use only the supplied facts, evidence and comparisons. Do not use external "
        "knowledge, invent refs, invent facts, invent evidence or create comparisons. "
        "Do not choose precedence between MOS, LAYOUT and XSD. Preserve material "
        "divergence. NOT_COMPARABLE is neither agreement nor conflict. Complementary "
        "facts are not total agreement. Every factual claim needs fact_refs and "
        "evidence_refs from the allowlists; cross-source claims need comparison_refs. "
        "Return only the exact structured schema."
    )
    return canonical_json(
        {
            "instructions": rules,
            "schema": SYNTHESIS_JSON_SCHEMA,
            "context": context.payload,
        }
    )


def _render(session, claims, context, limitations, status):
    if status == CompleteAnswerStatus.ABSTAINED.value:
        lines = ["ABSTAINED: nenhum fato autorizado foi resolvido."]
    elif status in {
        CompleteAnswerStatus.MODEL_ERROR.value,
        CompleteAnswerStatus.VALIDATION_FAILED.value,
    }:
        lines = [f"{status}: nenhuma claim final foi exposta."]
    else:
        lines = []
        for claim in claims:
            citations = []
            for ref in claim["evidence_refs"]:
                unit = context.evidence_map[ref]
                target = session.get(CitationTarget, unit.citation_target_id)
                citations.append(
                    f"[{target.document_family}: "
                    f"{target.human_label or target.source_local_stable_path}]"
                )
            lines.append(f"{claim['text']} {' '.join(citations)}")
        divergence = [
            item
            for item in context.payload["comparisons"]
            if item["kind"]
            in {"SAME_ASPECT_DIFFERENT_VALUE", "NOT_COMPARABLE", "DIFFERENT_ASPECT"}
        ]
        if divergence:
            lines.append("Comparações determinísticas:")
            lines.extend(
                f"- {item['ref']}: {item['kind']} ({item['aspect_key']})"
                for item in divergence
            )
    if limitations:
        lines.append("Limitações:")
        lines.extend(
            f"- {item['source']} / {item.get('aspect_key', 'source')}: {item['kind']}"
            for item in limitations
        )
    return "\n".join(lines)


def _persist_claims(session, run, output, context):
    claims = []
    for order, claim in enumerate(output["claims"], 1):
        stored = CompleteAnswerClaim(
            id=str(uuid.uuid4()),
            complete_answer_run_id=run.id,
            claim_key=claim["claim_id"],
            claim_order=order,
            text=claim["text"],
            text_sha256=hashlib.sha256(claim["text"].encode()).hexdigest(),
            validation_state="VALID",
        )
        session.add(stored)
        session.flush()
        for fact_ref in claim["fact_refs"]:
            session.add(
                CompleteAnswerClaimFact(
                    complete_answer_claim_id=stored.id,
                    fact_resolution_id=context.fact_map[fact_ref].id,
                )
            )
        for citation_order, evidence_ref in enumerate(claim["evidence_refs"], 1):
            session.add(
                CompleteAnswerCitation(
                    complete_answer_claim_id=stored.id,
                    evidence_unit_id=context.evidence_map[evidence_ref].id,
                    citation_order=citation_order,
                )
            )
        for comparison_ref in claim["comparison_refs"]:
            session.add(
                CompleteAnswerClaimComparison(
                    complete_answer_claim_id=stored.id,
                    comparison_id=context.comparison_map[comparison_ref].id,
                )
            )
        claims.append(stored)
    session.flush()
    return claims


def _finish(run, status, context, output, limitations, errors, attempt_count):
    run.execution_state = CompleteRunExecutionState.FINALIZED.value
    run.status = status
    run.synthesis_attempt_count = attempt_count
    run.synthesis_raw_response = output
    run.synthesis_validation_summary = {
        "errors": errors,
        "limitations": limitations,
        "context_digest": context.aggregation_digest,
    }
    run.updated_at = datetime.now(timezone.utc)


def execute_complete_synthesis(session, run, client):
    context = build_synthesis_context(session, run)
    run.synthesis_provider = "ollama"
    run.synthesis_model_id = getattr(client, "model", "gemma4:12b")
    run.synthesis_model_config = SYNTHESIS_MODEL_CONFIG
    run.synthesis_model_config_digest = parser_config_digest(SYNTHESIS_MODEL_CONFIG)
    run.synthesis_contract_revision = SYNTHESIS_CONTRACT_REVISION
    run.synthesis_prompt_revision = SYNTHESIS_PROMPT_REVISION
    prompt = _prompt(context)
    run.synthesis_prompt_digest = _digest(prompt)
    limitations = context.payload["limitations"]
    families = {item["source"] for item in context.payload["facts"]}
    if not families:
        _finish(
            run,
            CompleteAnswerStatus.ABSTAINED.value,
            context,
            None,
            limitations,
            [],
            0,
        )
        run.synthesis_rendered_answer = _render(
            session, [], context, limitations, run.status
        )
        session.flush()
        return run
    output = None
    attempts = 0
    if len(families) == 1:
        output = _source_claim_output(session, run, context) or _fallback_claims(
            context
        )
    else:
        try:
            output = client.generate(prompt)
            attempts = 1
            if _schema_errors(output):
                output = client.generate(prompt)
                attempts = 2
        except Exception as error:
            _finish(
                run,
                CompleteAnswerStatus.MODEL_ERROR.value,
                context,
                None,
                limitations,
                [f"PROVIDER_ERROR:{error}"],
                attempts + 1,
            )
            run.synthesis_rendered_answer = None
            run.synthesis_provider_metadata = getattr(client, "last_metadata", {})
            session.flush()
            return run
    if _schema_errors(output):
        _finish(
            run,
            CompleteAnswerStatus.MODEL_ERROR.value,
            context,
            output,
            limitations,
            _schema_errors(output),
            attempts,
        )
        run.synthesis_rendered_answer = None
        run.synthesis_provider_metadata = getattr(client, "last_metadata", {})
        session.flush()
        return run
    errors = validate_synthesis_output(output, context)
    if errors:
        _finish(
            run,
            CompleteAnswerStatus.VALIDATION_FAILED.value,
            context,
            output,
            limitations,
            errors,
            attempts,
        )
        run.synthesis_rendered_answer = None
        run.synthesis_provider_metadata = getattr(client, "last_metadata", {})
        session.flush()
        return run
    _persist_claims(session, run, output, context)
    negative = [item for item in limitations if item["kind"] != "SOURCE_NOT_APPLICABLE"]
    status = (
        CompleteAnswerStatus.PARTIAL.value
        if negative
        else CompleteAnswerStatus.ANSWERED.value
    )
    _finish(run, status, context, output, limitations, [], attempts)
    run.synthesis_rendered_answer = _render(
        session, output["claims"], context, limitations, run.status
    )
    run.synthesis_provider_metadata = getattr(client, "last_metadata", {})
    session.flush()
    return run
