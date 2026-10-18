# A263 — BodyMind «Segreteria oggi», niente Cuore Operativo nel menu

**Stato: STAGING / NON PUBBLICATO.** Basato su A253 live + patch A259 (incassi e operatore), A260 (grafica) e A261 **corretta** (compatibilità con il titolo condizionale di A260).

## Intervento realizzato e testato

Il sorgente `staging_patches/A263_simplifica_segreteria.py` è una patch per i sorgenti privati A256/A259 già clonati: modifica quattro file di interfaccia e NON deve essere eseguito direttamente su Railway.

- Dashboard: superficie unica «Segreteria oggi» con **Da fare**, **In scadenza / da verificare**, **In regola** (ultimo è uno stato navigabile, non un numero inventato).
- Scorciatoie: **Registra contanti**, **Tesserati**, **Automazioni**, **Documenti**. Incasso rapido riusa il backend Quote & Incassi.
- Cinque sezioni legacy restano come compatibilità tecnica ma vengono nascoste in modo permanente nella dashboard; è rimosso anche il pulsante «Mostra altri controlli» e il relativo JavaScript.
- Rimossa voce «Altri controlli» con Cuore dal menu laterale; rimosso «Cuore» dal dock delle automazioni; rimossa la scorciatoia «Pratiche aperte» nella scheda tesserato, dove esistono già documenti e incassi; Analytics rimanda agli avvisi invece che al vecchio Cuore.
- Nessuna variazione a registri, tabelle, incassi, PDF, funzioni dell'app Famiglie, numerazione ricevute, stati dei certificati o storico audit.
- Le route tecniche `/cuore-operativo` e relativi endpoint POST rimangono intatti, perché sono utilizzati da processi amministrativi e non possono essere rimossi senza una migrazione verificata. *«Senza traccia» riguarda la navigazione quotidiana, non la distruzione degli storici.*

## Controlli effettivamente svolti OFFLINE

- Applicazione sequenziale da un clone di A259: A260 → A261 corretta → A263, senza errori. È stato anche individuato e corretto un conflitto CSS: due pannelli legacy erano ancora visibili con la prima regola.
- Verifica AST di tutti i sorgenti Python nel clone; 10 viewport Chromium: **375, 390, 428, 768, 1024, 1152, 1280, 1366, 1440, 1920 px**. Risultato: 0 overflow orizzontale, 5 pannelli legacy nascosti, 4 azioni visibili, 3 stati.
- A259 locale: «In contanti?», bonifici e SumUp contano solo movimenti riconciliati; annullati e non pagati esclusi; blocco in caso di divergenze. Test UI operatore su 390, 768, 1024, 1152, 1366 e 1440 px.
- Backend Core Operativo e moduli incassi, ricevute A253, documenti e tesserati **non modificati nella logica**. I 10 file A253 hanno 8 hash originali: i 2 rimanenti (operatore e incassi) contengono gli interventi A259 intenzionali.
- Nessun test autenticato end-to-end su Railway ancora eseguito.

## Non ancora completato

1. Integrazione repository pubblico ↔ codice reale: la maggior parte di `/data/top2_app/asd_app` non è in GitHub. Serve una procedura di release privata e verificata; non utilizzare il branch di staging direttamente per il deploy.
2. Collaudo autenticato su clone isolato di DB e media, verifiche CSRF, responsive con CSS completo, flussi pagamenti e PDF, app Famiglie, documenti e procedure di ritorno.
3. Completa mappatura dei **link storici al Cuore** prodotti da altri moduli/override. Il menu primario è stato pulito, ma non è dimostrato che ogni pagina storica sia priva di link legacy.
4. Automazioni reali: WhatsApp Business non implica API automatica. Solo dopo configurazione di provider autorizzato/opt-in e template si possono abilitare invii programmati. SumUp richiede link reale e verifica indipendente/webhook prima di segnare una quota pagata; fino ad allora nessun invio automatico o saldo virtuale.

**Stato finale attuale:** A253 ONLINE INVARIATA. A259–A263 in STAGING. Nessun deploy, cancellazione, riavvio o modifica al database. Non unire alla produzione senza nuova verifica della release.
