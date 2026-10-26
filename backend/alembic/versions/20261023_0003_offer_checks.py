"""offers: regular price for sales, last check status

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("regular_price_mdl", sa.Numeric(10, 2)))
    op.add_column("offers", sa.Column("last_check_status", sa.String(9)))
    op.create_check_constraint(
        "regular_above_price", "offers", "regular_price_mdl IS NULL OR regular_price_mdl > price_mdl"
    )
    op.create_check_constraint(
        "check_status", "offers", "last_check_status IS NULL OR last_check_status IN ('ok', 'failed', 'page_gone')"
    )


def downgrade() -> None:
    op.drop_constraint("check_status", "offers", type_="check")
    op.drop_constraint("regular_above_price", "offers", type_="check")
    op.drop_column("offers", "last_check_status")
    op.drop_column("offers", "regular_price_mdl")
