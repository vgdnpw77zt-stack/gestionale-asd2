# A293 — Surgical quota corrections (release requirement)

The user needs authorized fine-grained changes to each athlete's sports fees, including interplay with payments and receipts. **Never rewrite issued receipts or original settled payments.**

## Admin UI
- Under `Pagamenti > Rettifiche quote`, select athlete + fee type (enrollment/monthly) + season/month/year and show the exact existing obligation, historical payments, receipts and payment links.
- Preview before submit: original amount, updated amount, reason, amount already received, amount outstanding, resulting delta, open SumUp links, and required follow-up adjustments.
- Require explicit confirmation, free-text reason, role check, CSRF and optimistic version check.
- For *unpaid and unlinked* quotas, apply a single transaction updating only the exact obligation row, and append immutable audit metadata (operator, timestamp, previous/new, source, tenant, period). Do not use name matching; only verified IDs.
- On partial/full payments or issued receipts, use a **separate linked adjustment workflow**: credit/debit document, refund or supplemental payment as appropriate, preserving original payment and receipt IDs, ledger history and tax numbering. Never synthesize a successful payment or retro-edit already issued PDFs.
- Do not alter SumUp payment links of fixed amount: revoke/disable old links and require a newly verified amount-specific link after the correction; any pending checkout requires reconciliation before modifying dues.
- Sync the same canonical due calculation across dashboard, athlete profile, family portal, reminders and online checkout offer. Avoid double charge or stale link.
- Preview/test in a cloned SQLite DB; preserve A292 receipt-hidden records, document archive, and tenant boundaries.

## Delivered pure policy
`fixes/a293/due_correction_policy.py` rejects unsafe changes and identifies the need for a separate accounting adjustment. `tests/test_a293_due_correction_policy.py` checks paid receipts, partial payments, conflicting versions, pending links, authorization and amount precision.

**Not installed**: actual Flask admin page, atomic DB transaction, reconciliation and fiscal adjustment flow still require live runtime code and tests. This policy must never be treated as completed feature or deployed blindly.
