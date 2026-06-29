"""add recorded events

Revision ID: a5d7c9e3f2b4
Revises: 8f2c9d4a1b7e
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "a5d7c9e3f2b4"
down_revision: Union[str, None] = "8f2c9d4a1b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recordedevent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column(
            "initiated_by_client_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("source_message_id", sa.Uuid(), nullable=False),
        sa.Column("original_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("event_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("event_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "event_date_granularity",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "event_date_precision",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("event_date_input", sa.JSON(), nullable=False),
        sa.Column("event_location", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chatsession.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["message.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recordedevent_chat_id"),
        "recordedevent",
        ["chat_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordedevent_event_date_granularity"),
        "recordedevent",
        ["event_date_granularity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordedevent_event_date_precision"),
        "recordedevent",
        ["event_date_precision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordedevent_event_datetime"),
        "recordedevent",
        ["event_datetime"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordedevent_created_at"),
        "recordedevent",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordedevent_initiated_by_client_id"),
        "recordedevent",
        ["initiated_by_client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recordedevent_source_message_id"),
        "recordedevent",
        ["source_message_id"],
        unique=False,
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_recordedevent_tags_gin "
        "ON recordedevent USING gin ((tags::jsonb))"
    )
    op.execute(
        "CREATE INDEX ix_recordedevent_event_name_trgm "
        "ON recordedevent USING gin (event_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_recordedevent_original_text_trgm "
        "ON recordedevent USING gin (original_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_recordedevent_event_location_trgm "
        "ON recordedevent USING gin ((event_location::text) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_recordedevent_tags_text_trgm "
        "ON recordedevent USING gin ((tags::text) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_tags_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_event_location_trgm")
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_original_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_event_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_tags_gin")
    op.drop_index(op.f("ix_recordedevent_source_message_id"), table_name="recordedevent")
    op.drop_index(
        op.f("ix_recordedevent_initiated_by_client_id"), table_name="recordedevent"
    )
    op.drop_index(op.f("ix_recordedevent_created_at"), table_name="recordedevent")
    op.drop_index(op.f("ix_recordedevent_event_datetime"), table_name="recordedevent")
    op.drop_index(
        op.f("ix_recordedevent_event_date_precision"), table_name="recordedevent"
    )
    op.drop_index(
        op.f("ix_recordedevent_event_date_granularity"), table_name="recordedevent"
    )
    op.drop_index(op.f("ix_recordedevent_chat_id"), table_name="recordedevent")
    op.drop_table("recordedevent")
