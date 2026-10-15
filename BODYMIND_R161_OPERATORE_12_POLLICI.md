# BodyMind R161 — Operatore, schermata 12 pollici (15 ottobre 2026)

**Sorgente runtime verificato:** `/data/top2_app/asd_app/routes_operator_bodymind.py`, SHA256 `22bc3be5d70ea7b8a507df70c145e60768b16484636416894d66ce1370450ecd`. Allegato `bodymind_operatore_sorgente.py` ricevuto dall'amministratore e analizzato.

**Difetto visibile:** su Firefox desktop 12 pollici il compositore si trasforma in una barra troppo alta, con input nativo `Seleziona file` esposto; pulsanti allegato/testo/microfono/invio non allineati; welcome fuori proporzione.

**Intervento pronto, ma NON ancora online:** script `bodymind_fix_operatore_12_pollici.py` fornito come allegato nella chat, patch R161 limitata a CSS del modulo operator, breakpoint desktop >800px; forzatura `#bmoAttachPicker{display:none!important}` anche su desktop; contenitore flex verticale con scorrimento messaggi separato; compositore grid a quattro elementi; nessun cambio endpoint, JS della chat, file upload, API, database, documenti, ricevute.

**Gate sicurezza**: SHA256 rigido dell'intero file; confronto degli anchor reali, compile del Python modificato, backup sul volume e replace atomico; HUP Gunicorn e test HTTP 200 /login, rollback se health fallisce. Test preview Chromium locale su 1024×768, 1152×720, 1280×800, 1366×768, 1440×900 e 1920×1080; stress con CSS confliggente iniettato: input file invisibile, messaggi separati dal composer, composer 62px alto e shell 80px, quattro controlli allineati, textarea editabile. Anteprima sintetica non autenticata.

**Non installare tramite merge/redeploy**: launcher di Railway muta il volume all'avvio. Eseguire soltanto dopo approvazione esplicita dell'amministratore e verificare in Firefox autenticato. PR #6 rimane bozza; nessuna produzione modificata durante questa preparazione.
