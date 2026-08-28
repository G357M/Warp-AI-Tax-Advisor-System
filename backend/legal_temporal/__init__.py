"""Temporal legal-data foundation.

This package is deliberately independent from the public RAG path.  It stores
official source evidence and bitemporal provision facts without making an
unreviewed historical record visible in answers.
"""

from legal_temporal.schema_contract import (
    SCHEMA_CONTRACT_SHA256,
    SCHEMA_VERSION,
)

__all__ = ["SCHEMA_CONTRACT_SHA256", "SCHEMA_VERSION"]
