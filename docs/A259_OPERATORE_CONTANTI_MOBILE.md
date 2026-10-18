# BodyMind A259 — Operatore e incasso contanti mobile (STAGING, NON PUBBLICATO)

Questo branch non è la produzione. Il servizio Railway continua a usare A253 senza riavvio.

## Correzioni isolate preparate
- Una domanda come «Quanti pagamenti in contanti abbiamo?» o «In contanti?» viene intercettata prima del planner IA e conta i movimenti operativi riconciliati A250/A253, esclusi annullati, non pagati, storni e zero. Risponde con numero, importo, metodo e periodo esplicito; errore di riconciliazione => blocco, non numero inventato. Supporta anche bonifico e carta/Pos/SumUp.
- Nuovo GET admin-only /quote-incassi/incasso-rapido: maschera mobile semplice che manda POST a /quote-incassi/incasso/<tid> usando il motore esistente e token CSRF. Non è un secondo sistema pagamenti. Conferma richiesta prima dell'invio; non attivare senza test end-to-end, inclusi doppi invii.
- Operatore mobile: barra di navigazione minima («Registra contanti», «Pagamenti», «Ricevute»), riduzione sovrapposizioni, controllo file nascosto e compose responsive; restano intatti upload, microfono, azioni e layout tesserati.
- Timeline rimossa SOLO dal quickdock in core.py, endpoint/storico preservati. Centro Operativo e automazioni non ancora modificati.

## QA completata su copia isolata
- Test SQL sintetico: cash 2 movimenti / 62,50 €, bonifico 1 / 45 €, annulled+pending esclusi, fail-closed se il ledger non concorda, zero scritture nel calcolo.
- Test HTML/JS della maschera contanti a 390×844, 768×1024, 1152×720: POST simulato verso la route originale, importo e CSRF presenti, nessun overflow.
- UI CSS operatore a 390×844, 768×1024, 1024×768, 1152×720, 1366×768 e 1440×900: nessun overflow, input hidden, composer sullo schermo.
- Sintassi dei file core.py, routes_operator_bodymind.py e routes_quote_incassi.py sul clone A256 compilata senza errori.
- Il patcher A259 richiede gli SHA live A253 del 18 ottobre prima di cambiare file. Le correzioni NON sono state eseguite sulla produzione.

## Vincoli di progetto da preservare
1. Niente downgrade dell'impaginazione tesserati, pagamenti A253, documenti, certificati, ricevute e app Famiglie.
2. Dashboard futura con tre stati: Da fare / In scadenza / Tutto in regola. Cuore Operativo semplificato, non rimosso a scapito delle funzioni; Timeline solo come storico interno.
3. Una pagina Automazioni: finestre giorni prima (5/7/10), ripetizione dopo 3 giorni se ancora da pagare, stop al saldo verificato; certificati e quote. WhatsApp Business automatico SOLO previa integrazione ufficiale e consenso; SMS manuale alternativa, email opzionale.
4. Link SumUp in promemoria e Famiglie, ma status «pagato» SOLO dopo conferma verificata del provider, mai perché è stato aperto il link.
5. Rilascio in staging privato: test autenticati, CSRF, duplicate POST, ricevute PDF, saldi, Family access e backup; poi esplicita autorizzazione per produzione.

Il repository è pubblico: nessun database o documento personale deve essere caricato qui.
