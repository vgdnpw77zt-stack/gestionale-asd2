# BodyMind A220 responsive fix — 15 ottobre 2026 (candidate)

La precedente patch A189 V2 aveva due limiti documentati nell'interfaccia reale:

1. Regole centrate su `.a189-page`, mentre nei log della sessione utente del 15/10 compare ripetutamente `/comunicazioni-automatiche`, il cui HTML è `.a34-page`.
2. Health check cercava il marker V2 nella pagina `/login`. È un indicatore di caricamento della regola globale, non una prova che la pagina autenticata sia stata corretta. Se il marker non era iniettato, il programma ripristinava il vecchio file.

**Nuovo installer V3**: `bodymind_12_fix_v3_sicuro.py` fornito in chat; intervento circoscritto al codice runtime `routes_a189_coherent_ops_repair.py` su volume, CSS mirato a `.a189-page`, `.a34-page`, `.a168-page`, `.a148-page`. Preflight verifica SHA dei due possibili sorgenti (originale `00d401ae...`, V2 `e74c0447...`), presenza dell'iniettore A189 sul vero HTML prima della scrittura e backup/rollback. Qualsiasi situazione inattesa blocca l'intervento.

**Verifiche locali eseguite**: sorgenti BASE e V2 compilano con patch V3; test Chromium con markup e classi derivati dal runtime a 390, 768, 1024, 1152, 1280, 1366, 1440, 1920 px senza overflow orizzontale nel test. Test non corrispondente alla pagina autenticata con dati reali.

**Non distribuire né unire questa PR** finché non vengono verificati in produzione: esito dell'installer, marker effettivamente servito, pagina aperta e screenshot da browser 12 pollici. Database, backup documentali, pagamenti e ricevute esclusi dall'intervento.

Il launcher Railway (`python /opt/bodymind-migration/migration_upload.py`) rimane invariato; non avviare redeploy generico.