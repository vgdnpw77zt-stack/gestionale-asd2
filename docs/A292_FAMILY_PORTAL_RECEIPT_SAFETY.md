# BodyMind A292 — intervento non pubblicato

## Difetto confermato
Il modulo `routes_bodymind_final.py` del candidato A291 legge e mostra fino a 20 record grezzi di `pagamenti`, senza distinguere reincassi e rettifiche da quote effettive. Il portale espone quindi movimenti tecnici ai genitori.

## Correzione verificata in staging
- Rimossa dalla pagina famiglia la lista `pays` grezza. Il riepilogo `quote_current` rimane.
- Introdotto un registro separato di visibilità delle ricevute, con comando amministratore **Elimina dall'App Famiglie / Ripristina**. La cancellazione è solo dal portale: `ricevute`, `pagamenti`, PDF e progressivi rimangono invariati.
- Registrazione di motivo, operatore, data e storico di ogni scelta.
- Filtro sia nella lista sia nell'accesso diretto al PDF: una ricevuta nascosta non è scaricabile dal portale.
- I pagamenti Stripe/PayPal/SumUp non vengono considerati funzionanti finché il checkout non è verificato.
- 5 test locali superati su SQLite in memoria, sintassi Python dei moduli verificata.

## Blocco di sicurezza al deploy
La configurazione Railway corrente avvia ancora `python /opt/bodymind-migration/migration_upload.py`. Nel Dockerfile quel file è una copia di `runtime_launcher.py`, che esegue molte patch `release_*.py`, preflight con operazioni su DB e pulizia backup a ogni avvio. Il cleanup storico **non ha eliminato questa dipendenza**.

La versione attuale gira dal volume `/data/top2_app/asd_app`; il repository non contiene il suo snapshot completo. Non fare merge/deploy del solo ramo: servono snapshot hash del live, test su copia del DB, nuovo avvio diretto validato, backup remoto verificato e rollback.

## Collaudi obbligatori prima della pubblicazione
1. Virginia D'Angelo: verificare il ledger e le ricevute effettivamente operative, senza correggere per supposizione gli importi.
2. Lato famiglia: nessun reincasso tecnico visibile, ricevute annullate assenti, solo saldo verificato.
3. Admin: nascondi/ripristina una ricevuta di test, PDF diretto bloccato e ripristinato, audit tracciato.
4. Stripe/SumUp/PayPal: quota già saldata non pagabile, link individuale valido solo per atleta/mese/importo corretti.
5. DB: `integrity_check`, `foreign_key_check`, conteggi invariati; smoke su iPhone e MacBook.
6. Backup: evitare nuovi archivi integrali sul Mac, verificare spazio e retention sul server.

Nessun dato live è stato modificato da questa preparazione.
