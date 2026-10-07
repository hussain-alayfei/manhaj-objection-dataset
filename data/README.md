# Private data workspace

Source files and JSON/JSONL/SQLite datasets are excluded from Git (`.gitignore`) and from
Vercel uploads (`.vercelignore`). The private delivery contains the user-supplied source,
unapproved seed candidates, and a local review database. They are not licensed under the
repository's MIT code license. Only this README, `benchmark/README.md` and `.gitkeep` files
are tracked.

- manhaj.db: local SQLite review database (the default `DATABASE_URL`). Production uses Supabase
  PostgreSQL; a copy of this file is the safe place to test writes.
- source/<id>/: original PDF (`original.pdf`), page-level raw/logical extraction (`pages.json`), and
  `pages/0001.webp ...`, the rendered pages for the in-site book viewer (`scripts/render_source_pages.py`).
- raw/: temporary uploads during local ingest.
- processed/: coverage inventories and extraction diagnostics.
- pending_review/: candidate record snapshots.
- approved/: only approved snapshots; authority remains the database.
- reviewed/: latest human-reviewed records, including rejected ones; not a training pool.
- rejected/: rejected snapshots.
- benchmark/: manual review shortlist until experts approve and freeze gold labels.
- exports/: approved-only exports with database manifests and hashes.

Run `python -m src.cli snapshots` to refresh materialized JSON snapshots after reviews.
Do not force-add these private paths to any Git repository, and never copy book text into tests.
