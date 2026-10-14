# Backup safety checkpoint — 2026-10-14

Status: corrected and tested offline; NOT deployed or integrated into the web UI.

The archive guard now preserves the historical directories, PDF directory and
top-level files previously omitted. It records excluded backup/cache directories
and SQLite sidecar suffixes. It retains literal `..` inside filenames; traversal
components are rejected instead of renaming user documents. Production `/data/`
document references can be checked against an offline volume without basename
guessing or changing database records.

The active snapshot still comes exclusively from `tenants/default/asd.db` using
SQLite's backup API. Historical `database/asd.db` and root `asd.db` files are
preserved separately under the archive's data namespace, never substituted for
the active snapshot. A WAL-mode regression test verifies committed rows survive.

Verification now rejects unsupported restoration namespaces, duplicate manifest
entries, conflicting active-database destinations and noncanonical paths before
creating a restore directory. A symlinked restore target is rejected.

Validation: `python -m unittest discover -s tests -p test_bodymind_archive_guard.py -v`
passed all 8 tests using synthetic SQLite and files. No live database was opened.

Release remains blocked: obtain an independently verified, consistent snapshot
of the live volume and reconcile the historical references documented in the
private audit. The existing web backup endpoint is unchanged and must not be
treated as repaired. Railway CLI installation was attempted but its official
binary download timed out through the environment's proxy. The available Railway
connector does not expose filesystem execution. Do not merge the draft PR, alter
the production branch, change the startup command, or deploy to work around this.

Next step: establish authorized CLI/SSH access to the specified BodyMind service,
run the guard without importing the application or its startup migrations, export
outside the live volume, compare source inventory and test a separate recovery.
An explicit user approval is still required for any production release or restore.
