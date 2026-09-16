# ruff: noqa: E501
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, text

from .evidence_service import assemble_evidence
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.evidence import EvidenceSetItem, EvidenceUnit
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
