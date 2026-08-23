#!/usr/bin/env python3
"""Create, use and prune an InfoHub-only Buildx cache boundary."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence


BUILDER_NAME_PATTERN = re.compile(r"^infohub-[A-Za-z0-9][A-Za-z0-9_.-]{0,55}$")
SPACE_PATTERN = re.compile(r"^[1-9][0-9]*(?:kb|mb|gb|tb)$", re.IGNORECASE)
EXPECTED_DRIVER = "docker-container"


class BuildkitPolicyError(RuntimeError):
    """Raised when the requested builder cannot satisfy the isolation policy."""


class Runner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            check=check,
            capture_output=capture_output,
            text=True,
        )


@dataclass(frozen=True)
class BuildkitPolicy:
    builder_name: str = "infohub-production-v1"
    max_used_space: str = "18gb"
    reserved_space: str = "6gb"
    min_free_space: str = "25gb"

    def validate(self) -> None:
        if not BUILDER_NAME_PATTERN.fullmatch(self.builder_name):
            raise BuildkitPolicyError("invalid Buildx builder name")
        for field_name in ("max_used_space", "reserved_space", "min_free_space"):
            value = getattr(self, field_name)
            if not SPACE_PATTERN.fullmatch(value):
                raise BuildkitPolicyError(f"invalid {field_name.replace('_', '-')}")


@dataclass(frozen=True)
class BuilderState:
    name: str
    driver: str
    created: bool


def _docker_command(*arguments: str) -> list[str]:
    return ["docker", *arguments]


def _parse_driver(output: str) -> str:
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "Driver":
            return value.strip()
    raise BuildkitPolicyError("Buildx inspect did not report a driver")


def inspect_builder(
    policy: BuildkitPolicy,
    runner: Runner,
) -> tuple[bool, str | None]:
    result = runner.run(
        _docker_command("buildx", "inspect", policy.builder_name),
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        return True, _parse_driver(result.stdout)

    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    if "no builder" in diagnostic or "not found" in diagnostic:
        return False, None
    raise BuildkitPolicyError("Buildx builder inspection failed")


def ensure_builder(policy: BuildkitPolicy, runner: Runner) -> BuilderState:
    policy.validate()
    exists, driver = inspect_builder(policy, runner)
    created = False

    if not exists:
        runner.run(
            _docker_command(
                "buildx",
                "create",
                "--name",
                policy.builder_name,
                "--driver",
                EXPECTED_DRIVER,
            )
        )
        created = True
        exists, driver = inspect_builder(policy, runner)
        if not exists:
            raise BuildkitPolicyError("created Buildx builder cannot be inspected")

    if driver != EXPECTED_DRIVER:
        raise BuildkitPolicyError(
            f"builder {policy.builder_name!r} uses {driver!r}, expected {EXPECTED_DRIVER!r}"
        )

    runner.run(
        _docker_command("buildx", "inspect", policy.builder_name, "--bootstrap")
    )
    return BuilderState(
        name=policy.builder_name,
        driver=driver,
        created=created,
    )


def prune_builder(
    policy: BuildkitPolicy,
    runner: Runner,
    *,
    execute: bool,
) -> None:
    policy.validate()
    exists, driver = inspect_builder(policy, runner)
    if not exists:
        raise BuildkitPolicyError("project Buildx builder does not exist")
    if driver != EXPECTED_DRIVER:
        raise BuildkitPolicyError("refusing to prune a non-isolated Buildx builder")

    print(
        "INFOHUB_BUILDKIT_PRUNE_PLAN="
        + json.dumps(
            {
                **asdict(policy),
                "driver": driver,
                "execute": execute,
                "scope": "named_builder_only",
            },
            sort_keys=True,
        )
    )
    if not execute:
        return

    runner.run(
        _docker_command(
            "buildx",
            "prune",
            "--builder",
            policy.builder_name,
            "--force",
            "--max-used-space",
            policy.max_used_space,
            "--reserved-space",
            policy.reserved_space,
            "--min-free-space",
            policy.min_free_space,
        )
    )


def build_images(
    policy: BuildkitPolicy,
    runner: Runner,
    *,
    compose_file: Path,
) -> BuilderState:
    policy.validate()
    resolved_compose = compose_file.resolve()
    if compose_file.is_symlink() or not resolved_compose.is_file():
        raise BuildkitPolicyError("compose file must be a regular non-symlink file")

    state = ensure_builder(policy, runner)
    # Enforce the boundary both before and after a build. The first prune keeps
    # stale project cache from consuming the space needed by this deployment;
    # the second bounds any new cache produced by the build.
    prune_builder(policy, runner, execute=True)
    try:
        runner.run(
            _docker_command(
                "buildx",
                "bake",
                "--file",
                str(resolved_compose),
                "--builder",
                policy.builder_name,
                "--load",
                "backend",
                "frontend",
            )
        )
    except Exception:
        try:
            prune_builder(policy, runner, execute=True)
        except Exception as cleanup_error:
            print(
                f"warning: project Buildx cache cleanup failed: {cleanup_error}",
                file=sys.stderr,
            )
        raise

    prune_builder(policy, runner, execute=True)
    return state


def _policy_from_environment() -> BuildkitPolicy:
    return BuildkitPolicy(
        builder_name=os.getenv(
            "INFOHUB_BUILDX_BUILDER",
            "infohub-production-v1",
        ),
        max_used_space=os.getenv(
            "INFOHUB_BUILDKIT_MAX_USED_SPACE",
            "18gb",
        ),
        reserved_space=os.getenv(
            "INFOHUB_BUILDKIT_RESERVED_SPACE",
            "6gb",
        ),
        min_free_space=os.getenv(
            "INFOHUB_BUILDKIT_MIN_FREE_SPACE",
            "25gb",
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ensure", help="Create and bootstrap the isolated builder")

    build = subparsers.add_parser(
        "build",
        help="Build and load production images, then enforce cache bounds",
    )
    build.add_argument(
        "--compose-file",
        type=Path,
        default=Path("docker-compose.yml"),
    )

    prune = subparsers.add_parser(
        "prune",
        help="Print the scoped prune plan; apply only with --execute",
    )
    prune.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    policy = _policy_from_environment()
    runner = SubprocessRunner()

    try:
        if args.command == "ensure":
            state = ensure_builder(policy, runner)
            print(
                "INFOHUB_BUILDX_BUILDER="
                + json.dumps({**asdict(state), **asdict(policy)}, sort_keys=True)
            )
        elif args.command == "build":
            state = build_images(
                policy,
                runner,
                compose_file=args.compose_file,
            )
            print(
                "INFOHUB_BUILDX_BUILD="
                + json.dumps({**asdict(state), **asdict(policy)}, sort_keys=True)
            )
        elif args.command == "prune":
            prune_builder(policy, runner, execute=args.execute)
        else:  # pragma: no cover - argparse enforces the command set.
            raise BuildkitPolicyError("unsupported command")
    except (BuildkitPolicyError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
