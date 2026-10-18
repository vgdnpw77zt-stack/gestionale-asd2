# A270 — Unico rilascio / criterio definitivo e QA

**STAGING. NON PUBBLICATO.** Nessuna operazione su Railway o database di produzione in questa fase.

## Decisione dell'ASD confermata
- Mensile dovuto **entro il giorno 10**.
- Intervalli predefiniti: 7 giorni prima, ripetizione dopo 3 giorni, massimo 3. In caso di invii effettivamente confermati, il calendario illustrativo è 3, 6, 9. È una impostazione modificabile dalla pagina Automazioni, non un invio automatico immediato.
- Link SumUp HTTPS configurabile nelle impostazioni. Per ora vuoto.
- Numero Business WhatsApp facoltativo e configurabile nelle impostazioni, **non** equivale a un'integrazione API.
- Per automatizzare messaggi in uscita servono API ufficiali, autorizzazioni, template approvati e verifica di consegna. Credenziali solo nei segreti protetti Railway: non nel repository GitHub, non in un campo visibile né nei messaggi di chat.
- Un link SumUp aperto non è prova di pagamento; una bozza WhatsApp non è un messaggio inviato.

## Codice effettivamente versionato
- `staging/A270/bodymind_a269_reminders.py`: decisioni deterministiche, quote pagate/esenti escluse, stop su stato/credito/decisioni ambigui, anti-duplicati.
- `staging/A270/bodymind_a269_read_model.py`: lettura contabile di prova senza mutazioni.
- `staging/A270/patch_existing_automation_ui.py`: impostazioni espandibili, campi modificabili, salvataggio con validazione; senza invii.
- `staging/A270/A270_APPLY_ON_A269.py`: patch fail-closed e idempotente; supporta clone A269 pulito oppure variante A270 parzialmente assemblata, rifiuta sorgenti sconosciuti.

## Difetto rilevato e realmente risolto in staging
Una prima composizione aveva già il giorno 10 nel form ma lasciava `Policy.due_day=None` nel file di runtime. Il nuovo collaudo controlla **il modulo importato dal clone integrato**, non soltanto quello dei test. Staging attuale: `Policy().due_day == 10`, invio disabilitato; la patch si può riapplicare senza cambiamenti. Nessun aggiornamento è stato applicato in produzione.

## QA documentata nel clone
- **41 test unitari locali** passati: incluse 4 nuove prove di integrazione (clone pulito, clone misto, conflitti bloccati senza scritture, regole runtime/A267B).
- Check AST di 184 moduli; nessun errore di sintassi.
- Test mobile Automazioni 375/390/428/768/1024/1152/1366/1920 px senza overflow nel rendering sintetico.
- `routes_contabilita.py` e `bodymind_a265_cashbook.py` del clone coincidono **byte per byte** con il payload A267B.
- Verifica che il filtro `bonifico` sia fatto PRIMA di `LIMIT 300`.
- Test su DB **sintetico**, non una conferma di correttezza di tutti i dati reali.

## Vincoli di release unica
1. Nessun riavvio del vecchio launcher Railway: al lancio esegue molti script mutativi storici.
2. Backup coerente SQLite + media con manifest SHA-256 e prova di ripristino.
3. Confronto degli hash A253/A267B effettivi in produzione prima di costruire il rilascio.
4. Collaudo autenticato di tesserate, quote e incassi, ricevute, contabilità, uscite mobile, sconti, certificati, moduli unici, app Famiglie, upload/download, alerts, operatore e backup.
5. UI mobile verificata con CSS completo e dati isolati, non soltanto HTML sintetico.
6. Se WhatsApp API o link SumUp non sono ancora disponibili, pubblicare in sicurezza le impostazioni **spente** e bozze manuali; attivazione provider solo dopo test dedicato.
7. **Un solo rilascio finale approvato** e rollback pronto, senza cancellazioni DB/documenti.

**Stato:** A267B in produzione secondo l'ultima verifica; A270 e interfaccia semplificata in staging. Non dichiarare automatismi o restyling operativi online finché non superano i gate.
