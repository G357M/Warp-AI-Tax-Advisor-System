from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_INFOHUB_DB_URL = "postgresql://infohub_user:xcX88l6XiMs-jDK@localhost:5432/infohub_ai"


@dataclass
class BackendConfig:
    mode: str = "fixtures"
    database_url: Optional[str] = None


def load_backend_config() -> BackendConfig:
    database_url = (
        os.getenv("INFOHUB_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_INFOHUB_DB_URL
    )
    return BackendConfig(
        mode=os.getenv("INFOHUB_V2_BACKEND_MODE", "fixtures"),
        database_url=database_url,
    )
