"""Contracts for the read-only production storage pressure audit."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "audit_production_storage.py"
SPEC = importlib.util.spec_from_file_location("audit_production_storage", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeDockerRunner:
    def __init__(self, sizes_by_builder, *, failed_builder=None):
        self.sizes_by_builder = sizes_by_builder
        self.failed_builder = failed_builder
        self.calls: list[tuple[str, ...]] = []

    def run(self, command, *, check=True, capture_output=False):
        command_tuple = tuple(command)
        self.calls.append(command_tuple)
        builder = command_tuple[command_tuple.index("--builder") + 1]
        if builder == self.failed_builder:
            return subprocess.CompletedProcess(command, 1, "", "unavailable")
        output = "\n".join(
            json.dumps({"ID": f"record-{index}", "Size": size})
            for index, size in enumerate(self.sizes_by_builder[builder])
        )
        return subprocess.CompletedProcess(command, 0, output, "")


def _policy(**overrides):
    values = {
        "min_free_bytes": 25_000_000_000,
        "max_used_percent": Decimal("82"),
        "project_builder": "infohub-production-v1",
        "max_project_cache_bytes": 18_000_000_000,
        "legacy_builder": "default",
        "legacy_observation_ceiling_bytes": 60_000_000_000,
    }
    values.update(overrides)
    return MODULE.StoragePolicy(**values)


def _disk(*, total=150_000_000_000, used=110_000_000_000, free=37_000_000_000):
    return SimpleNamespace(total=total, used=used, free=free)


def test_size_parser_matches_buildx_decimal_units():
    assert MODULE.parse_size("8.192kB") == 8_192
    assert MODULE.parse_size("859.9MB") == 859_900_000
    assert MODULE.parse_size("5.742GB") == 5_742_000_000
    assert MODULE.parse_size("0B") == 0


def test_healthy_audit_is_aggregate_only_and_read_only():
    runner = FakeDockerRunner(
        {
            "infohub-production-v1": ["5GB", "742MB"],
            "default": ["34.616GB", "19.644GB"],
        }
    )

    report = MODULE.audit_storage(
        _policy(),
        runner,
        disk_usage=lambda path: _disk(),
    )

    assert report["status"] == "healthy"
    assert report["project_cache"]["cache_bytes"] == 5_742_000_000
    assert report["legacy_cache"]["cache_bytes"] == 54_260_000_000
    assert report["legacy_cache"]["management"] == "observe_only_no_automatic_prune"
    assert report["violations"] == []
    assert all(call[:3] == ("docker", "buildx", "du") for call in runner.calls)
    assert not any("prune" in call or "rm" in call for call in runner.calls)
    assert "Description" not in json.dumps(report)


@pytest.mark.parametrize(
    ("policy_overrides", "disk", "expected"),
    [
        ({}, _disk(free=24_999_999_999), "root_free_below_minimum"),
        (
            {},
            _disk(used=123_000_000_001, free=26_000_000_000),
            "root_used_above_maximum",
        ),
        (
            {"max_project_cache_bytes": 5_000_000_000},
            _disk(),
            "project_cache_above_maximum",
        ),
        (
            {"legacy_observation_ceiling_bytes": 50_000_000_000},
            _disk(),
            "legacy_cache_above_observation_ceiling",
        ),
    ],
)
def test_pressure_thresholds_are_machine_readable(policy_overrides, disk, expected):
    runner = FakeDockerRunner(
        {
            "infohub-production-v1": ["5.742GB"],
            "default": ["54.26GB"],
        }
    )

    report = MODULE.audit_storage(
        _policy(**policy_overrides),
        runner,
        disk_usage=lambda path: disk,
    )

    assert report["status"] == "pressure"
    assert expected in report["violations"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"root_path": Path("/tmp")},
        {"min_free_bytes": 0},
        {"max_used_percent": Decimal("100")},
        {"project_builder": "default"},
        {"project_builder": "other-project"},
        {"legacy_builder": "plausible"},
    ],
)
def test_invalid_policy_fails_before_docker(overrides):
    runner = FakeDockerRunner({})

    with pytest.raises(MODULE.StorageAuditError):
        MODULE.audit_storage(
            _policy(**overrides),
            runner,
            disk_usage=lambda path: _disk(),
        )

    assert runner.calls == []


def test_buildx_failure_is_fail_closed():
    runner = FakeDockerRunner(
        {
            "infohub-production-v1": ["5.742GB"],
            "default": ["54.26GB"],
        },
        failed_builder="default",
    )

    with pytest.raises(MODULE.StorageAuditError, match="default"):
        MODULE.audit_storage(
            _policy(),
            runner,
            disk_usage=lambda path: _disk(),
        )


def test_nightly_runner_alerts_on_storage_pressure_without_pruning():
    runner = (REPOSITORY_ROOT / "run_scraper.sh").read_text(encoding="utf-8")
    audit = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "audit_production_storage.py" in runner
    assert 'grep \'^PRODUCTION_STORAGE_AUDIT=\'' in runner
    assert '"production storage audit"' in runner
    assert "docker buildx prune" not in audit
    assert "docker system prune" not in audit


def test_frontend_dockerfile_uses_modern_env_syntax():
    dockerfile = (REPOSITORY_ROOT / "frontend" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "ENV NODE_ENV=production" in dockerfile
    assert "ENV PORT=3000" in dockerfile
    assert 'ENV HOSTNAME="0.0.0.0"' in dockerfile
