"""replace message content with typed chunks

Revision ID: 8f2c9d4a1b7e
Revises: 2c8f5e4a9b31
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8f2c9d4a1b7e"
down_revision: Union[str, None] = "2c8f5e4a9b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("message", sa.Column("chunks", sa.JSON(), nullable=True))
    op.execute(
        """
        UPDATE message
        SET chunks = json_build_array(
            json_build_object(
                'index', 0,
                'type', 'message_content',
                'content', content
            )
        )
        """
    )
    op.alter_column("message", "chunks", nullable=False)
    op.drop_column("message", "content")


def downgrade() -> None:
    op.add_column(
        "message",
        sa.Column("content", sa.String(), nullable=False, server_default=""),
    )
    op.execute(
        """
        UPDATE message
        SET content = COALESCE(
            (
                SELECT string_agg(chunk->>'content', '')
                FROM json_array_elements(chunks) AS chunk
                WHERE chunk->>'type' = 'message_content'
            ),
            ''
        )
        """
    )
    op.alter_column("message", "content", server_default=None)
    op.drop_column("message", "chunks")
