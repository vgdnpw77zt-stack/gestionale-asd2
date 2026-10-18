# A270 — scadenza BodyMind e predisposizione integrazioni (STAGING)

Conferma della gestione BodyMind Aerial Studio ASD: le quote mensili scadono **il giorno 10 di ogni mese**.

- Regola predefinita: entro il 10, anticipo di 7 giorni, ripeti dopo 3 giorni se ancora da pagare, massimo 3 solleciti. Se gli invii precedenti risultano confermati, i giorni indicativi sono 3, 6 e 9; bozze non inviate non contano.
- Il modello contabile non sollecita mai quote pagate, esenti, di stato dubbio o potenzialmente coperte da crediti precedenti.
- Il link di pagamento SumUp è un campo HTTPS nelle **Automazioni → Promemoria quote**, modificabile senza toccare il codice. Vuoto fino alla comunicazione dell'utente. Il click non segna pagato.
- Il numero WhatsApp Business dell'ASD è un campo facoltativo, di solo recapito: un numero NON abilita le spedizioni automatiche.
- Le credenziali Meta/WhatsApp Cloud API devono essere inserite fra i **segreti Railway/gestore protetto**, non in GitHub né nel form in chiaro. Invio con template approvati/consenso/documentazione da collaudare.
- Fino alla connessione col provider, il motore produce esclusivamente bozze manuali; messaggi realmente inviati vengono contati soltanto con conferma dell'invio.
- Non modifica **A253/A267B**, ricevute, registrazioni, titoli, file, certificati, app Famiglie, né fa alcun deploy.

## Test eseguiti

37 test locali superati: calendario 3/6/9, giorno 10 predefinito, modalità invio spenta, salva configurazione, numero WhatsApp valido/non valido, campo SumUp vuoto/HTTPS, protezione da link malevoli, prevenzione doppi invii, stato pagamento saldato, SQLite di test e UI mobile in Chromium. Test su dati sintetici e HTML isolato, **non** collaudo autenticato live.

## Prima della release unica

Serve un clone completo DB/media con accesso autenticato, verifica dei file A267B e backup/restore; poi collegamento del provider WhatsApp e conferma SumUp. Non dichiarare l'invio automatico operativo prima della prova reale.