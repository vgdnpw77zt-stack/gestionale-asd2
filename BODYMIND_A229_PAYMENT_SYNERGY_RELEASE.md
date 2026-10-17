# BODYMIND A229 — Sinergia contabile Home e Atlete (17/10/2026)

**Stato:** implementato e testato localmente, NON installato online. Script allegato nella chat: `bodymind_a229_sinergia_home_atlete_contabilita.py`, SHA256 `9fbe3c152e4a9367205df44436440f437df7e8a725c86c8dfda160a9c76ffd3f`.

## Difetto isolato nel sorgente V8

`_r141_truth` in `core.py` aggrega lo stato mensile in un booleano: `not mensile_ok` finisce nel pannello "Mensile da verificare" della Home mobile. Le schede atleta R143/R145 leggono un'altra funzione documentale, il modulo pagamenti una terza proiezione e Quote & Incassi controlla ancora altri stati, inclusa una logica che può interpretare stringhe come "unpaid" in modo errato. Il numero "6" non equivale pertanto necessariamente a sei veri insoluti.

## Correzione preparata

L'A229 introduce il modulo di **sola lettura** `bodymind_payment_synergy_v9.py` e aggiorna `core.py` senza scrivere al DB. Classifica ogni quota in PAGATO, NON DOVUTO, DA PAGARE, DA VERIFICARE, DA RICONCILIARE, DA DEFINIRE. Riconcilia coerentemente Home mobile, Atlete, dettagli atleta R143/R145, Pagamenti, Quote & Incassi, KPI dashboard e task. Una quota non dovuta non genera solleciti; una quota non dovuta con incasso ancora attivo viene evidenziata come CONTRADDIZIONE da riconciliare e non come debito; l'iscrizione motivata da 1 EUR non diventa automaticamente un debito di 50 EUR. Zero SQL writes.

## Checksum del codice

- Baseline V8 core `4d1d01d6ebb2dae718c89d4bd9e02665c1769e0fb64b3be06403c170a203276d`
- Target A229 core `bd578b2fc1ef6d729b63f76ca810bc95d094c1e395bd84504f1ffe77c8ae7377`
- Nuovo helper `70ba93abd976438096307193c0f3bd05590567d07eed3cee910120242c038f10`
- Header post-apply `X-BodyMind-Payment-Flow: 9` e `X-BodyMind-Payment-Synergy: A229`

## QA isolato

14 assert classificazione, integrazione con le due funzioni originali del core V8 e il pannello R141, compile Python, prova installatore con CHECK, APPLY, idempotenza, rollback provocato e DB SQLite invariato. Installer effettua stampa degli stati reali del mese in **sola lettura** prima del rilascio, poi snapshot SQLite integro, backup sorgenti, atomic replace, reload HUP, health headers e rollback se serve.

**Non usare il merge della PR per distribuire**: l'installer non è nella branch di produzione e la versione del volume può essere sovrascritta dal launcher Railway. Nessun redeploy senza audit. Nessuna ricevuta o movimento reale è stato corretto o eliminato dall'A229. QA finale autenticata e riconciliazione contabile separata restano necessari.
