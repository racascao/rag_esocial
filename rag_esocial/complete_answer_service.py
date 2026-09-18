import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from .identity import canonical_json, parser_config_digest
from .models.answer import (
    AnswerRequest,
    AnswerRequestFactResolution,
    AnswerRun,
)
from .models.build import CanonicalEntity, CorpusBuild
from .models.complete_answer import (
    CompleteAnswerRequest,
    CompleteAnswerRequestedAspect,
    CompleteAnswerRequestSource,
    CompleteAnswerRun,
    CompleteAnswerSourceInput,
    CompleteAnswerSourceRun,
    CompleteRunExecutionState,
    CompleteSourceAvailability,
)
from .models.corpus import DocumentFamily
from .models.fact_resolution import FactResolution, RequestedFact
from .search_service import PROFILES

CONTRACT_REVISION = "complete-answer-contract-v1"
ORCHESTRATION_REVISION = "complete-orchestration-v1"
SOURCE_ORDER = (
    DocumentFamily.MOS.value,
    DocumentFamily.LAYOUT.value,
    DocumentFamily.XSD.value,
)
PROFILE_FAMILY = {
    profile: next(family for family in SOURCE_ORDER if profile.startswith(family))
    for profile in PROFILES
}


class CompleteAnswerError(Exception):
    """Base error for deterministic Complete Mode orchestration validation."""


class CompleteIdentityError(CompleteAnswerError):
    pass


class CompleteBuildMismatchError(CompleteAnswerError):
    pass


class CompleteMembershipError(CompleteAnswerError):
    pass


class CompleteDuplicateMembershipError(CompleteMembershipError):
    pass


@dataclass(frozen=True)
class CompleteSourceInputSpec:
    document_family: str
    requested_fact: RequestedFact
    retrieval_profile: str
    query: str
    top_k: int
    retrieval_config: dict = field(default_factory=dict)
    assembly_config: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CompleteRequestedAspectSpec:
    aspect_key: str
    subject_kind: str
    subject_key: str
    source_inputs: tuple[CompleteSourceInputSpec, ...]
    qualifiers: dict = field(default_factory=dict)
    canonical_entity: CanonicalEntity | None = None


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _normalize_sources(sources):
    values = tuple(sources)
    if len(values) != len(set(values)):
        raise CompleteIdentityError("duplicate document family")
    if set(values) != set(SOURCE_ORDER):
        raise CompleteIdentityError("complete request requires MOS, LAYOUT and XSD")
    return SOURCE_ORDER


def _canonical_plan(build, question, sources, source_configs, aspects, config):
    question = question.strip()
    if not question:
        raise CompleteIdentityError("question is required")
    sources = _normalize_sources(sources)
    source_configs = source_configs or {}
    if set(source_configs) - set(sources):
        raise CompleteIdentityError("source config references unknown family")
    if not aspects:
        raise CompleteIdentityError("at least one requested aspect is required")

    canonical_aspects = []
    seen_aspects = set()
    seen_inputs = set()
    for aspect in aspects:
        key = aspect.aspect_key.strip()
        subject_kind = aspect.subject_kind.strip()
        subject_key = aspect.subject_key.strip()
        if not key or not subject_kind or not subject_key:
            raise CompleteIdentityError("aspect key and subject are required")
        if key in seen_aspects:
            raise CompleteIdentityError("duplicate requested aspect")
        seen_aspects.add(key)
        entity_key = None
        if aspect.canonical_entity:
            if (
                aspect.canonical_entity.entity_kind != subject_kind
                or aspect.canonical_entity.canonical_key != subject_key
            ):
                raise CompleteIdentityError("canonical entity does not match subject")
            entity_key = aspect.canonical_entity.stable_key
        inputs = []
        for source_input in aspect.source_inputs:
            source = source_input.document_family
            requested = source_input.requested_fact
            query = source_input.query.strip()
            if source not in sources:
                raise CompleteMembershipError("source input is outside request")
            if source_input.retrieval_profile not in PROFILE_FAMILY:
                raise CompleteIdentityError("unknown retrieval profile")
            if PROFILE_FAMILY[source_input.retrieval_profile] != source:
                raise CompleteMembershipError("retrieval profile has wrong family")
            if not query or source_input.top_k <= 0:
                raise CompleteIdentityError("query and positive top_k are required")
            if requested.corpus_build_id != build.id:
                raise CompleteBuildMismatchError(
                    "requested fact belongs to other build"
                )
            input_value = {
                "source": source,
                "requested_fact_digest": requested.request_digest,
                "profile": source_input.retrieval_profile,
                "query": query,
                "top_k": source_input.top_k,
                "retrieval_config": source_input.retrieval_config,
                "assembly_config": source_input.assembly_config,
            }
            input_digest = _digest(input_value)
            if input_digest in seen_inputs:
                raise CompleteIdentityError("duplicate source input")
            seen_inputs.add(input_digest)
            inputs.append((input_value, input_digest, requested, source_input))
        canonical_aspects.append(
            (
                {
                    "aspect_key": key,
                    "subject_kind": subject_kind,
                    "subject_key": subject_key,
                    "canonical_entity_key": entity_key,
                    "qualifiers": aspect.qualifiers,
                    "inputs": [
                        value
                        for value, _, _, _ in sorted(
                            inputs,
                            key=lambda item: (
                                SOURCE_ORDER.index(item[0]["source"]),
                                item[1],
                            ),
                        )
                    ],
                },
                aspect,
                sorted(
                    inputs,
                    key=lambda item: (
                        SOURCE_ORDER.index(item[0]["source"]),
                        item[1],
                    ),
                ),
            )
        )
    canonical_aspects.sort(
        key=lambda item: (
            item[0]["aspect_key"],
            item[0]["subject_kind"],
            item[0]["subject_key"],
        )
    )
    source_payload = [
        {"source": source, "config": source_configs.get(source, {})}
        for source in sources
    ]
    orchestration_config = config or {}
    payload = {
        "build_digest": build.build_digest,
        "question": question,
        "sources": source_payload,
        "aspects": [item[0] for item in canonical_aspects],
        "contract_revision": CONTRACT_REVISION,
        "orchestration_revision": ORCHESTRATION_REVISION,
        "orchestration_config": orchestration_config,
    }
    return question, source_payload, canonical_aspects, orchestration_config, payload


def create_complete_answer_request(
    session,
    build: CorpusBuild,
    question: str,
    sources,
    aspects,
    source_configs=None,
    orchestration_config=None,
):
    question, source_payload, aspects, config, payload = _canonical_plan(
        build,
        question,
        sources,
        source_configs,
        aspects,
        orchestration_config,
    )
    request_digest = _digest(payload)
    existing = session.scalar(
        select(CompleteAnswerRequest).where(
            CompleteAnswerRequest.corpus_build_id == build.id,
            CompleteAnswerRequest.request_digest == request_digest,
        )
    )
    if existing:
        return existing, False

    now = datetime.now(timezone.utc)
    request = CompleteAnswerRequest(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        question=question,
        question_digest=hashlib.sha256(question.encode()).hexdigest(),
        contract_revision=CONTRACT_REVISION,
        orchestration_revision=ORCHESTRATION_REVISION,
        orchestration_config=config,
        orchestration_config_digest=parser_config_digest(config),
        request_digest=request_digest,
        created_at=now,
    )
    session.add(request)
    session.flush()

    source_rows = {}
    for order, source_value in enumerate(source_payload):
        source = CompleteAnswerRequestSource(
            id=str(uuid.uuid4()),
            complete_answer_request_id=request.id,
            document_family=source_value["source"],
            source_order=order,
            source_config=source_value["config"],
            source_config_digest=parser_config_digest(source_value["config"]),
        )
        session.add(source)
        source_rows[source.document_family] = source
    session.flush()

    input_order = {source: 0 for source in SOURCE_ORDER}
    for aspect_order, (aspect_value, aspect_spec, inputs) in enumerate(aspects):
        aspect = CompleteAnswerRequestedAspect(
            id=str(uuid.uuid4()),
            complete_answer_request_id=request.id,
            aspect_key=aspect_value["aspect_key"],
            aspect_order=aspect_order,
            subject_kind=aspect_value["subject_kind"],
            subject_key=aspect_value["subject_key"],
            canonical_entity_id=(
                aspect_spec.canonical_entity.id
                if aspect_spec.canonical_entity
                else None
            ),
            qualifiers=aspect_value["qualifiers"],
            aspect_digest=_digest(aspect_value),
        )
        session.add(aspect)
        session.flush()
        for value, input_digest, requested, source_spec in inputs:
            source = value["source"]
            session.add(
                CompleteAnswerSourceInput(
                    id=str(uuid.uuid4()),
                    complete_answer_request_id=request.id,
                    request_source_id=source_rows[source].id,
                    requested_aspect_id=aspect.id,
                    requested_fact_id=requested.id,
                    input_order=input_order[source],
                    retrieval_profile=value["profile"],
                    query=value["query"],
                    query_digest=hashlib.sha256(value["query"].encode()).hexdigest(),
                    top_k=value["top_k"],
                    retrieval_config=source_spec.retrieval_config,
                    retrieval_config_digest=parser_config_digest(
                        source_spec.retrieval_config
                    ),
                    assembly_config=source_spec.assembly_config,
                    assembly_config_digest=parser_config_digest(
                        source_spec.assembly_config
                    ),
                    input_digest=input_digest,
                )
            )
            input_order[source] += 1
    session.flush()
    return request, True


def create_complete_answer_run(session, request: CompleteAnswerRequest):
    build = session.get(CorpusBuild, request.corpus_build_id)
    if not build:
        raise CompleteBuildMismatchError("complete request build does not exist")
    now = datetime.now(timezone.utc)
    run = CompleteAnswerRun(
        id=str(uuid.uuid4()),
        complete_answer_request_id=request.id,
        corpus_build_id=request.corpus_build_id,
        run_key=str(uuid.uuid4()),
        execution_state=CompleteRunExecutionState.RUNNING.value,
        status=None,
        context_digest=None,
        failure_code=None,
        failure_details=None,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()
    return run


def _source_plan(session, run, source):
    if source not in SOURCE_ORDER:
        raise CompleteMembershipError("unknown document family")
    if run.request.corpus_build_id != run.corpus_build_id:
        raise CompleteBuildMismatchError("complete run crosses build boundary")
    plan = session.scalar(
        select(CompleteAnswerRequestSource).where(
            CompleteAnswerRequestSource.complete_answer_request_id
            == run.complete_answer_request_id,
            CompleteAnswerRequestSource.document_family == source,
        )
    )
    if not plan:
        raise CompleteMembershipError("source is not a member of complete request")
    return plan


def register_complete_source_run(
    session,
    complete_run: CompleteAnswerRun,
    source: str,
    answer_request: AnswerRequest,
    answer_run: AnswerRun,
    outcome_summary=None,
):
    if complete_run.execution_state != CompleteRunExecutionState.RUNNING.value:
        raise CompleteMembershipError("complete run is not accepting source runs")
    plan = _source_plan(session, complete_run, source)
    if (
        answer_request.corpus_build_id != complete_run.corpus_build_id
        or answer_request.corpus_build_id != complete_run.request.corpus_build_id
    ):
        raise CompleteBuildMismatchError("answer request belongs to other build")
    if answer_request.document_family != source:
        raise CompleteMembershipError("answer request has wrong family")
    if answer_request.question != complete_run.request.question:
        raise CompleteMembershipError("answer request has wrong question")
    if answer_run.answer_request_id != answer_request.id:
        raise CompleteMembershipError("answer run belongs to other answer request")

    planned_fact_ids = set(
        session.scalars(
            select(CompleteAnswerSourceInput.requested_fact_id).where(
                CompleteAnswerSourceInput.request_source_id == plan.id
            )
        ).all()
    )
    request_fact_ids = set(
        session.scalars(
            select(FactResolution.requested_fact_id)
            .join(
                AnswerRequestFactResolution,
                AnswerRequestFactResolution.fact_resolution_id == FactResolution.id,
            )
            .where(AnswerRequestFactResolution.answer_request_id == answer_request.id)
        ).all()
    )
    if not planned_fact_ids or planned_fact_ids != request_fact_ids:
        raise CompleteMembershipError("answer request does not match source inputs")

    reused = session.scalar(
        select(CompleteAnswerSourceRun).where(
            CompleteAnswerSourceRun.answer_run_id == answer_run.id
        )
    )
    if reused:
        if (
            reused.complete_answer_run_id == complete_run.id
            and reused.request_source_id == plan.id
        ):
            return reused, False
        raise CompleteDuplicateMembershipError(
            "answer run already belongs to a complete run"
        )
    duplicate = session.scalar(
        select(CompleteAnswerSourceRun).where(
            CompleteAnswerSourceRun.complete_answer_run_id == complete_run.id,
            CompleteAnswerSourceRun.request_source_id == plan.id,
        )
    )
    if duplicate:
        raise CompleteDuplicateMembershipError(
            "complete run already has a source execution for this family"
        )

    item = CompleteAnswerSourceRun(
        id=str(uuid.uuid4()),
        complete_answer_run_id=complete_run.id,
        complete_answer_request_id=complete_run.complete_answer_request_id,
        request_source_id=plan.id,
        answer_request_id=answer_request.id,
        answer_run_id=answer_run.id,
        document_family=source,
        source_order=plan.source_order,
        availability=CompleteSourceAvailability.AVAILABLE.value,
        outcome_summary=outcome_summary or {},
        created_at=datetime.now(timezone.utc),
    )
    session.add(item)
    session.flush()
    return item, True


def mark_complete_run_failed(session, run, failure_code, details=None):
    if run.execution_state != CompleteRunExecutionState.RUNNING.value:
        raise CompleteMembershipError("only a running complete run may fail")
    if not failure_code or not failure_code.strip():
        raise CompleteIdentityError("failure code is required")
    run.execution_state = CompleteRunExecutionState.FAILED.value
    run.status = None
    run.failure_code = failure_code.strip()
    run.failure_details = details or {}
    run.updated_at = datetime.now(timezone.utc)
    session.flush()
    return run


def inspect_complete_run(session, run):
    source_rows = session.scalars(
        select(CompleteAnswerSourceRun)
        .where(CompleteAnswerSourceRun.complete_answer_run_id == run.id)
        .order_by(CompleteAnswerSourceRun.source_order)
    ).all()
    return {
        "run_id": run.id,
        "run_key": run.run_key,
        "request_id": run.complete_answer_request_id,
        "corpus_build_id": run.corpus_build_id,
        "execution_state": run.execution_state,
        "status": run.status,
        "failure_code": run.failure_code,
        "sources": [
            {
                "document_family": item.document_family,
                "availability": item.availability,
                "answer_request_id": item.answer_request_id,
                "answer_run_id": item.answer_run_id,
                "outcome_summary": item.outcome_summary,
            }
            for item in source_rows
        ],
    }
