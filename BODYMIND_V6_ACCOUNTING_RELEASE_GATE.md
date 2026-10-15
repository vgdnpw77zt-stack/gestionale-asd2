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
