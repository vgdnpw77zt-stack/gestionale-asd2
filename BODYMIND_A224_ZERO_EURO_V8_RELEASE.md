# BodyMind A224 / V8 — quota 0 EUR e rettifiche (pre-rilascio)

**Stato:** implementato e testato su dati SQLite temporanei, **NON applicato in produzione**. Non fondere questa PR: startup Railway può ripristinare il codice vecchio.

La V7 impedisce l'inserimento di 0 EUR nel POST /pagamenti/registra-unico, benché la UI consenta min=0, e impone erroneamente l'iscrizione esatta di 50 EUR. La quota mensile non dovuta impedisce anche la correzione dell'eventuale movimento già registrato come incassato.

## Regole corrette
- Iscrizione ordinaria 50 EUR, ma 1 EUR o altra cifra positiva ammessa **solo con motivazione**; il salvataggio come pagamento POSITIVO indica incasso effettivo.
- Mensile ordinario 70 EUR; riduzioni positive motivate.
- **0 EUR non è un incasso**. Il POST salva una decisione motivata, senza creare movimenti pagati o ricevute da 0.
- Se l'utente corregge esplicitamente un incasso fittizio esistente, richiede ID preciso, annulla (non elimina) movimento e ricevuta originale, salva audit. Non interviene sugli altri movimenti.
- 2+ movimenti attivi per la stessa quota: la decisione 0 globale si blocca; serve riconciliazione effettiva.
- Una quota non dovuta può essere riaperta con motivo in un'unica transazione assieme all'incasso; se l'incasso fallisce, la decisione torna allo stato precedente.
- Esenzione iscrizione: nuova tabella decisioni con motivo, audit, etichetta UI "NON DOVUTA" e esclusione dai solleciti; l'eventuale futuro incasso la disattiva senza cancellare lo storico.
- I valori storici di Balbinetti (#53 iscrizione 1 EUR; #38 mensile ottobre 50 EUR contraddittorio a NON DOVUTO) **NON sono modificati automaticamente durante l'installazione**.
- Gaia/Fabiani/Annunziato/Frioli non sono riconciliate automaticamente.

## Sorgenti
- Baseline V7 core: 4d94c26c66c67edc713440464ec879df79c38684d29143cfed47f96bd8b40294
- Baseline V7 monthly helper: f554ceab9e160f7447e9bdd62c81c61ef0b4f8e13988813e9b11fcb43210b316
- Baseline V7 enrollment helper: 14c5b874b01b6d92a1181cb0164b2a2d1a56504bd43175a08ef04f85b671db9b
- Target V8 core: 4d1d01d6ebb2dae718c89d4bd9e02665c1769e0fb64b3be06403c170a203276d
- Target V8 enrollment helper: a00feafce61a1c43dcd9b35844fd928d4b11a4ad172d8498acf1879f7ed70518
- New bodymind_payment_zero_v8.py: 681fda9abe83756c3286e4bd7ab6785916f9ad6f7b8d7100b75013a90fc40710
- Installer bodymind_a224_quote_zero_correggibili_v8.py: 2fa9de4d3a2a7e3c2505abf884f2b0c663d4ba64e88e49fa50f11720e09cb03e; disponibile come allegato in questa chat, comprende 3 sorgenti compressi, backup e rollback.
- Test: scenario SQLite con #53 / #38 e duplicati #47/#48, rettifica a 0, riapertura 70, registrazione 1 motivata, gestione senza falsa ricevuta, truth/read-model, installer dry-run, apply simulato e rollback simulato, PASS. Il test 0 NON è stato eseguito sul database reale.

## Gate
1. Installer preflight controlla checksum V7, quick_check e foreign keys. In caso di errore si ferma.
2. Backup sorgenti + backup SQLite consistente prima della scrittura.
3. Cambia solo file Python sul volume, **non registra alcun incasso nel rilascio**.
4. Reload Gunicorn, health HTTP=200 e header X-BodyMind-Payment-Flow: 8, rollback del codice in caso di fallimento.
5. Dopo l'installazione è obbligatorio un test manuale mirato con conferma reale, verificando il movimento/receipt nel DB prima e dopo. Test reali non devono creare incassi fittizi.
6. No Railway redeploy finché il launcher non è verificato.
