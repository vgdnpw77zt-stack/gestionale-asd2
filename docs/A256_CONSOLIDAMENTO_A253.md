# BodyMind — A256: consolidamento sicuro dopo A253
Data: 2026-10-18. **Solo branch di lavoro; NON distribuire, NON unire automaticamente.**

## Base accertata
- Branch di partenza: `railway-top2-production`, commit `d9ad075cac84a375f8b4b6aa94d052d5b3274407`.
- In produzione, la versione A253 è stata caricata con reload Gunicorn HUP (nuovo worker PID 238), senza rieseguire `runtime_launcher.py`. La verifica visiva di Ricevute e Contabilità è stata confermata dall'amministratore.
- Controllo integrità A255: 151 pagamenti, 143 ricevute, 140 movimenti; DB consistente. Importi dell'ultimo audit: 6.020 € entrate effettive, 724,16 € uscite, 5.295,84 € saldo. Non sono valori da forzare se nuovi movimenti legittimi intervengono.
- Snapshot dei sorgenti e copia consistente SQLite: `/data/top2_app/bodymind-a253-rollback-20261018_163630` (percorso sul volume persistente, NON su GitHub).
- **La base GitHub non contiene l'intero `/data/top2_app/asd_app`. I 10 sorgenti A253 devono essere importati dopo verifica SHA, insieme al resto dell'applicazione. Questa cartella NON è ancora una release riproducibile.**

## Audit launcher / immagine, sola lettura
- 150 script `release_*.py` nel repository e 131 `runpy.run_path` diretti nel launcher (quest'ultimo numero include script non denominati `release_*.py`).
- 21 script `release_*.py` non richiamati *direttamente* dal launcher. Nessuno è ancora dichiarato eliminabile: occorre cercare dipendenze indirette, import dinamici, file usati dagli altri script, e migrazioni mai rese permanenti.
- `runtime_launcher.py` contiene una routine di retention che può eliminare vecchi backup e un meccanismo di ripristino automatico del database. Prima del prossimo riavvio/deploy confrontarne la copia effettiva nell'immagine e predisporre sostituzioni fail-closed, testate su clone.
- Da A254: Gunicorn in PID 1, worker PID 205 prima dell'attivazione; HTTP `/health` 200; circa 1,36 GiB liberi sul volume al momento della misura. Questi PID e capacità non sono valori stabili.

### I 21 candidati, NON autorizzati alla cancellazione
```
release_autopilot_r7.py
release_cloud_agent_diag_r45c.py
release_cloud_agent_smoke_r45.py
release_cloud_agent_smoke_r45b.py
release_desktop_save_verify_r106.py
release_document_association_repair_r144.py
release_document_consistency_probe_r136.py
release_document_deadlink_probe_r134.py
release_inbound_preview_r149.py
release_ios_123_key_r152.py
release_mu_canonical_convergence_r108.py
release_mu_nomatch_create_r117.py
release_operator_logic_qa_r34.py
release_operator_pending_reconcile_r55.py
release_operator_upload_truth_multidoc_r66.py
release_payment_history_probe_r128.py
release_presence_probe_r132.py
release_secretary_simplify_r123.py
release_ui_audit_r122.py
release_ui_target_audit_r123.py
release_upload_state_probe_r142.py
```
Alcuni di questi file contengono operazioni potenzialmente mutative: **non archiviarli o eliminarli solo perché assenti dalle chiamate dirette al launcher**.

## SHA-256 dei dieci file A253 live confermati da A255
| File in `/data/top2_app/asd_app/` | SHA-256 |
|---|---|
| bodymind_a237_finance_truth.py | `468947794166d48147745260cb18b7200407354ddce76c485b9ed9bb661fbfa1` |
| bodymind_a250_finance_view.py | `e549a01a8968b9bf057357100279cd617159110211bf67e78efd6aeb11d3bc7f` |
| bodymind_a253_manual.py | `a093105ad5320c038fe2856f3603ea9be303939101c1fd398dbe5a9d3d22ea01` |
| routes_a202_operational_integrity.py | `7945b1f79a7ef0c162119686882d7f700bf9815c829689047382707a369070a8` |
| routes_bodymind_final.py | `f6c115a5cdedf24f0b5476bb19997977d7a6d79658789b7983f8c44b31c14786` |
| routes_bodymind_fix29.py | `4b6ad983d5d23431d1bb941ce4547081c45040e152ccb7ba21887fecbf03e12a` |
| routes_contabilita.py | `fe5eef0e974c28710e00d90337b09e5270323b5d2f09ee41eb410842300f82a9` |
| routes_operator_bodymind.py | `96bbf726d4f5aeaa0d812512af2a6b4b1a0c8ad655ecc65ea369e6d09827db97` |
| routes_quote_incassi.py | `e8eb09c84d44238590e3542266f12239d43be092a39cf70e0e4858320475ee49` |
| routes_ricevute.py | `235150dd07c85bcf9356c066bdbf8632205e143a4b83f5c0e7af6d383f3b1c7c` |

## Chiusure obbligatorie prima di eliminare script o distribuire
1. Esportare una copia completa e consistente dell'applicazione reale sul volume; inventario file, SHA, riferimenti e import dinamici. Non esportare dati personali in un repository pubblico.
2. Portare il codice effettivo in un repository privato o in un archivio protetto, evitando dati e credenziali; preservare il punto di ripristino A253.
3. Eseguire l'intero launcher e l'app su una copia isolata, con volume e DB clonati (non avviare sul DB di produzione).
4. Classificare ogni vecchio script: dipendenza necessaria / migrazione incorporata / test diagnostico / inutilizzato dimostrato. Solo l'ultima categoria si può rimuovere.
5. Sostituire backup retention e database recovery automatici con procedure che non possano cancellare backup o sostituire il database attuale all'insaputa dell'amministratore; collaudare crash e rollback.
6. Testare route Flask attive, auth/CSRF, pagamenti e rettifiche, ricevute/PDF/progressivi, prima nota CRUD, esportazioni, Moduli Unici, certificati, firme e archivio documentale.
7. Confrontare inventari e hash dei documenti e conteggi record prima/dopo; verificare anche la ripartenza a freddo.
8. Rilascio solo dopo approvazione esplicita e con rollback dei soli sorgenti, senza restore automatico di database obsoleti.

**Nessuno script storico è stato cancellato in questa fase; nessuna modifica di runtime/produzione.**
