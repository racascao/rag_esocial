"""Deterministic, factual cross-source aggregation for Complete Mode 9B.

This module deliberately stops before synthesis.  Its only positive inputs are
resolved facts with an authorized FactResolutionSupport chain.
"""

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from .identity import canonical_json
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.complete_answer import (
    CompleteAnswerRequestedAspect,
    CompleteAnswerRun,
    CompleteAnswerSourceInput,
    CompleteAnswerSourceRun,
)
from .models.corpus import DocumentFamily
from .models.cross_source import CrossSourceComparison, CrossSourceComparisonMember
from .models.evidence import EvidenceSetItem, EvidenceUnit
from .models.fact_resolution import (
    FactResolution,
    FactResolutionSupport,
    RequestedFact,
    RuntimeStatus,
)

COMPARISON_REVISION = "cross-source-comparison-v1"
COMPARISON_KINDS = (
    "SAME_ASPECT_SAME_VALUE",
    "SAME_ASPECT_DIFFERENT_VALUE",
    "COMPLEMENTARY",
    "DIFFERENT_ASPECT",
    "NOT_COMPARABLE",
    "SINGLE_SOURCE",
)
SOURCE_ORDER = (
    DocumentFamily.MOS.value,
    DocumentFamily.LAYOUT.value,
    DocumentFamily.XSD.value,
)


class CrossSourceAggregationError(Exception):
    """Base error for 9B identity, membership and support-chain failures."""


class CrossSourceMembershipError(CrossSourceAggregationError):
    pass


class CrossSourceBuildMismatchError(CrossSourceAggregationError):
    pass


class CrossSourceSupportError(CrossSourceAggregationError):
    pass


class CrossSourceIdentityError(CrossSourceAggregationError):
    pass


@dataclass(frozen=True)
class _ResolvedMember:
    source_input: CompleteAnswerSourceInput
    resolution: FactResolution
    requested: RequestedFact
    family: str
    value: object
    value_digest: str
    fact_ref: str
    evidence_refs: tuple[str, ...]
    evidence_payload: tuple[dict, ...]


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _next_ref(refs, family, prefix):
    count = sum(1 for ref in refs if ref.startswith(f"{family}:{prefix}"))
    return f"{family}:{prefix}{count + 1}"


def _normalize(value):
    if isinstance(value, str):
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        return unicodedata.normalize("NFC", value).strip()
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    return value


def _stable_input_key(item):
    return (
        SOURCE_ORDER.index(item.request_source.document_family),
        item.input_order,
        item.input_digest,
    )


def _source_plan(session, run, family):
    rows = session.scalars(
        select(CompleteAnswerSourceRun).where(
            CompleteAnswerSourceRun.complete_answer_run_id == run.id,
            CompleteAnswerSourceRun.document_family == family,
        )
    ).all()
    if len(rows) > 1:
        raise CrossSourceMembershipError("duplicate source run for family")
    return rows[0] if rows else None


def _validate_source_run(session, run, source_run, family):
    if source_run.complete_answer_request_id != run.complete_answer_request_id:
        raise CrossSourceMembershipError("source run belongs to another request")
    if source_run.document_family != family:
        raise CrossSourceMembershipError("source run family mismatch")
    if source_run.source_order != SOURCE_ORDER.index(family):
        raise CrossSourceMembershipError("source run order mismatch")
    if source_run.answer_request_id is None or source_run.answer_run_id is None:
        return
    answer_request = source_run.answer_request
    if (
        answer_request.corpus_build_id != run.corpus_build_id
        or answer_request.document_family != family
        or answer_request.question != run.request.question
    ):
        raise CrossSourceMembershipError("source AnswerRequest crosses boundary")
    if source_run.answer_run.answer_request_id != answer_request.id:
        raise CrossSourceMembershipError("source AnswerRun membership mismatch")


def _authorized_support(session, run, resolution, family):
    requested = session.get(RequestedFact, resolution.requested_fact_id)
    if not requested or requested.corpus_build_id != run.corpus_build_id:
        raise CrossSourceBuildMismatchError("requested fact belongs to another build")
    if resolution.document_family != family:
        raise CrossSourceMembershipError("resolution family mismatch")
    if resolution.runtime_status != RuntimeStatus.RESOLVED.value:
        return (), ()
    if resolution.evidence_set_id is None:
        raise CrossSourceSupportError("resolved fact has no evidence set")
    supports = session.scalars(
        select(FactResolutionSupport)
        .where(FactResolutionSupport.fact_resolution_id == resolution.id)
        .order_by(FactResolutionSupport.support_order, FactResolutionSupport.id)
    ).all()
    if not supports:
        raise CrossSourceSupportError("resolved fact has no support")
    units = []
    for support in supports:
        unit = session.get(EvidenceUnit, support.evidence_unit_id)
        if not unit:
            raise CrossSourceSupportError("support references missing evidence unit")
        target = session.get(CitationTarget, unit.citation_target_id)
        build_target = session.get(
            CorpusBuildCitationTarget,
            {
                "build_id": run.corpus_build_id,
                "citation_target_id": unit.citation_target_id,
            },
        )
        evidence_item = session.get(
            EvidenceSetItem,
            {
                "evidence_set_id": resolution.evidence_set_id,
                "evidence_unit_id": unit.id,
            },
        )
        if (
            unit.corpus_build_id != run.corpus_build_id
            or unit.document_family != family
            or not target
            or target.document_family != family
            or not build_target
            or not evidence_item
        ):
            raise CrossSourceSupportError(
                "support chain leaves authorized build/source"
            )
        units.append((support, unit, target))
    return tuple(units), requested


def _comparison_rules(config):
    rules = config.get("comparison_rules", []) if isinstance(config, dict) else []
    complementary = set()
    different_aspect = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise CrossSourceIdentityError("comparison rule must be an object")
        kind = rule.get("kind")
        if kind == "COMPLEMENTARY":
            values = tuple(
                sorted((rule.get("left_fact_type"), rule.get("right_fact_type")))
            )
            if not all(isinstance(item, str) and item for item in values):
                raise CrossSourceIdentityError("invalid complementary rule")
            complementary.add(values)
        elif kind == "DIFFERENT_ASPECT":
            values = tuple(
                sorted((rule.get("left_aspect_key"), rule.get("right_aspect_key")))
            )
            if not all(isinstance(item, str) and item for item in values):
                raise CrossSourceIdentityError("invalid different-aspect rule")
            different_aspect.add(values)
        else:
            raise CrossSourceIdentityError("unknown comparison rule")
    return complementary, different_aspect


def _classify(aspect, members, complementary):
    if len(members) == 1:
        return "SINGLE_SOURCE"
    types = {member.requested.fact_type for member in members}
    if len(types) == 1:
        values = {member.value_digest for member in members}
        return (
            "SAME_ASPECT_SAME_VALUE"
            if len(values) == 1
            else "SAME_ASPECT_DIFFERENT_VALUE"
        )
    pairs = {
        tuple(sorted((left.requested.fact_type, right.requested.fact_type)))
        for index, left in enumerate(members)
        for right in members[index + 1 :]
    }
    return (
        "COMPLEMENTARY" if pairs and pairs.issubset(complementary) else "NOT_COMPARABLE"
    )


def _comparison_payload(kind, key, aspect_key, members):
    return {
        "comparison_key": key,
        "comparison_kind": kind,
        "comparison_revision": COMPARISON_REVISION,
        "aspect_key": aspect_key,
        "members": [
            {
                "source": member.family,
                "input_digest": member.source_input.input_digest,
                "fact_ref": member.fact_ref,
                "value_digest": member.value_digest,
            }
            for member in members
        ],
    }


def _persist_comparison(session, run, aspect_id, aspect_key, key, order, kind, members):
    details = _comparison_payload(kind, key, aspect_key, members)
    value_digest = _digest([member.value for member in members])
    comparison_digest = _digest(details)
    existing = session.scalar(
        select(CrossSourceComparison).where(
            CrossSourceComparison.complete_answer_run_id == run.id,
            CrossSourceComparison.comparison_key == key,
        )
    )
    if existing:
        if existing.comparison_digest != comparison_digest:
            raise CrossSourceIdentityError("comparison identity changed within a run")
        return existing
    comparison = CrossSourceComparison(
        id=str(uuid.uuid4()),
        complete_answer_run_id=run.id,
        requested_aspect_id=aspect_id,
        comparison_key=key,
        comparison_order=order,
        comparison_kind=kind,
        comparison_revision=COMPARISON_REVISION,
        details=details,
        value_digest=value_digest,
        comparison_digest=comparison_digest,
        created_at=datetime.now(timezone.utc),
    )
    session.add(comparison)
    session.flush()
    for member_order, member in enumerate(members):
        session.add(
            CrossSourceComparisonMember(
                comparison_id=comparison.id,
                source_input_id=member.source_input.id,
                fact_resolution_id=member.resolution.id,
                document_family=member.family,
                member_order=member_order,
                fact_ref=member.fact_ref,
                evidence_refs=list(member.evidence_refs),
                normalized_value=member.value,
                normalized_value_digest=member.value_digest,
            )
        )
    session.flush()
    return comparison


def aggregate_cross_source(session, run: CompleteAnswerRun):
    """Build and persist the deterministic 9B context for one complete run."""
    request = run.request
    build = run.build
    if (
        request.corpus_build_id != run.corpus_build_id
        or build.id != run.corpus_build_id
    ):
        raise CrossSourceBuildMismatchError("complete run crosses build boundary")
    complementary, different_aspect = _comparison_rules(request.orchestration_config)
    source_runs = {
        family: _source_plan(session, run, family) for family in SOURCE_ORDER
    }
    for family, source_run in source_runs.items():
        if source_run:
            _validate_source_run(session, run, source_run, family)

    inputs = session.scalars(
        select(CompleteAnswerSourceInput).where(
            CompleteAnswerSourceInput.complete_answer_request_id == request.id
        )
    ).all()
    inputs.sort(key=_stable_input_key)
    aspects = session.scalars(
        select(CompleteAnswerRequestedAspect).where(
            CompleteAnswerRequestedAspect.complete_answer_request_id == request.id
        )
    ).all()
    aspects.sort(key=lambda item: (item.aspect_order, item.aspect_key))

    resolution_map = {}
    for source_run in source_runs.values():
        if not source_run or not source_run.answer_request_id:
            continue
        from .models.answer import AnswerRequestFactResolution

        rows = session.scalars(
            select(FactResolution)
            .join(
                AnswerRequestFactResolution,
                AnswerRequestFactResolution.fact_resolution_id == FactResolution.id,
            )
            .where(
                AnswerRequestFactResolution.answer_request_id
                == source_run.answer_request_id
            )
        ).all()
        for resolution in rows:
            key = (source_run.document_family, resolution.requested_fact_id)
            if key in resolution_map:
                raise CrossSourceMembershipError(
                    "duplicate resolution for source input"
                )
            resolution_map[key] = resolution

    facts = []
    evidence = []
    fact_ref_by_id = {}
    evidence_ref_by_id = {}
    coverage = []
    aspect_members = {}
    for aspect in aspects:
        aspect_coverage = []
        members = []
        aspect_inputs = [
            item for item in inputs if item.requested_aspect_id == aspect.id
        ]
        for family in SOURCE_ORDER:
            family_inputs = [
                item
                for item in aspect_inputs
                if item.request_source.document_family == family
            ]
            source_entry = {"source": family, "inputs": []}
            if not family_inputs:
                source_entry["status"] = "SOURCE_NOT_APPLICABLE"
            elif not source_runs[family]:
                source_entry["status"] = "SOURCE_MATERIALIZATION_UNAVAILABLE"
                for item in family_inputs:
                    source_entry["inputs"].append(
                        {
                            "input_digest": item.input_digest,
                            "status": source_entry["status"],
                        }
                    )
            else:
                statuses = []
                for item in family_inputs:
                    resolution = resolution_map.get((family, item.requested_fact_id))
                    if not resolution:
                        raise CrossSourceMembershipError(
                            "source run omits planned resolution"
                        )
                    requested = session.get(RequestedFact, resolution.requested_fact_id)
                    if not requested or requested.corpus_build_id != build.id:
                        raise CrossSourceBuildMismatchError(
                            "resolution requested fact build mismatch"
                        )
                    if (
                        requested.subject_kind != aspect.subject_kind
                        or requested.subject_key != aspect.subject_key
                    ):
                        raise CrossSourceMembershipError(
                            "requested fact is outside the declared aspect subject"
                        )
                    supported, _ = _authorized_support(session, run, resolution, family)
                    status = resolution.runtime_status
                    entry = {
                        "input_digest": item.input_digest,
                        "fact_digest": requested.request_digest,
                        "status": status,
                        "reason_code": resolution.reason_code,
                    }
                    if status == RuntimeStatus.RESOLVED.value:
                        value = _normalize(resolution.resolved_value)
                        value_digest = _digest(value)
                        if resolution.id not in fact_ref_by_id:
                            fact_ref_by_id[resolution.id] = _next_ref(
                                fact_ref_by_id.values(), family, "F"
                            )
                            facts.append(
                                {
                                    "ref": fact_ref_by_id[resolution.id],
                                    "source": family,
                                    "fact_digest": requested.request_digest,
                                    "fact_type": requested.fact_type,
                                    "subject_kind": requested.subject_kind,
                                    "subject_key": requested.subject_key,
                                    "value": value,
                                    "value_digest": value_digest,
                                }
                            )
                        refs = []
                        for _, unit, target in supported:
                            if unit.id not in evidence_ref_by_id:
                                evidence_ref_by_id[unit.id] = _next_ref(
                                    evidence_ref_by_id.values(), family, "E"
                                )
                                evidence.append(
                                    {
                                        "ref": evidence_ref_by_id[unit.id],
                                        "source": family,
                                        "citation_target": target.stable_key,
                                        "source_local_stable_path": (
                                            target.source_local_stable_path
                                        ),
                                        "human_label": target.human_label,
                                        "content_sha256": unit.rendered_content_sha256,
                                        "rendered_content": unit.rendered_content,
                                    }
                                )
                            refs.append(evidence_ref_by_id[unit.id])
                        member = _ResolvedMember(
                            item,
                            resolution,
                            requested,
                            family,
                            value,
                            value_digest,
                            fact_ref_by_id[resolution.id],
                            tuple(refs),
                            tuple(
                                next(row for row in evidence if row["ref"] == ref)
                                for ref in refs
                            ),
                        )
                        members.append(member)
                        entry["fact_ref"] = member.fact_ref
                        entry["evidence_refs"] = list(member.evidence_refs)
                    statuses.append(status)
                    source_entry["inputs"].append(entry)
                source_entry["status"] = (
                    RuntimeStatus.RESOLVED.value
                    if any(
                        status == RuntimeStatus.RESOLVED.value for status in statuses
                    )
                    else statuses[0]
                )
            aspect_coverage.append(source_entry)
        aspect_members[aspect.id] = members
        coverage.append(
            {
                "aspect_key": aspect.aspect_key,
                "subject_kind": aspect.subject_kind,
                "subject_key": aspect.subject_key,
                "sources": aspect_coverage,
            }
        )

    comparison_rows = []
    comparison_specs = []
    for aspect in aspects:
        members = sorted(
            aspect_members[aspect.id],
            key=lambda item: _stable_input_key(item.source_input),
        )
        if members:
            kind = _classify(aspect, members, complementary)
            key = f"aspect:{aspect.aspect_key}"
            comparison_specs.append((aspect.id, aspect.aspect_key, key, kind, members))
    for left_index, left in enumerate(aspects):
        for right in aspects[left_index + 1 :]:
            pair = tuple(sorted((left.aspect_key, right.aspect_key)))
            if pair not in different_aspect:
                continue
            members = sorted(
                aspect_members[left.id] + aspect_members[right.id],
                key=lambda item: _stable_input_key(item.source_input),
            )
            if members:
                comparison_specs.append(
                    (
                        None,
                        f"{left.aspect_key}|{right.aspect_key}",
                        f"aspects:{pair[0]}|{pair[1]}",
                        "DIFFERENT_ASPECT",
                        members,
                    )
                )
    comparison_specs.sort(key=lambda item: item[2])
    for order, (aspect_id, aspect_key, key, kind, members) in enumerate(
        comparison_specs
    ):
        row = _persist_comparison(
            session, run, aspect_id, aspect_key, key, order, kind, members
        )
        comparison_rows.append(row)
    comparison_ref = {
        row.id: f"X{index}" for index, row in enumerate(comparison_rows, 1)
    }
    comparisons = [
        {
            "ref": comparison_ref[row.id],
            "key": row.comparison_key,
            "kind": row.comparison_kind,
            "aspect_key": row.details.get("aspect_key"),
            "member_refs": [
                {
                    "source": member.document_family,
                    "fact_ref": member.fact_ref,
                    "evidence_refs": member.evidence_refs,
                }
                for member in sorted(row.members, key=lambda item: item.member_order)
            ],
            "value_digest": row.value_digest,
        }
        for row in comparison_rows
    ]
    context = {
        "revision": COMPARISON_REVISION,
        "build_digest": build.build_digest,
        "request_digest": request.request_digest,
        "run_key": run.run_key,
        "facts": sorted(
            facts,
            key=lambda item: (
                SOURCE_ORDER.index(item["source"]),
                int(item["ref"].split(":F", 1)[1]),
            ),
        ),
        "evidence": sorted(
            evidence,
            key=lambda item: (
                SOURCE_ORDER.index(item["source"]),
                int(item["ref"].split(":E", 1)[1]),
            ),
        ),
        "coverage": coverage,
        "comparisons": comparisons,
    }
    context_digest = _digest(context)
    if run.context_digest and run.context_digest != context_digest:
        raise CrossSourceIdentityError("context digest changed within a run")
    run.context_digest = context_digest
    run.updated_at = datetime.now(timezone.utc)
    session.flush()
    return context, context_digest


def serialize_cross_source_context(context) -> str:
    """Canonical JSON serialization used for reproducibility and digest checks."""
    return canonical_json(context)
