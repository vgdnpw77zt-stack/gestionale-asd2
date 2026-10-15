# BodyMind Cuore operativo — correzione 12" basata sul runtime reale (15/10/2026)

Questa nota sostituisce **il vecchio CSS generico nella PR #6**, che è insufficiente e **non deve essere distribuito**. Il nuovo intervento è circoscritto al modulo effettivo `/data/top2_app/asd_app/routes_a189_coherent_ops_repair.py`, acquisito dallo ZIP dell'istanza attiva (SHA256 `00d401ae08ebb614e078933dfed64e5d8bcb92bddbd857dc9be9e4f58ec3e799`).

**Difetto dimostrato nel sorgente:** `.a189-grid` riserva 360 px alla sidebar fino a viewport 1100 px; `.a189-practice` mantiene una quarta colonna `auto` per i pulsanti; la combinazione comprime il testo sui viewport intermedi. I filtri `Tutti / Pagamenti / Documenti / Da verificare / Invii` sono pulsanti privi di click handler.

**Correzione preparata e testata localmente:** media query per impilare la sidebar sotto i 1500px; righe pratica a tre colonne con pulsanti sotto il testo; layout mobile a una colonna; filtri accessibili con stato `aria-pressed` e selezione client-side, senza alterare i record. Installer Python con confronto SHA256, backup del solo sorgente e rollback automatico sul fallimento del controllo HTTP dopo reload Gunicorn. Nessuna scrittura DB né launcher/migrazione.

**Test browser sintetico su HTML/classi del runtime:** viewport 390×844, 768×1024, 1024×768, 1152×720, 1280×800, 1366×768, 1440×900, 1920×1080: assente overflow orizzontale nello scenario; interazione filtri 1/3 e Tutti 3/3; sintassi Python valida. A 1152px la colonna di testo della pratica nel test passa da 370px a 938px.

**Non ancora verificato:** installazione sul volume e rendering della pagina autenticata reale. Non effettuare merge/redeploy e non considerare la PR #6 precedente un fix pronto.

Lo script applicativo è consegnato come allegato al dialogo; eseguire soltanto previa autorizzazione, da terminale utente con SSH funzionante.