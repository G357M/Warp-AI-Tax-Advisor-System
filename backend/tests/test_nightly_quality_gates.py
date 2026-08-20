"""Contracts for deterministic, privacy-safe nightly quality gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_nightly_runs_both_read_only_quality_evaluators():
    runner = (ROOT / "run_scraper.sh").read_text(encoding="utf-8")
    quality_runner = (ROOT / "run_quality_gates.sh").read_text(encoding="utf-8")

    assert 'run_quality_gates.sh" "$LOG_FILE"' in runner
    assert "evaluate_rag_v2_live_corpus.py" in quality_runner
    assert "evaluate_decision_facts_quality.py" in quality_runner
    assert '"DECISION_FACTS_QUALITY_EVAL="' in quality_runner
    assert "--execute" in quality_runner
    assert "evaluate_answer_safety_live.py" not in quality_runner
    assert '! chmod 0600 "$host_report" "$host_baseline"' in quality_runner
    assert '"${host_artifact}.previous"' in quality_runner
    assert 'chmod 0600 "${host_artifact}.previous"' in quality_runner


def test_nightly_alert_receives_only_machine_summary():
    runner = (ROOT / "run_quality_gates.sh").read_text(encoding="utf-8")
    alert = (ROOT / "quality_gate_alert.sh").read_text(encoding="utf-8")

    assert 'grep "^${summary_prefix}"' in runner
    assert '"$exit_code" "$label" "$summary"' in runner
    assert '"$exit_code" "$label" "$output"' not in runner
    assert "cut -c1-2500" in alert
    assert "--fail --silent --show-error" in alert
    assert "TELEGRAM_BOT_TOKEN" in alert


def test_standalone_runner_propagates_gate_failure_to_operator_only():
    nightly = (ROOT / "run_scraper.sh").read_text(encoding="utf-8")
    runner = (ROOT / "run_quality_gates.sh").read_text(encoding="utf-8")

    assert 'QUALITY_FAILURES+=("$label")' in runner
    assert 'if [ "${#QUALITY_FAILURES[@]}" -ne 0 ]' in runner
    assert "exit 1" in runner
    assert '|| QUALITY_GATE_EXIT=$?' in nightly
    assert "exit $EXIT_CODE" in nightly
