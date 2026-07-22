"""use jsonb for recorded event metadata

Revision ID: 7ec9c6b679d9
Revises: cd394fd503ad
Create Date: 2026-07-20 10:11:16.541816

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7ec9c6b679d9"
down_revision: Union[str, None] = "cd394fd503ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_recordedevent_keywords_text_trgm",
        table_name="recordedevent",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_recordedevent_tags_gin",
        table_name="recordedevent",
        postgresql_using="gin",
    )

    for column_name in (
        "tags",
        "keywords",
        "affected_profession_categories",
        "response_profession_categories",
    ):
        op.alter_column(
            "recordedevent",
            column_name,
            existing_type=postgresql.JSON(astext_type=sa.Text()),
            type_=postgresql.JSONB(astext_type=sa.Text()),
            existing_nullable=False,
            postgresql_using=f"{column_name}::jsonb",
        )

    op.create_index(
        "ix_recordedevent_tags_gin",
        "recordedevent",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_recordedevent_keywords_text_trgm",
        "recordedevent",
        [sa.literal_column("CAST(keywords AS TEXT)").label("keywords_text")],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"keywords_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_recordedevent_affected_profession_categories_gin",
        "recordedevent",
        ["affected_profession_categories"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_recordedevent_response_profession_categories_gin",
        "recordedevent",
        ["response_profession_categories"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    for index_name in (
        "ix_recordedevent_response_profession_categories_gin",
        "ix_recordedevent_affected_profession_categories_gin",
        "ix_recordedevent_keywords_text_trgm",
        "ix_recordedevent_tags_gin",
    ):
        op.drop_index(
            index_name,
            table_name="recordedevent",
            postgresql_using="gin",
        )

    for column_name in (
        "response_profession_categories",
        "affected_profession_categories",
        "keywords",
        "tags",
    ):
        op.alter_column(
            "recordedevent",
            column_name,
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            type_=postgresql.JSON(astext_type=sa.Text()),
            existing_nullable=False,
            postgresql_using=f"{column_name}::json",
        )

    op.create_index(
        "ix_recordedevent_tags_gin",
        "recordedevent",
        [sa.literal_column("CAST(tags AS JSONB)").label("tags_jsonb")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_recordedevent_keywords_text_trgm",
        "recordedevent",
        [sa.literal_column("CAST(keywords AS TEXT)").label("keywords_text")],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"keywords_text": "gin_trgm_ops"},
    )
