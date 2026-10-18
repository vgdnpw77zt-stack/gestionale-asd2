# A265 — Correzione mobile Uscite e riepilogo contanti/bonifici — STAGING

Stato: NON DEPLOYATO. Il codice A253 online e il DB di produzione restano invariati.

## Risultati
- Eliminato sul clone l'intercettore prima della route `/contabilita`: il registro contabile completo resta il punto di accesso a entrate e uscite.
- La lista Uscite diventa leggibile per schede a 375–720px; mostra descrizione, data, importo, metodo e giustificativo senza tabella larga 900px.
- Filtro `Solo bonifici` cerca prima dell'applicazione del limite 300; riconosce bonifico, bonifico bancario, sepa, banca, bank transfer e iban.
- Le uscite bonifico sono elencate nella vista Contabilità con apertura dell'elemento già registrato, **senza ricrearne uno nuovo**.
- Riepilogo riconciliato per contanti, bonifici, carte/SumUp, addebiti e altri; numero incassi, iscrizioni, mensilità, quote distinte, uscite per metodo e sconti/esenzioni documentati.
- Attenzione: «saldo movimenti contanti» è *un flusso contabile*, **non** la giacenza fisica presso la presidente. Richiede apertura cassa, consegne, versamenti e riconciliazione per diventare giacenza fisica.
- Questa versione non cambia alcun pagamento, ricevuta, certificato, documento o stato di sollecito.

## QA effettivo (clone, dati sintetici)
- Test canonico A237 + A253: 180 EUR entrate, 100 EUR uscite, 3 incassi contanti ma 1 mensilità distinta nel canale contanti, 2 sconti e 1 esenzione; un'uscita bonifico sintetica visibile e cliccabile.
- DB sintetico immutato dopo il rendering; riconciliazione mismatch bloccata, nessun dato annullato sommato.
- Chromium viewport 375, 390, 428, 768, 1024, 1152, 1280, 1366px; nessun overflow, descrizione e metodo spesa visibili.
- Un test addizionale **esegue l'espressione f-string** della pagina Uscite: intercettato e corretto un problema di graffe CSS che passava il solo controllo sintattico.
- Sorgenti modificati nel clone: `core.py`, `routes_contabilita.py`, nuovo `bodymind_a265_cashbook.py`. Patch conservativa a ancore esatte: in caso di divergenza si ferma.

## Cosa resta obbligatorio prima del rilascio
1. Eseguire A265 in modalità CHECK su una copia coerente del DB Railway reale: verificare che le etichette dei metodi e le decisioni sconto si riconcilino con A237.
2. Provare route GET autenticate su clone con i file statici, con casi di pagamenti concorrenti, bonifico al presidente e giustificativo allegato.
3. Verificare che tutti gli script della sequenza A259–A264 abbiano eseguito correttamente il clone; A265 richiede come base il `core.py` già consolidato, **non** il file upstream GitHub isolato.
4. Confrontare hash e conteggi DB/documenti prima e dopo; backup verificato e rollback del solo codice.
5. Soltanto dopo i collaudi e approvazione esplicita: pubblicare senza avviare il launcher storico e verificare mobile/iPhone e 12–13 pollici.
