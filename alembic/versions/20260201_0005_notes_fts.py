"""notes full-text search (sqlite fts5)

Revision ID: 20260201_0005
Revises: 20260201_0004
Create Date: 2026-02-01 00:00:00
"""

from __future__ import annotations

from alembic import op


# Revision identifiers, used by Alembic.
revision = "20260201_0005"
down_revision = "20260201_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # v2.0: only SQLite uses FTS5; non-sqlite backends fall back to ILIKE.
        return

    # Contentless FTS table. We store note_id/user_id for filtering and joining.
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
          title,
          body_md,
          note_id UNINDEXED,
          user_id UNINDEXED
        );
        """
    )

    # Backfill existing notes. Deleted notes are intentionally excluded from the index.
    op.execute(
        """
        INSERT INTO notes_fts(note_id, user_id, title, body_md)
        SELECT n.id, n.user_id, n.title, n.body_md
        FROM notes AS n
        WHERE n.deleted_at IS NULL
          AND n.id NOT IN (SELECT note_id FROM notes_fts);
        """
    )

    # Keep FTS index in sync.
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes
        WHEN new.deleted_at IS NULL
        BEGIN
          INSERT INTO notes_fts(note_id, user_id, title, body_md)
          VALUES (new.id, new.user_id, new.title, new.body_md);
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes
        BEGIN
          DELETE FROM notes_fts WHERE note_id = old.id;
        END;
        """
    )

    # Handles title/body changes as well as soft delete/restore transitions.
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes
        BEGIN
          DELETE FROM notes_fts WHERE note_id = old.id;
          INSERT INTO notes_fts(note_id, user_id, title, body_md)
          SELECT new.id, new.user_id, new.title, new.body_md
          WHERE new.deleted_at IS NULL;
        END;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    op.execute("DROP TRIGGER IF EXISTS notes_au;")
    op.execute("DROP TRIGGER IF EXISTS notes_ad;")
    op.execute("DROP TRIGGER IF EXISTS notes_ai;")
    op.execute("DROP TABLE IF EXISTS notes_fts;")
