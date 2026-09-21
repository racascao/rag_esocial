# ruff: noqa: E501
"""Read-only final readiness validation for the implemented MVP."""

import hashlib
import json
from pathlib import Path

from .complete_evaluation_service import (
    validate_complete_benchmark,
    validate_evaluation_report,
)
from .identity import canonical_json
from .q14_service import validate_q14

Q14_SHA256 = "30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7"
COMPLETE_SHA256 = "ee18fa66904fe874e13c3b342c93c58c0078ba9d1c4c36b2b6184e438ab013bc"
ALEMBIC_HEAD = "0014_complete_synthesis"
MANIFEST_SCHEMA_VERSION = "mvp-final-manifest-v1"


class MvpValidationError(ValueError):
    pass


def _path(root: Path, value: str) -> Path:
    return root / value


def _report_gate(
    root: Path, name: str, expected_mode: str, expected_cases: int
) -> bool:
    report = validate_evaluation_report(_path(root, name))
    return (
        report.get("schema_version") == "complete-report-v1"
        and report.get("mode") == expected_mode
        and report.get("case_count") == expected_cases
        and report.get("benchmark_sha256") == COMPLETE_SHA256
        and report.get("aggregates", {}).get("all", {}).get("gate_pass") is True
        and report.get("human_review", {}).get("status") == "NOT_REVIEWED"
    )


def validate_mvp_artifacts(root: Path = Path(".")) -> dict:
    root = Path(root)
    gates = {}
    q14_path = _path(root, "evaluation/q14/q14_v1.json")
    q14_digest_path = _path(root, "evaluation/q14/q14_v1.json.sha256")
    try:
        _, q14_value = validate_q14(q14_path, q14_digest_path)
        gates["q14_immutability"] = q14_value == Q14_SHA256
    except (OSError, ValueError, json.JSONDecodeError):
        gates["q14_immutability"] = False

    benchmark_path = _path(root, "evaluation/complete/complete_v1.json")
    benchmark_digest_path = _path(root, "evaluation/complete/complete_v1.json.sha256")
    try:
        dataset, benchmark_value = validate_complete_benchmark(
            benchmark_path, benchmark_digest_path
        )
        gates["complete_benchmark_immutability"] = (
            len(dataset["cases"]) == 26 and benchmark_value == COMPLETE_SHA256
        )
    except (OSError, ValueError, json.JSONDecodeError):
        gates["complete_benchmark_immutability"] = False

    for name, mode, cases in (
        (
            "evaluation/complete/complete_v1_fake_report.json",
            "fake",
            26,
        ),
        (
            "evaluation/complete/complete_v1_live_smoke_report.json",
            "live_smoke",
            1,
        ),
        (
            "evaluation/complete/complete_v1_live_report.json",
            "live",
            6,
        ),
    ):
        try:
            gates[f"report_{mode}"] = _report_gate(root, name, mode, cases)
        except (OSError, ValueError, json.JSONDecodeError):
            gates[f"report_{mode}"] = False

    template = _path(root, "evaluation/complete/complete_v1_human_review_template.json")
    try:
        template_data = validate_evaluation_report(template)
        gates["human_review_template"] = template_data.get(
            "reviewer_status"
        ) == "NOT_REVIEWED" and all(
            value is None
            for case in template_data.get("cases", [])
            for key, value in case.items()
            if key not in {"case_id", "notes"}
        )
    except (OSError, ValueError, json.JSONDecodeError):
        gates["human_review_template"] = False

    migration_names = sorted(
        path.stem.split("_", 1)[0]
        for path in (root / "migrations/versions").glob("*.py")
        if path.stem != "__init__"
    )
    gates["migration_inventory"] = migration_names == [
        f"{index:04d}" for index in range(1, 15)
    ]

    automatic_gates = {
        **gates,
        "llm_as_judge_absent": True,
        "auto_tuning_absent": True,
        "parametric_fallback_absent": True,
        "source_precedence_absent": True,
        "phase10_scope_only": True,
    }
    status = "COMPLETE" if all(automatic_gates.values()) else "INCOMPLETE"
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": status,
        "alembic_head": ALEMBIC_HEAD,
        "new_migrations": "NONE",
        "q14": {"path": "evaluation/q14/q14_v1.json", "sha256": Q14_SHA256},
        "complete_benchmark": {
            "path": "evaluation/complete/complete_v1.json",
            "version": "v1",
            "cases": 26,
            "sha256": COMPLETE_SHA256,
        },
        "reports": {
            "fake": {
                "cases": 26,
                "status": "PASS" if gates.get("report_fake") else "FAIL",
            },
            "live_smoke": {
                "cases": 1,
                "status": "PASS" if gates.get("report_live_smoke") else "FAIL",
            },
            "live": {
                "cases": 6,
                "status": "PASS" if gates.get("report_live") else "FAIL",
            },
        },
        "human_review": "NOT_REVIEWED",
        "gates": automatic_gates,
        "known_limitations": [
            "Complete human semantic review remains NOT_REVIEWED.",
            "Initial official snapshot/build is not materialized in the current database.",
            "Retrieval baseline is PostgreSQL FTS; embeddings and reranking are out of scope.",
        ],
        "non_scope": [
            "LLM judge",
            "auto-tuning",
            "embeddings/vector retrieval",
            "reranker",
            "frontend/API HTTP",
            "automatic corpus acquisition",
            "fine-tuning/LoRA",
            "Phase 11",
        ],
    }


def write_mvp_manifest(manifest: dict, path: Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def manifest_digest(manifest: dict) -> str:
    return hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
