# A279 — Chiusura tecnica in staging e verifiche obbligatorie per UN SOLO deploy

Stato: **STAGING, NON IN PRODUZIONE**. La produzione attuale è A253 + A267B + A273.

## Concluso nel clone di sviluppo

- Baseline A267B preservata **byte per byte** per `routes_contabilita.py` e `bodymind_a265_cashbook.py`.
- Anticancellazione automatica dei PDF A273 riapplicata nel clone; chiamata storica `cleanup_old_files(PDF_DIR, "ricevuta_*.pdf", keep=30)` neutralizzata.
- A259–A271: operatori, mobile, dashboard compatta, navigation senza Cuore Operativo, automazioni e app Famiglie con predisposizione link SumUp. Invii effettivi disabilitati finché Meta/consensi/template non sono configurati.
- A274/A280: pagina amministrativa CSRF per cambio metodo di un pagamento verificato, con ricevuta collegata, prima nota unica, blocchi per provider e salvataggio audit atomico. Nessun pagamento/numero/data/PDF duplicato o rigenerato.
- A275: dashboard e dettaglio flussi leggono A237 senza cache e mostrano errore se i dati non quadrano.
- A276/A277: giorno di ingresso confermato con storico; report separa tesserate entrate a settembre/ottobre, data del versamento e competenza della mensilità.
- A279: lista ricevute non propone più un PDF inesistente; l'eventuale ricostruzione offre solo anteprime marcate **NON ORIGINALE** da revisionare senza scrivere su archivio/DB.
- A279: strumento read-only unico su DB vero per verificare la tariffa standard 70 €, sconti, esenzioni, richieste di pagamento (il KPI 150 € è somma di link, **non debito certo**), registri contanti/bonifici e PDF, con confronto A237.

## QA oggettiva

- 189 sorgenti Python integrati: AST superato.
- A274 16 test, A275 18, A276 13, A277 4, A269–A271 44, A279 21 test aggiuntivi (8 smoke integrati). Test *locali e sintetici*, non equivalenti a prova autenticata sul live.
- Protezioni A273 e A267B confermate nel clone.

## Blocchi REALI; niente finta chiusura

1. **Ricevute:** A272 live: 144 ricevute, 112 attive; 87 attive senza PDF accessibile e 26 annullate senza PDF. A273 ha protetto archivio ma non ha trovato alcun PDF candidato nell'unico archivio ZIP/TAR ispezionato. Non recuperate, non dichiarare risolto. Per ogni ricevuta mancante verificare data, progressivo, intestatario, importo, causale, pagamento e fonte probatoria; mai riprodurre l'originale identico inventando data o emissione.
2. **Cassa/quote:** accesso SQL read-only al DB corrente per conoscere nominativi, metodi, 150 € `payment_requests`, ingresso reale settembre/ottobre, listino 70 e agevolazioni; questa lettura è disponibile mediante lo script locale A279 sul Mac del proprietario, non attraverso Railway API.
3. **Provider:** link SumUp ancora non fornito; WhatsApp API business, template e consenso ancora non configurati; nessun invio automatico.
4. **Collaudi/release:** manca copia isolata completa DB+media, prova di restore e funzionalità Flask autenticata, PDF, storico, portale Famiglie e responsive reale. Il vecchio Railway launcher di 131 patch va neutralizzato e testato su clone PRIMA di qualsiasi restart/redeploy.
5. **Release:** nessun merge nel ramo `railway-top2-production`, nessun deploy Railway, nessuna sostituzione del volume di produzione fatta da A279.

Il pacchetto A279 di staging rimane privato e condiviso solo nella conversazione: il repository GitHub pubblico **non riceve codice runtime privato, database, nomi di minori o credenziali**.

## Regola del prossimo intervento

**Un solo rilascio, quando backup, audit e test superano i gate e l'utente autorizza.** Fino ad allora la produzione A273 funzionante non si tocca.