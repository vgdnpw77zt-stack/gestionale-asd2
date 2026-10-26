# BODYMIND A350 — matrice reale e release gate (26 ottobre 2026)

**Stato: A350 implementazione parziale in branch, validazione reale del sorgente e test sintetici superati; NON MERGED, NON PUBBLICATA.**

## Versioni
- Repo: `vgdnpw77zt-stack/gestionale-asd2`.
- PR draft: https://github.com/vgdnpw77zt-stack/gestionale-asd2/pull/13
- Base A349 immutabile: `0842271129fffe83392198afddebedacd34c2e90`.
- Il service Railway `bodymind-app` risulta collegato ancora alla base A349, deploy `b7021c1d-1a35-4069-a922-5e9bcb062265` SUCCESS.
- Volume vero preservato: `bodymind-data-d0BI` a `/data`; nessun riavvio o deploy A350 eseguito.

## Evidenze su codice e ambiente LIVE
1. **A350 SSH read-only:** https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/runs/40372055352 — fonte applicativa 214 file, manifest A349 valido, SQLite integrity preflight PASS, 4 rotte area familiare individuate. Questo controllo opera nell'app Railway vera, ma senza leggere record personali.
2. **Backend contract read-only:** https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/runs/40373216916 — tre handler reali individuati: `bodymind_portal`, `bodymind_upload`, `bodymind_doc`; campi medici, quote, tesserati, presenze e `documenti.visibile` confermati. Nel sorgente A349 mancava il controllo esplicito `visibile` sul download diretto. Il template mostrava un successo upload tramite query string, e Home richiamava inizializzazione schema quote. Quest'ultimo comportamento non è stato modificato senza prova di regressione.
3. **Trasformazione A350 completa in memoria:** https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/runs/40374692327 — codice originale A349 hash `12391e9f3fdc3dd92f91325c26f7e695cab28cbc771a721165708c2dfc4c9021` trasformato con gli asset A350 e compilato senza scritture. Codice candidato prodotto `8bbb503c24242e88aa97bc1eb973f92e69aa395df27c00d38f6809c9435532d1`.
4. **Funzione download A350, due famiglie sintetiche:** https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/runs/40374884396 — PASS con SQLite solo in memoria: download proprio visibile, cross-family negato, nascosto e NULL negati, token inesistente e documento mancante negati. File temporanei sintetici soltanto sotto `/tmp` nel test, rimossi automaticamente. Non è prova di autenticazione live reale.
5. **Upload su handler reale, dati sintetici e filesystem temporaneo:** https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/runs/40375229182 — PASS con tesserato fittizio, salvataggio e registrazione documentale solo su SQLite in memoria e /tmp; token estraneo rifiutato. Non comprova CSRF né upload su una sessione reale.
6. **QA isolata:** https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/workflows/a350-signature.yml — 29 unit test (inclusa nuova guardia), Chromium sintetico su 320/375/390/430/768/1024/1440, Dockerfile build e asset SHA. Citare soltanto run SUCCESS sul commit finale.

## Matrice integrazione Area Famiglie ↔ gestionale

| Interfaccia | Autorità | Evidenza verificata | Resta |
|---|---|---|---|
| Home | `tesserati`, assegnazione corsi, quote, certificato | Handler Flask live e campi SQLite individuati | Dati e UX di account autenticati, pagato/scaduto su record sintetici integrati |
| Corsi e presenze | `corsi`, `presenze`, `bodymind_rapid_roster` | Schema presente sul database live | Join, roster e orari verificati con famiglie autorizzate |
| Pagamenti | `quote_mensili`, `pagamenti`, `ricevute` | Tabelle presenti; UI non introduce movimenti | Quotazioni contabili e ricevute riconciliate; accesso diretto autorizzato; checkout reale |
| Video/galleria | Media esistenti da A349, sito ufficiale | Rimosso mapping per parole del titolo; solo asset/reel con associazione esplicita; demo mobile testata | Foto live e CTA effettive, riproduzione iPhone reale |
| Documenti | `documenti`, `tesserati.online_token`, filesystem autorizzato | Handler reale A350 corretto in memoria, 2 famiglie sintetiche isolate | Handler upload sintetico testato; mancano CSRF, tipi file, conferma e sessione reale |
| Certificato | `tesserati.certificato_scadenza` + verifiche segreteria | Colonna confermata | Scadenze, validazione upload/documenti/flag con casi autorizzati |
| Account | associazione nucleo / athlete token lato server | lookup token nell'handler reale | Multi-figlio, sessione, autorizzazioni di nucleo con due account autenticati |

## B0-B9

| Check | Stato | Motivazione |
|---|---|---|
| B0 base/commit produzione | PASS | A349 reale, SHA e volumi letti e bloccati |
| B1 endpoint reali | PASS PARZIALE | Tre handler e schema reali esaminati; non tutte le API e permessi |
| B2 design system totale | NON VERIFICATO | Stili A350 circoscritti; non audit visivo di tutte le pagine autenticate |
| B3 Home/video reale | NON VERIFICATO | Test sintetici e source dry-run, non browser login autentico |
| B4 nav/accessibilità | PASS SINTETICO | 7 viewport Chromium, focus; manca device iOS reale |
| B5 corsi/presenze | NON VERIFICATO | Tesserato-corso e roster reali non confrontati |
| B6 pagamenti/ricevute | NON VERIFICATO | Senza riconciliazione e permessi end-to-end |
| B7 documenti/certificati | PASS PARZIALE | Due famiglie sintetiche: IDOR/download nascosti; upload e certificato non verificati |
| B8 galleria e sicurezza | PASS PARZIALE | Link immagine esplicito e origini; non tutte le foto mappate |
| B9 release/rollback | NON VERIFICATO | Rollback solo sintetico; no deployment A350, no smoke postdeploy |

## Blocchi release P0
- Handler upload già testato su due token sintetici in SQLite solo in memoria; restano prove CSRF globale, controllo dei tipi/dimensioni file, feedback e upload autenticato end-to-end.
- Validare corrispondenza pagamenti/ricevute/quote e certificati rispetto al backend con almeno due nuclei distinti, senza dati reali nei log.
- Verificare completo frontend autenticato sulle dimensioni richieste e iOS; video senza blur e controlli funzionanti.
- Solo in seguito valutare merge e deploy con source lock, backup codice, rollback testato, check `/health` e smoke post-deploy.

**NON fare deploy automatico solo perché unit test/SSH in memoria risultano verdi. Non toccare o salvare copie di database reali nei CI.**
