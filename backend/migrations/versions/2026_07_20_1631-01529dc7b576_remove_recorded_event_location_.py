"""remove recorded event location granularity

Revision ID: 01529dc7b576
Revises: fbb70b582e55
Create Date: 2026-07-20 16:31:04.768806

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "01529dc7b576"
down_revision: Union[str, None] = "fbb70b582e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("recordedevent", "location_granularity")


def downgrade() -> None:
    op.add_column(
        "recordedevent",
        sa.Column("location_granularity", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE recordedevent
        SET location_granularity = CASE
            WHEN location_latitude IS NOT NULL THEN 'coordinates'
            WHEN location_address IS NOT NULL THEN 'address'
            WHEN location_place_name IS NOT NULL THEN 'place'
            WHEN location_city IS NOT NULL THEN 'city'
            WHEN location_region IS NOT NULL THEN 'region'
            WHEN location_country_code IS NOT NULL THEN 'country'
            WHEN location_continent IS NOT NULL THEN 'continent'
            ELSE 'unknown'
        END
        """
    )
    op.alter_column(
        "recordedevent",
        "location_granularity",
        existing_type=sa.String(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_recordedevent_location_granularity",
        "recordedevent",
        "location_granularity IN ("
        "'coordinates', 'address', 'place', 'city', 'region', "
        "'country', 'continent', 'unknown'"
        ")",
    )
