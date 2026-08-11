"""structured event tagging

Revision ID: cd394fd503ad
Revises: 37a26f3a92e1
Create Date: 2026-07-19 13:34:11.839672

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd394fd503ad"
down_revision: Union[str, None] = "37a26f3a92e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recordedevent",
        sa.Column("keywords", sa.JSON(), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column("affected_profession_categories", sa.JSON(), nullable=True),
    )
    op.add_column(
        "recordedevent",
        sa.Column("response_profession_categories", sa.JSON(), nullable=True),
    )

    op.execute("UPDATE recordedevent SET keywords = tags")
    op.execute(
        """
        UPDATE recordedevent AS event
        SET tags = COALESCE(
            (
                SELECT json_agg(recognized.tag_value ORDER BY recognized.first_position)
                FROM (
                    SELECT
                        legacy.tag_value,
                        MIN(legacy.position) AS first_position
                    FROM json_array_elements_text(event.tags)
                        WITH ORDINALITY AS legacy(tag_value, position)
                    WHERE legacy.tag_value = ANY (
                        ARRAY[
                            'health_incident',
                            'disease_outbreak',
                            'mortality_or_safe_burial',
                            'supply_shortage',
                            'equipment_issue',
                            'staffing_gap',
                            'infrastructure_or_energy_failure',
                            'wash_issue',
                            'service_disruption',
                            'access_constraint',
                            'security_incident',
                            'displacement',
                            'food_or_nutrition_insecurity',
                            'environmental_hazard',
                            'coordination_or_information_gap',
                            'community_concern'
                        ]
                    )
                    GROUP BY legacy.tag_value
                ) AS recognized
            ),
            '["other"]'::json
        )
        """
    )
    op.execute(
        """
        UPDATE recordedevent
        SET
            affected_profession_categories = '[]'::json,
            response_profession_categories = '[]'::json
        """
    )

    op.alter_column("recordedevent", "keywords", nullable=False)
    op.alter_column(
        "recordedevent",
        "affected_profession_categories",
        nullable=False,
    )
    op.alter_column(
        "recordedevent",
        "response_profession_categories",
        nullable=False,
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_recordedevent_tags_gin "
        "ON recordedevent USING gin ((tags::jsonb))"
    )
    op.execute(
        "CREATE INDEX ix_recordedevent_keywords_text_trgm "
        "ON recordedevent USING gin ((keywords::text) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_keywords_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_recordedevent_tags_gin")
    op.execute("UPDATE recordedevent SET tags = keywords")
    op.drop_column("recordedevent", "response_profession_categories")
    op.drop_column("recordedevent", "affected_profession_categories")
    op.drop_column("recordedevent", "keywords")
