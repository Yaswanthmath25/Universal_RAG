"""
One-shot migration: add access control columns if missing.
Run once:  python -m backend.migrate
"""

from sqlalchemy import text

from backend.database import engine


MIGRATIONS = [
    """
    ALTER TABLE documents
      ADD COLUMN IF NOT EXISTS access_scope VARCHAR(32)
      NOT NULL DEFAULT 'company_policy'
    """,
    """
    ALTER TABLE documents
      ADD COLUMN IF NOT EXISTS target_user_id VARCHAR(255)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_documents_access_scope
      ON documents(access_scope)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_documents_target_user_id
      ON documents(target_user_id)
    """,
    """
    ALTER TABLE chat_history
      ADD COLUMN IF NOT EXISTS order_state TEXT
    """,
]


def run():
    with engine.begin() as conn:
        for sql in MIGRATIONS:
            conn.execute(text(sql))
            print("✓", sql.strip().splitlines()[0].strip())
    print("\n✅ Migration complete. Restart the backend now.")


if __name__ == "__main__":
    run()