# A260 — Dashboard semplice di segreteria (STAGING, non pubblicata)

Proposta chirurgica di UI, senza alcuna rimozione delle funzioni già operative.

## Cosa contiene
- Nuova pagina **/segreteria/oggi**: 3 KPI («Da fare», «In scadenza», «Tutto in regola»), due liste sintetiche con link reali alla scheda, accesso rapido a incasso contanti, documenti e automazioni.
- Riutilizza `get_dashboard_metrics` e `_active_tesserati_rows` già presenti in `core.py`; niente motore parallelo, niente tabelle nuove.
- «Tutto in regola» = tesserati attivi non coinvolti in avvisi del periodo: non equivale a validazione medico-documentale.
- Colori sobri e coerenti, rossi solo per criticità effettive; contrasto e messaggi brevi.
- Routing admin-only. GET di sola presentazione; nessun invio WhatsApp o modifica quote.

## Test statici/sintetici completati
- Rendering HTML e CSS Chromium con larghezze 390, 768, 1152, 1440: nessuno scroll orizzontale.
- Classificazione 1 alert critical, 1 warning, 1 tesserato active senza avvisi; inactive escluso.
- URL esterne rifiutate, contenuto HTML non attendibile correttamente escapato.
- Nessun database di produzione utilizzato.

## Stato e limiti
- Il modulo è parcheggiato in `staging/A260` e **non è importato dall'app in esecuzione**; /segreteria/oggi quindi non esiste ancora online.
- Prima dell'attivazione: QA Flask sulla app clonata, autentificazione/admin, coerenza con le reali route sovrascritte, originali UI 390/768/1024/1152/1366/1440, test ricevute e saldo A253.
- Dashboard e layout tesserati esistenti NON sono sostituiti. Serve una decisione di navigazione post-QA.
- Automazioni programmabili WhatsApp/SumUp: lavoro separato, non attivato e non verificato, nel rispetto di policy/template/consenso e riconciliazione pagamenti.
