# BODYMIND A222 — Operatore desktop 12 pollici

**Stato:** patch CSS preparata, compilata e collaudata in Chromium su HTML estratto dal sorgente reale, **non installata online**.

**Origine verificata:** file allegato `/data/top2_app/asd_app/routes_operator_bodymind.py`, SHA256 `22bc3be5d70ea7b8a507df70c145e60768b16484636416894d66ce1370450ecd`.

**Problema:** sul desktop con sidebar il vecchio CSS `BODYMIND_R52_CHAT_NATIVE_UI` forza `.bmo{position:fixed;width:100vw}`, che può superare lo spazio disponibile dentro il gestionale. Il composer eredita varie regole desktop/mobile ed è troppo grande, con possibili sovrapposizioni e file input visibile.

**Soluzione:** solo nuovo CSS finale `BODYMIND_A222_COMPACT_DESKTOP_OPERATOR_FIX`, limitato ai viewport 801–1650px. La chat diventa relativa e a larghezza 100% del contenitore, messaggi scorrevoli, composer nella flow layout alto ~60px, textarea min 200px, attach/mic/send in colonne dedicate e file picker visivamente nascosto. Nessun cambiamento ai widget vocali, API, JavaScript, file upload, database o codici R156 iOS.

**Preflight/script:** `bodymind_fix_operatore_12_pollici.py` è allegato alla chat corrente, controlla SHA256 originale e idempotenza, compila il sorgente risultante, salva backup sotto `/data/top2_app/bodymind-a222-operator-rollback-*`, scrive atomicamente, HUP Gunicorn, verifica HTTP /login, tenta rollback su errore. Non eseguire su sorgente diverso.

**QA offline:** parse CSS senza errori, Python compilabile; Chromium con HTML estratto dal file runtime e sidebar simulata, viewport 1024×768, 1152×720, 1280×800, 1366×768, 1440×900, 1600×900: file picker invisibile, 3 pulsanti dentro composer, barra sotto messaggi, no root overflow, input >= 200px. Mobile <=800 e desktop >=1651 non modificati.

**Limitazione:** simulazione locale; prima di considerarlo risolto occorre installare sul runtime ed esaminare screenshot della vera pagina autenticata. La correzione sul volume non sopravvive necessariamente al prossimo redeploy Railway, startup command ancora da auditare.

PR volutamente DRAFT, non unire né ridistribuire automaticamente.
