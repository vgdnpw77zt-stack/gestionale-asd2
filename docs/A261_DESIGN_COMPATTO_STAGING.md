# A261 — Semplificazione UI della dashboard e dell'operatore (STAGING)

**2026-10-18. Non rilasciato in produzione; A253 attiva e non modificata.**

## Interventi di codice riproducibili

- `staging/design/a260_patch.py`: applicare **soltanto** a una copia offline A259 verificata, con le stesse impronte SHA del sorgente, per generare dashboard «Segreteria oggi» e rifinitura della chat operatore.
- `staging/design/a261_patch.py`: applicare dopo A260 per mostrare all'avvio soltanto la testata utile, con pulsante «Mostra altri controlli»; i cinque pannelli esistenti rimangono nel DOM, completi, e sono mostrati nuovamente a richiesta.
- `staging/design/test_a261.py`: usa **il vero template HTML** della dashboard modificata e Playwright Chromium. Esamina 375, 390, 428, 768, 1024, 1152, 1366, 1440 e 1920 px; verifica che tutti i pannelli esistenti riappaiano, che il pulsante sia raggiungibile, che l'espansione ARIA cambi e che non vi siano errori JS e overflow orizzontale nella vista compatta.
- Il terzo stato è chiamato «Tutto in regola» **solo quando gli alert sono davvero zero**. In presenza di alert, il link si chiama «Consulta le schede»; nessun conteggio di atlete «in regola» viene inventato.
- Nessun CSS delle schede tesserate è riscritto, nessuna modifica a tabelle o record, nessun invio automatico WhatsApp e nessuna conferma SumUp simulata.

## Risultato prova isolata

- Controllo sintattico A260 e A261: PASS.
- Patch A261 idempotente: seconda applicazione non altera il sorgente (SHA identico).
- 9 viewport prova sintetica *basata sul vero template della dashboard*, con valori fittizi: PASS. 0 errori JavaScript e 0 overflow orizzontale nella visualizzazione iniziale. Tutti i 5 pannelli legacy riaperti dopo clic.
- Questi test **non** includono il layout e gli asset effettivi dell'intera applicazione, né sessione autentica, richieste AJAX, autorizzazioni, CSRF o vera UI di produzione.

## Sicurezza e rilascio

L'attuale branch pubblico non contiene l'intero runtime reale `/data/top2_app/asd_app`; non fare merge e non deployare soltanto questa versione del branch. Le patch sono studiate per la copia offline A256/A259 e richiedono ulteriore test end-to-end su clone privato completo prima di qualsiasi rilascio. Il processo Railway di A253, il volume dati, le ricevute, i certificati e l'app Famiglie restano invariati.
