# BodyMind A263 — Origine degli incassi e menu essenziale (STAGING)

**Solo codice di prova. NON distribuito su Railway, NON usare il branch di staging come sorgente deploy.**

Obiettivo: su dashboard compatta A261 (senza downgrade), mostrare quanto proviene da iscrizioni, quote mensili, pagamenti di altra causale ed entrate manuali, con numero di incassi e tesserati distinti, matrice per canale di incasso e agevolazioni documentate (sorelle/fratelli, metà anno, metà mese, altre riduzioni). Tutte le cifre riconciliano con A237/A253 e non sommano mai le ricevute una seconda volta. Esclusi pagamenti annullati, non pagati e importi zero. Gli sconti sono indicatori documentali: una quota corrente non dimostra da sola il prezzo storico.

La voce Cuore operativo è nascosta dalla navigazione ordinaria e il quickdock mostra soltanto Dashboard e Automazioni. Le route tecniche, i log, gli stati delle pratiche concluse, i database e l'engine delle automazioni non vengono eliminati. I vecchi pannelli di dashboard sono accessibili dal pulsante «Mostra altri controlli». Non cambiamo tesserati o documenti.

## Sorgenti

- `source/bodymind_a262_income_origin.py`: analisi in sola lettura delle origini, matrice contabile e rendering responsive.
- `source/bodymind_a237_finance_truth.py`: riferimento A263 *di staging* per i test. Non installarlo autonomamente.
- `patch_income_a262.py`: patch a due file applicabile soltanto a un clone verificato A261/A253.
- `patch_navigation_a263.py`: modifica solo i link in `core.py` di un clone verificato.
- `tests/test_a263_finance.py`: fixture contabile sintetica con funzioni A253 mockate (o vere con `BODYMIND_A253_SOURCE`).
- `tests/test_finance_layout.py`: Playwright Chromium, 9 viewport, tabella espandibile.

## Collaudi isolati effettuati

- `python tests/test_a263_finance.py` **PASS**: 182 € entrate finte ripartite 75 iscrizioni, 95 mensili, 12 manuali; 5 € uscita e 177 € saldo; conto sconti mensili per *mese/persona* e tranche separate; pagamenti annullati/non pagati esclusi; controllo DB immutato; mismatch vietato.
- `python tests/test_finance_layout.py` **PASS**: 375/390/428/768/1024/1152/1366/1440/1920 px, zero overflow documento, tabella interna scorre solo su mobile.
- `python /mnt/data/a263_work/test_a263_extra.py` **PASS sul clone locale**: categorie esplicite, sconti "nessuno" esclusi, navigazione ridotta, patch idempotente e sintassi Python valida.

Questi sono test **con dati fittizi**, non analisi in tempo reale dei numeri veri o test end-to-end autenticati su Railway.

## Passi necessari prima di pubblicare

1. Staging privato completo (app, template, CSS, assets, copia anonima o protetta del DB), verifica schema reale delle quote e note.
2. Snapshot backup verificato di DB + media e integrità file, nessuna cancellazione automatica.
3. Verifica sessione amministratore, dashboard con e senza sconti, export, modifiche/annullamenti, certificati, documenti, familiari e UI 12-13 pollici/iPhone.
4. Commit applicativo riproducibile, revisione, verifica senza differenze nelle pagine tesserati, conferma esplicita prima del deploy.

Il percorso `/cuore-operativo` può rimanere raggiungibile mediante URL diretto per audit e vecchi collegamenti: **non elimina registrazioni e non asserisce di eliminarle**. Tutti i dati storici dell'ASD rimangono necessari alla contabilità e tracciabilità.
