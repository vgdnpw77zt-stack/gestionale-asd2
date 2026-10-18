# A258 — prima riduzione reale sul BRANCH ISOLATO (non produzione)

Data 2026-10-18. Baseline: archivio live A256 (344 sorgenti SHA validi) e A253 attiva.

## Cosa cambia qui
- 11 script `release_*.py` non chiamati direttamente dal launcher, né menzionati in alcuno dei 343 sorgenti Python A256, sono rimossi **solo da questo branch**.
- Il `COPY` del Dockerfile di questo branch non li installa più.
- Tutti i 131 target diretti `runpy.run_path` verificati nella copia live restano presenti. Test AST sui 343 file: senza errori.
- Il launcher storico e la configurazione di deploy reale non sono stati cambiati. **Non fare merge o deploy di questo branch.**
- I vecchi script restano recuperabili tramite Git History; alcuni erano migrazioni potenzialmente mutative.

## 11 script rimossi dal branch
- `release_document_consistency_probe_r136.py`
- `release_document_deadlink_probe_r134.py`
- `release_ios_123_key_r152.py`
- `release_mu_nomatch_create_r117.py`
- `release_operator_logic_qa_r34.py`
- `release_operator_pending_reconcile_r55.py`
- `release_payment_history_probe_r128.py`
- `release_presence_probe_r132.py`
- `release_ui_audit_r122.py`
- `release_ui_target_audit_r123.py`
- `release_upload_state_probe_r142.py`

## Bootstrap pulito (pacchetto A258)
Creato e testato localmente un bootstrap alternativo con controlli SQLite in sola lettura e SHA dei dieci sorgenti A253, senza migrazioni, restore o rimozione backup. È distribuito nel pacchetto isolato A258, ma **non** è ancora collegato al Dockerfile produttivo: non abbiamo assets/statici/media e copia isolata del DB reale per la prova di avvio autenticato.

## Blocchi prima di qualsiasi rilascio
1. Allestire clone PRIVATO dei sorgenti più risorse statiche, media e copia SQLite coerente, senza credenziali live.
2. Testare avvio Gunicorn isolato, auth, CSRF, route, CRUD, PDF, documenti, ricevute, backup, import/export.
3. Separare migrazioni dallo startup e consolidare comportamenti legacy nel codice verificato.
4. Preparare manifest rollback e passaggio protetto, senza Railway restart e senza cancellare backup di produzione.

**A253 ONLINE INVARIATA — niente deploy, database intatto.**
