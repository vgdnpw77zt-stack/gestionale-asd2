## Current status — v4, 2026-10-15

Production runtime logs show monthly validation rejected an empty reason. The
v3 redirect appended a second question mark, losing form context and hiding the
validation message. HTTP 200 after reloading was not evidence of a successful
payment edit. V4 is prepared, not yet installed or verified online.

V4 returns an explicit HTTP 422 form with escaped original submitted values,
CSRF token, payment ID and actionable reason. No notes in query strings or
cookies. Existing monthly correction form labels the reason clearly and requires
it in the browser. Accounting logic remains v3: atomic cancellation/replacement
with a new receipt, preserving historical numbers and originals.

Verified against actual v3 core SHA256
`ac6d7bf745a95141220e468d1b83a32c226811492100c332ff20a3a1ac5b18a5`.
11 isolated tests cover missing reason, retained inputs, resubmission, resulting
receipt PDF amount, permissions, CSRF, concurrency and transactional rollback.
The external archive and restoration evidence below remain historical; do not
restore that DB over payments recorded later. Installer backs up current core
and helper; reload health failure restores code only. Direct SSH from this
assistant is unavailable; operator installation is required.

---
Historical release notes follow; statements are scoped to each earlier release.

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


## Version 2 — agreed monthly amount, 2026-10-15

Version 1 was applied to the persistent code and reloaded in Gunicorn on
2026-10-14. A real full monthly payment and its new progressive receipt were
confirmed by read-only production query; cancelled history was preserved.
The Railway image/startup pipeline remains unchanged.

The user clarified that an entered amount is the total agreed monthly fee,
not an instalment. Version 2 removes equality with the default price and
requires a reason in the existing notes field when the amount changes.
Positive amounts with at most two decimal places are accepted without any
percentage rule. Zero/waived amounts do not generate receipts through this flow.
The same SQLite transaction records old/new due and reason, keeps the base fee,
updates the agreed due and discount, and creates the actual receipt. A failed
save rolls back the fee change too. Issued payments/receipts remain protected.

The installer upgrades the exact installed v1 core hash
`dec06c52dfbe9a9e3159a6dd9cb36bb94db34901b6890459f333b306810c28ab`.
It backs up both core and the old helper. Optional `--apply --reload` identifies
one Gunicorn master, reloads it, and verifies HTTP 200 with the v2 response
header. If health verification fails, it restores both code files and reloads
the previous version; no database rollback is performed. A failure to confirm
rollback health is reported explicitly.

11 tests pass against reconstructed exact v1 source and an isolated DB copy,
including arbitrary amounts, increases, reductions, missing reasons, failed
save rollback, protected receipts, simultaneous saves, real Flask writer and
full core/session/CSRF checks with outbound connections disabled.
V2 production installation and verification are still pending.


## Version 3 — correct an issued monthly payment and its receipt atomically

An explicit edit of a settled monthly payment now automatically cancels the
old movement and old receipt and inserts a replacement payment and receipt.
Original amounts, receipt numbers and PDF files are preserved; the replacement
gets the next progressive. Both versions are linked in payment notes. No manual
second receipt operation is required. New registration still cannot overwrite
an issued movement accidentally. Ambiguous, mismatched or already cancelled
selections are rejected. The supplied note records the correction reason.

The old cancellation, new agreed fee, replacement payment, receipt and links
are one BEGIN IMMEDIATE transaction. A receipt-insertion failure rolls back
all changes. A repeated correction of the old ID cannot create another receipt.

11 expanded tests pass against the exact deployed v2 source, including a real
HTTP edit of a settled payment, opening the corrected PDF and extracting its
new amount, fault injection during receipt creation, rollback preservation,
double submission and unchanged historical amounts/numbers. Installer upgrade
and backup of both old code files were tested in an isolated directory.
Input core SHA256:
`3b4602e39779c2906295b9183d70c2a6f7c41e354d110161e5d01d174da22b89`.
The response version header is now 3. V3 production application remains pending.
