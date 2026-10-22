# Backend

FastAPI + PostgreSQL backend for the PC Configurator. Contains the component
catalog schema, migrations, manually maintained seed data, a read-only catalog
API, and compatibility checks that do not modify stored data.
Python 3.12 or newer is recommended. Run all commands below from `backend/`.

## Setup

1. Create a database and role (in `psql` as `postgres`):

   ```sql
   CREATE ROLE pc_app LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE pc_configurator OWNER pc_app;
   ```

2. Copy `.env.example` to `.env` and put your password in `DATABASE_URL`.
   `.env` is git-ignored.

3. Install dependencies, create the tables, and load the seed data (Linux/macOS):

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -m alembic upgrade head
   .venv/bin/python -m scripts.seed
   ```

   On Windows, create the environment with `python -m venv .venv` and replace
   `.venv/bin/python` with `.venv\Scripts\python.exe` in the remaining commands.

4. Start the API:

   ```bash
   .venv/bin/python -m uvicorn app.main:app --reload
   ```

   Interactive API documentation: <http://127.0.0.1:8000/docs>.
   OpenAPI schema: <http://127.0.0.1:8000/openapi.json>.
   The API does not create tables or seed data automatically.

## API

| Method | Path | Result |
|---|---|---|
| GET | `/health` | API liveness; no database query |
| GET | `/health/db` | PostgreSQL connectivity; HTTP 503 if unavailable |
| GET | `/components` | Paginated components with store offers |
| GET | `/components/{component_id}` | A component's specifications and store offers; HTTP 404 if absent |
| GET | `/stores` | Stores sorted by name |
| POST | `/compatibility/check` | Check a complete or partial selection without saving it |

`/components` supports optional `category`, `tier`, and `brand` filters.
Categories: `cpu`, `motherboard`, `ram`, `gpu`, `storage`, `psu`, `case`, `cooler`.
Tiers: `low`, `mid`, `high`. Brand matching is exact, case-insensitive, and trims
surrounding spaces. Combined filters use AND.

Example: <http://127.0.0.1:8000/components?category=cpu&tier=low&brand=AMD&limit=10&offset=0>.

The response has `items`, `total` (matching rows before pagination), `limit`
(default 20, range 1–100), and `offset` (default 0, nonnegative). Components are
ordered by ID so pagination is deterministic. Invalid parameters return HTTP 422.

Component details include a typed `specs` object for their category. If a manually
entered component has no specifications yet, `specs` is `null`. A component without
offers returns `offers: []`. All offers are included, including out-of-stock and
on-order offers, ordered by price and then store ID. Each offer includes its store,
availability, product URL, and `checked_on` date. Decimal values such as `price_mdl`
are JSON strings (e.g. `"2499.00"`) to preserve precision. Unknown stock quantities
are `null`, rather than zero.

Data comes exclusively from PostgreSQL. There are no store API calls, scraping,
or automatic updates. Continue editing and rerunning `seed/seed.sql` to maintain
the catalog. Accounts, saved builds, and catalog editing endpoints are not yet
implemented.

## Compatibility checks

Send a JSON object to `POST /compatibility/check`. Obtain component IDs from
`GET /components`; IDs below are examples, not guaranteed across databases:

```json
{
  "components": {
    "cpu": 1,
    "motherboard": 7,
    "ram": 13
  }
}
```

The MVP accepts one component per category: one RAM kit and one storage device.
Partial builds are allowed, but at least one selection is required. IDs must be
positive JSON integers; duplicate IDs, unknown categories, extra request fields,
and a component selected under the wrong category return HTTP 422. IDs absent
from the catalog return HTTP 404. A valid request returns HTTP 200 even when the
parts are incompatible: compatibility is the result, not an HTTP failure.

The response includes:

- `status`: `incompatible` if a known conflict exists; otherwise `incomplete` if
  required categories are absent; otherwise `undetermined` if selected data
  cannot resolve a modeled check; otherwise `compatible` under the modeled rules.
- `missing_categories`: CPU, motherboard, RAM, storage, PSU, and case are required.
  A discrete GPU is also required when the selected CPU has no integrated graphics;
  a separate cooler is required when the CPU does not include one. An unknown CPU
  spec cannot establish those extra requirements and is reported as missing data.
- `issues`: stable rule `code`, `severity` (`error` or `warning`), affected
  `component_ids`, and a human-readable `message` with relevant values.
- `checked_rules`: codes of hard constraints actually evaluated, whether passed
  or failed. A missing component or missing spec never counts as a passed check.
- `estimated_power_w`: sum of recorded peak draw for selected parts, excluding
  the PSU itself. For partial builds this is only a lower bound.
- `recommended_psu_w`: the greater of rounded-up peak draw plus 20% and the GPU's
  recorded PSU recommendation. The 20% margin is an MVP policy. Capacity below
  recorded draw is an error; capacity meeting draw but below the recommendation
  is a warning. This is an estimate, not measured consumption.
- `limitations`: checks the current schema cannot fully establish. `compatible`
  means no conflicts in the modeled rules; it is not a physical assembly guarantee.

Implemented rules:

| Area | Checks |
|---|---|
| Platform | CPU/motherboard sockets; CPU memory support; motherboard/RAM DDR generation |
| RAM | Kit module count versus available slots; kit capacity versus board maximum |
| Case | Motherboard form factor; GPU length; air cooler height |
| Cooling | Cooler socket support; AIO maximum radiator size; advisory thermal rating |
| Storage | M.2 slot for M.2 NVMe; SATA port for non-M.2 SATA storage |
| Power | Selected peak draw versus PSU wattage; recommended capacity with margin |

Unknown specifications and empty supported-value lists produce warnings and
cannot establish compatibility. PSU/case form-factor differences are unresolved
because adapters are not modeled. AIO radiator sizes above the case maximum are
conflicts; sizes within the maximum still require exact mount verification.
The existing catalog defines `max_radiator_mm = null` as no AIO radiator support;
selecting an AIO with such a case returns a conflict. A missing case spec is
reported as unknown data instead.
M.2 SATA protocol support and non-M.2 NVMe connections require manual verification.

Motherboard CPU support/BIOS versions, power cable inventories, drive bays, exact
M.2 lengths/protocols, and interacting clearances are not fully modeled. Matching
sockets alone do not establish CPU support; see [Intel's compatibility guidance](https://www.intel.com/content/www/us/en/support/articles/000092149/processors.html).
Radiator fit also depends on dimensions and mounting arrangements; see
[Corsair's radiator guidance](https://help.corsair.com/hc/en-us/articles/360052178672-Hydro-X-Tips-on-choosing-the-right-radiator-for-your-Hydro-X-cooler).

Rule code lives in `app/services/compatibility.py`, independently of HTTP/database
access. Binary rules are available through `check_pair` for later AC-3 reuse;
build completeness and total power are checked separately by `check_build`.
AC-3 domain filtering, recommendation generation, Min-Cost Max-Flow, and TOPSIS
are future milestones; this endpoint checks a user's existing selection.

## Tests

Install test dependencies and run:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

HTTP validation, compatibility rule boundaries, liveness, OpenAPI, and
unavailable-database checks run without PostgreSQL. Catalog and compatibility
endpoint integration tests are skipped unless `TEST_DATABASE_URL` is
set. Use a **separate test database** with migrations and seed data loaded:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://pc_app:YOUR_PASSWORD@localhost:5432/pc_configurator_test'
DATABASE_URL="$TEST_DATABASE_URL" .venv/bin/python -m alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" .venv/bin/python -m scripts.seed
.venv/bin/python -m pytest -q
```

Create `pc_configurator_test` first with the same role as in setup. In PowerShell,
use `$env:TEST_DATABASE_URL = '...'` and `$env:DATABASE_URL = $env:TEST_DATABASE_URL`
before running the migration and seed commands. Integration tests use transactions
that roll back their changes; the database must still be dedicated to tests.

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
