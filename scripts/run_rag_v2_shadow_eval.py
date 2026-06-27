import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.rag_v2.pipeline_v2 import pipeline_v2
from backend.rag_v2.db_utils import db_status

FIXTURES = ROOT / "tests" / "fixtures_rag_v2_shadow_eval.json"
LIVE_FIXTURES = ROOT / "tests" / "fixtures_rag_v2_shadow_eval_live.json"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPORTS_DIR / "rag_v2_shadow_eval_report.json"
SUMMARY_PATH = REPORTS_DIR / "rag_v2_shadow_eval_summary.md"


def main() -> int:
    fixture_cases = json.loads(FIXTURES.read_text())
    live_cases = json.loads(LIVE_FIXTURES.read_text()) if LIVE_FIXTURES.exists() else []
    backend = db_status()
    live_db_ready = backend.get("mode") == "db" and backend.get("connectable")

    cases = list(fixture_cases)
    if live_db_ready:
        cases.extend(live_cases)

    results = []
    passed = 0
    skipped = 0

    for case in cases:
        trace = pipeline_v2.build_trace(case["query"])
        ranked = trace.reranking.get("top_ranked_documents", [])
        top = ranked[0] if ranked else {}

        expected_channels = case.get("expected_top_channel_any_of")
        expected_doc_types = case.get("expected_top_document_type_any_of")
        expected_title_substrings = case.get("expected_top_title_contains_any_of")
        expected_title_substring = case.get("expected_top_title_contains")
        actual_title = (top.get("title") or "").lower()

        checks = {
            "class": trace.classification.get("question_class") == case["expected_class"],
            "top_document_type": top.get("document_type") in expected_doc_types if expected_doc_types else top.get("document_type") == case.get("expected_top_document_type"),
            "top_channel": top.get("channel") in expected_channels if expected_channels else top.get("channel") == case.get("expected_top_channel"),
            "top_title": any(part.lower() in actual_title for part in expected_title_substrings) if expected_title_substrings else (expected_title_substring.lower() in actual_title if expected_title_substring else True),
            "audit_passed": bool(trace.source_audit.get("passed")),
        }
        success = all(checks.values())
        if success:
            passed += 1

        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected": case,
                "actual": {
                    "question_class": trace.classification.get("question_class"),
                    "channels_used": trace.candidate_generation.get("channels_used", []),
                    "top_document_id": top.get("document_id"),
                    "top_title": top.get("title"),
                    "top_document_type": top.get("document_type"),
                    "top_channel": top.get("channel"),
                    "top_score": top.get("final_score"),
                    "audit_passed": trace.source_audit.get("passed"),
                    "audit_warnings": trace.source_audit.get("warnings", []),
                },
                "checks": checks,
                "success": success,
            }
        )

    if live_cases and not live_db_ready:
        skipped = len(live_cases)

    report = {
        "backend": backend,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "skipped_live_cases": skipped,
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    lines = [
        "# RAG v2 shadow eval summary",
        "",
        f"- backend mode: {backend['mode']}",
        f"- db connectable: {backend['connectable']}",
        f"- db driver: {backend['driver']}",
        f"- db error: {backend['error']}",
        "",
        f"- total: {report['total']}",
        f"- passed: {report['passed']}",
        f"- failed: {report['failed']}",
        f"- skipped live cases: {report['skipped_live_cases']}",
        "",
        "## Cases",
        "",
    ]
    for item in results:
        status = "PASS" if item["success"] else "FAIL"
        lines.extend(
            [
                f"### {item['id']} — {status}",
                f"- query: {item['query']}",
                f"- class: {item['actual']['question_class']}",
                f"- top: {item['actual']['top_document_type']} via {item['actual']['top_channel']}",
                f"- title: {item['actual']['top_title']}",
                f"- audit: {item['actual']['audit_passed']}",
                "",
            ]
        )
    SUMMARY_PATH.write_text("\n".join(lines))

    print(f"Saved JSON report: {REPORT_PATH}")
    print(f"Saved summary: {SUMMARY_PATH}")
    print(f"PASS {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
