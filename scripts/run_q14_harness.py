"""Execute Q14 fake, smoke and live against the existing PostgreSQL fixture harness."""

import argparse
import json
import runpy
import tempfile
from pathlib import Path

from rag_esocial.answer_service import OllamaAnswerModelClient
from rag_esocial.config import get_settings
from rag_esocial.evaluation_service import write_report
from rag_esocial.q14_service import DeterministicQ14Client, evaluate_q14


def main(smoke_only=False):
    harness = runpy.run_path("tests/test_mos_integration.py")
    build_fixture = harness["build_fixture"]
    resolution_fixture = harness["_resolution_fixture"]
    cleanup = harness["cleanup"]
    settings = get_settings()
    dataset = Path("evaluation/q14/q14_v1.json")
    with tempfile.TemporaryDirectory(prefix="q14-live-") as directory:
        session, snapshot, build, _, _, ids = build_fixture(Path(directory))
        ids["builds"].append(build.id)
        try:
            resolution_fixture(session, snapshot, build)
            session.commit()
            fake = evaluate_q14(
                session,
                build,
                dataset,
                DeterministicQ14Client,
                "fake-deterministic",
            )
            write_report(fake, "evaluation/q14/q14_v1_fake_report.json")
            session.commit()

            diagnostic_client = OllamaAnswerModelClient(
                settings.ollama_base_url, settings.llm_model
            )
            runtime = diagnostic_client.status()
            if not runtime["reachable"] or not runtime["model_available"]:
                raise RuntimeError(f"OLLAMA_PREFLIGHT_FAILED:{runtime}")

            def live_client():
                return OllamaAnswerModelClient(
                    settings.ollama_base_url, settings.llm_model
                )

            smoke = evaluate_q14(
                session,
                build,
                dataset,
                live_client,
                "ollama",
                case_ids={"mos-answered-conceito"},
                runtime_metadata=runtime,
            )
            write_report(smoke, "evaluation/q14/q14_v1_live_smoke_report.json")
            session.commit()
            if smoke["results"][0]["observed_status"] != "ANSWERED":
                raise RuntimeError(
                    "LIVE_SMOKE_CONTRACT_FAILED:"
                    + json.dumps(smoke["results"][0], ensure_ascii=False)
                )
            if smoke_only:
                print(json.dumps(smoke, ensure_ascii=False, indent=2, sort_keys=True))
                return

            live = evaluate_q14(
                session,
                build,
                dataset,
                live_client,
                "ollama",
                runtime_metadata=runtime,
            )
            write_report(live, "evaluation/q14/q14_v1_live_report.json")
            session.commit()
            print(
                json.dumps(
                    {
                        "dataset_sha256": live["dataset_sha256"],
                        "fake_cases": len(fake["results"]),
                        "fake_metrics": fake["aggregates"],
                        "smoke_status": smoke["results"][0]["observed_status"],
                        "live_cases": len(live["results"]),
                        "live_metrics": live["aggregates"],
                        "live_statuses": [
                            {
                                "case_id": row["case_id"],
                                "expected": row["expected_status"],
                                "observed": row["observed_status"],
                                "model_calls": row["model_call_count"],
                            }
                            for row in live["results"]
                        ],
                        "runtime": runtime,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        finally:
            cleanup(session, ids)
            session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-only", action="store_true")
    main(smoke_only=parser.parse_args().smoke_only)
