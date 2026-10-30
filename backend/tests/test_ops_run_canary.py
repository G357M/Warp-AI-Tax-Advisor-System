"""ops/run_canary.sh (nightly + manual canary) and the manual-run guard in scraper_alert.sh."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CANARY = ROOT / "ops" / "run_canary.sh"
SCRAPER_ALERT = ROOT / "scraper_alert.sh"
RUN_SCRAPER = ROOT / "run_scraper.sh"

needs_posix = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("flock") is None,
    reason="requires bash and flock (Linux CI / production host)",
)


def _bin(tmp_path: Path, canary_exit: int) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(f'#!/usr/bin/env bash\necho "CANARY: 9/10 failed=pit_rate"\nexit {canary_exit}\n',
                      encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    (bin_dir / "alert.sh").write_text('printf "%s|%s\\n" "$1" "$2" >> "$(dirname "$0")/alerts.log"\n',
                                      encoding="utf-8", newline="\n")
    return bin_dir


def _run_canary(tmp_path: Path, canary_exit: int = 0, args=(), trigger=None) -> subprocess.CompletedProcess:
    bin_dir = _bin(tmp_path, canary_exit)
    env = {**os.environ,
           "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "INFOHUB_CANARY_ALERT": str(bin_dir / "alert.sh"),
           "INFOHUB_OPS_STATUS_DIR": str(tmp_path / "status"),
           "INFOHUB_LOG_DIR": str(tmp_path / "logs")}
    env.pop("INFOHUB_JOB_TRIGGER", None)
    if trigger:
        env["INFOHUB_JOB_TRIGGER"] = trigger
    return subprocess.run(["bash", str(CANARY), *args], env=env, capture_output=True, text=True)


def _status(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "status" / "canary.json").read_text(encoding="utf-8"))


@needs_posix
def test_manual_canary_writes_status_alert_and_own_log(tmp_path):
    result = _run_canary(tmp_path, trigger="manual")
    assert result.returncode == 0, result.stderr
    status = _status(tmp_path)
    assert status["exit_code"] == 0 and status["trigger"] == "manual"
    assert status["summary"] == "CANARY: 9/10 failed=pit_rate"
    assert (tmp_path / "bin" / "alerts.log").read_text(encoding="utf-8") == "0|CANARY: 9/10 failed=pit_rate\n"
    assert len(list((tmp_path / "logs").glob("canary_*.log"))) == 1


@needs_posix
def test_failing_canary_exits_with_its_code_and_appends_to_the_given_log(tmp_path):
    log = tmp_path / "nightly.log"
    log.write_text("before\n", encoding="utf-8")
    result = _run_canary(tmp_path, canary_exit=1, args=(str(log),))
    assert result.returncode == 1
    status = _status(tmp_path)
    assert status["exit_code"] == 1 and status["trigger"] == "cron"
    assert "CANARY: 9/10" in log.read_text(encoding="utf-8")
    assert not (tmp_path / "logs").exists()


def test_nightly_run_uses_the_shared_canary_script():
    text = RUN_SCRAPER.read_text(encoding="utf-8")
    assert 'ops/run_canary.sh" "$LOG_FILE"' in text
    assert "canary_eval.py" not in text


def _alert(tmp_path: Path, *args, manual=False, streak="1"):
    (tmp_path / "logs").mkdir(exist_ok=True)
    streak_file = tmp_path / "logs" / "zero_new_streak"
    streak_file.write_text(streak, encoding="utf-8")
    env = {**os.environ, "INFOHUB_DIR": str(tmp_path)}
    env.pop("INFOHUB_MANUAL_RUN", None)
    if manual:
        env["INFOHUB_MANUAL_RUN"] = "1"
    result = subprocess.run(["bash", str(SCRAPER_ALERT), *args], env=env, capture_output=True, text=True)
    return result, streak_file.read_text(encoding="utf-8").strip()


@needs_posix
@pytest.mark.parametrize("args", [("0", "0"), ("0", "5"), ("1", "?")])
def test_manual_run_leaves_the_zero_streak_alone(tmp_path, args):
    result, streak = _alert(tmp_path, *args, manual=True, streak="2")
    assert result.returncode == 0 and streak == "2"


@needs_posix
def test_manual_failure_still_alerts(tmp_path):
    result, _ = _alert(tmp_path, "1", "?", manual=True)
    assert "would have sent" in result.stdout and "FAILED" in result.stdout


@needs_posix
def test_nightly_run_still_counts_the_streak(tmp_path):
    _, streak = _alert(tmp_path, "0", "0", streak="1")
    assert streak == "2"
