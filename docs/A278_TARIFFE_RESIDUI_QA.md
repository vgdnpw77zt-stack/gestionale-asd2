# A278 — Quota mensile Standard, eccezioni e «Da recuperare» (STAGING ONLY)

**Scopo:** evitare che «150 € da recuperare» venga interpretato come insoluto certo quando sono solo richieste online da riconciliare, e uniformare il suggerimento dei pagamenti al listino ufficiale.

## Fonte di verità
- Tariffa ordinaria richiesta: **70 € al mese**. Non forzata nel database corrente; il nuovo form **Impostazioni → Tariffe e quote** permette di impostarla e auditarla.
- Per ogni atleta vengono rispettati: tariffa standard, agonista, sorelle, personalizzata, sconto fisso, decisione motivata del singolo mese, esenzione/sospensione, ingresso settembre/ottobre confermato.
- Le mensilità già aperte **non vengono riscritte automaticamente** se cambia il listino. Le decisioni esistenti, incassi e ricevute restano invariati. Variazioni storiche necessitano riconciliazione individuale con motivazione.
- Il campo importo della schermata pagamenti non usa più il valore hardcoded di 70 €. Se manca una tariffa verificabile, resta vuoto e obbliga a controllare.
- **Quota iscrizione**: il vecchio suggerimento di 50 € è mantenuto separato; non significa che sia parte di un singolo mensile da 70 €.
- L'endpoint legacy POST /quote-incassi/listino viene disattivato come scrittura diretta senza audit e rimanda al nuovo modulo tracciato.
- **«Spiega i residui»**: pagina read-only per atleta e mese con dovuto registrato, pagato effettivo, residuo (solo se verificato), eccezioni, richieste aperte non sommate al debito.
- Quote non configurate o con importo diverso dal listino senza motivazione, conflitti tra decisione e riga mensile, crediti storici da riconciliare: **da verificare**, non invii automatici.

## QA effettuato
- Patch A276→A278 applicata a clone del codice A256/A270; tutte le ancore e le AST Python verificate, nessun file dati modificato.
- **25 test di modulo**: 24 passati; 1 test client Flask autenticato saltato poiché Flask non è disponibile nell'ambiente locale. Non va spacciato per E2E.
- **16 verifiche grafiche Playwright** sulle pagine Tariffe e Quote e Spiega i residui, da 375 a 1920 px: nessuno scorrimento orizzontale.
- Fixture esempio: richiesta aperta €150 e quota €70 con pagamento completo => insoluto €0; la richiesta resta «da riconciliare». Questo è **un dato di test**, NON prova del caso reale nel DB BodyMind.
- Fixture caso €150 come mensile salvato mentre Standard €70 senza motivo => «da verificare» anziché debito certo.

## Gate prima del rilascio unico
1. Validare contro la versione **A273 installata**, dopo A267B; le patch non vanno applicate a un runtime sconosciuto o sovrascritto.
2. Verificare su copia isolata SQLite e media autentici lo storico e le rettifiche A274/A275/A276/A277, con verifica per atleta e mese.
3. Test client Flask autenticati / CSRF, inserimento e variazione tariffa, credito, doppio click, concorrenza, ricevute, app Famiglie.
4. Diagnosi documentale A272: 87 ricevute attive senza PDF accessibile; l'archivio A273 scansionato non ha trovato originali. Non ricostruire automaticamente PDF storici senza verifica di coerenza.
5. Consolidare launcher/immagine da codice privato e attivare **una sola release** dopo backup DB+media e restore testato. Non fare deploy diretto del branch pubblico.
6. Provider SumUp/WhatsApp non ancora configurati: permettere solo messaggi manuali o bozze senza falsi invii.

**Produzione ancora A273/A267B; A278 solo staging, nessun deploy o DB live modificato.**
