# BodyMind A257 — Analisi dell'archivio A256 (SOLO LETTURA)
Data: 18 ottobre 2026 · **Non pubblicare questo branch.** Non contiene nuove patch operative.

## Verifica dell'archivio acquisito
- `BodyMind_A256_Sorgenti_Live_20261018_194447.tar.gz`: 344 file del manifest; **344/344 SHA-256 e dimensioni verificati**.
- SHA-256 archivio: `976717100582d090a9c63e5ddb6bbc47803476b776e4bd39e30ba603a8d081ac`.
- 343 sorgenti Python superano il parsing AST; nessun errore di sintassi; alcuni warning non bloccanti sulle sequenze escape.
- Non include DB, media, documenti, ricevute o credenziali ambiente.
- I 10 file A253 live hanno tutti gli SHA-256 attesi registrati nell'attivazione A255. **Non alterare questa baseline.**

## Script realmente presenti nell'immagine attiva
- `/opt/bodymind`: **140** script `release_*.py` (GitHub ne elenca 150, differenza da rispettare).
- `runtime_launcher.py`: **131** riferimenti diretti `runpy.run_path`, tutti risolti nell'immagine acquisita.
- **11** script `release_*.py` nell'immagine **non sono richiamati direttamente** e non sono citati testualmente negli altri 342 sorgenti Python:
```
release_document_consistency_probe_r136.py
release_document_deadlink_probe_r134.py
release_ios_123_key_r152.py
release_mu_nomatch_create_r117.py
release_operator_logic_qa_r34.py
release_operator_pending_reconcile_r55.py
release_payment_history_probe_r128.py
release_presence_probe_r132.py
release_ui_audit_r122.py
release_ui_target_audit_r123.py
release_upload_state_probe_r142.py
```
Tutti e 11 sono esplicitamente citati nel `COPY` del Dockerfile GitHub. Una rimozione richiede adeguare **anche** il Dockerfile; controllare task esterni prima di considerarli inutili.

### Prova statica su clone isolato
Copia fisica dei sorgenti container; rimossi gli 11 candidati **solo dalla copia**:
- Script `release_*.py` rimasti: 129.
- Tutti i 131 riferimenti diretti del launcher ancora risolti.
- 343 file Python originali: parsing AST superato.
**Non è stato eseguito il boot Flask, un build Docker o un test E2E**. Non è autorizzata cancellazione su produzione.

## Rischi bloccanti rilevati nel launcher
1. `cleanup_trigger = 1536 MiB` e rimozione automatica di backup in `/data/release_backups`: A254 riportava 1,36 GiB liberi. Un cold start può quindi attivare la retention distruttiva.
2. Recovery DB automatico: in presenza di errori d'integrità può sostituire il database attuale con backup vecchi. Deve essere fail-closed, con scelta umana di restore.
3. Numerose migrazioni storiche al boot; in particolare `release_operator_review_actions_r156.py` contiene correzioni su tabella ricevute e patch PDF condizionale a `routes_ricevute.py`. Il marcatore PDF è già presente in A253, ma non costituisce una garanzia generale che il boot sia privo di effetti.
4. GitHub non contiene la totalità dell'app su `/data/top2_app`; non esiste ancora un'immagine autonoma e riproducibile della baseline A253. Il repository è pubblico: non caricare sorgenti live senza revisione e collocazione privata.

## Chiusura richiesta
1. Inventariare dipendenze e scritture di tutti i file di avvio.
2. Portare i sorgenti effettivi in repository **privato** o archivio protetto senza dati/credenziali.
3. Consolidare migrazioni una tantum con registro versioni, disabilitare retention distruttiva e ripristini DB automatici all'avvio.
4. Provare cold start su clone con copie di DB/media isolati, HTTP autenticato, CRUD/riconciliazione pagamenti, ricevute PDF, esportazioni, documenti e integrità.
5. Solo dopo test + autorizzazione: togliere codice inutilizzato e correggere Dockerfile/launcher. Rollback del codice; mai restore involontario di vecchi DB.

**Nessuna modifica a produzione né cancellazione.**
