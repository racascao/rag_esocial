# ruff: noqa: E501
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, text

from .evidence_service import assemble_evidence
from .fact_resolution_service import requested_fact, resolve_requested_fact
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.evidence import EvidenceSetItem, EvidenceUnit
from .models.fact_resolution import RuntimeStatus
from .models.search import SearchProjection
from .search_service import materialize_projection


def load_dataset(path):
    value = json.loads(Path(path).read_text())
    digest = hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    return value, digest


def _targets(session, build, identities, case_id):
    result = []
    for identity in identities:
        rows = session.scalars(
            select(CitationTarget)
            .join(CorpusBuildCitationTarget)
            .where(
                CorpusBuildCitationTarget.build_id == build.id,
                CitationTarget.document_family == identity["document_family"],
                CitationTarget.source_local_stable_path
                == identity["source_local_stable_path"],
            )
        ).all()
        if len(rows) != 1:
            raise ValueError(f"GOLD_TARGET_NOT_IN_BUILD:{case_id}:{identity}")
        result.append(rows[0].id)
    return set(result)


def evaluate_retrieval_evidence(session, build, dataset_path):
    data, digest = load_dataset(dataset_path)
    results = []
    for case in data["cases"]:
        required = _targets(
            session, build, case["required_citation_targets"], case["case_id"]
        )
        acceptable = _targets(
            session, build, case.get("acceptable_context_targets", []), case["case_id"]
        )
        for profile in case["applicable_profiles"]:
            projection, _ = materialize_projection(session, build, profile)
            rows = (
                session.execute(
                    text(
                        "SELECT id, root_citation_target_id, ts_rank_cd(search_vector, websearch_to_tsquery('simple', :q)) score FROM search_units WHERE search_projection_id=:p AND search_vector @@ websearch_to_tsquery('simple', :q) ORDER BY score DESC, source_local_stable_path ASC"
                    ),
                    {"q": case["query"], "p": projection.id},
                )
                .mappings()
                .all()
            )
            hit_targets = [row["root_citation_target_id"] for row in rows]
            first = next(
                (
                    index + 1
                    for index, target in enumerate(hit_targets)
                    if target in required
                ),
                None,
            )
            evidence_set, _ = assemble_evidence(
                session, build, projection, case["query"], max(case["k_values"])
            )
            assembled = set(
                session.scalars(
                    select(EvidenceUnit.citation_target_id)
                    .join(EvidenceSetItem)
                    .where(EvidenceSetItem.evidence_set_id == evidence_set.id)
                ).all()
            )
            metrics = {}
            for k in case["k_values"]:
                metrics[f"retrieval_target_recall_at_{k}"] = len(
                    required & set(hit_targets[:k])
                ) / len(required)
            metrics.update(
                {
                    "mrr": 1 / first if first else 0,
                    "evidence_required_recall": len(required & assembled)
                    / len(required),
                    "evidence_target_precision": len(
                        assembled & (required | acceptable)
                    )
                    / len(assembled)
                    if assembled
                    else None,
                    "all_required_covered": required <= assembled,
                    "retrieval_candidate_count": len(hit_targets),
                    "assembled_target_count": len(assembled),
                }
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "family": case["family"],
                    "profile": profile,
                    "metrics": metrics,
                }
            )
    aggregates = {}
    for result in results:
        key = f"{result['family']}:{result['profile']}"
        bucket = aggregates.setdefault(
            key,
            {
                "family": result["family"],
                "profile": result["profile"],
                "case_count": 0,
                "mrr_total": 0.0,
                "recall_total": 0.0,
                "full_coverage_count": 0,
            },
        )
        bucket["case_count"] += 1
        bucket["mrr_total"] += result["metrics"]["mrr"]
        bucket["recall_total"] += result["metrics"]["evidence_required_recall"]
        bucket["full_coverage_count"] += int(result["metrics"]["all_required_covered"])
    for bucket in aggregates.values():
        count = bucket["case_count"]
        bucket["mrr"] = bucket.pop("mrr_total") / count
        bucket["evidence_required_recall"] = bucket.pop("recall_total") / count
        bucket["full_coverage_rate"] = bucket["full_coverage_count"] / count
    return {
        "dataset_id": data["dataset_id"],
        "dataset_sha256": digest,
        "dataset_kind": data["dataset_kind"],
        "build_id": build.id,
        "results": results,
        "aggregates": list(aggregates.values()),
    }


def write_report(report, output_path):
    Path(output_path).write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )


def _expected_runtime(case):
    return case.get(
        "expected_runtime_status",
        {
            "COVERED": RuntimeStatus.RESOLVED.value,
            "SOURCE_NOT_APPLICABLE": RuntimeStatus.SOURCE_NOT_APPLICABLE.value,
            "ASPECT_NOT_COVERED": RuntimeStatus.ASPECT_NOT_COVERED.value,
            "CORPUS_UNSUPPORTED": RuntimeStatus.UNSUPPORTED.value,
        }[case["gold_coverage_state"]],
    )


def evaluate_fact_resolution_status(session, build, dataset_path):
    data, digest = load_dataset(dataset_path)
    results = []
    for case in data["cases"]:
        request = case["requested_fact"]
        item, _ = requested_fact(
            session,
            build,
            request["fact_type"],
            request["subject_kind"],
            request["subject_key"],
            request.get("qualifiers", {}),
        )
        evidence_set = None
        if case.get("profile"):
            projection = session.scalar(
                select(SearchProjection).where(
                    SearchProjection.corpus_build_id == build.id,
                    SearchProjection.profile == case["profile"],
                )
            )
            if not projection:
                raise ValueError(f"PROJECTION_NOT_MATERIALIZED:{case['case_id']}")
            evidence_set, _ = assemble_evidence(
                session, build, projection, case["query"], case.get("top_k", 5)
            )
        resolution, _ = resolve_requested_fact(
            session, item, case["source"], evidence_set
        )
        expected_runtime = _expected_runtime(case)
        value_match = (
            resolution.resolved_value == case.get("expected_value")
            if resolution.runtime_status == RuntimeStatus.RESOLVED.value
            and "expected_value" in case
            else None
        )
        results.append(
            {
                "case_id": case["case_id"],
                "gold_coverage_state": case["gold_coverage_state"],
                "expected_runtime_status": expected_runtime,
                "runtime_status": resolution.runtime_status,
                "resolved_value": resolution.resolved_value,
                "value_exact_match": value_match,
                "resolution_id": resolution.id,
            }
        )
    covered = [row for row in results if row["gold_coverage_state"] == "COVERED"]
    resolved = [
        row for row in covered if row["runtime_status"] == RuntimeStatus.RESOLVED.value
    ]
    counts = {}
    runtime_counts = {}
    for row in results:
        counts[f"{row['gold_coverage_state']}:{row['runtime_status']}"] = (
            counts.get(f"{row['gold_coverage_state']}:{row['runtime_status']}", 0) + 1
        )
        runtime_counts[row["runtime_status"]] = (
            runtime_counts.get(row["runtime_status"], 0) + 1
        )
    aggregates = {
        "CoveredFactResolutionRecall": sum(
            bool(row["value_exact_match"]) for row in covered
        )
        / len(covered)
        if covered
        else None,
        "ResolvedValueExactMatch": sum(
            bool(row["value_exact_match"]) for row in resolved
        )
        / len(resolved)
        if resolved
        else None,
        "RuntimeStatusExactMatch": sum(
            row["runtime_status"] == row["expected_runtime_status"] for row in results
        )
        / len(results)
        if results
        else None,
        "NoRelevantEvidenceRateOnCovered": sum(
            row["runtime_status"] == RuntimeStatus.NO_RELEVANT_EVIDENCE.value
            for row in covered
        )
        / len(covered)
        if covered
        else None,
    }
    return {
        "schema_version": "fact-resolution-status-v1",
        "dataset_id": data["dataset_id"],
        "dataset_kind": data["dataset_kind"],
        "dataset_sha256": digest,
        "build_id": build.id,
        "build_digest": build.build_digest,
        "resolver_revision": "fact-resolver-v1",
        "results": results,
        "aggregates": aggregates,
        "confusion_counts": counts,
        "runtime_status_counts": runtime_counts,
    }
