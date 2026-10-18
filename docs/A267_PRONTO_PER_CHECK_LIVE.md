# A267 — Correzione mirata su A253, senza downgrade (rilascio da autorizzare)

**Stato: installer verificato in isolamento; NON applicato alla produzione.**

## Problemi risolti nei sorgenti

1. `/contabilita` non deve più essere intercettato dal `before_request` dell'interfaccia Uscite. Mantiene il proprio registro A253, le operazioni sui movimenti manuali e la riconciliazione.
2. `/pagamenti/uscite` mantiene il movimento già presente «bonifico al presidente» senza duplicarlo. Su mobile ogni riga mostra data, causale, importo, metodo, giustificativo e link alle azioni, in luogo della tabella orizzontale da 900 px.
3. Il filtro «Solo bonifici» viene eseguito nel database **prima** del limite di 300 righe, così un bonifico non sparisce perché preceduto da tante uscite in contanti. Nessun dato viene modificato dal filtro.
4. Riepilogo di cassa A265 per metodo: numero incassi, iscrizioni, mensili, mensilità distinte (acconti non raddoppiati), uscite e trasferimenti; sconti/esenzioni documentati ma non contabilizzati come incassi; saldo movimenti contanti chiaramente distinto dalla giacenza fisica custodita dalla presidente.
5. A266: filtra false segnalazioni delle quote già pagate/non dovute a partire da `meta.tesserato_id`, lasciando avvisi reali su certificati, tutela minori e quote dovute. Un recapito valido evita allarmi generici per l'altro recapito assente.

## Esclusioni deliberate

- Nessuna riscrittura di pagamenti, ricevute o database.
- Nessuna installazione degli interventi visual A259–A264 ancora in staging: farebbero diventare il fix contabile un rilascio ad alto rischio.
- Nessuna eliminazione di route storiche o dello storico audit del Cuore Operativo in questa correzione mirata.
- Nessuna automazione WhatsApp/Meta o conferma SumUp inventata.

## Test svolti

- Patch A265 e A266 applicate in sequenza al clone A256/A253 originale; SHA prima/dopo registrati; compilazione Python superata.
- 189 moduli Python controllati in AST sul clone integrato A259–A266, 0 errori.
- Fixture SQLite: distinzioni tra incassi, mensilità, acconti, sconti, esenzioni, metodi e uscita bonifico al presidente; A237 e A265 riconciliati; DB identico prima/dopo.
- Layout spese a 375, 390, 428, 768, 1024, 1152, 1280, 1366 px senza overflow; query bonifici non limitata dall'elenco generale.
- A266: alert quote già pagate/non dovute rimossi; avvisi di quote realmente dovute e certificati preservati.
- Preflight installatore A267 simulato con sorgenti baseline A253, SHA reali e database sintetico: passato.

## Processo di installazione previsto

Solo tramite SSH autenticato del proprietario al servizio **live**; `--check` in sola lettura, `--apply` dopo consenso esplicito, verifica SHA dei sorgenti invariati e A253, preflight contabile su DB corrente in read-only, spazio libero, processo Gunicorn e HTTP. Quindi backup consistente di SQLite e dei due sorgenti sostituiti, installazione atomica di `core.py` e `routes_contabilita.py`, aggiunta di `bodymind_a265_cashbook.py`, reload di worker tramite HUP senza Railway restart. **Non fare redeploy Railway**: il launcher legacy esegue script storici.

A267 si blocca su fonte modificata, DB incoerente, backup non verificato o processi non riconosciuti. Non si presume alcun importo reale del bonifico alla presidente. Dopo installazione resta necessario collaudo autenticato di Contabilità/Uscite/Ricevute.

Il sorgente completo del launcher contiene sorgenti applicativi privati: è distribuito separatamente e non viene caricato nel repository pubblico.

**Nessuna modifica applicata al live da questo commit.**
