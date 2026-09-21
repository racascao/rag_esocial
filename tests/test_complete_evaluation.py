import json
from pathlib import Path

import pytest

from rag_esocial.complete_evaluation_service import (
    CompleteBenchmarkError,
    build_human_review_template,
    evaluate_complete_fake,
    validate_complete_benchmark,
    validate_evaluation_report,
)
from rag_esocial.q14_service import q14_digest

BENCHMARK = Path("evaluation/complete/complete_v1.json")


def test_complete_benchmark_v1_is_frozen_and_covers_matrix():
    dataset, digest = validate_complete_benchmark(BENCHMARK)
    assert len(dataset["cases"]) == 26
    assert digest == "ee18fa66904fe874e13c3b342c93c58c0078ba9d1c4c36b2b6184e438ab013bc"
    assert {case["category"] for case in dataset["cases"]} == {
        case["category"] for case in dataset["cases"]
    }


def test_complete_benchmark_rejects_duplicate_ids_and_gold_overlap(tmp_path):
    dataset = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    dataset["cases"][1]["case_id"] = dataset["cases"][0]["case_id"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    with pytest.raises(CompleteBenchmarkError, match="INVALID_OR_DUPLICATE_CASE_ID"):
        validate_complete_benchmark(path, require_frozen=False)

    dataset = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    dataset["cases"][0]["gold"]["forbidden_fact_refs"] = ["MOS:F1"]
    path.write_text(json.dumps(dataset), encoding="utf-8")
    with pytest.raises(CompleteBenchmarkError, match="EXPECTED_FORBIDDEN_OVERLAP_FACT"):
        validate_complete_benchmark(path, require_frozen=False)


def test_complete_fake_report_is_deterministic_and_has_structural_gates(tmp_path):
    first = evaluate_complete_fake(BENCHMARK, tmp_path / "first.json")
    second = evaluate_complete_fake(BENCHMARK, tmp_path / "second.json")
    assert first == second
    assert first["aggregates"]["fake"]["gate_pass"] is True
    assert first["gates"]["unauthorized_fact_refs"] == 0
    assert first["gates"]["unauthorized_evidence_refs"] == 0
    assert first["gates"]["unauthorized_comparison_refs"] == 0
    assert first["gates"]["all_no_fact_zero_calls"] is True
    assert first["human_review"]["status"] == "NOT_REVIEWED"
    assert validate_evaluation_report(tmp_path / "first.json")["report_sha256"]


def test_complete_human_review_template_is_unfilled(tmp_path):
    target = tmp_path / "review.json"
    template = build_human_review_template(BENCHMARK, target)
    assert template["reviewer_status"] == "NOT_REVIEWED"
    assert all(item["overall_human_pass"] is None for item in template["cases"])
    assert len(template["cases"]) == 26


def test_q14_digest_and_file_are_unchanged():
    dataset = json.loads(Path("evaluation/q14/q14_v1.json").read_text())
    assert q14_digest(dataset) == (
        "30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7"
    )
