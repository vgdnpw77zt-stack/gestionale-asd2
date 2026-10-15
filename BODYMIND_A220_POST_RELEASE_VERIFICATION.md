# A220 V3 — verifica post installazione (15 ottobre 2026)

## Evidenze runtime

Output SSH fornito dall'amministratore:

```
RUNTIME SOURCE SHA256: e74c04475ba9913a09f0563fcc81712ef9f2594ebd3b598a9695bc45fc2c8fef
V3 PRESENT IN SOURCE: False
BEFORE: HTTP=200 A189_LOADED=True V3_VISIBLE=False
PREPARED CSS+JS; new source SHA256: d5a0c283c863a53d15d200aeb0b59cf76ff730b5e7ffa0e7fb9ffdbed019318e
AFTER: HTTP=200 A189_LOADED=True V3_VISIBLE=True
SUCCESS: V3 CSS served in HTML; backup: /data/top2_app/bodymind-a220-rollback-l7hp5u4a/routes_a189_coherent_ops_repair.py
```

Questo conferma il caricamento del CSS globale dal modulo A189. Non conferma da solo il comportamento geometrico dell'interfaccia autenticata.

## Check Railway (15 ottobre 2026)

- Ambiente production: servizio bodymind-app ONLINE, 1 replica running, 0 crash, 0 warning e 0 issue
- Deployment Railway immutato: b6b78a15-3ea2-49f7-9765-5aae8a429c3c del 13 ottobre
- GET /comunicazioni-automatiche?mese=10&anno=2026 alle 15:07:06 UTC (17:07 italiane), HTTP 200, body 951672 byte
- GET della stessa pagina alle 13:45 UTC, HTTP 200, body 943046 byte
- Delta HTML 8626 byte, compatibile con il CSS iniettato; da NON interpretare come misura esatta del solo CSS, perché i contenuti della pagina possono cambiare

## Sorgenti valutati

Archive `bodymind_cuore_sorgenti.zip` acquisito dal runtime e verificato. `routes_a189_coherent_ops_repair.py` gestisce l'iniezione globale via @app.after_request; markup effettivo A189 `.a189-page .a189-grid` e A34 `.a34-page .a16-form-grid` presente in `routes_auto_comunicazioni.py`.

## Limiti e criteri di accettazione

- Verificare uno screenshot autentico dell'utente a viewport effettivo 1024×768, 1152×720 e/o 1280×800, non soltanto la dimensione fisica del dispositivo
- Controllare grid delle pratiche, timeline, bottoni, filtri, tabelle e assenza di overflow orizzontale
- Verificare che i filtri aggiornino davvero le righe e non nascondano pratiche erroneamente
- Non avviare redeploy Railway: launcher attualmente `python /opt/bodymind-migration/migration_upload.py`, non verificato per conservare questa patch sul volume
- Non eseguire ulteriori patch alla cieca; preservare lo snapshot/backup e il database

**Stato: V3 installata e servita; verifica visiva autenticata IN ATTESA. PR #6 resta draft/non mergeabile per release automatico.**
