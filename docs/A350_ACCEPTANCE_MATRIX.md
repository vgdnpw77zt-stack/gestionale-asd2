# BODYMIND A350 — Signature Experience
## Registro delle prove e matrice di accettazione (26 ottobre 2026)

**Stato ufficiale: A350 implementata in branch per un intervento circoscritto; validazione parziale; NON pubblicata.**  
Non qualificare questa PR come A350 COMPLETATA. Ogni verifica descritta qui distingue il codice della repo dal motore Flask/SQLite privato.

### Identificazione e immutabilita

- Repo GitHub: `vgdnpw77zt-stack/gestionale-asd2`.
- Branch base: `bodymind-a349-boutique-rebuild-20261026`; SHA controllato `0842271129fffe83392198afddebedacd34c2e90`.
- Branch di lavoro: `bodymind-a350-signature-experience-20261026`.
- Draft PR: https://github.com/vgdnpw77zt-stack/gestionale-asd2/pull/13 — target A349 (non `main`).
- Railway service: `bodymind-app` (`9dfa6991-ce53-4ad3-a118-dfd605c55548`).
- Deploy produzione letto: `b7021c1d-1a35-4069-a922-5e9bcb062265`, `SUCCESS`, 2026-10-26T03:00:42.822Z; sorgente **pinnata** a SHA A349.
- Volume esistente: `bodymind-data-d0BI` montato su `/data`, 5000 MB; non eseguita alcuna operazione di mutazione.
- La repo contiene 34 voci file/directory alla base A349; i 214 sorgenti privati reali e il database non sono parte del checkout.

### Matrice Area Famiglie <-> fonte autorevole

| Sezione | Componente di UI noto | Fonte di verita | Endpoint, autorizzazioni e comportamento effettivo | Risultato |
|---|---|---|---|---|
| Home | `.hero`, `.main .stats` | Tesserati, corso, quote e certificato nel Flask/SQLite live | Rotte Flask e corrispondenze reali **non disponibili** dal repository; impossibile verificare multi-atleta, alert e stati | NON VERIFICATO |
| Corsi e presenze | `#corsi`, card corso | Corsi, assegnazioni e presenze del gestionale | Nessun endpoint reale validato, possibile disallineamento atlete/corsi precedentemente segnalato | NON VERIFICATO |
| Pagamenti | `#pagamenti` | Pagamenti, quote mensili, ricevute SQLite; provider link solo se supportato | Nessuna mutazione eseguita; pagato/dovuto, link/receipt e autorizzazione non testati con sessione vera | NON VERIFICATO |
| Video e galleria | `#media`, `#familyMediaTrack`, video hero | Media app + contenuto pubblico pubblicato sul sito | A350 modifica solo linking delle foto: mapping esplicito dell'asset pubblico gara, altre immagini non associate. Riproduzione privata non validata | PASS sintetico / reale NON VERIFICATO |
| Documenti e certificati | `#documenti` | Archivio documentale, certificati, autorizzazioni e scadenze server-side | Upload, download, IDOR fra famiglie/minori e validita certificati non testati | NON VERIFICATO |
| Account | Sessione e selettore atleta originali | Sessione e legame nucleo familiare gestiti dal server | Il nuovo layer non li modifica; isolamento e CSRF non verificati | NON VERIFICATO |

**Principio di sicurezza:** l'interfaccia A350 non introduce API, ID atleta, importi, scadenze, ricevute, pagamenti simulati o storage parallelo. Non equivale ad audit delle API esistenti.

### Modifiche realmente implementate

1. `bootstrap/family_a350_verified_gallery.js`: sostituzione integrale dello script inline A341 che cercava parole nei titoli delle fotografie. Associazione consentita solo per `/static/media/bodymind-competition-double.webp` al reel gara ufficialmente definito nel sorgente `site/app.py` del branch `railway-site-v1`. Per le altre immagini: nessuna destinazione individuale presunta, azione globale verso la sezione `/#movimento` del sito ufficiale. Link esterni con `noopener noreferrer`, `no-referrer`; fallback immagine.
2. `bootstrap/family_a350_signature.css`: token e stili mirati per galleria scorrevole, accessibilita del focus, contrasto, touch/area sicura, fallback e reduced motion. Preserva A349 e non ristruttura template applicativi.
3. `bootstrap/clean_runtime_launcher.py`: verifica impronte Git blob degli asset, requisito di sorgente A349 verificata, copia di rollback in `/data/release_packages`, cambio atomico limitato a `asd_app/routes_bodymind_final.py`, analisi sintattica, validazione SQLite in sola lettura e verifica sorgente dopo la patch. Nessuna auto-migrazione, nessun restore automatico; rifiuta drift.
4. `Dockerfile`: due sole nuove righe COPY per asset A350, nessun cambio di entrypoint/runtime/dati.
5. `tests/test_a350_signature.py`: guard, impronte, sostituzione dello script, drift, test di installazione/ripristino file su volume sintetico.
6. `tests/browser_a350_signature.py`: Chromium sintetico ai sette breakpoint 320/375/390/430/768/1024/1440, mapping, assenza overflow, navigazione, ratio video e idempotenza JS.
7. `.github/workflows/a350-signature.yml`: test Python/JavaScript, Docker build, integrazione sintetica, screenshot senza dati reali.

### Checklist B0-B9 (PASS / FAIL / NON VERIFICATO)

| Check | Stato | Evidenza e limite |
|---|---|---|
| B0 — Ricognizione, versione e origine | PASS | SHA A349 + pin Railway + volume verificati via GitHub/Railway, nessun deploy A350 |
| B1 — Matrice completa degli endpoint server | NON VERIFICATO | Il Flask reale risiede esclusivamente sul volume e non e stato esaminato |
| B2 — Design system e uniformita completa | FAIL | Nuovo layer circoscritto presente; non testate tutte le schermate autentiche |
| B3 — Home, hero e video autenticati | NON VERIFICATO | Solo proof su shell sintetica e ratio video; nessun dato Home reale |
| B4 — Cinque destinazioni, safe area e accessibilita | NON VERIFICATO | Browser sintetico 7 viewport; controllo in account veri ancora richiesto |
| B5 — Corsi, orari, presenze e multi-atleta | NON VERIFICATO | Nessuna ispezione backend/autorizzazione; dati live non esaminati |
| B6 — Pagamenti, ricevute e link validi | NON VERIFICATO | Nessuna modifica contabile, nessun test autenticato di regole o salvataggi |
| B7 — Documenti, upload e certificati | NON VERIFICATO | Validita e privilegi minori non testati; nessun upload reale |
| B8 — Galleria, permessi e sicurezza | FAIL | Mappatura fotografica indovinata rimossa; mapping completo e audit IDOR/CSRF ancora mancanti |
| B9 — QA totale, produzione e rollback verificato | FAIL | QA + rollback solo sintetici; niente rilascio e nessun test prod A350 |

### Build, test e attestazioni

- GitHub Actions: `https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/workflows/a350-signature.yml`
- Workflow Clean Boot legacy: `https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/workflows/bodymind-cleanboot.yml`.
- **Nota di prova:** non sostituire i risultati CI con test di utenti reali. Ogni esito PASS e limitato al test eseguito.
- Test da completare: confronti autenticati tra due nuclei distinti, IDOR, CSRF, controllo stato quote/certificati/receipt, performance reali, iOS e dispositivi fisici, video reale, overlay tutte le sezioni, `/health` live post deploy, log e deploy ID A350.
- Una build Docker isolata non dimostra la sicurezza della migrazione sul volume reale: applicazione A350 da bloccare fino alla verifica degli hash di sorgente e backup live.

### Rollback del solo codice

Condizione di rilascio: sorgente A349 preflight PASS, backup A349 leggibile, nessuna modifica esterna al modulo UI.  
Una volta applicata, la procedura A350 prevederebbe `BODYMIND_A350_RECOVER_A349=1` per restore **esatto del solo file sorgente A349**, senza rollback dei database. Questo meccanismo e stato testato unicamente su volume sintetico. **Non e stato eseguito in produzione.**

### Blocchi P0 ancora presenti

- Accesso di lettura ai sorgenti runtime sul volume per identificazione endpoint/permessi.
- Dati sintetici nell'autenticazione reale o sandbox isolata equivalente per verificare due famiglie senza esporre i dati di altri nuclei.
- Audit funzionale e di sicurezza delle sezioni amministrative.
- Verifica iOS e mobile reale e interazione completa.
- Validazione di produzione e rollback end-to-end prima di qualunque indicazione A350 COMPLETATA.

**Nessuna operazione destructiva o variazione Railway richiesta da questo branch.**
