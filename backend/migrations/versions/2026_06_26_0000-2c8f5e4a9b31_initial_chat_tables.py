"""initial chat tables

Revision ID: 2c8f5e4a9b31
Revises:
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "2c8f5e4a9b31"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chatsession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chatsession_client_id"), "chatsession", ["client_id"], unique=False
    )

    op.create_table(
        "message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chatsession.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_message_chat_id"), "message", ["chat_id"], unique=False)
    op.create_index(op.f("ix_message_role"), "message", ["role"], unique=False)
    op.create_index(op.f("ix_message_status"), "message", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_message_status"), table_name="message")
    op.drop_index(op.f("ix_message_role"), table_name="message")
    op.drop_index(op.f("ix_message_chat_id"), table_name="message")
    op.drop_table("message")
    op.drop_index(op.f("ix_chatsession_client_id"), table_name="chatsession")
    op.drop_table("chatsession")
