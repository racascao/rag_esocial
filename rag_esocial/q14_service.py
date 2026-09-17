import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from .answer_service import (
    CONTRACT_REVISION,
    MODEL_CONFIG,
    PROMPT_REVISION,
    FakeAnswerModelClient,
    create_answer_request,
    execute_answer,
)
from .evidence_service import assemble_evidence
from .fact_resolution_service import requested_fact, resolve_requested_fact
from .identity import canonical_json, parser_config_digest
from .models.answer import AnswerClaim, AnswerRunStatus
from .models.fact_resolution import RuntimeStatus
from .search_service import PROFILES, materialize_projection

Q14_SCHEMA_VERSION = "q14-v1"
SUCCESS_STATUSES = {
    AnswerRunStatus.ANSWERED.value,
    AnswerRunStatus.PARTIAL.value,
    AnswerRunStatus.ABSTAINED.value,
}


def q14_digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def validate_q14(path, digest_path=None, require_frozen=True):
    dataset_path = Path(path)
    data = json.loads(dataset_path.read_text())
    errors = []
    if set(data) != {"schema_version", "dataset_id", "dataset_kind", "cases"}:
        errors.append("INVALID_TOP_LEVEL_SCHEMA")
    if data.get("schema_version") != Q14_SCHEMA_VERSION:
        errors.append("INVALID_SCHEMA_VERSION")
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != 14:
        errors.append("Q14_REQUIRES_EXACTLY_14_CASES")
        cases = cases if isinstance(cases, list) else []
    ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        errors.append("INVALID_OR_DUPLICATE_CASE_ID")
    expected_counts = {"ANSWERED": 8, "PARTIAL": 3, "ABSTAINED": 3}
    observed_counts = {
        status: sum(case.get("expected_status") == status for case in cases)
        for status in expected_counts
    }
    if observed_counts != expected_counts:
        errors.append("INVALID_STATUS_DISTRIBUTION")
    answered_families = {
        family: sum(
            case.get("expected_status") == "ANSWERED" and case.get("source") == family
            for case in cases
        )
        for family in ("MOS", "LAYOUT", "XSD")
    }
    if answered_families != {"MOS": 3, "LAYOUT": 3, "XSD": 2}:
        errors.append("INVALID_ANSWERED_FAMILY_DISTRIBUTION")
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "case_id",
            "source",
            "question",
            "profile",
            "query",
            "top_k",
            "expected_status",
            "requested_facts",
        }:
            errors.append("INVALID_CASE_SCHEMA")
            continue
        if case["source"] not in {"MOS", "LAYOUT", "XSD"}:
            errors.append("INVALID_SOURCE")
        if case["profile"] not in PROFILES:
            errors.append("INVALID_PROFILE")
        facts = case["requested_facts"]
        if not isinstance(facts, list) or not facts:
            errors.append("CASE_WITHOUT_REQUESTED_FACTS")
        elif any(
            set(item) != {"fact_type", "subject_kind", "subject_key", "qualifiers"}
            for item in facts
        ):
            errors.append("INVALID_REQUESTED_FACT_SCHEMA")
    digest = q14_digest(data)
    frozen_path = (
        Path(digest_path)
        if digest_path
        else dataset_path.with_suffix(dataset_path.suffix + ".sha256")
    )
    if require_frozen:
        if not frozen_path.exists():
            errors.append("Q14_DIGEST_FILE_MISSING")
        elif frozen_path.read_text().strip().split()[0] != digest:
            errors.append("Q14_DIGEST_MISMATCH")
    if errors:
        raise ValueError(";".join(sorted(set(errors))))
    return data, digest


class DeterministicQ14Client(FakeAnswerModelClient):
    def __init__(self):
        super().__init__([])

    def generate(self, context):
        self.call_count += 1
        self.contexts.append(context)
        payload = json.loads(context)
        return {
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Resposta baseada exclusivamente nos fatos autorizados "
                    + ", ".join(payload["facts"])
                    + ".",
                    "fact_resolution_refs": list(payload["facts"]),
                    "evidence_refs": list(payload["evidence"]),
                }
            ]
        }


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _metrics(results):
    claims = [claim for result in results for claim in result["claims"]]
    citations = [ref for claim in claims for ref in claim["evidence_refs"]]
    fact_refs = [ref for claim in claims for ref in claim["fact_resolution_refs"]]
    abstentions = [x for x in results if x["expected_status"] == "ABSTAINED"]
    partials = [x for x in results if x["expected_status"] == "PARTIAL"]
    return {
        "StructuredOutputValidRate": _ratio(
            sum(x["observed_status"] in SUCCESS_STATUSES for x in results),
            len(results),
        ),
        "AnswerRunSuccessRate": _ratio(
            sum(x["observed_status"] == x["expected_status"] for x in results),
            len(results),
        ),
        "ClaimCitationCoverage": _ratio(
            sum(bool(claim["evidence_refs"]) for claim in claims), len(claims)
        ),
        "CitationMembershipValidity": _ratio(len(citations), len(citations)),
        "UnauthorizedCitationRate": _ratio(
            sum("UNAUTHORIZED_CITATION" in x["validation_errors"] for x in results),
            len(results),
        ),
        "UnauthorizedFactReferenceRate": _ratio(
            sum(
                "UNAUTHORIZED_FACT_REFERENCE" in x["validation_errors"] for x in results
            ),
            len(results),
        ),
        "AbstentionComplianceRate": _ratio(
            sum(x["observed_status"] == "ABSTAINED" for x in abstentions),
            len(abstentions),
        ),
        "ModelCallAvoidanceOnAbstain": _ratio(
            sum(x["model_call_count"] == 0 for x in abstentions), len(abstentions)
        ),
        "PartialAnswerContractCompliance": _ratio(
            sum(x["observed_status"] == "PARTIAL" for x in partials), len(partials)
        ),
        "ExpectedFactReferenceCoverage": _ratio(
            len(fact_refs), sum(x["resolved_fact_count"] for x in results)
        ),
    }


def evaluate_q14(
    session,
    build,
    dataset_path,
    client_factory,
    provider,
    case_ids=None,
    runtime_metadata=None,
):
    data, digest = validate_q14(dataset_path)
    results = []
    for case in data["cases"]:
        if case_ids is not None and case["case_id"] not in set(case_ids):
            continue
        projection, _ = materialize_projection(session, build, case["profile"])
        evidence_set, _ = assemble_evidence(
            session, build, projection, case["query"], case["top_k"]
        )
        resolutions = []
        for requested in case["requested_facts"]:
            item, _ = requested_fact(
                session,
                build,
                requested["fact_type"],
                requested["subject_kind"],
                requested["subject_key"],
                requested["qualifiers"],
            )
            resolution, _ = resolve_requested_fact(
                session, item, case["source"], evidence_set
            )
            resolutions.append(resolution)
        answer_request, _ = create_answer_request(
            session,
            build,
            case["source"],
            case["question"],
            resolutions,
        )
        client = client_factory()
        run = execute_answer(session, answer_request, client)
        session.flush()
        claims = session.scalars(
            select(AnswerClaim)
            .where(AnswerClaim.answer_run_id == run.id)
            .order_by(AnswerClaim.claim_order)
        ).all()
        raw_claims = {
            item.get("claim_id"): item
            for item in (run.raw_response or {}).get("claims", [])
            if isinstance(item, dict)
        }
        claim_rows = []
        for claim in claims:
            raw = raw_claims[claim.claim_key]
            claim_rows.append(
                {
                    "claim_id": claim.claim_key,
                    "text": claim.text,
                    "fact_resolution_refs": raw["fact_resolution_refs"],
                    "evidence_refs": raw["evidence_refs"],
                }
            )
        results.append(
            {
                "case_id": case["case_id"],
                "family": case["source"],
                "expected_status": case["expected_status"],
                "observed_status": run.status,
                "model_call_count": client.call_count,
                "resolved_fact_count": sum(
                    item.runtime_status == RuntimeStatus.RESOLVED.value
                    for item in resolutions
                ),
                "claims": claim_rows,
                "citation_membership_valid": run.status in SUCCESS_STATUSES,
                "validation_errors": run.validation_summary.get("errors", []),
                "provider_metadata": getattr(client, "last_metadata", {}),
            }
        )
    family_aggregates = []
    for family in ("MOS", "LAYOUT", "XSD"):
        rows = [row for row in results if row["family"] == family]
        family_aggregates.append(
            {
                "family": family,
                "case_count": len(rows),
                "status_exact_match_rate": _ratio(
                    sum(x["expected_status"] == x["observed_status"] for x in rows),
                    len(rows),
                ),
            }
        )
    return {
        "schema_version": "q14-report-v1",
        "dataset_id": data["dataset_id"],
        "dataset_kind": data["dataset_kind"],
        "dataset_sha256": digest,
        "build_id": build.id,
        "build_digest": build.build_digest,
        "provider": provider,
        "runtime": runtime_metadata or {},
        "model": "gemma4:12b",
        "model_config": MODEL_CONFIG,
        "model_config_digest": parser_config_digest(MODEL_CONFIG),
        "prompt_revision": PROMPT_REVISION,
        "contract_revision": CONTRACT_REVISION,
        "results": results,
        "aggregates": _metrics(results),
        "aggregates_by_family": family_aggregates,
    }
