"""catalog: components, per-category specs, stores, offers

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MEMORY_TYPES = "('DDR4', 'DDR5')"
BOARD_FF = "ARRAY['E-ATX', 'ATX', 'Micro-ATX', 'Mini-ITX']::text[]"


def _spec_pk() -> sa.Column:
    return sa.Column(
        "component_id", sa.Integer(), sa.ForeignKey("components.id", ondelete="CASCADE"), primary_key=True
    )


def upgrade() -> None:
    category = postgresql.ENUM(
        "cpu", "motherboard", "ram", "gpu", "storage", "psu", "case", "cooler", name="component_category"
    )
    tier = postgresql.ENUM("low", "mid", "high", name="component_tier")
    availability = postgresql.ENUM("in_stock", "on_order", "out_of_stock", name="offer_availability")

    op.create_table(
        "components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("category", category, nullable=False, index=True),
        sa.Column("tier", tier, nullable=False, index=True),
        sa.Column("brand", sa.String(60), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("perf_score", sa.Numeric(5, 1)),
        sa.Column("perf_source", sa.Text()),
        sa.Column("power_draw_w", sa.Integer(), nullable=False),
        sa.Column("release_year", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("brand", "model"),
        sa.CheckConstraint("perf_score IS NULL OR perf_score BETWEEN 0 AND 100", name="perf_score_range"),
        sa.CheckConstraint("power_draw_w >= 0", name="power_draw_nonneg"),
    )

    op.create_table(
        "cpu_specs",
        _spec_pk(),
        sa.Column("socket", sa.String(20), nullable=False, index=True),
        sa.Column("cores", sa.Integer(), nullable=False),
        sa.Column("threads", sa.Integer(), nullable=False),
        sa.Column("base_clock_ghz", sa.Numeric(3, 1), nullable=False),
        sa.Column("boost_clock_ghz", sa.Numeric(3, 1), nullable=False),
        sa.Column("tdp_w", sa.Integer(), nullable=False),
        sa.Column("integrated_graphics", sa.Boolean(), nullable=False),
        sa.Column("memory_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("includes_cooler", sa.Boolean(), nullable=False),
        sa.CheckConstraint("memory_types <@ ARRAY['DDR4', 'DDR5']::text[]", name="cpu_memory_types"),
    )

    op.create_table(
        "motherboard_specs",
        _spec_pk(),
        sa.Column("socket", sa.String(20), nullable=False, index=True),
        sa.Column("chipset", sa.String(20), nullable=False),
        sa.Column("form_factor", sa.String(12), nullable=False),
        sa.Column("memory_type", sa.String(4), nullable=False),
        sa.Column("memory_slots", sa.Integer(), nullable=False),
        sa.Column("max_memory_gb", sa.Integer(), nullable=False),
        sa.Column("m2_slots", sa.Integer(), nullable=False),
        sa.Column("sata_ports", sa.Integer(), nullable=False),
        sa.Column("wifi", sa.Boolean(), nullable=False),
        sa.CheckConstraint(f"memory_type IN {MEMORY_TYPES}", name="mb_memory_type"),
        sa.CheckConstraint("form_factor IN ('E-ATX', 'ATX', 'Micro-ATX', 'Mini-ITX')", name="mb_form_factor"),
    )

    op.create_table(
        "ram_specs",
        _spec_pk(),
        sa.Column("memory_type", sa.String(4), nullable=False),
        sa.Column("capacity_gb", sa.Integer(), nullable=False),
        sa.Column("modules", sa.Integer(), nullable=False),
        sa.Column("speed_mts", sa.Integer(), nullable=False),
        sa.Column("cas_latency", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"memory_type IN {MEMORY_TYPES}", name="ram_memory_type"),
    )

    op.create_table(
        "gpu_specs",
        _spec_pk(),
        sa.Column("chipset", sa.String(60), nullable=False),
        sa.Column("vram_gb", sa.Integer(), nullable=False),
        sa.Column("length_mm", sa.Integer(), nullable=False),
        sa.Column("slot_width", sa.Numeric(2, 1), nullable=False),
        sa.Column("tdp_w", sa.Integer(), nullable=False),
        sa.Column("recommended_psu_w", sa.Integer(), nullable=False),
        sa.Column("power_connectors", sa.String(40)),
    )

    op.create_table(
        "storage_specs",
        _spec_pk(),
        sa.Column("storage_type", sa.String(10), nullable=False),
        sa.Column("interface", sa.String(20), nullable=False),
        sa.Column("form_factor", sa.String(10), nullable=False),
        sa.Column("capacity_gb", sa.Integer(), nullable=False),
        sa.Column("read_mbps", sa.Integer()),
        sa.Column("write_mbps", sa.Integer()),
        sa.CheckConstraint("storage_type IN ('nvme', 'sata_ssd', 'hdd')", name="storage_type"),
    )

    op.create_table(
        "psu_specs",
        _spec_pk(),
        sa.Column("wattage", sa.Integer(), nullable=False),
        sa.Column("efficiency", sa.String(20), nullable=False),
        sa.Column("modular", sa.String(4), nullable=False),
        sa.Column("form_factor", sa.String(4), nullable=False),
        sa.Column("has_16pin", sa.Boolean(), nullable=False),
        sa.CheckConstraint("form_factor IN ('ATX', 'SFX')", name="psu_form_factor"),
        sa.CheckConstraint("modular IN ('none', 'semi', 'full')", name="psu_modular"),
    )

    op.create_table(
        "case_specs",
        _spec_pk(),
        sa.Column("supported_board_form_factors", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("max_gpu_length_mm", sa.Integer(), nullable=False),
        sa.Column("max_cooler_height_mm", sa.Integer(), nullable=False),
        sa.Column("max_radiator_mm", sa.Integer()),
        sa.Column("psu_form_factor", sa.String(4), nullable=False),
        sa.Column("included_fans", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"supported_board_form_factors <@ {BOARD_FF}", name="case_board_ffs"),
        sa.CheckConstraint("psu_form_factor IN ('ATX', 'SFX')", name="case_psu_form_factor"),
    )

    op.create_table(
        "cooler_specs",
        _spec_pk(),
        sa.Column("cooler_type", sa.String(3), nullable=False),
        sa.Column("supported_sockets", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("height_mm", sa.Integer()),
        sa.Column("radiator_mm", sa.Integer()),
        sa.Column("max_tdp_w", sa.Integer()),
        sa.CheckConstraint("cooler_type IN ('air', 'aio')", name="cooler_type"),
        sa.CheckConstraint(
            "(cooler_type = 'air' AND height_mm IS NOT NULL) OR (cooler_type = 'aio' AND radiator_mm IS NOT NULL)",
            name="cooler_dimensions",
        ),
    )

    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("website", sa.String(200), nullable=False),
    )

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "component_id", sa.Integer(), sa.ForeignKey("components.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("price_mdl", sa.Numeric(10, 2), nullable=False),
        sa.Column("availability", availability, nullable=False),
        sa.Column("stock_qty", sa.Integer()),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.UniqueConstraint("component_id", "store_id"),
        sa.CheckConstraint("price_mdl > 0", name="price_positive"),
        sa.CheckConstraint("stock_qty IS NULL OR stock_qty >= 0", name="stock_nonneg"),
    )


def downgrade() -> None:
    for table in (
        "offers",
        "stores",
        "cooler_specs",
        "case_specs",
        "psu_specs",
        "storage_specs",
        "gpu_specs",
        "ram_specs",
        "motherboard_specs",
        "cpu_specs",
        "components",
    ):
        op.drop_table(table)
    for enum_name in ("offer_availability", "component_tier", "component_category"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
