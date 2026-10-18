# BodyMind A264 — Flussi e bilancio nella dashboard ESSENZIALE (STAGING)

**Stato: non distribuito, nessuna scrittura sul DB e nessun restart Railway.**

## Problema di integrazione individuato

L'A263 semplificata nasconde tutti i pannelli storici della dashboard e rimuove «Mostra altri controlli». Questo è intenzionale per eliminare la pesantezza visiva, ma la precedente A262/A263 contabilità usava uno dei pannelli nascosti e cercava l'anchor del toggle A261; i dettagli richiesti per iscrizioni, mensili, metodi e sconti potevano quindi risultare invisibili.

## Intervento A264

- Mantiene i tre stati «Da fare», «In scadenza / da verificare», «In regola» e la navigazione semplice senza Cuore Operativo.
- Mostra nell'area **sempre visibile** «Segreteria oggi» quattro valori: Entrate, Uscite, Saldo dei registri, Movimenti attivi.
- Sotto i valori mostra **origine degli incassi**: Iscrizioni, Quote mensili, Altri pagamenti, Entrate manuali; importo, incassi, numero di persone quando il record è collegato a un tesserato.
- Il prospetto **Metodi di incasso, iscrizioni, mensili e sconti** espande i dati riconciliati e i tipi di agevolazione documentata; su iPhone la tabella scorre solo dentro il suo riquadro.
- La classificazione usa gli stessi movimenti attivi riconciliati da A237/A253; ricevute non vengono sommate due volte, annullati/non pagati/zeri non aumentano i totali. Le mensilità in due tranche rimangono due incassi ma un solo mese scontato. **«Sorella» da sola non dimostra uno sconto**.
- In caso di quadratura incoerente l'avviso «Contabilità da verificare» viene mostrato nella dashboard visibile, non dietro un pannello nascosto.
- I valori sono **storici complessivi dei registri**, non un bilancio della banca e non ancora filtrati per stagione sportiva. È raccomandato introdurre un selettore «Storico / stagione / mese» in una fase successiva, conservando il filtro corrente per gli alert tesserati.

## Verifiche svolte OFFLINE

1. Applica la patch al sorgente A262/A263 su clone: sintassi e idempotenza OK.
2. Fixture fittizia: 182 € di entrate (75 iscrizioni, 95 mensili, 12 entrate manuali), 5 € uscite, 177 € saldo, tutti i subtotali riconciliati, senza cambiamenti dell'hash SQLite.
3. Chromium a **375, 390, 428, 768, 1024, 1152, 1280, 1366, 1440 e 1920 px**: dettaglio contabile visibile nella sezione A263 corretta, i vecchi pannelli nascosti, zero overflow e zero errori JS, link apre entrambi i dettagli.
4. Simulazione fallimento di riconciliazione: messaggio visibile nella schermata compatta, header risposta `review-needed`.

## Limiti e rilascio

Non abbiamo una copia completa protetta del DB di produzione per verificare causali e sconti reali; la fixture è sintetica. Non effettuare deploy dal branch GitHub pubblico: non contiene l'app live completa. Prima serve clone privato, verifica schema reale SQLite in sola lettura, test autenticati di tutte le route, documenti, ricevute, app Famiglie, responsive e backup; approvazione separata prima della pubblicazione.

Le route e i record del Cuore Operativo restano conservati per audit. Il Cuore sparisce dalla navigazione ordinaria senza cancellazioni storiche.
