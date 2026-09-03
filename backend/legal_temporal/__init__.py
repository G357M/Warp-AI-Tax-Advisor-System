"""Temporal legal-data foundation.

This package is deliberately independent from the public RAG path.  It stores
official source evidence and bitemporal provision facts without making an
unreviewed historical record visible in answers.
"""

__all__ = ["SCHEMA_CONTRACT_SHA256", "SCHEMA_VERSION"]


def __getattr__(name):
    # Evidence/review tooling is offline: importing it must not load database
    # settings or construct an engine. Preserve the public schema exports.
    if name in __all__:
        from legal_temporal import schema_contract

        return getattr(schema_contract, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
