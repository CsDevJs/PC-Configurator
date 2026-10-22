"""Load the catalog seed data (seed/seed.sql) into the database.

Usage (from backend/):  python -m scripts.seed

seed.sql is plain SQL, so you can also paste it into pgAdmin's Query Tool.
It upserts every row, so running it again after editing a price updates the DB.
"""

from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from app.config import settings

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "seed.sql"


def main() -> None:
    # psycopg wants a plain postgresql:// URL, without SQLAlchemy's "+psycopg" driver suffix.
    url = make_url(settings.database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    # autocommit: seed.sql manages its own BEGIN/COMMIT.
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(SEED_FILE.read_text(encoding="utf-8"))
        components = conn.execute(
            "SELECT category, count(*) FROM components GROUP BY category ORDER BY category"
        ).fetchall()
        offers = conn.execute("SELECT count(*) FROM offers").fetchone()[0]
    print("components per category:", dict(components))
    print("offers:", offers)


if __name__ == "__main__":
    main()
