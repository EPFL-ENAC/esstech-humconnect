"""store recorded event locations relationally

Revision ID: fbb70b582e55
Revises: 7aa296dca4e7
Create Date: 2026-07-20 14:29:52.333401

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "fbb70b582e55"
down_revision: Union[str, None] = "7aa296dca4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column_name in (
        "location_raw_text",
        "location_region",
        "location_city",
        "location_address",
        "location_place_name",
        "location_detail",
    ):
        op.add_column(
            "recordedevent",
            sa.Column(column_name, sa.String(), nullable=True),
        )
    op.add_column(
        "recordedevent",
        sa.Column("location_continent", sa.String(), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column("location_country_code", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column("location_latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column("location_longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column("location_granularity", sa.String(), nullable=True),
    )

    op.execute(
        """
        UPDATE recordedevent
        SET
            location_raw_text = NULLIF(BTRIM(event_location ->> 'value'), ''),
            location_region = CASE
                WHEN event_location ->> 'precision' = 'region'
                THEN NULLIF(BTRIM(event_location ->> 'value'), '')
            END,
            location_city = CASE
                WHEN event_location ->> 'precision' = 'city'
                THEN NULLIF(BTRIM(event_location ->> 'value'), '')
            END,
            location_place_name = CASE
                WHEN event_location ->> 'precision' = 'exact'
                THEN NULLIF(BTRIM(event_location ->> 'value'), '')
            END,
            location_granularity = CASE
                WHEN NULLIF(BTRIM(event_location ->> 'value'), '') IS NULL
                THEN 'unknown'
                WHEN event_location ->> 'precision' = 'exact' THEN 'place'
                WHEN event_location ->> 'precision' IN ('city', 'region')
                THEN event_location ->> 'precision'
                WHEN event_location ->> 'precision' = 'country' THEN 'country'
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
        "ck_recordedevent_location_continent",
        "recordedevent",
        "location_continent IN ("
        "'africa', 'antarctica', 'asia', 'europe', "
        "'north_america', 'oceania', 'south_america'"
        ")",
    )
    op.create_check_constraint(
        "ck_recordedevent_location_country_code",
        "recordedevent",
        "location_country_code ~ '^[A-Z]{2}$'",
    )
    op.create_check_constraint(
        "ck_recordedevent_location_latitude_range",
        "recordedevent",
        "location_latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_recordedevent_location_longitude_range",
        "recordedevent",
        "location_longitude BETWEEN -180 AND 180",
    )
    op.create_check_constraint(
        "ck_recordedevent_location_granularity",
        "recordedevent",
        "location_granularity IN ("
        "'coordinates', 'address', 'place', 'city', 'region', "
        "'country', 'continent', 'unknown'"
        ")",
    )
    op.create_check_constraint(
        "ck_recordedevent_location_coordinate_pair",
        "recordedevent",
        "(location_latitude IS NULL) = (location_longitude IS NULL)",
    )

    for column_name in (
        "location_continent",
        "location_country_code",
        "location_latitude",
        "location_longitude",
    ):
        op.create_index(
            op.f(f"ix_recordedevent_{column_name}"),
            "recordedevent",
            [column_name],
            unique=False,
        )

    op.drop_column("recordedevent", "event_location")


def downgrade() -> None:
    op.add_column(
        "recordedevent",
        sa.Column(
            "event_location",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE recordedevent
        SET event_location = json_build_object(
            'value', COALESCE(
                location_raw_text,
                location_address,
                location_place_name,
                location_city,
                location_region,
                location_country_code,
                location_continent,
                CASE
                    WHEN location_latitude IS NOT NULL
                    THEN location_latitude::text || ', ' || location_longitude::text
                END
            ),
            'precision', CASE location_granularity
                WHEN 'coordinates' THEN 'exact'
                WHEN 'address' THEN 'exact'
                WHEN 'place' THEN 'exact'
                WHEN 'city' THEN 'city'
                WHEN 'region' THEN 'region'
                WHEN 'country' THEN 'country'
                WHEN 'continent' THEN 'region'
                ELSE 'unknown'
            END
        )
        """
    )
    op.alter_column(
        "recordedevent",
        "event_location",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=False,
    )

    for column_name in (
        "location_longitude",
        "location_latitude",
        "location_country_code",
        "location_continent",
    ):
        op.drop_index(
            op.f(f"ix_recordedevent_{column_name}"),
            table_name="recordedevent",
        )

    for constraint_name in (
        "ck_recordedevent_location_coordinate_pair",
        "ck_recordedevent_location_granularity",
        "ck_recordedevent_location_longitude_range",
        "ck_recordedevent_location_latitude_range",
        "ck_recordedevent_location_country_code",
        "ck_recordedevent_location_continent",
    ):
        op.drop_constraint(
            constraint_name,
            "recordedevent",
            type_="check",
        )

    for column_name in (
        "location_granularity",
        "location_longitude",
        "location_latitude",
        "location_detail",
        "location_place_name",
        "location_address",
        "location_city",
        "location_region",
        "location_country_code",
        "location_continent",
        "location_raw_text",
    ):
        op.drop_column("recordedevent", column_name)
