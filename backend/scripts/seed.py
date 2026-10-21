"""Load the catalog seed CSVs into the database.

Usage (from backend/):  python -m scripts.seed

Idempotent: every row is upserted by its natural key (component slug, store slug,
component+store for offers), so re-running after editing a CSV updates the DB.
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import ARRAY, Boolean, Date, Integer, Numeric, func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import SPEC_MODELS, Category, Component, Offer, Store
from app.db.session import engine

DATA_DIR = Path(__file__).resolve().parent.parent / "seed" / "data"
COMPONENT_FIELDS = ("slug", "tier", "brand", "model", "perf_score", "perf_source", "power_draw_w", "release_year")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def convert(table, row: dict[str, str]) -> dict:
    """Turn CSV strings into Python values based on each column's SQL type."""
    out = {}
    for key, raw in row.items():
        col_type = table.c[key].type
        if raw == "":
            out[key] = None
        elif isinstance(col_type, ARRAY):
            out[key] = raw.split("|")
        elif isinstance(col_type, Boolean):
            out[key] = raw.strip().lower() == "true"
        elif isinstance(col_type, Integer):
            out[key] = int(raw)
        elif isinstance(col_type, Numeric):
            out[key] = Decimal(raw)
        elif isinstance(col_type, Date):
            out[key] = date.fromisoformat(raw)
        else:
            out[key] = raw
    return out


def upsert(conn, table, rows: list[dict], key: list[str]) -> None:
    if not rows:
        return
    stmt = insert(table).values(rows)
    updates = {c: stmt.excluded[c] for c in rows[0] if c not in key}
    conn.execute(stmt.on_conflict_do_update(index_elements=key, set_=updates))


def main() -> None:
    components_table = Component.__table__
    with engine.begin() as conn:
        stores = [convert(Store.__table__, r) for r in read_csv(DATA_DIR / "stores.csv")]
        upsert(conn, Store.__table__, stores, ["slug"])

        for category, spec_model in SPEC_MODELS.items():
            path = DATA_DIR / "components" / f"{category.value}.csv"
            if not path.exists():
                continue
            spec_table = spec_model.__table__
            for row in read_csv(path):
                base = {k: row[k] for k in COMPONENT_FIELDS}
                component = convert(components_table, base) | {"category": category}
                upsert(conn, components_table, [component], ["slug"])
                component_id = conn.execute(
                    select(components_table.c.id).where(components_table.c.slug == row["slug"])
                ).scalar_one()

                spec_raw = {k: v for k, v in row.items() if k not in COMPONENT_FIELDS}
                spec = convert(spec_table, spec_raw) | {"component_id": component_id}
                upsert(conn, spec_table, [spec], ["component_id"])

        component_ids = dict(conn.execute(select(components_table.c.slug, components_table.c.id)).all())
        store_ids = dict(conn.execute(select(Store.__table__.c.slug, Store.__table__.c.id)).all())
        offers = []
        for row in read_csv(DATA_DIR / "offers.csv"):
            component_slug = row.pop("component_slug")
            store_slug = row.pop("store_slug")
            if component_slug not in component_ids:
                raise ValueError(f"offers.csv references unknown component '{component_slug}'")
            offer = convert(Offer.__table__, row)
            offer["component_id"] = component_ids[component_slug]
            offer["store_id"] = store_ids[store_slug]
            offers.append(offer)
        upsert(conn, Offer.__table__, offers, ["component_id", "store_id"])

    counts = {c.value: 0 for c in Category}
    with engine.connect() as conn:
        for category, n in conn.execute(
            select(components_table.c.category, func.count()).group_by(components_table.c.category)
        ):
            counts[category.value] = n
        offer_count = conn.execute(select(func.count()).select_from(Offer.__table__)).scalar_one()
    print("components per category:", counts)
    print("offers:", offer_count)


if __name__ == "__main__":
    main()
