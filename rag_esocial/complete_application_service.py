"""Application boundary for the public Complete Mode CLI."""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from .answer_service import (
    OllamaAnswerModelClient,
    create_answer_request,
    execute_answer,
)
from .complete_answer_service import (
    SOURCE_ORDER,
    CompleteRequestedAspectSpec,
    CompleteSourceInputSpec,
    create_complete_answer_request,
    create_complete_answer_run,
    register_complete_source_run,
)
from .cross_source_service import aggregate_cross_source
from .evidence_service import assemble_evidence
from .fact_resolution_service import requested_fact, resolve_requested_fact
from .models.build import CanonicalEntity, CitationTarget
from .models.complete_answer import (
    CompleteAnswerCitation,
    CompleteAnswerClaim,
    CompleteAnswerClaimComparison,
    CompleteAnswerClaimFact,
    CompleteAnswerRequest,
    CompleteAnswerRun,
    CompleteAnswerSourceInput,
)
from .models.cross_source import CrossSourceComparison
from .models.evidence import EvidenceUnit
from .models.fact_resolution import FactResolution, FactResolutionSupport, RequestedFact
from .search_service import materialize_projection
from .synthesis_service import (
    OllamaSynthesisModelClient,
    execute_complete_synthesis,
)


class CompleteInputError(ValueError):
    pass


@dataclass(frozen=True)
class CompleteExecutionResult:
    request: CompleteAnswerRequest
    run: CompleteAnswerRun
    payload: dict


def load_complete_input(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompleteInputError(f"input Complete inválido: {error}") from error
    if not isinstance(value, dict):
        raise CompleteInputError("input Complete deve ser um objeto JSON")
    return value


def _required(value, name):
    if not isinstance(value, str) or not value.strip():
        raise CompleteInputError(f"campo obrigatório inválido: {name}")
    return value.strip()


def _build_aspects(session, build, data):
    aspects = data.get("aspects")
    if not isinstance(aspects, list) or not aspects:
        raise CompleteInputError("aspects deve ser uma lista não vazia")
    result = []
    for aspect in aspects:
        if not isinstance(aspect, dict):
            raise CompleteInputError("cada aspect deve ser um objeto")
        aspect_key = _required(aspect.get("aspect_key"), "aspect_key")
        subject_kind = _required(aspect.get("subject_kind"), "subject_kind")
        subject_key = _required(aspect.get("subject_key"), "subject_key")
        entity = None
        entity_key = aspect.get("canonical_entity_key")
        if entity_key:
            entity = session.scalar(
                select(CanonicalEntity).where(CanonicalEntity.stable_key == entity_key)
            )
            if not entity:
                raise CompleteInputError(
                    f"CanonicalEntity não encontrada: {entity_key}"
                )
        inputs = []
        for source_input in aspect.get("source_inputs", []):
            if not isinstance(source_input, dict):
                raise CompleteInputError("cada source_input deve ser um objeto")
            family = _required(source_input.get("source"), "source").upper()
            if family not in SOURCE_ORDER:
                raise CompleteInputError(f"source inválida: {family}")
            requested = None
            requested_id = source_input.get("requested_fact_id")
            if requested_id:
                requested = session.get(RequestedFact, requested_id)
                if requested is None:
                    resolution = session.get(FactResolution, requested_id)
                    if resolution:
                        requested = session.get(
                            RequestedFact, resolution.requested_fact_id
                        )
            if requested is None:
                payload = source_input.get("requested_fact")
                if not isinstance(payload, dict):
                    raise CompleteInputError(
                        "source_input exige requested_fact_id ou requested_fact"
                    )
                requested, _ = requested_fact(
                    session,
                    build,
                    _required(payload.get("fact_type"), "fact_type"),
                    _required(payload.get("subject_kind"), "subject_kind"),
                    _required(payload.get("subject_key"), "subject_key"),
                    payload.get("qualifiers") or {},
                )
            if requested.corpus_build_id != build.id:
                raise CompleteInputError("RequestedFact pertence a outro build")
            inputs.append(
                CompleteSourceInputSpec(
                    document_family=family,
                    requested_fact=requested,
                    retrieval_profile=_required(source_input.get("profile"), "profile"),
                    query=_required(source_input.get("query"), "query"),
                    top_k=int(source_input.get("top_k", 5)),
                    retrieval_config=source_input.get("retrieval_config") or {},
                    assembly_config=source_input.get("assembly_config") or {},
                )
            )
        result.append(
            CompleteRequestedAspectSpec(
                aspect_key=aspect_key,
                subject_kind=subject_kind,
                subject_key=subject_key,
                source_inputs=tuple(inputs),
                qualifiers=aspect.get("qualifiers") or {},
                canonical_entity=entity,
            )
        )
    return tuple(result)


def _default_source_client(settings, _family):
    return OllamaAnswerModelClient(
        base_url=settings.ollama_base_url, model=settings.llm_model
    )


def _default_synthesis_client(settings):
    return OllamaSynthesisModelClient(
        base_url=settings.ollama_base_url, model=settings.llm_model
    )


def execute_complete(
    session,
    build,
    data,
    settings,
    source_client_factory=None,
    synthesis_client_factory=None,
):
    question = _required(data.get("question"), "question")
    aspects = _build_aspects(session, build, data)
    source_client_factory = source_client_factory or (
        lambda family: _default_source_client(settings, family)
    )
    synthesis_client_factory = synthesis_client_factory or (
        lambda: _default_synthesis_client(settings)
    )
    request, _ = create_complete_answer_request(
        session,
        build,
        question,
        SOURCE_ORDER,
        aspects,
        source_configs=data.get("source_configs") or {},
        orchestration_config=data.get("orchestration_config") or {},
    )
    session.commit()
    run = create_complete_answer_run(session, request)
    session.commit()

    inputs = session.scalars(
        select(CompleteAnswerSourceInput).where(
            CompleteAnswerSourceInput.complete_answer_request_id == request.id
        )
    ).all()
    for family in SOURCE_ORDER:
        family_inputs = [
            item for item in inputs if item.request_source.document_family == family
        ]
        if not family_inputs:
            continue
        resolutions = []
        for item in family_inputs:
            projection, _ = materialize_projection(
                session, build, item.retrieval_profile, config=item.retrieval_config
            )
            evidence, _ = assemble_evidence(
                session,
                build,
                projection,
                item.query,
                item.top_k,
            )
            resolution, _ = resolve_requested_fact(
                session, item.requested_fact, family, evidence
            )
            resolutions.append(resolution)
        source_request, _ = create_answer_request(
            session, build, family, question, resolutions, model_id=settings.llm_model
        )
        # Persist the deterministic source plan before crossing the provider
        # boundary; the model call must not hold retrieval work in a long
        # transaction.
        session.commit()
        source_run = execute_answer(
            session, source_request, source_client_factory(family)
        )
        register_complete_source_run(
            session,
            run,
            family,
            source_request,
            source_run,
            {"answer_status": source_run.status},
        )
        session.commit()

    aggregate_cross_source(session, run)
    session.commit()
    run = session.get(CompleteAnswerRun, run.id)
    execute_complete_synthesis(session, run, synthesis_client_factory())
    session.commit()
    payload = complete_show_payload(session, run.run_key)
    return CompleteExecutionResult(request, run, payload)


def complete_show_payload(session, run_key: str) -> dict | None:
    """Read-only reconstruction from persisted Complete Mode state."""
    run = session.scalar(
        select(CompleteAnswerRun).where(CompleteAnswerRun.run_key == run_key)
    )
    if not run:
        return None
    request = run.request
    comparisons = session.scalars(
        select(CrossSourceComparison)
        .where(CrossSourceComparison.complete_answer_run_id == run.id)
        .order_by(CrossSourceComparison.comparison_order)
    ).all()
    comparison_refs = {row.id: f"X{index}" for index, row in enumerate(comparisons, 1)}
    fact_refs = {}
    evidence_refs = {}
    for row in comparisons:
        for member in sorted(row.members, key=lambda item: item.member_order):
            fact_refs[member.fact_resolution_id] = member.fact_ref
            supports = session.scalars(
                select(FactResolutionSupport)
                .where(
                    FactResolutionSupport.fact_resolution_id
                    == member.fact_resolution_id
                )
                .order_by(FactResolutionSupport.support_order, FactResolutionSupport.id)
            ).all()
            for support, ref in zip(supports, member.evidence_refs):
                evidence_refs[support.evidence_unit_id] = ref
    claims = session.scalars(
        select(CompleteAnswerClaim)
        .where(CompleteAnswerClaim.complete_answer_run_id == run.id)
        .order_by(CompleteAnswerClaim.claim_order)
    ).all()
    claim_payload = []
    for claim in claims:
        fact_rows = session.scalars(
            select(CompleteAnswerClaimFact)
            .where(CompleteAnswerClaimFact.complete_answer_claim_id == claim.id)
            .order_by(CompleteAnswerClaimFact.fact_resolution_id)
        ).all()
        citation_rows = session.scalars(
            select(CompleteAnswerCitation)
            .where(CompleteAnswerCitation.complete_answer_claim_id == claim.id)
            .order_by(CompleteAnswerCitation.citation_order)
        ).all()
        comparison_rows = session.scalars(
            select(CompleteAnswerClaimComparison)
            .where(CompleteAnswerClaimComparison.complete_answer_claim_id == claim.id)
            .order_by(CompleteAnswerClaimComparison.comparison_id)
        ).all()
        claim_payload.append(
            {
                "claim_id": claim.claim_key,
                "text": claim.text,
                "fact_refs": [fact_refs[row.fact_resolution_id] for row in fact_rows],
                "evidence_refs": [
                    evidence_refs[row.evidence_unit_id] for row in citation_rows
                ],
                "comparison_refs": [
                    comparison_refs[row.comparison_id] for row in comparison_rows
                ],
            }
        )
    citations = []
    for row in session.scalars(
        select(CompleteAnswerCitation)
        .join(CompleteAnswerClaim)
        .where(CompleteAnswerClaim.complete_answer_run_id == run.id)
        .order_by(
            CompleteAnswerClaim.claim_order,
            CompleteAnswerCitation.citation_order,
        )
    ).all():
        unit = session.get(EvidenceUnit, row.evidence_unit_id)
        target = session.get(CitationTarget, unit.citation_target_id)
        citations.append(
            {
                "family": target.document_family,
                "label": target.human_label or target.source_local_stable_path,
                "path": target.source_local_stable_path,
            }
        )
    return {
        "run_key": run.run_key,
        "request_digest": request.request_digest,
        "build_digest": run.build.build_digest,
        "status": run.status,
        "execution_state": run.execution_state,
        "question": request.question,
        "answer": run.synthesis_rendered_answer,
        "claims": claim_payload,
        "citations": citations,
        "comparisons": [
            {
                "ref": comparison_refs[row.id],
                "kind": row.comparison_kind,
                "key": row.comparison_key,
            }
            for row in comparisons
        ],
        "limitations": (run.synthesis_validation_summary or {}).get("limitations", []),
        "sources": [
            {
                "family": source.document_family,
                "availability": source.availability,
                "answer_status": source.answer_run.status
                if source.answer_run
                else None,
            }
            for source in sorted(run.source_runs, key=lambda item: item.source_order)
        ],
        "synthesis": {
            "provider": run.synthesis_provider,
            "model": run.synthesis_model_id,
            "attempt_count": run.synthesis_attempt_count,
        },
    }
