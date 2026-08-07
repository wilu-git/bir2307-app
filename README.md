# BIR 2307 Generator

Web app for Favor Church's BIR Form 2307 (Certificate of Creditable Tax
Withheld at Source) workflow: import the existing Excel tracker, recompute
Expanded Withholding Tax, generate the certificate PDF on the real official
form, track status through to signed/received, and search/audit everything.

Built with Streamlit + SQLite/SQLAlchemy + reportlab/pypdf, per the project
spec (`BIR2307.md`). Business logic lives in `app/core/`; `app/ui/*.py`
are thin wrappers around it (rendering the 3-pane workspace), so swapping
Streamlit for FastAPI+React later doesn't require rewriting the core.

## Setup

Requires Python 3.11+ (developed and tested on 3.14).

```bash
cd bir2307-app
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # then edit .env — see below
```

Edit `.env`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string. Defaults to a local SQLite file under `./data/`. |
| `APP_PASSWORD` | Shared password for the single-user MVP login gate. **Change from the default.** |
| `DATA_DIR` | Root folder for uploads and generated PDFs. |
| `LOG_DIR` | Folder for rotating structured loguru logs. |

The database and folders are created automatically on first run — no
migration step needed for the MVP.

## Run

```bash
streamlit run app/main.py
```

Open the URL Streamlit prints (default `http://localhost:8501`), sign in
with `APP_PASSWORD`, and use the left navigation panel: **Uploads** →
**Certificates** → **Search** → **Logs**. Selecting an item in the middle
list shows its details/PDF preview in the right-hand panel.

### Required first step: replace the placeholder payor record

Favor Church's own TIN and registered address are **not present anywhere**
in the source workbook, so the app seeds a payor row with an obvious
placeholder (`000-000-000-000`, "PLACEHOLDER TIN - REPLACE..."). Every
certificate will print this placeholder until you update it. Replace it
with a quick DB edit before generating any certificate you intend to
actually issue:

```bash
python -c "
from app.core.db import SessionLocal
from app.core.models import Payor
with SessionLocal() as s:
    p = s.query(Payor).first()
    p.tin = '000-000-000-000'          # real TIN
    p.registered_name = 'FAVOR CHURCH PH INC'
    p.address = 'real registered address'
    p.zip_code = '0000'
    s.commit()
"
```

## Tests

```bash
pytest              # all tests
black app tests     # formatting
ruff check app tests
```

59 tests cover EWT computation (against real, empirically-verified rates),
TIN validation, the duplicate-BILL-NO. collapse/merge logic, computation
mismatch flagging, certificate grouping/idempotency, status transitions,
event-log resolution, and certificate search.

## Database schema

SQLite via SQLAlchemy ORM (`app/core/models.py`) — swapping to Postgres
later is a `DATABASE_URL` change, not a rewrite.

- **payees** / **payors** — one row per payee TIN; exactly one payor row
  for this MVP (single withholding agent).
- **atc_codes** — ATC code, description, flat withholding rate. Seeded
  with the 8 codes actually found in Favor Church's real data (see
  "Assumptions" below) — add more rows here as new codes come up.
- **import_batches** — one row per Excel upload, with row/success/error
  counts.
- **transactions** — one row per imported spreadsheet line, FK'd to
  payee/payor/batch/ATC code, with both the uploaded and recomputed
  amounts plus the full original row (`raw_row_json`) for traceability.
- **certificates** — one per payee per calendar quarter, aggregating its
  linked transactions' totals; `status` enum
  (`draft`/`generated`/`forwarded`/`completed_signed`/`void`).
- **certificate_transactions** — join table (a certificate can bundle
  multiple transactions across ATC codes and BILL NO.s).
- **status_log** / **event_logs** — append-only. `status_log` records
  every certificate status change; `event_logs` records every
  import/validation/computation/PDF/status event, each with both a
  plain-language `message` and a developer-only `technical_detail`.
  Resolution (`resolved_by`/`resolved_at`/`resolution_note`) can only be
  set once per row — the Logs page can't edit or clear an existing
  resolution.

## Assumptions & known limitations

Noted here per the spec's request to record anything not explicitly
covered, or resolved differently than a first read might suggest:

- **ATC rates are a single flat rate per code**, not threshold-tiered
  (e.g. real BIR rates for some categories depend on the payee's annual
  gross income). The schema only stores one `default_rate` per code. The
  8 codes seeded (`WI100`/`WC100`, `WC120`, `WC158`, `WI160`/`WC160`,
  `WI050`, `WI051`) and their rates were verified two ways: cross-checked
  against the official BIR ATC schedule, *and* empirically recomputed from
  every historical row in the real sheet that used each code (near-100%
  consistent). If a rate is ever wrong for a specific transaction, the
  importer logs a `COMPUTATION_MISMATCH` warning rather than silently
  miscomputing — it still imports the row.
- **Certificate PDF is generated by overlaying data onto the real,
  official BIR Form 2307 (Jan 2018 ENCS)** —
  `app/assets/bir2307_official_template.pdf`, sourced from
  bir.gov.ph/bir-forms and never modified — rather than reconstructing the
  form's layout in code. Overlay coordinates were hand-measured off the
  template; they're tuned for the common case (a handful of ATC lines,
  reasonably short names/addresses) and may need adjusting for edge cases
  (a certificate with many more than ~12 ATC line items in one quarter, or
  unusually long payee/payor names).
- **Certificate "period" is the calendar quarter** containing each
  transaction's `Date Accomplished`, falling back to the transaction's
  import timestamp when that's blank — the confirmed column mapping has no
  separate "date paid" field to use instead. Most rows in the real sheet
  have `Date Accomplished` blank, so most certificates end up anchored to
  when they were imported rather than when the payment was actually made;
  revisit this if a cleaner payment-date field becomes available.
- **The importer targets a sheet named "BIR 2307" by name** inside the
  uploaded workbook (configurable in the Upload page), not just the first
  sheet — the real Favor Church export is a 16-sheet workbook (payroll,
  budget, donations, etc.) where that's one sheet among many.
- **Single shared-password login** (`APP_PASSWORD`), with a hardcoded
  `current_user` threaded through every status/log write from day one —
  structured so real per-user accounts (Preparer/Approver/Viewer) can
  replace `app/core/auth.py`'s `require_login()` later without touching
  call sites.
- Rows that are structurally not a transaction (the sheet's periodic
  "TOTAL AMOUNT" subtotal rows, trailing blank template rows) are silently
  skipped during import rather than logged as errors — anything missing
  both `BILL NO.` and `TIN NUMBER` can't be attributed to a payee. Rows
  that have identifying info but are missing something required (e.g. a
  handful of "Payroll" entries that got miscategorized into this sheet
  with no gross amount) are still logged as `ROW_VALIDATION` errors so
  they surface for someone to look at.

## Backups

This is financial record-keeping data. There's no automated backup in the
MVP — back up manually and regularly:

```bash
# Copy both, on whatever schedule fits (e.g. after every import/generation session):
cp data/bir2307.db /path/to/backup/location/
cp -r data/generated_pdfs /path/to/backup/location/
```

Keep backups off the machine running the app if possible. Never commit
`data/`, `.env`, or anything under `data/uploads/` — they contain real
TINs, names, and addresses (`.gitignore` already excludes them).
