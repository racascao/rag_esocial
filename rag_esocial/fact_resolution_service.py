import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .identity import canonical_json, entity_stable_key, parser_config_digest
from .models.build import CanonicalEntity, CitationTarget
from .models.evidence import EvidenceSetItem, EvidenceUnit
from .models.fact_resolution import (
    FactResolution,
    FactResolutionSupport,
    RequestedFact,
    RuntimeStatus,
)
from .models.facts import SourceFact

REQUEST_REVISION = "requested-fact-v1"
RESOLVER_REVISION = "fact-resolver-v1"


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def requested_fact(
    session, build, fact_type, subject_kind, subject_key, qualifiers=None
):
    qualifiers = qualifiers or {}
    payload = {
        "fact_type": fact_type,
        "subject_kind": subject_kind,
        "subject_key": subject_key,
        "qualifiers": qualifiers,
    }
    digest = _digest(payload)
    item = session.scalar(
        select(RequestedFact).where(
            RequestedFact.corpus_build_id == build.id,
            RequestedFact.request_digest == digest,
        )
    )
    if item:
        return item, False
    entity = session.scalar(
        select(CanonicalEntity).where(
            CanonicalEntity.stable_key == entity_stable_key(subject_kind, subject_key)
        )
    )
    item = RequestedFact(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        request_revision=REQUEST_REVISION,
        fact_type=fact_type,
        subject_kind=subject_kind,
        subject_key=subject_key,
        canonical_entity_id=entity.id if entity else None,
        qualifiers=qualifiers,
        request_payload=payload,
        request_digest=digest,
        created_at=datetime.now(timezone.utc),
    )
    session.add(item)
    session.flush()
    return item, True


def fact_type_registry(session, build_id):
    rows = session.execute(
        select(SourceFact.fact_type, CitationTarget.document_family)
        .join(CitationTarget)
        .where(SourceFact.corpus_build_id == build_id)
    ).all()
    registry = {}
    for fact_type, family in rows:
        registry.setdefault(
            fact_type,
            {
                "fact_type": fact_type,
                "sources": set(),
                "multiplicity": "SINGLE",
                "strategy": "SOURCE_FACT_EXACT",
            },
        )["sources"].add(family)
    return {
        key: {**value, "sources": sorted(value["sources"])}
        for key, value in registry.items()
    }


def _subject_facts(session, requested, family):
    query = (
        select(SourceFact)
        .join(CitationTarget)
        .where(
            SourceFact.corpus_build_id == requested.corpus_build_id,
            CitationTarget.document_family == family,
            SourceFact.fact_type == requested.fact_type,
        )
    )
    if requested.canonical_entity_id:
        query = query.where(
            SourceFact.subject_entity_id == requested.canonical_entity_id
        )
    elif requested.subject_kind == "FIELD":
        query = query.where(
            CitationTarget.source_local_stable_path == requested.subject_key
        )
    else:
        return []
    return session.scalars(query).all()


def resolve_requested_fact(
    session, requested, source_family, evidence_set=None, resolver_config=None
):
    resolver_config = resolver_config or {}
    config_digest = parser_config_digest(resolver_config)
    if evidence_set and evidence_set.corpus_build_id != requested.corpus_build_id:
        raise ValueError("evidence set belongs to another build")
    existing = session.scalar(
        select(FactResolution).where(
            FactResolution.requested_fact_id == requested.id,
            FactResolution.document_family == source_family,
            FactResolution.evidence_set_id
            == (evidence_set.id if evidence_set else None),
            FactResolution.resolver_config_digest == config_digest,
        )
    )
    if existing:
        return existing, False
    registry = fact_type_registry(session, requested.corpus_build_id)
    entry = registry.get(requested.fact_type)
    provenance = {
        "requested_fact_id": requested.id,
        "source_family": source_family,
        "applicable": bool(entry and source_family in entry["sources"]),
        "evidence_set_id": evidence_set.id if evidence_set else None,
    }
    status, reason, value, strategy, matches = (
        RuntimeStatus.UNSUPPORTED.value,
        "UNSUPPORTED_FACT_TYPE",
        None,
        "NONE",
        [],
    )
    if not entry or source_family not in entry["sources"]:
        status, reason = (
            RuntimeStatus.SOURCE_NOT_APPLICABLE.value,
            "FACT_TYPE_NOT_APPLICABLE",
        )
    else:
        coverage = _subject_facts(session, requested, source_family)
        provenance["coverage_fact_ids"] = sorted(item.id for item in coverage)
        if not requested.canonical_entity_id and requested.subject_kind != "FIELD":
            status, reason = RuntimeStatus.UNSUPPORTED.value, "SUBJECT_NOT_IN_BUILD"
        elif not coverage:
            status, reason = (
                RuntimeStatus.ASPECT_NOT_COVERED.value,
                "FACT_ASPECT_NOT_MATERIALIZED",
            )
        elif not evidence_set:
            status, reason = (
                RuntimeStatus.NO_RELEVANT_EVIDENCE.value,
                "EVIDENCE_SET_REQUIRED",
            )
        else:
            authorized = set(
                session.scalars(
                    select(EvidenceUnit.citation_target_id)
                    .join(EvidenceSetItem)
                    .where(EvidenceSetItem.evidence_set_id == evidence_set.id)
                ).all()
            )
            matches = [
                item for item in coverage if item.citation_target_id in authorized
            ]
            provenance["authorized_citation_target_ids"] = sorted(authorized)
            if not matches:
                status, reason = (
                    RuntimeStatus.NO_RELEVANT_EVIDENCE.value,
                    "AUTHORIZED_EVIDENCE_MISSING_FACT_TARGET",
                )
            else:
                values = {
                    canonical_json(
                        item.structured_value
                        if item.structured_value is not None
                        else {"value": item.string_value}
                    ): item
                    for item in matches
                }
                if len(values) != 1:
                    status, reason = (
                        RuntimeStatus.UNSUPPORTED.value,
                        "AMBIGUOUS_FACT_VALUES",
                    )
                else:
                    selected = next(iter(values.values()))
                    value = (
                        selected.structured_value
                        if selected.structured_value is not None
                        else {"value": selected.string_value}
                    )
                    status, reason, strategy = (
                        RuntimeStatus.RESOLVED.value,
                        None,
                        "SOURCE_FACT_EXACT",
                    )
    resolution = FactResolution(
        id=str(uuid.uuid4()),
        requested_fact_id=requested.id,
        document_family=source_family,
        evidence_set_id=evidence_set.id if evidence_set else None,
        resolver_revision=RESOLVER_REVISION,
        resolver_config=resolver_config,
        resolver_config_digest=config_digest,
        runtime_status=status,
        reason_code=reason,
        resolved_value=value,
        resolution_strategy=strategy,
        provenance=provenance,
        created_at=datetime.now(timezone.utc),
    )
    session.add(resolution)
    session.flush()
    if status == RuntimeStatus.RESOLVED.value:
        units = {
            unit.citation_target_id: unit
            for unit in session.scalars(
                select(EvidenceUnit)
                .join(EvidenceSetItem)
                .where(EvidenceSetItem.evidence_set_id == evidence_set.id)
            ).all()
        }
        for order, item in enumerate(
            sorted(matches, key=lambda value: (value.fact_key, value.id))
        ):
            session.add(
                FactResolutionSupport(
                    id=str(uuid.uuid4()),
                    fact_resolution_id=resolution.id,
                    evidence_unit_id=units[item.citation_target_id].id,
                    source_fact_id=item.id,
                    resolved_fact_id=None,
                    support_role="FACTUAL_SUPPORT",
                    support_order=order,
                    provenance={"fact_key": item.fact_key},
                )
            )
    session.flush()
    return resolution, True
