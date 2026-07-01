"""add auth user profiles

Revision ID: 3f7a9d2c1e5b
Revises: a5d7c9e3f2b4
Create Date: 2026-06-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "3f7a9d2c1e5b"
down_revision: Union[str, None] = "a5d7c9e3f2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
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

    op.add_column("chatsession", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "recordedevent", sa.Column("initiated_by_user_id", sa.Uuid(), nullable=True)
    )

    op.execute(
        """
        INSERT INTO userprofile (
            id,
            keycloak_sub,
            email,
            username,
            first_name,
            last_name,
            properties,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            client_id,
            NULL,
            NULL,
            NULL,
            NULL,
            '{}'::json,
            now(),
            now()
        FROM (
            SELECT client_id FROM chatsession
            UNION
            SELECT initiated_by_client_id AS client_id FROM recordedevent
        ) legacy_users
        WHERE client_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE chatsession
        SET user_id = userprofile.id
        FROM userprofile
        WHERE userprofile.keycloak_sub = chatsession.client_id
        """
    )
    op.execute(
        """
        UPDATE recordedevent
        SET initiated_by_user_id = userprofile.id
        FROM userprofile
        WHERE userprofile.keycloak_sub = recordedevent.initiated_by_client_id
        """
    )

    op.alter_column("chatsession", "user_id", nullable=False)
    op.alter_column("recordedevent", "initiated_by_user_id", nullable=False)
    op.create_index(op.f("ix_chatsession_user_id"), "chatsession", ["user_id"])
    op.create_index(
        op.f("ix_recordedevent_initiated_by_user_id"),
        "recordedevent",
        ["initiated_by_user_id"],
    )
    op.create_foreign_key(
        "fk_chatsession_user_id_userprofile",
        "chatsession",
        "userprofile",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_recordedevent_initiated_by_user_id_userprofile",
        "recordedevent",
        "userprofile",
        ["initiated_by_user_id"],
        ["id"],
    )

    op.drop_index(op.f("ix_recordedevent_initiated_by_client_id"), "recordedevent")
    op.drop_column("recordedevent", "initiated_by_client_id")
    op.drop_index(op.f("ix_chatsession_client_id"), "chatsession")
    op.drop_column("chatsession", "client_id")


def downgrade() -> None:
    op.add_column(
        "chatsession",
        sa.Column("client_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column(
            "initiated_by_client_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE chatsession
        SET client_id = userprofile.keycloak_sub
        FROM userprofile
        WHERE userprofile.id = chatsession.user_id
        """
    )
    op.execute(
        """
        UPDATE recordedevent
        SET initiated_by_client_id = userprofile.keycloak_sub
        FROM userprofile
        WHERE userprofile.id = recordedevent.initiated_by_user_id
        """
    )

    op.alter_column("recordedevent", "initiated_by_client_id", nullable=False)
    op.alter_column("chatsession", "client_id", nullable=False)
    op.create_index(
        op.f("ix_recordedevent_initiated_by_client_id"),
        "recordedevent",
        ["initiated_by_client_id"],
    )
    op.create_index(op.f("ix_chatsession_client_id"), "chatsession", ["client_id"])

    op.drop_constraint(
        "fk_recordedevent_initiated_by_user_id_userprofile",
        "recordedevent",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_chatsession_user_id_userprofile",
        "chatsession",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_recordedevent_initiated_by_user_id"), table_name="recordedevent"
    )
    op.drop_index(op.f("ix_chatsession_user_id"), table_name="chatsession")
    op.drop_column("recordedevent", "initiated_by_user_id")
    op.drop_column("chatsession", "user_id")

    op.drop_index(op.f("ix_userprofile_username"), table_name="userprofile")
    op.drop_index(op.f("ix_userprofile_keycloak_sub"), table_name="userprofile")
    op.drop_index(op.f("ix_userprofile_email"), table_name="userprofile")
    op.drop_table("userprofile")
