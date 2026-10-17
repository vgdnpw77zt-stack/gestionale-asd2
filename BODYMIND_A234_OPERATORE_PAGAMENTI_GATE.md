# BodyMind A234 — Operatore Modulo Unico e annullamenti Quote & Incassi

**Stato al 17 ottobre 2026: IMPLEMENTATO E TESTATO IN ISOLAMENTO, NON PUBBLICATO ONLINE.**

## Martina Labbia
Diagnosi A233 del database reale: documento `inbound_documents.id=214` denominato `Iscrizione Labbia .pdf`, tipo `modulo_unico_tesseramento`, confidence semantica 0.88, stato `needs_manual_match`, senza tesserato collegato. Due job di upload terminati `completed`, entrambi con `mode=identity_review` e `confidence_sotto_90`; nessuna proposta di creazione. L'account è admin e non è un errore di permessi. Il codice operatore richiede addirittura `sem_conf>=0.95` per entrare nel ramo di nuova tesserata, e usa la stessa confidence generica di classificazione documentale come gate identità.

**A234:** mostra nella pagina Operatore una lista di Moduli Unici non associati e per ciascuno la route admin `/operatore-bodymind/verifica-identita/<id>`. L'amministratore confronta con il PDF i valori identificativi già estratti, conferma nome/cognome/codice fiscale, supera la verifica R65 `enrollment_identity_ready(...require_valid_cf=True)`, verifica l'assenza di duplicati prima e dopo il backup, preserva PDF originale e usa `create_athlete_from_analysis` R65. Riconduce l'inbound all'anagrafica; prova la produzione del Modulo Unico nel dossier e comunica onestamente se la produzione resta da verificare. Non muta il confidence 0.88 originario. **Non abbassa globalmente la soglia di auto-creazione.** Nessuna persona creata dall'installazione.

## Quote & Incassi
La route legacy `POST /pagamenti/elimina` annullava pagamento+ricevuta senza motivazione e senza rettificare una eventuale riga `movimenti` generata automaticamente. A234 reindirizza ogni comando legacy alla nuova conferma admin `/pagamenti/annulla-movimento/<id>`: ID univoco, motivazione obbligatoria e conferma non-rimborso. La transazione annulla lo stato del solo pagamento, la sua ricevuta, storna i `movimenti` **auto_generati** (senza cancellarli), corregge l'eventuale `quote_mensili.stato=pagato` diventato orfano, e salva audit. Blocca ricevute attive multiple e movimenti manuali/di tipo inatteso. In Quote & Incassi mostra per default solo movimenti incassati attivi, con link *Annulla registrazione #ID* e storico non attivo collassato.

## Garanzie e limiti
- Baseline codice CORE: A229 `bd578b2fc1ef6d729b63f76ca810bc95d094c1e395bd84504f1ffe77c8ae7377`.
- SHA target CORE A234: `e0256b6edfd63ae40dcd5b65c62dc0e616d77e4f551e1854d9a361cd12cc78c8`.
- Nuovo modulo `bodymind_a234_operator_ledger.py` SHA256 `4eeaefa5e3ce32d32c833002e8082f6e85bff636fac1b075c8ad423aef6c63b4`.
- Installatore `bodymind_a234_fix_operatore_annulla_movimenti.py` SHA256 `53cfd119709fdeeca561ee8ea03127363eb786f861b5476ff6d95e0dc5809f9c`.
- `X-BodyMind-Operator-Ledger: A234` in risposta HTTP, mentre `flow=9` e `synergy=A229` devono restare.
- Test SQLite: 14 asserzioni di annullamento incluse idempotenza, isolamento ID, ricevute, cassa, duplicati e rollback; test identità, core AST, installatore dry-run, apply, idempotenza, rollback e version mismatch: PASS.
- Non è stato eseguito QA online autenticato. L'utente deve applicare il singolo installatore via SSH; MAI redeploy Railway per propagare codice, startup può sovrascrivere codice volume.
- Ricevute annullate rimangono nello storico contabile/protetto; l'interfaccia normale mostra solo documenti validi.
- A231 KPI e A232 rettifiche competenza iscrizioni sono interventi separati e non vengono applicati automaticamente da A234.
