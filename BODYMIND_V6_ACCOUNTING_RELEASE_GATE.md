# BodyMind V6 — Rettifiche iscrizioni/mensili e ID pagamento esatto

**Stato**: preparato e testato localmente, **NON installato in produzione**. La release è consegnata come `bodymind_pagamenti_v6_iscrizioni_mensili_tutte.py` nella conversazione. Questa PR contiene il registro dell'intervento; non va unita per distribuire il codice.

## Problemi dal runtime verificato

- `core.py` V4 SHA256 `cfbdcd0f9df68aef1f2ab21cb65ddb3d0ff4b197997bfcb7c83674de686ebd9a`; V5 canonica SHA256 `219fd6153fc1fca719c549dcb9a57ee9efcd333e415708c4971c149d6b837cd5`.
- Link `Apri pagamento` può precompilare il movimento aggregato errato in assenza di validazione tipo, anno e mese.
- Rettifica iscrizione V4/V5 muta il pagamento e la ricevuta già emessa: serve storicizzazione, non aggiornamento silenzioso.
- Gruppi con più movimenti attivi dello stesso tipo/periodo non devono essere annullati automaticamente senza riconciliazione.
- Le iscrizioni annuali devono rispettare la stagione luglio–giugno, evitando il conflitto fra due stagioni adiacenti che condividono l'anno civile.

## Release generata

- Installer V6 SHA256 `da202e661661345fe7eafea09bc134c52f74314b121e776773acc391676791bd`.
- Core post-install previsto SHA256 `fd49c8bcc26732bf1c971cbad3d4cb5c996a92849f950169dba22796ee5bb02c`.
- Helper annuale `bodymind_enrollment_guard_v6.py` SHA256 `a87a21de737e69ea73db74b3d03276fa029069186aca00b549d8dcec37b9ebb3`.
- V5 helper mensile invariato SHA256 `93083ee1efa738ab5d2fe4a42f067d9b8a49a1c6a51c1a674be10504645bdd0c`.
- Installatore idempotente con preflight hash V4/V5; CHECK ONLY default: inventario dei possibili doppi incassi, focus su Balbinetti e Gaia Abbatini; --apply --reload crea backup SQLite consistente e snapshot sorgenti, HUP Gunicorn, salute HTTP e rollback del codice su errore. **Nessuna rettifica di dati durante installazione**.
- V6 non comprende riconciliazione automatica dei doppioni: serve ispezione ricevute e movimenti reali per ogni gruppo.

## QA eseguita offline

- 11 test annuali (rettifica, idempotenza, anno/stagione, blocco doppi, ricevute).
- 11 test mensili V5 precedenti, ancora superati.
- 1 test errore 303 sulla stessa pagina con input conservato.
- 7 test del writer Flask estratto dal core su SQLite temporaneo (nuovo incasso, rettifica iscrizione, doppio invio, mensile 70, rettifica 50, ricevute, ID incrociati).
- 2 test separati di dry-run installer con input V4 e V5 (senza scrittura).
- Sintassi Python preflight superata.

## Gate di produzione

1. Diagnostica readonly sul vero /data/tenants/default/asd.db per Balbinetti e tutti i gruppi duplicati.
2. Nessun inserimento/annullamento di test sul database reale senza verifica esplicita di una quota e della ricevuta.
3. Nessun redeploy Railway: startup `python /opt/bodymind-migration/migration_upload.py` potrebbe sostituire file sul volume; verificare prima il launcher.
4. Visualizzare la registrazione e il nuovo link nel browser autenticato.


## Aggiornamento V6.1 — controllo dopo i log di produzione

L'installer V6 originario conteneva ancora, nel ramo dei campi iniziali non validi, il redirect `302 /pagamenti?errore=dati_non_validi`. Railway ha registrato esplicitamente questo errore il 15 ottobre, 18:38 ora italiana. **Preferire esclusivamente il nuovo allegato `bodymind_pagamenti_v6_1_iscrizioni_mensili_tutte.py`** (SHA256 `b9ae8bf2ec5825bef4daa9fc72c2b842a6ad99eef505a62c1778294e82e95cdf`, core post-install `b85e28c3f47d1eb83cf6ad3583e195758a6126f8cab916dc90e8ceafd9a616dc`) che riutilizza `payment_form_error` per validazioni fallite e mantiene input/motivazione nella sessione anziché mostrare il vecchio errore generico.

Rieseguiti 11 test iscrizioni, 11 test mensili, 7 test writer SQLite, 2 dry-run installer su baseline V4/V5, test form error e integrità SHA: superati. Nessun test applica scritture al database di produzione. La PR resta in bozza e *non include* l'installatore eseguibile: per pubblicarlo in modo persistente è necessario integrare anche il percorso di startup Railway, previa verifica del launcher. **Non effettuare redeploy automatico.**


## Caso riproducibile: Ludovica Annunziato (ID 13), ottobre 2026

Diagnosticato a runtime con output V6.1:
- mensile pagamento `#35`, importo `50.00`, `stato=paid_manual`, `online_status=paid_manual`
- mensile pagamento `#36`, importo `45.00`, `stato=paid_manual`, `online_status=paid_manual`
- in `bodymind_one_step_monthlies.py` V5, usato anche da V6.1, `prepare_monthly` seleziona tutti i pagamenti mensili attivi per tesserata/mese/anno, poi `if len(active)>1: raise PaymentReviewRequired('Esistono più pagamenti attivi per questo mese: verifica necessaria per evitare duplicati.')`.

**Effetto deterministico:** V6.1 impedisce qualsiasi modifica del mensile ottobre 2026 per questa tesserata finché non viene riconciliato il doppio movimento; questo è un blocco contabile intenzionale, non prova di un errore JavaScript. Il blocco non dovrebbe essere rimosso senza un flusso di revisione esplicito che preservi ricevute e audit. Determinare con la segreteria se #35 e #36 rappresentino due incassi reali o se il secondo sia una rettifica/doppione. Gli HTTP POST 303 rilevati non riportano il tesserato_id e non sono attribuibili con certezza.

**Nessuna scrittura/modifica contabile effettuata qui.**
