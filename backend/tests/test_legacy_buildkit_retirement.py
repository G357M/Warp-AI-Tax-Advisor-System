"""Contracts for exact-ID retirement from the shared legacy Buildx builder."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "retire_infohub_legacy_buildkit.py"
SPEC = importlib.util.spec_from_file_location("retire_infohub_legacy_buildkit", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


RECORDS = {
    "a" * 25: {
        "ID": "a" * 25,
        "CreatedAt": "2026-07-02 07:06:24 +0000 UTC",
        "Description": MODULE.EXPECTED_DESCRIPTION,
        "Mutable": False,
        "Reclaimable": True,
        "Shared": False,
        "Size": "8.67GB",
        "Type": "regular",
    },
    "b" * 25: {
        "ID": "b" * 25,
        "CreatedAt": "2026-07-08 16:33:42 +0000 UTC",
        "Description": MODULE.EXPECTED_DESCRIPTION,
        "Mutable": False,
        "Reclaimable": True,
        "Shared": False,
        "Size": "8.639GB",
        "Type": "regular",
    },
}


class FakeDockerRunner:
    def __init__(self, records=None):
        self.records = deepcopy(RECORDS if records is None else records)
        self.calls: list[tuple[str, ...]] = []

    def run(self, command, *, check=True, capture_output=False):
        command_tuple = tuple(command)
        self.calls.append(command_tuple)
        if command_tuple[:3] == ("docker", "buildx", "du"):
            selector = command_tuple[command_tuple.index("--filter") + 1]
            record_id = selector.removeprefix("id=")
            record = self.records.get(record_id)
            output = "" if record is None else json.dumps(record)
            return subprocess.CompletedProcess(command, 0, output, "")
        if command_tuple[:3] == ("docker", "buildx", "prune"):
            selector = command_tuple[command_tuple.index("--filter") + 1]
            self.records.pop(selector.removeprefix("id="), None)
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command_tuple}")


def test_dry_run_builds_stable_review_plan_without_pruning():
    runner = FakeDockerRunner()

    plan = MODULE.build_plan(["b" * 25, "a" * 25], runner)
    summary = MODULE.plan_summary(plan, execute=False)

    assert [record.record_id for record in plan.records] == ["a" * 25, "b" * 25]
    assert plan.record_count == 2
    assert plan.total_bytes == 17_309_000_000
    assert len(plan.plan_sha256) == 64
    assert summary["execute"] is False
    assert all(call[:3] == ("docker", "buildx", "du") for call in runner.calls)
    assert not any("prune" in call for call in runner.calls)


def test_execute_uses_exact_id_and_all_safety_filters_then_verifies_absence():
    runner = FakeDockerRunner()
    plan = MODULE.build_plan(list(RECORDS), runner)

    MODULE.execute_plan(
        plan,
        runner,
        expected_record_count=plan.record_count,
        expected_total_bytes=plan.total_bytes,
        expected_plan_sha256=plan.plan_sha256,
    )

    assert runner.records == {}
    prune_calls = [call for call in runner.calls if call[2] == "prune"]
    assert len(prune_calls) == 2
    for call, record in zip(prune_calls, plan.records, strict=True):
        assert call[:5] == (
            "docker",
            "buildx",
            "prune",
            "--builder",
            "default",
        )
        filters = [
            call[index + 1]
            for index, value in enumerate(call)
            if value == "--filter"
        ]
        assert filters == [
            f"id={record.record_id}",
            "inuse=false",
            "shared=false",
            "mutable=false",
            "type=regular",
            "description=requirements-production.txt",
        ]
        assert "--force" in call


@pytest.mark.parametrize(
    ("guard", "value", "message"),
    [
        ("expected_record_count", 1, "record count"),
        ("expected_total_bytes", 1, "total bytes"),
        ("expected_plan_sha256", "0" * 64, "SHA-256"),
    ],
)
def test_execute_guard_mismatch_fails_before_prune(guard, value, message):
    runner = FakeDockerRunner()
    plan = MODULE.build_plan(list(RECORDS), runner)
    arguments = {
        "expected_record_count": plan.record_count,
        "expected_total_bytes": plan.total_bytes,
        "expected_plan_sha256": plan.plan_sha256,
    }
    arguments[guard] = value

    with pytest.raises(MODULE.LegacyRetirementError, match=message):
        MODULE.execute_plan(plan, runner, **arguments)

    assert not any(call[2] == "prune" for call in runner.calls)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("Description", "npm ci", "approved legacy InfoHub"),
        ("Type", "source.local", "type"),
        ("Reclaimable", False, "not reclaimable"),
        ("Shared", True, "shared"),
        ("Mutable", True, "mutable"),
        ("Size", "unknown", "invalid cache size"),
    ],
)
def test_unapproved_record_metadata_is_rejected(field, value, message):
    records = deepcopy(RECORDS)
    records["a" * 25][field] = value
    runner = FakeDockerRunner(records)

    with pytest.raises(MODULE.LegacyRetirementError, match=message):
        MODULE.build_plan(["a" * 25], runner)

    assert not any(call[2] == "prune" for call in runner.calls)


@pytest.mark.parametrize(
    "record_ids",
    [
        [],
        ["short"],
        ["a" * 25, "a" * 25],
        [f"{index:025d}" for index in range(MODULE.MAX_RECORDS + 1)],
    ],
)
def test_invalid_candidate_set_fails_without_docker(record_ids):
    runner = FakeDockerRunner()

    with pytest.raises(MODULE.LegacyRetirementError):
        MODULE.build_plan(record_ids, runner)

    assert runner.calls == []


def test_tool_has_no_global_or_non_cache_deletion_path():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "docker system prune" not in source
    assert "docker builder prune" not in source
    assert "docker image rm" not in source
    assert "docker volume rm" not in source
    assert 'LEGACY_BUILDER = "default"' in source
