#!/usr/bin/env python
"""Install the additive account verification/recovery schema safely.

Existing users are grandfathered as verified only when ``email_verified_at``
is first introduced. Re-running this migration never verifies later accounts.
All statements run in one transaction and are safe to repeat.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from core.database import SessionLocal


def _column_exists(db, table: str, column: str) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = :table AND column_name = :column)"
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def main() -> None:
    db = SessionLocal()
    try:
        first_email_migration = not _column_exists(db, "users", "email_verified_at")
        if first_email_migration:
            db.execute(text("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP"))
            db.execute(
                text("UPDATE users SET email_verified_at = COALESCE(created_at, NOW())")
            )

        db.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "session_version INTEGER NOT NULL DEFAULT 0"
            )
        )
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS auth_action_tokens ("
                "id UUID PRIMARY KEY, "
                "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "purpose VARCHAR(32) NOT NULL, "
                "token_hash VARCHAR(64) NOT NULL UNIQUE, "
                "expires_at TIMESTAMP NOT NULL, "
                "consumed_at TIMESTAMP NULL, "
                "created_at TIMESTAMP NOT NULL DEFAULT NOW())"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_auth_action_tokens_token_hash "
                "ON auth_action_tokens (token_hash)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_auth_action_tokens_user_purpose_created "
                "ON auth_action_tokens (user_id, purpose, created_at)"
            )
        )
        db.commit()

        unverified = db.execute(
            text("SELECT COUNT(*) FROM users WHERE email_verified_at IS NULL")
        ).scalar_one()
        print(
            "auth recovery schema: ok "
            f"(first_email_migration={str(first_email_migration).lower()}, "
            f"unverified_users={unverified})"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
