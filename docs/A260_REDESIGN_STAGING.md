# BodyMind A260 — interfaccia leggera e percorso segreteria (STAGING)

**Non pubblicato, nessun deploy automatico, nessuna modifica ai dati reali.**

## Interventi concreti

1. **Dashboard «Segreteria oggi».** Primo blocco compatto con 3 viste: Da fare (`severity=critical`), In scadenza/da verificare (`severity=warning`), Tutto in regola (link all'elenco tesserati, **nessun conteggio inventato**). I valori derivano da `get_dashboard_metrics`, con periodo già selezionato.
2. **Quattro azioni** in evidenza: registra contanti, tesserati, automazioni, documenti. Sono link a route già presenti nella A259 e/o nel gestionale; nessun endpoint con scritture inventato.
3. **Aspetto premium sobrio.** Fondo blu ardesia, ombre ridotte, leggibilità e contrasto, focus tastiera, icone non invadenti, rosso solo su problemi urgenti, ambra per warning, verde per passaggio agli stati.
4. **Operatore più leggibile** su iPhone e 12–13”: messaggi, intestazione, scorciatoie, barra di scrittura e selettore file nascosto senza invadere il campo. La funzione di allegare, la voce, la chat e l'IA **non** sono rimosse.
5. **Menu semplificato.** Automazioni diventa link principale per amministratore, la sezione tecnica diventa «Altri controlli». La Timeline rimane fuori dal dock, con storico tecnico conservato.
6. **Nessun downgrade.** Anagrafiche, incassi e ricevute A253, CSS tesserate e documenti non vengono riscritti. La dashboard originaria resta interamente disponibile sotto il nuovo riepilogo, incluso drag/drop Autopilot.

## Verifiche locali

- Tre sorgenti sottoposti a controllo SHA della base A259, compilati con Python e ripassati una seconda volta senza differenze (idempotenza).
- Otto risoluzioni sintetiche Chromium: 390×844, 428×926, 768×1024, 1024×768, 1152×720, 1366×768, 1440×900, 1920×1080. Nessun overflow orizzontale nel **preview statico della nuova testata**.
- Verificato a livello di codice che le route di upload, voce, pagamenti e documenti restano nel sorgente.
- La prova è sul clone A256+A259, **non** copre l'effettivo DOM della dashboard in produzione, l'autenticazione, l'intero CSS statico o le interazioni live.

## Stato e prossimi vincoli

**Non fare deploy di questo branch.** Prima: importazione completa e privata dei sorgenti realmente attivi, confronto con tutti gli override CSS runtime, prova con asset reali e dati clonati, regressione su pagamenti/receipt/documenti, rollback e autorizzazione alla pubblicazione. Non introdurre automatismi WhatsApp o SumUp che segnino pagato senza conferma del provider: sono integrazioni separate e non realizzate da questa modifica grafica.