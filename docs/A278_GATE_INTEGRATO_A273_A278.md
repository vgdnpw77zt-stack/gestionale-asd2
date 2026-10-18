# A278 — Gate unificato A273–A278 (senza deployment)

Questo documento aggiorna la preparazione del rilascio **unico** BodyMind; **non autorizza né esegue il deploy**.

## Verifiche concluse

- Clonati i 183+ moduli della variante A270 e applicate in sequenza le modifiche A273, A274, A275, A276, A277, A278.
- **190 file Python in AST senza errori**, salvi due vecchi SyntaxWarning non bloccanti.
- **Protezione A273 preservata**: in `core.py` il guard impedisce a `cleanup_old_files` di cancellare PDF `ricevuta_*.pdf`.
- **A275**: snapshot contabile read-only e `Cache-Control: no-store`, la dashboard non deve mostrare bilanci precedenti dopo una rettifica.
- **A276/A277**: data ingresso confermata; esclusione dei periodi precedenti nei promemoria, senza cancellare incassi vecchi.
- **A278**: tariffa Standard (da impostare a 70 € in vivo con approvazione), eccezioni, singole mensilità motivatamente diverse dal listino, richieste aperte non duplicate come debito.
- **Due file A267B mantengono identico SHA-256**: `routes_contabilita.py` = `9d677c49a435bbb94118730da116054796146ca97e32db714b1a4514882212b9`; `bodymind_a265_cashbook.py` = `1ba2799f1ff64be0582c57639dc5e124e5562846e9a7f4bb8ca92c7dd3422d92`.
- Test ripetuti: A274 16, A275 18, A276 13, A277 4, A278 25 (24 superati, 1 test client Flask saltato: ambiente non ha Flask). **16 controlli viewport Playwright** A278 a 375, 390, 428, 768, 1024, 1152, 1366 e 1920 px, senza overflow.
- Casi finanziari con **dati sintetici**: una richiesta pending da €150 **non** si somma alla quota €70; se il pagamento di €70 esiste, residuo zero, ma il pending resta da riconciliare. Se una mensilità risulta €150 anziché €70 senza motivazione, è `da_verificare`, non debito certo.

## Blocchi aperti e motivi per cui NON pubblicare ancora

1. **Nessun accesso diretto a /data live** dalle API GitHub/Railway per controllare chi compone i 150 €, le quote storiche e le eccezioni. È necessario usare il report completo in sola lettura sulla copia reale e condividerne solo dati privati, non su repository pubblico.
2. Ricevute: A272 ha censito 87 PDF attivi mancanti su 112; A273 ha protetto il percorso ma **non ripristina documenti**. Nessuno dei PDF risulta trovato nell'unico archivio ZIP/TAR ispezionato.
3. Test end-to-end **con autenticazione** di salvataggio tariffe, modifica pagamento, ricevute, documenti, app Famiglie, dashboard e mobile ancora assenti.
4. WhatsApp API e link SumUp saranno inseriti dal proprietario; in assenza, solo bozze e nessun saldo automatico.
5. Prima di rilascio unico: clone completo e privato del DB e dei media, backup e restore collaudati, check SHA A273/A267B live, avvio a freddo senza gli oltre 100 script storici. Il ramo di staging GitHub non contiene ancora l'intero runtime e non deve essere unito/redeployato direttamente.

Nessun importo fittizio scritto sul server, nessun reset del listino, nessuna modifica a ricevute, date o progressivi.
