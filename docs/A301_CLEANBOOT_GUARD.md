# BodyMind A301 clean boot — STAGING ONLY

- A301 live code contains 209 Python sources under /data/top2_app; all 208 are fingerprinted by an immutable SHA256 of their path+SHA inventory.
- This image includes NO legacy release scripts and never calls the old runtime_launcher.py or runpy. All prior migrations/patch replays and automatic DB restores/backup deletion are eliminated from the new image.
- The startup check reads SQLite strictly in mode=ro, checks integrity+FK and table counts; it modifies **nothing**. Tampered/modified code blocks startup.
- Dockerfile preserves Railway's historic custom startCommand path by COPYING the **new clean launcher** to that path; this is not the old script.
- **Do not change production branch or trigger Railway redeploy until a full isolated cold boot on copied real DB is complete**; 3 local tests and offline source lock preflight are not sufficient to claim full boot with real data.
- Preserve the full A301 user-held Mac backup, SHA256 d71ce2ac752965696ad6fc054bb605eafa994eb10c74aa3759f225a3dfe55fa8.
- No personal data, DB, medical files, originals, or proprietary app sources have been uploaded here.
- bodymind-site is separate and must not be affected.

## A302 (candidate only)
An additional private payment-note presentation module and an update to core.py now make existing `pagamenti.note_pagamento`, `quote_mensili.note`, and quota-decision audit reasons visible on the Pagamenti page, preserving original provenance without fabricating lost notes from HTTP logs. Source inventory lock updated to 209 files. Deploy only after authenticated QA of the A302 hotloaded runtime and a cold-boot clone; no private application source is on GitHub.
