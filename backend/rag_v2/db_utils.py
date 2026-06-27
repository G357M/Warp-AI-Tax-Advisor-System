from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

from .adapters import load_backend_config


def db_available() -> bool:
    status = db_status()
    return bool(status.get("mode") == "db" and status.get("connectable"))


@lru_cache(maxsize=1)
def db_status() -> Dict[str, Any]:
    cfg = load_backend_config()
    status: Dict[str, Any] = {
        "mode": cfg.mode,
        "has_database_url": bool(cfg.database_url),
        "database_url_source": "env_or_default" if cfg.database_url else "missing",
        "driver": None,
        "connectable": False,
        "error": None,
    }

    try:
        import psycopg  # type: ignore

        status["driver"] = "psycopg"
    except ModuleNotFoundError:
        try:
            import psycopg2  # type: ignore

            status["driver"] = "psycopg2"
        except ModuleNotFoundError:
            status["error"] = "psycopg or psycopg2 is required for db mode"
            return status

    if not cfg.database_url:
        status["error"] = "INFOHUB_DATABASE_URL is not configured"
        return status

    try:
        rows = run_query("SELECT 1 AS ok")
        status["connectable"] = bool(rows and rows[0].get("ok") == 1)
    except Exception as exc:  # pragma: no cover - defensive probe path
        status["error"] = f"{type(exc).__name__}: {exc}"

    return status


def run_query(sql: str, params: List[Any] | None = None) -> List[Dict[str, Any]]:
    cfg = load_backend_config()
    if not cfg.database_url:
        raise RuntimeError("INFOHUB_DATABASE_URL is not configured")

    params = params or []

    try:
        import psycopg

        with psycopg.connect(cfg.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except ModuleNotFoundError:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except Exception as exc:
            raise RuntimeError("psycopg or psycopg2 is required for db mode") from exc

        conn = psycopg2.connect(cfg.database_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
