# A271 — Pagamento SumUp in area Famiglie, solo quando verificato

**Ambiente: STAGING. Nessun deployment in produzione.**

## Intervento
`staging/A271/A271_family_sumup_staging.py` applica una piccola modifica alla route **già esistente** `app-tesserato/<token>` e al suo template. Nessuna nuova route, token, forma di pagamento, ricevuta o modifica di dati.

Il pulsante «Paga online con SumUp» compare nella pagina di pagamenti personali solo quando:
1. Il mese corrente è configurato e il motore quote segnala **residuo positivo e stato dovuto**.
2. Il read-model A269 controlla, con **SQLite query_only**, versamenti reali, ricevute, riduzioni/esenzioni e crediti precedenti. Lo stato deve risultare riconciliato `da_pagare` oppure `parziale`, con residuo positivo e crediti verificati.
3. L'amministrazione ha inserito un link SumUp HTTPS valido nelle impostazioni A270.

In caso di dato ambiguo, link assente o schema incompatibile, il pulsante NON compare. **Il click non registra un pagamento**: serve conferma del provider o riconciliazione amministrativa.

Rimangono invariati token delle famiglie, download PDF, documenti, upload, certificati, presenze e navigazione corrente.

## QA locale
- **45 test locali superati** nell'insieme A270/A271 (41 A270 + 4 A271).
- HTML del vero template Famiglie analizzato con Jinja2: link condizionale, attributi HTML escapati, link esterno con `noopener noreferrer nofollow`, pulsanti PDF/upload preservati.
- Playwright Chromium 375/390/428/768/1024/1152/1366 px, nessun overflow orizzontale; pulsante min. 44 px.
- Patch idempotente; Python parse; check A267B `routes_contabilita.py` e `bodymind_a265_cashbook.py` **identici byte per byte** ai sorgenti della release online già installata.
- Nessuna scrittura su DB o invio di messaggi; fixture con atleta fittizia, senza dati personali.
- **Non eseguiti** test autenticati end-to-end contro database e media di produzione.

## Gate del rilascio unico
Le patch A259–A271 sono ancora in un clone che richiede allestimento privato completo (static/media/DB) e confronto con i sorgenti A267B effettivi nel volume live. I link SumUp reali e l'API WhatsApp non sono configurati. Gli invii resteranno disattivati finché provider, consenso e template non saranno collaudati.

Nessun merge/redeploy del branch pubblico, launcher legacy da disinnescare in ambiente isolato prima di ogni restart della produzione. **Un solo futuro rilascio, con backup, rollback e autorizzazione.**
