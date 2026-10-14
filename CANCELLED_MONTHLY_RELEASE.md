# Monthly cancellation repair — 2026-10-14

Prepared against the running core snapshot SHA256
`469e397ac43e44b0d17ad8ddc75b39c5274d64cf84db953997129eae23fae898`.
Railway still reports deployment `b6b78a15-3ea2-49f7-9765-5aae8a429c3c`,
commit `64c9a2163313f5b82f9c3f27b4476133a90409db`, SUCCESS.
This repair has NOT been installed or verified in production.

## Scope

The canonical writer inserts `mensile` even when a cancelled historical row
occupies its UNIQUE key. The startup deduplicator deletes repeated keys:
dropping the index or allowing duplicate keys would endanger history.
Preserve the index and all old rows; use `mensile_reincasso_N` for a new,
distinct full payment after cancellation. Existing monthly readers recognize
this monthly prefix. No database migration or import-time writes.

Serialize selection and insertion with BEGIN IMMEDIATE. Block additional
requests once an active movement exists. Never overwrite issued receipts or
reactivate cancelled rows. An explicit pending movement can be completed only
when period/member match and no receipt or settlement evidence exists.

This is deliberately limited to the exact positive full monthly fee already
configured in quote_mensili. Partial payments, administrative amount changes,
ambiguous records and non-due fees return a review message. Annual registration
is unchanged. This is not a complete accounting redesign or the full PR #4.

## Evidence

User downloaded complete archive (about 2677 MiB) and confirmed SHA256:
`bf48ad2c4efa0f7d6ceea3db6ec15f74d341e4af11d5ab8ea3adcd8e50b98248`.
Isolated extraction checked 1558 file hashes. Explicit SQLite API backup was
copied separately and passed integrity_check and foreign_key_check.
Snapshot: 44 members, 127 payments, 119 receipts, 162 document records,
88 monthly fees. No production test payments created.

All 177 supplied Python source files match the restored manifest hashes.
Eight targeted tests pass, including simultaneous requests, protected receipts,
explicit pending selection, Flask POST of the extracted real writer against a
private cloned database, and full core import with actual session/CSRF guards.
In the isolated clone, two new payments produce exactly two new receipts with
the next global progressives; every old payment and receipt remains unchanged.
Outbound network is disabled in full-core tests. License and setup wizard are
test fixtures; no production authentication or license controls are changed.
23 existing accounting/archive tests also pass.
Installer dry-run, application on temporary code, and hash-mismatch refusal pass.

## Deployment / rollback

The module's CLI defaults to CHECK ONLY. It requires the expected core hash.
`--apply` backs up core.py alongside the application, installs the helper and
atomically replaces core.py. It does not modify SQLite or restart processes.
Do not merge the divergent repair PR to deliver this hotfix.

Before application, inspect the current source hash and the exact app server
process. After application, reload only the verified app server and inspect
startup/HTTP logs. Do not run the full release/migration launcher for this
code-only hotfix. Verify online without synthetic accounting entries.

Rollback: restore core.py from the recorded code backup, reload the same app
server and verify health. Keep all newer database rows and receipts. Do not
restore the old database: new monthly causes remain readable by old code.
The helper can remain unused after code rollback. A future full deployment
must deliberately integrate the patch; this installer alone does not change
the Docker image/startup pipeline.

## Still open

No online verification yet; no responsive screenshots or receipt-PDF end-to-end
test. The complete restored media tree is held by the user/on-server, not in
the local HTTP fixture. Document audit finds two historical zero-byte PDFs and
unresolved references in other document tables; these are preserved, not fixed.
The broader backup UI, alert and document interventions remain open.
