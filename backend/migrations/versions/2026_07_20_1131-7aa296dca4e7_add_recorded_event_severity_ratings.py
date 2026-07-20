"""add recorded event severity ratings

Revision ID: 7aa296dca4e7
Revises: 7ec9c6b679d9
Create Date: 2026-07-20 11:31:56.406500

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7aa296dca4e7"
down_revision: Union[str, None] = "7ec9c6b679d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for scale in ("local", "country", "global"):
        column_name = f"{scale}_severity"
        op.add_column(
            "recordedevent",
            sa.Column(column_name, sa.Float(), nullable=True),
        )
        op.create_check_constraint(
            f"ck_recordedevent_{column_name}_range",
            "recordedevent",
            f"{column_name} BETWEEN 0 AND 10",
        )


def downgrade() -> None:
    for scale in ("global", "country", "local"):
        column_name = f"{scale}_severity"
        op.drop_constraint(
            f"ck_recordedevent_{column_name}_range",
            "recordedevent",
            type_="check",
        )
        op.drop_column("recordedevent", column_name)
