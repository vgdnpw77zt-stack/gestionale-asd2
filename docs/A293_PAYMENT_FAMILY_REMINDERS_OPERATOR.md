# BODYMIND A293 — payment configuration, family checkout, reminders, operator UI

## Runtime baseline
A292 lives on Railway persistent volume at /data/top2_app/asd_app and must not be overwritten by a GitHub redeploy. Branch A293 is **staging only**. No live deployment, payment activation or outbound reminder is authorized by this PR.

## Payments — actual implementation requirements
1. Add an admin-only **Impostazioni > Pagamenti online** screen (desktop/mobile): SumUp, Stripe, PayPal individually configurable, with disabled/enabled states and a clear test/production indicator. Protect all mutations with real Flask authentication, administrator role and CSRF.
2. SumUp links will be provided later. A generic SumUp link can be saved as a configuration reference but **must not** be offered as a verified athlete-specific checkout unless athlete, month/season and exact amount are guaranteed to match. Prefer provider-created per-obligation checkout sessions or a preconfigured link scoped and audited to that obligation.
3. Family UI: offer **Paga ora** only for verified positive unpaid obligations, never for zero, waived, paid, canceled, duplicated, technical correction or mismatched debt. Display provider, amount, payment subject, period, state, and allow return from checkout.
4. Opening the link or redirecting back is NOT proof of payment. Persist a pending attempt and wait for verified provider webhook/API reconciliation; idempotently record a canonical payment only after confirmation, preventing double charging and duplicate receipts. Audit provider transaction IDs and actor/source without exposing secrets.
5. Settings must store secrets encrypted with existing vault machinery or Railway secret variables; never in client HTML, git, logs, unencrypted DB or public URLs. Test webhooks signatures and event replay.
6. Preserve A292 receipt visibility and accounting history. No historical row deletion.

## Individual family access in reminders
1. Resolve the **existing** personal family token/access code and the currently verified recipient for each athlete. Do not generate arbitrary codes or reuse another athlete's link.
2. Include a distinct personal App Famiglie URL and appropriate access instructions in each reminder template. Treat tokens as credentials: don't log or display them in bulk preview; use authenticated delivery, explicit recipient match and opt-in/lawful-basis verification.
3. Every reminder is idempotent and audit logged, with previews and an authorized, explicit send. **Never turn on automatic SMS/WhatsApp/email broadcasts by merely deploying A293.**
4. A guardian with multiple associated athletes must see the correct athlete-specific dues and credentials, without cross-tenant or cross-family leakage.

## Operator message composer — identified existing code
- Live target: `/data/top2_app/asd_app/routes_operator_bodymind.py`
- Prior launcher migrations: `release_operator_mobile_composer_r154.py` and `release_operator_mobile_composer_r155.py`. R154 notes its CSS might be inserted in the wrong style block; R155 attempts to anchor it to `BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL` and has many `!important` overrides.
- Before patching: fetch live source SHA and inspect actual CSS/HTML boundaries, viewport JS handlers and computed browser layout at 390px, 768px, 1024px, 1280px and full desktop. Test onscreen keyboard on iOS and on Mac; composer must never obscure send/attach/mic or conversation history.
- Patch the actual authoritative style once, scoped to the operator page, avoiding another global override. Verify no regression in secretary/dashboard/family views.

## Release gates
- A292 baseline SHA and backup are verified before any file replacement.
- SQLite copied and dry-run tested, count and document inventory before/after.
- Real auth and CSRF; provider signature tests; no fake paid states; no duplicate receipt.
- Browser-based visual mobile and desktop checks; rollback verified; deliberate activation only after confirmed configuration.

## Code delivered in this PR
`fixes/a293/family_payment_policy.py` contains **isolated fail-closed policy primitives**, and `tests/test_a293_family_payment_policy.py` exercises their safety invariants. Neither file is registered in Flask production, and these files alone are NOT a finished payment system.
