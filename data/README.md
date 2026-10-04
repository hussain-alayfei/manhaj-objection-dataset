# Private data workspace

Source files and JSON/JSONL/SQLite datasets are excluded from Git. The private delivery
contains the user-supplied source, unapproved seed candidates, and a local review database.
They are not licensed under the repository's MIT code license.

- source/: original PDF and page-level raw/logical extraction.
- processed/: coverage inventories and extraction diagnostics.
- pending_review/: candidate record snapshots.
- approved/: only approved snapshots; authority remains the database.
- reviewed/: latest human-reviewed records, including rejected ones; not a training pool.
- rejected/: rejected snapshots.
- benchmark/: manual review shortlist until experts approve and freeze gold labels.
- exports/: approved-only exports with database manifests and hashes.

Run `python -m src.cli snapshots` to refresh materialized JSON snapshots after reviews.
Do not force-add these private paths to a public Git repository.
