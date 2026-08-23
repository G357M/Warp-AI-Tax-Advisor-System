"""Contracts for the project-scoped production Buildx cache policy."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "manage_infohub_buildkit.py"
SPEC = importlib.util.spec_from_file_location("manage_infohub_buildkit", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeDockerRunner:
    def __init__(
        self,
        *,
        exists: bool,
        driver: str = "docker-container",
        fail_bake: bool = False,
    ) -> None:
        self.exists = exists
        self.driver = driver
        self.fail_bake = fail_bake
        self.calls: list[tuple[str, ...]] = []

    def run(self, command, *, check=True, capture_output=False):
        command_tuple = tuple(command)
        self.calls.append(command_tuple)

        if command_tuple[:3] == ("docker", "buildx", "inspect"):
            if "--bootstrap" in command_tuple:
                return subprocess.CompletedProcess(command, 0, "", "")
            if not self.exists:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    "ERROR: no builder found",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                f"Name: test\nDriver: {self.driver}\n",
                "",
            )

        if command_tuple[:3] == ("docker", "buildx", "create"):
            self.exists = True
            return subprocess.CompletedProcess(command, 0, "", "")

        if command_tuple[:3] == ("docker", "buildx", "bake") and self.fail_bake:
            if check:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 1, "", "failed")

        return subprocess.CompletedProcess(command, 0, "", "")


def _policy(**overrides):
    values = {
        "builder_name": "infohub-production-v1",
        "max_used_space": "18gb",
        "reserved_space": "6gb",
        "min_free_space": "25gb",
    }
    values.update(overrides)
    return MODULE.BuildkitPolicy(**values)


def test_ensure_creates_an_isolated_builder_without_changing_default():
    runner = FakeDockerRunner(exists=False)

    state = MODULE.ensure_builder(_policy(), runner)

    assert state.created is True
    assert state.driver == "docker-container"
    create = next(call for call in runner.calls if call[2] == "create")
    assert create == (
        "docker",
        "buildx",
        "create",
        "--name",
        "infohub-production-v1",
        "--driver",
        "docker-container",
    )
    assert "--use" not in create
    assert (
        "docker",
        "buildx",
        "inspect",
        "infohub-production-v1",
        "--bootstrap",
    ) in runner.calls


def test_existing_non_isolated_builder_is_rejected_without_pruning():
    runner = FakeDockerRunner(exists=True, driver="docker")

    with pytest.raises(MODULE.BuildkitPolicyError, match="expected 'docker-container'"):
        MODULE.ensure_builder(_policy(), runner)

    assert not any("create" in call for call in runner.calls)
    assert not any("prune" in call for call in runner.calls)


def test_build_loads_named_images_and_prunes_only_the_named_builder():
    runner = FakeDockerRunner(exists=True)

    MODULE.build_images(
        _policy(),
        runner,
        compose_file=REPOSITORY_ROOT / "docker-compose.yml",
    )

    bake = next(call for call in runner.calls if call[2] == "bake")
    assert "--builder" in bake
    assert bake[bake.index("--builder") + 1] == "infohub-production-v1"
    assert "--load" in bake
    assert bake[-2:] == ("backend", "frontend")

    prune_calls = [call for call in runner.calls if call[2] == "prune"]
    assert len(prune_calls) == 2
    assert prune_calls[0] == prune_calls[1] == (
        "docker",
        "buildx",
        "prune",
        "--builder",
        "infohub-production-v1",
        "--force",
        "--max-used-space",
        "18gb",
        "--reserved-space",
        "6gb",
        "--min-free-space",
        "25gb",
    )
    assert not any(call[:3] == ("docker", "builder", "prune") for call in runner.calls)


def test_prune_is_dry_run_by_default(capsys):
    runner = FakeDockerRunner(exists=True)

    MODULE.prune_builder(_policy(), runner, execute=False)

    assert not any(call[2] == "prune" for call in runner.calls)
    assert '"execute": false' in capsys.readouterr().out


def test_failed_build_attempts_only_scoped_cleanup():
    runner = FakeDockerRunner(exists=True, fail_bake=True)

    with pytest.raises(subprocess.CalledProcessError):
        MODULE.build_images(
            _policy(),
            runner,
            compose_file=REPOSITORY_ROOT / "docker-compose.yml",
        )

    prune_calls = [call for call in runner.calls if call[2] == "prune"]
    assert len(prune_calls) == 2
    assert all(call[4] == "infohub-production-v1" for call in prune_calls)


@pytest.mark.parametrize(
    "overrides",
    [
        {"builder_name": "default*"},
        {"builder_name": "default"},
        {"builder_name": "other-project"},
        {"builder_name": ""},
        {"max_used_space": "18"},
        {"reserved_space": "0gb"},
        {"min_free_space": "25 gigabytes"},
    ],
)
def test_invalid_policy_values_fail_before_docker(overrides):
    runner = FakeDockerRunner(exists=True)

    with pytest.raises(MODULE.BuildkitPolicyError):
        MODULE.ensure_builder(_policy(**overrides), runner)

    assert runner.calls == []


def test_deploy_and_compose_pin_the_project_builder_contract():
    deploy = (REPOSITORY_ROOT / "scripts" / "deploy_production.sh").read_text(
        encoding="utf-8"
    )
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "python3 scripts/manage_infohub_buildkit.py build" in deploy
    assert "docker compose build backend frontend" not in deploy
    assert "image: infohub-backend" in compose
    assert "image: infohub-frontend" in compose
