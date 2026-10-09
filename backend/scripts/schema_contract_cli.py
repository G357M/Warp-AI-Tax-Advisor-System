"""Shared command line for additive schema scripts pinned to a reviewed DDL contract.

A script defines its DDL tuple and an ``apply_schema(connection)`` audit, then
calls :func:`run`. Without ``--apply`` it only prints the contract digest; with
``--apply`` the caller must pass the same digest it reviewed, and the DDL runs
in one PostgreSQL transaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from typing import Callable, Iterable, Sequence


def ddl_contract_sha256(ddl: Iterable[str]) -> str:
    """Digest of the DDL with whitespace normalised, so formatting never changes it."""
    return hashlib.sha256("\n".join(" ".join(sql.split()) for sql in ddl).encode()).hexdigest()


def run(
    *,
    output_key: str,
    label: str,
    contract: str,
    apply_schema: Callable[[object], dict],
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-contract-sha256")
    args = parser.parse_args(argv)
    if args.apply and args.expected_contract_sha256 != contract:
        raise SystemExit(f"{label} contract mismatch: explicit reviewed SHA-256 is required")
    result = {"contract_sha256": contract, "execute": args.apply}
    if args.apply:
        from core.database import engine

        if engine.dialect.name != "postgresql":
            raise SystemExit(f"{label} schema requires PostgreSQL")
        with engine.begin() as connection:
            result.update(apply_schema(connection))
    print(f"{output_key}=" + json.dumps(result, sort_keys=True))
    return 0
