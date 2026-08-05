"""merge Alembic heads

Revision ID: 8e1aa18725cb
Revises: ea62939d14ff, 879882220532
Create Date: 2026-08-05 22:44:28.089061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e1aa18725cb'
down_revision: Union[str, None] = ('ea62939d14ff', '879882220532')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
