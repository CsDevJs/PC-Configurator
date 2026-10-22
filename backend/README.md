# Backend

FastAPI + PostgreSQL backend for the PC Configurator. Currently contains the
component catalog: schema, migrations and seed data.

## Setup

1. Create a database and role (in `psql` as `postgres`):

   ```sql
   CREATE ROLE pc_app LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE pc_configurator OWNER pc_app;
   ```

2. Copy `.env.example` to `.env` and put your password in `DATABASE_URL`.
   `.env` is git-ignored.

3. Install dependencies, create the tables, and load the seed data:

   ```bash
   python -m venv .venv
   .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
   .venv/Scripts/alembic upgrade head
   .venv/Scripts/python -m scripts.seed
   ```

## Schema

| Table | Purpose |
|---|---|
| `components` | One row per product: category, tier (`low`/`mid`/`high`), brand, model, `perf_score`, `power_draw_w` |
| `cpu_specs`, `motherboard_specs`, `ram_specs`, `gpu_specs`, `storage_specs`, `psu_specs`, `case_specs`, `cooler_specs` | Typed specs, one row per component, keyed by `component_id` |
| `stores` | Xstore, NeoComputer, Darwin, Ultra |
| `offers` | A store's price (MDL), availability and product URL for a component; one row per (component, store) |

The fields used by compatibility checks:

- CPU `socket` ↔ motherboard `socket`
- CPU `memory_types` ∋ motherboard `memory_type` = RAM `memory_type`
- Motherboard `form_factor` ∈ case `supported_board_form_factors`
- GPU `length_mm` ≤ case `max_gpu_length_mm`
- Air cooler `height_mm` ≤ case `max_cooler_height_mm`; AIO `radiator_mm` ≤ case `max_radiator_mm`
- CPU `socket` ∈ cooler `supported_sockets`
- PSU `wattage` vs. the sum of `power_draw_w`

## Seed data

All catalog data is in one SQL file, `seed/seed.sql`, grouped by section: stores,
then each category (its `components` rows followed by its spec rows), then
store offers. Rows reference each other by `slug`, never by numeric id.

Load it in either of two ways (after `alembic upgrade head`):

- `python -m scripts.seed` from `backend/`, or
- open `seed/seed.sql` in pgAdmin's Query Tool, connected to `pc_configurator`, and press F5.

Every `INSERT` ends in `ON CONFLICT … DO UPDATE`, so the file is safe to re-run.
To change a price or add a part, edit `seed.sql` and run it again.

### Where the data came from (2026-10-21)

- **Prices and URLs** were looked up by hand on each store's website on 2026-10-21.
  They are the current (discounted) prices shown on the site.
- **Availability**: Darwin and Ultra were checked on each product page
  ("Stoc epuizat" / "Notifică" → `out_of_stock`). Xstore and NeoComputer don't
  show stock clearly, so an offer is marked `in_stock` when the product can be
  added to the cart.
- **NeoComputer RAM**: listings don't show Kingston part numbers. They were
  matched by capacity, speed and series.
- **Specs** come from the store spec tables, corrected with manufacturer specs
  where the store was clearly wrong.
- **`perf_score` values are rough estimates** (`perf_source` says so), only for
  CPUs and GPUs. Replace them with sourced benchmark numbers before the evaluation chapter.
