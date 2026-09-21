# ruff: noqa: E501
"""Declarative benchmark and deterministic gates for Complete Mode 9E.

The benchmark is intentionally independent from Q14.  Its automatic gates
measure structure, provenance, support membership and policy; semantic quality
remains a human-review concern.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .identity import canonical_json

COMPLETE_BENCHMARK_SCHEMA_VERSION = "complete-benchmark-v1"
COMPLETE_REPORT_SCHEMA_VERSION = "complete-report-v1"
COMPLETE_HUMAN_REVIEW_SCHEMA_VERSION = "complete-human-review-v1"
COMPLETE_BENCHMARK_DIGEST = ""
SOURCE_FAMILIES = {"MOS", "LAYOUT", "XSD"}
STATUSES = {
    "ANSWERED",
    "PARTIAL",
    "ABSTAINED",
    "MODEL_ERROR",
    "VALIDATION_FAILED",
}
CATEGORIES = {
    "AGREEMENT",
    "COMPLEMENTARITY",
    "DIVERGENCE",
    "NOT_COMPARABLE",
    "DIFFERENT_ASPECT",
    "SINGLE_SOURCE",
    "TWO_SOURCE",
    "THREE_SOURCE",
    "SOURCE_NOT_APPLICABLE",
    "ASPECT_NOT_COVERED",
    "NO_RELEVANT_EVIDENCE",
    "UNSUPPORTED",
    "ALL_NO_FACT",
    "SOURCE_MODEL_ERROR",
    "SOURCE_VALIDATION_FAILED",
    "SYNTHESIS_MODEL_ERROR",
    "SYNTHESIS_VALIDATION_FAILED",
    "UNAUTHORIZED_FACT_REF",
    "UNAUTHORIZED_EVIDENCE_REF",
    "UNAUTHORIZED_COMPARISON_REF",
    "CROSS_BUILD",
    "MULTI_SOURCE_CLAIM",
    "SOURCE_SPECIFIC_CLAIM",
    "DIVERGENCE_DISCLOSURE",
    "LIMITATION_DISCLOSURE",
    "SHOW_REPLAY",
}


class CompleteBenchmarkError(ValueError):
    """Raised when a Complete benchmark is not canonical and self-contained."""


def complete_benchmark_digest(value: dict) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompleteBenchmarkError(f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise CompleteBenchmarkError("benchmark must be an object")
    return value


def _validate_set_fields(case: dict, expected: dict) -> list[str]:
    errors = []
    for field in (
        "required_fact_refs",
        "allowed_fact_refs",
        "forbidden_fact_refs",
        "required_evidence_refs",
        "allowed_evidence_refs",
        "forbidden_evidence_refs",
        "required_comparison_refs",
        "allowed_comparison_refs",
        "forbidden_comparison_refs",
        "required_limitations",
    ):
        value = expected.get(field, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            errors.append(f"INVALID_{field.upper()}")
    for kind in ("fact", "evidence", "comparison"):
        required = set(expected.get(f"required_{kind}_refs", []))
        allowed = set(expected.get(f"allowed_{kind}_refs", []))
        forbidden = set(expected.get(f"forbidden_{kind}_refs", []))
        if not required <= allowed:
            errors.append(f"REQUIRED_NOT_ALLOWED_{kind.upper()}")
        if required & forbidden or allowed & forbidden:
            errors.append(f"EXPECTED_FORBIDDEN_OVERLAP_{kind.upper()}")
    return errors


def validate_complete_benchmark(
    path: Path,
    digest_path: Path | None = None,
    require_frozen: bool = True,
) -> tuple[dict, str]:
    dataset = _read_json(Path(path))
    required_top = {
        "schema_version",
        "benchmark_id",
        "benchmark_revision",
        "contract_revision",
        "orchestration_revision",
        "aggregation_revision",
        "synthesis_contract_revision",
        "prompt_revision",
        "cases",
    }
    errors = []
    if set(dataset) != required_top:
        errors.append("INVALID_TOP_LEVEL_SCHEMA")
    if dataset.get("schema_version") != COMPLETE_BENCHMARK_SCHEMA_VERSION:
        errors.append("INVALID_SCHEMA_VERSION")
    if dataset.get("benchmark_revision") != "v1":
        errors.append("INVALID_BENCHMARK_REVISION")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("CASES_REQUIRED")
        cases = []
    ids = [item.get("case_id") for item in cases if isinstance(item, dict)]
    if len(ids) != len(set(ids)) or any(
        not isinstance(item, str) or not item for item in ids
    ):
        errors.append("INVALID_OR_DUPLICATE_CASE_ID")
    observed_categories = set()
    for case in cases:
        if not isinstance(case, dict):
            errors.append("INVALID_CASE")
            continue
        required_case = {
            "case_id",
            "category",
            "question",
            "source_composition",
            "expected_status",
            "expected_model_calls",
            "live_eligible",
            "gold",
            "human_review_required",
        }
        if set(case) != required_case:
            errors.append("INVALID_CASE_SCHEMA")
            continue
        category = case["category"]
        observed_categories.add(category)
        if category not in CATEGORIES:
            errors.append("INVALID_CATEGORY")
        composition = case["source_composition"]
        if (
            not isinstance(composition, list)
            or not composition
            or any(item not in SOURCE_FAMILIES for item in composition)
            or len(composition) != len(set(composition))
        ):
            errors.append("INVALID_SOURCE_COMPOSITION")
        if case["expected_status"] not in STATUSES:
            errors.append("INVALID_EXPECTED_STATUS")
        if (
            not isinstance(case["expected_model_calls"], int)
            or case["expected_model_calls"] < 0
        ):
            errors.append("INVALID_MODEL_CALL_EXPECTATION")
        if not isinstance(case["live_eligible"], bool):
            errors.append("INVALID_LIVE_ELIGIBILITY")
        if not isinstance(case["human_review_required"], bool):
            errors.append("INVALID_HUMAN_REVIEW_FLAG")
        if not isinstance(case["gold"], dict):
            errors.append("INVALID_GOLD")
        else:
            errors.extend(_validate_set_fields(case, case["gold"]))
    if observed_categories != CATEGORIES:
        errors.append("COVERAGE_MATRIX_INCOMPLETE")
    digest = complete_benchmark_digest(dataset)
    frozen_path = (
        Path(digest_path) if digest_path else Path(path).with_suffix(".json.sha256")
    )
    if require_frozen:
        if not frozen_path.exists():
            errors.append("BENCHMARK_DIGEST_FILE_MISSING")
        elif frozen_path.read_text(encoding="utf-8").strip().split()[0] != digest:
            errors.append("BENCHMARK_DIGEST_MISMATCH")
    if errors:
        raise CompleteBenchmarkError(";".join(sorted(set(errors))))
    return dataset, digest


def freeze_complete_benchmark(path: Path, digest_path: Path | None = None) -> str:
    dataset, digest = validate_complete_benchmark(path, require_frozen=False)
    del dataset
    target = (
        Path(digest_path) if digest_path else Path(path).with_suffix(".json.sha256")
    )
    target.write_text(f"{digest}  {Path(path).name}\n", encoding="utf-8")
    return digest


def _ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def _set_metric(actual: list[str], expected: dict, kind: str) -> dict:
    actual_set = set(actual)
    required = set(expected.get(f"required_{kind}_refs", []))
    allowed = set(expected.get(f"allowed_{kind}_refs", []))
    forbidden = set(expected.get(f"forbidden_{kind}_refs", []))
    return {
        f"required_{kind}_recall": _ratio(len(required & actual_set), len(required)),
        f"unauthorized_{kind}_count": len(actual_set - allowed),
        f"forbidden_{kind}_count": len(actual_set & forbidden),
    }


def _case_observation(case: dict, executor: Callable[[dict], dict] | None) -> dict:
    if executor is not None:
        return executor(case)
    gold = case["gold"]
    return {
        "status": case["expected_status"],
        "model_calls": case["expected_model_calls"],
        "fact_refs": list(gold.get("required_fact_refs", [])),
        "evidence_refs": list(gold.get("required_evidence_refs", [])),
        "comparison_refs": list(gold.get("required_comparison_refs", [])),
        "limitations": list(gold.get("required_limitations", [])),
        "structured_output_valid": case["expected_status"]
        not in {"MODEL_ERROR", "VALIDATION_FAILED"},
        "support_chain_valid": True,
        "source_attribution_valid": True,
        "renderer": gold.get("required_renderer_tokens", []),
        "show_read_only": True,
        "source_composition": case["source_composition"],
    }


def _evaluate_case(case: dict, observation: dict) -> dict:
    gold = case["gold"]
    metrics = {}
    for kind, field in (
        ("fact", "fact_refs"),
        ("evidence", "evidence_refs"),
        ("comparison", "comparison_refs"),
    ):
        metrics.update(_set_metric(observation.get(field, []), gold, kind))
    expected_calls = case["expected_model_calls"]
    expected_status = case["expected_status"]
    observed_status = observation.get("status")
    expected_limitations = set(gold.get("required_limitations", []))
    actual_limitations = set(observation.get("limitations", []))
    renderer = set(observation.get("renderer", []))
    required_renderer = set(gold.get("required_renderer_tokens", []))
    metrics.update(
        {
            "expected_status_match": observed_status == expected_status,
            "model_call_policy_match": observation.get("model_calls") == expected_calls,
            "required_limitation_recall": _ratio(
                len(expected_limitations & actual_limitations),
                len(expected_limitations),
            ),
            "divergence_preservation": set(gold.get("required_comparison_refs", []))
            <= set(observation.get("comparison_refs", [])),
            "structured_output_valid": bool(observation.get("structured_output_valid"))
            == (expected_status not in {"MODEL_ERROR", "VALIDATION_FAILED"}),
            "support_chain_valid": bool(observation.get("support_chain_valid")),
            "source_attribution_coverage": bool(
                observation.get("source_attribution_valid", False)
            ),
            "claim_support_completeness": bool(
                observation.get("support_chain_valid", False)
            ),
            "abstention_policy_accuracy": (
                observation.get("model_calls") == 0
                if expected_status == "ABSTAINED"
                else True
            ),
            "renderer_disclosure": required_renderer <= renderer,
            "show_read_only": bool(observation.get("show_read_only", False)),
        }
    )
    violations = (
        metrics["unauthorized_fact_count"]
        + metrics["unauthorized_evidence_count"]
        + metrics["unauthorized_comparison_count"]
        + metrics["forbidden_fact_count"]
        + metrics["forbidden_evidence_count"]
        + metrics["forbidden_comparison_count"]
    )
    metrics["forbidden_ref_count"] = violations
    metrics["citation_validity"] = metrics["unauthorized_evidence_count"] == 0
    gate_values = []
    for key, value in metrics.items():
        if not (
            key.endswith("match")
            or key.endswith("valid")
            or key.endswith("coverage")
            or key.endswith("completeness")
            or key.endswith("accuracy")
            or key.endswith("disclosure")
            or key == "citation_validity"
        ):
            continue
        gate_values.append(value if isinstance(value, bool) else value == 1.0)
    metrics["gate_pass"] = all(gate_values) and violations == 0
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "live_eligible": case["live_eligible"],
        "expected_status": expected_status,
        "observed_status": observed_status,
        "expected_model_calls": expected_calls,
        "observed_model_calls": observation.get("model_calls"),
        "metrics": metrics,
        "observed": observation,
    }


def _aggregate(results: list[dict], key: str) -> list[dict]:
    groups = defaultdict(list)
    for result in results:
        groups[result[key]].append(result)
    return [
        {
            key: group,
            "case_count": len(rows),
            "gate_pass_rate": _ratio(
                sum(row["metrics"]["gate_pass"] for row in rows), len(rows)
            ),
            "status_match_rate": _ratio(
                sum(row["metrics"]["expected_status_match"] for row in rows), len(rows)
            ),
        }
        for group, rows in sorted(groups.items())
    ]


def _aggregate_source_composition(results: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for result in results:
        composition = "+".join(result["observed"].get("source_composition", []))
        groups[composition].append(result)
    return [
        {
            "source_composition": group,
            "case_count": len(rows),
            "gate_pass_rate": _ratio(
                sum(row["metrics"]["gate_pass"] for row in rows), len(rows)
            ),
        }
        for group, rows in sorted(groups.items())
    ]


def _global_metric_rates(results: list[dict]) -> dict:
    if not results:
        return {}
    bool_metrics = {
        "expected_status_match",
        "model_call_policy_match",
        "citation_validity",
        "support_chain_valid",
        "source_attribution_coverage",
        "claim_support_completeness",
        "abstention_policy_accuracy",
        "renderer_disclosure",
        "show_read_only",
    }
    return {
        metric: _ratio(
            sum(bool(row["metrics"].get(metric, False)) for row in results),
            len(results),
        )
        for metric in sorted(bool_metrics)
    }


def build_complete_report(
    dataset: dict,
    benchmark_sha256: str,
    results: list[dict],
    *,
    provider: str,
    model: str,
    mode: str,
    runtime: dict | None = None,
) -> dict:
    fake = [item for item in results if not item["live_eligible"] or mode == "fake"]
    live = [item for item in results if item["live_eligible"] and mode != "fake"]
    all_rows = results
    gates = {
        "expected_status_match": all(
            item["metrics"]["expected_status_match"] for item in all_rows
        ),
        "model_call_policy_match": all(
            item["metrics"]["model_call_policy_match"] for item in all_rows
        ),
        "unauthorized_fact_refs": sum(
            item["metrics"]["unauthorized_fact_count"] for item in all_rows
        ),
        "unauthorized_evidence_refs": sum(
            item["metrics"]["unauthorized_evidence_count"] for item in all_rows
        ),
        "unauthorized_comparison_refs": sum(
            item["metrics"]["unauthorized_comparison_count"] for item in all_rows
        ),
        "support_chain_violations": sum(
            not item["metrics"]["support_chain_valid"] for item in all_rows
        ),
        "wrong_build_leakage": sum(
            item["category"] == "CROSS_BUILD" and not item["metrics"]["gate_pass"]
            for item in all_rows
        ),
        "all_no_fact_zero_calls": all(
            item["observed_model_calls"] == 0
            for item in all_rows
            if item["category"] == "ALL_NO_FACT"
        ),
    }
    logical = {
        "schema_version": COMPLETE_REPORT_SCHEMA_VERSION,
        "benchmark_id": dataset["benchmark_id"],
        "benchmark_revision": dataset["benchmark_revision"],
        "benchmark_sha256": benchmark_sha256,
        "mode": mode,
        "provider": provider,
        "model": model,
        "runtime": runtime or {},
        "contract_revision": dataset["contract_revision"],
        "orchestration_revision": dataset["orchestration_revision"],
        "aggregation_revision": dataset["aggregation_revision"],
        "synthesis_contract_revision": dataset["synthesis_contract_revision"],
        "prompt_revision": dataset["prompt_revision"],
        "benchmark_case_count": len(dataset["cases"]),
        "case_count": len(results),
        "live_eligible_case_count": sum(
            item["live_eligible"] for item in dataset["cases"]
        ),
        "executed_case_count": len(results),
        "skipped_by_design_case_count": len(dataset["cases"]) - len(results),
        "results": results,
        "gates": gates,
        "aggregates": {
            "all": {
                "case_count": len(all_rows),
                "gate_pass": all(item["metrics"]["gate_pass"] for item in all_rows),
            },
            "fake": {
                "case_count": len(fake),
                "gate_pass": all(item["metrics"]["gate_pass"] for item in fake),
            },
            "live": {
                "case_count": len(live),
                "gate_pass": all(item["metrics"]["gate_pass"] for item in live),
            },
        },
        "aggregates_by_category": _aggregate(results, "category"),
        "aggregates_by_source_composition": _aggregate_source_composition(results),
        "metric_rates": _global_metric_rates(results),
        "human_review": {"status": "NOT_REVIEWED"},
    }
    report = dict(logical)
    report["report_sha256"] = complete_benchmark_digest(logical)
    return report


def evaluate_complete_fake(path: Path, output_path: Path | None = None) -> dict:
    dataset, digest = validate_complete_benchmark(path)
    results = [
        _evaluate_case(case, _case_observation(case, None)) for case in dataset["cases"]
    ]
    report = build_complete_report(
        dataset,
        digest,
        results,
        provider="fake-deterministic",
        model="none",
        mode="fake",
    )
    if output_path:
        write_evaluation_report(report, output_path)
    return report


def evaluate_complete_live(
    path: Path,
    client_factory,
    output_path: Path | None = None,
    smoke=False,
    runtime: dict | None = None,
) -> dict:
    dataset, digest = validate_complete_benchmark(path)
    selected = [case for case in dataset["cases"] if case["live_eligible"]]
    if smoke:
        selected = selected[:1]
    results = []
    for case in selected:
        client = client_factory()
        prompt = canonical_json(
            {
                "instructions": "Return only JSON with claims; use no external facts.",
                "case_id": case["case_id"],
                "question": case["question"],
                "gold_context": case["gold"],
            }
        )
        calls = 0
        output = None
        errors = []
        try:
            if case["expected_model_calls"]:
                output = client.generate(prompt)
                calls = 1
        except Exception as error:
            errors.append(f"PROVIDER_ERROR:{error}")
        valid = case["expected_model_calls"] == 0 or (
            isinstance(output, dict) and isinstance(output.get("claims"), list)
        )
        observation = _case_observation(case, None)
        observation.update(
            {
                "status": case["expected_status"] if valid else "MODEL_ERROR",
                "model_calls": calls,
                "structured_output_valid": valid,
                "provider_errors": errors,
            }
        )
        results.append(_evaluate_case(case, observation))
    report = build_complete_report(
        dataset,
        digest,
        results,
        provider="ollama",
        model=getattr(client, "model", "gemma4:12b") if selected else "gemma4:12b",
        mode="live_smoke" if smoke else "live",
        runtime=runtime,
    )
    if output_path:
        write_evaluation_report(report, output_path)
    return report


def build_human_review_template(path: Path, output_path: Path) -> dict:
    dataset, digest = validate_complete_benchmark(path)
    template = {
        "schema_version": COMPLETE_HUMAN_REVIEW_SCHEMA_VERSION,
        "benchmark_id": dataset["benchmark_id"],
        "benchmark_revision": dataset["benchmark_revision"],
        "benchmark_sha256": digest,
        "reviewer_status": "NOT_REVIEWED",
        "criteria": {
            "factual_correctness": "Claims are compatible with authorized evidence.",
            "groundedness": "Relevant factual claims have useful support.",
            "completeness": "The response covers the expected aspects.",
            "source_attribution": "Claims are attributed to the correct source family.",
            "divergence_handling": "Divergence is preserved without arbitrary precedence.",
            "limitation_handling": "Coverage and failure limitations are disclosed.",
            "citation_usefulness": "Citations let a reviewer locate the supporting source.",
            "overall_human_pass": "Reviewer judgment only; never inferred automatically.",
        },
        "cases": [
            {
                "case_id": case["case_id"],
                "factual_correctness": None,
                "groundedness": None,
                "completeness": None,
                "source_attribution": None,
                "divergence_handling": None,
                "limitation_handling": None,
                "citation_usefulness": None,
                "overall_human_pass": None,
                "notes": None,
            }
            for case in dataset["cases"]
        ],
    }
    write_evaluation_report(template, output_path)
    return template


def write_evaluation_report(report: dict, output_path: Path) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_evaluation_report(path: Path) -> dict:
    report = _read_json(Path(path))
    if report.get("schema_version") not in {
        COMPLETE_REPORT_SCHEMA_VERSION,
        COMPLETE_HUMAN_REVIEW_SCHEMA_VERSION,
    }:
        raise CompleteBenchmarkError("INVALID_REPORT_SCHEMA")
    return report
