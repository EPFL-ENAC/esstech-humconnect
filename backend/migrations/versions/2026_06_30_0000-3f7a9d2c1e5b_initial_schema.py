"""initial schema

Revision ID: 3f7a9d2c1e5b
Revises:
Create Date: 2026-06-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "3f7a9d2c1e5b"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "userprofile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("keycloak_sub", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keycloak_sub"),
    )
    op.create_index(op.f("ix_userprofile_email"), "userprofile", ["email"])
    op.create_index(
        op.f("ix_userprofile_keycloak_sub"), "userprofile", ["keycloak_sub"]
    )
    op.create_index(op.f("ix_userprofile_username"), "userprofile", ["username"])

    op.create_table(
        "chatsession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["userprofile.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chatsession_user_id"), "chatsession", ["user_id"])

    op.create_table(
        "message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("chunks", sa.JSON(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chatsession.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_message_chat_id"), "message", ["chat_id"])
    op.create_index(op.f("ix_message_role"), "message", ["role"])
    op.create_index(op.f("ix_message_status"), "message", ["status"])

    op.create_table(
        "recordedevent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("initiated_by_user_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["userprofile.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["message.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recordedevent_chat_id"), "recordedevent", ["chat_id"])
    op.create_index(
        op.f("ix_recordedevent_created_at"), "recordedevent", ["created_at"]
    )
    op.create_index(
        op.f("ix_recordedevent_event_date_granularity"),
        "recordedevent",
        ["event_date_granularity"],
    )
    op.create_index(
        op.f("ix_recordedevent_event_date_precision"),
        "recordedevent",
        ["event_date_precision"],
    )
    op.create_index(
        op.f("ix_recordedevent_event_datetime"), "recordedevent", ["event_datetime"]
    )
    op.create_index(
        op.f("ix_recordedevent_initiated_by_user_id"),
        "recordedevent",
        ["initiated_by_user_id"],
    )
    op.create_index(
        op.f("ix_recordedevent_source_message_id"),
        "recordedevent",
        ["source_message_id"],
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
    op.drop_index(
        op.f("ix_recordedevent_source_message_id"), table_name="recordedevent"
    )
    op.drop_index(
        op.f("ix_recordedevent_initiated_by_user_id"), table_name="recordedevent"
    )
    op.drop_index(op.f("ix_recordedevent_event_datetime"), table_name="recordedevent")
    op.drop_index(
        op.f("ix_recordedevent_event_date_precision"), table_name="recordedevent"
    )
    op.drop_index(
        op.f("ix_recordedevent_event_date_granularity"), table_name="recordedevent"
    )
    op.drop_index(op.f("ix_recordedevent_created_at"), table_name="recordedevent")
    op.drop_index(op.f("ix_recordedevent_chat_id"), table_name="recordedevent")
    op.drop_table("recordedevent")
    op.drop_index(op.f("ix_message_status"), table_name="message")
    op.drop_index(op.f("ix_message_role"), table_name="message")
    op.drop_index(op.f("ix_message_chat_id"), table_name="message")
    op.drop_table("message")
    op.drop_index(op.f("ix_chatsession_user_id"), table_name="chatsession")
    op.drop_table("chatsession")
    op.drop_index(op.f("ix_userprofile_username"), table_name="userprofile")
    op.drop_index(op.f("ix_userprofile_keycloak_sub"), table_name="userprofile")
    op.drop_index(op.f("ix_userprofile_email"), table_name="userprofile")
    op.drop_table("userprofile")
