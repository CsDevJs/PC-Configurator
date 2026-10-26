"""users and saved builds

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The enum type already exists (created in 0001); only reference it.
    category = postgresql.ENUM(name="component_category", create_type=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "builds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "build_items",
        sa.Column(
            "build_id", sa.Integer(), sa.ForeignKey("builds.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("category", category, primary_key=True),
        sa.Column(
            "component_id",
            sa.Integer(),
            sa.ForeignKey("components.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("saved_price_mdl", sa.Numeric(10, 2)),
        sa.Column("saved_store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_table("build_items")
    op.drop_table("builds")
    op.drop_table("users")
