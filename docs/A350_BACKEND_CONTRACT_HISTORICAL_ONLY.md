# A350 — Ispezione compatibilità storica del motore Famiglie (NON live)

**Tipo di evidenza: sorgenti precedenti, NON produzione.** Questo documento deriva dalla lettura in sola lettura dell'archivio `BODYMIND_A317_CORRETTO_CON_VERIFICA_PREDEPLOY_NON_INSTALLARE.zip` del 22 ottobre 2026, sotto `SORGENTI_CANDIDATI_COMPLETI/asd_app/routes_bodymind_final.py`. L'archivio reca esplicitamente la dicitura NON INSTALLARE. **Non è stato pubblicato, applicato o copiato sul runtime corrente.**

La configurazione Railway produzione verificata il 26 ottobre 2026 punta invece a A349 `0842271129fffe83392198afddebedacd34c2e90`, il cui sorgente Flask risiede sul volume persistente e NON nel checkout A350. Le rotte qui sotto sono quindi **candidati storici**, non endpoint live confermati.

## Endpoint e flussi osservati in A317

| Operazione | Implementazione storica | Dati / permessi da verificare nell'effettiva A349 |
|---|---|---|
| Area Famiglie | `GET /area-famiglie`, `POST /area-famiglie` | PIN/identità nucleo, limiti tentativi, sessione |
| Scheda atleta | `app_tesserato` -> `bodymind_portal(token)` | `tesserati.online_token`, isolamento tra tesserati e famiglie |
| Presenze | query `presenze` filtrata su `tesserato_id` | join corsi, corso reale, stati e permessi |
| Quote | `monthly_status(conn, tid, mm, yy)` | confronto col ledger amministrativo, nessuna inizializzazione schema su GET |
| Ricevute | `receipts_operational`, `family_visible_receipts` | esportazione autorizzata, annullate/nascoste, URL diretti |
| Documenti | `GET /app-tesserato/<token>/documento/<int:doc_id>` | proprietà del tesserato, `visibile`, documenti comuni, path traversal |
| Upload | `POST /app-tesserato/<token>/upload-onboarding` | CSRF, file type/size, successo DB+FS atomico, aggiornamento stato certificato |
| Video e galleria | `_family_media_items(config)`, `familyMediaTrack` | media effettivi, poster, origini, mappatura outbound |
| Settings media | `/impostazioni/area-famiglie/media` e `admin_required` | verifica configurazione live e preview con dati sintetici |
| Manifest PWA | `/app-tesserato/<token>/manifest.json` | accessi, caching, service worker, sessione scaduta |

## Tre blocchi tecnici ad alta priorità da verificare sulla vera A349

1. **GET non deve modificare lo schema**. La versione A317 chiamava `ensure_quote_schema(conn)` dentro il rendering della Home. Verificare che nella versione reale A349 nessun GET esegua DDL o mutazioni, anche in caso di database storico.
2. **Caricamento certificato e conferma**. In A317 l'upload eseguiva inserimenti su `documenti` e `inbound_documents`, mentre il badge medico usava `tesserati.certificato_scadenza`. Serve verificare come l'A349 sincronizzi ora la validazione riconosciuta dalla segreteria: un semplice upload non deve far risultare valida automaticamente una certificazione ancora da controllare.
3. **Conferma di successo non falsificabile da query string**. Il template storico visualizzava il messaggio `Documento caricato` in base a `request.args.get('upload') == 'ok'`. Verificare in A349 che tale messaggio derivi dalla conferma server e da uno stato di richiesta, non dal solo parametro modificabile.

Questi sono **rischi di regressione storica da verificare**, non vulnerabilità accertate della versione A349.

## Requisiti di rilascio

- Acquisire versione sorgenti live solo con procedura autorizzata e senza pubblicare dati personali o materiale sul repository pubblico.
- Confrontare hash del file `routes_bodymind_final.py` e manifest sorgenti prima di ogni patch. Se differisce: STOP.
- Eseguire test a due nuclei sintetici con permessi, certificati, ricevute, presenze, segreteria, IDOR/CSRF e nessuna mutazione impropria.
- Verificare `/health` e app autenticata **dopo** il nuovo deploy, non confondere A349 con A350.
- Restare in **draft/non pubblicata** finché questi punti restano NON VERIFICATI.

Nessun dato di tesserati, PDF, token, database o file personali è incluso in questo documento.
