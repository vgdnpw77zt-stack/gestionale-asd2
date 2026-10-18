# A278 — Regola base, eccezioni, debiti veri e richieste da riconciliare

**STAGING / nessun deploy.** Verifica statica effettuata sui sorgenti A256/A270; non sono disponibili i record `payment_requests` attuali del DB live in questo collegamento. Non attribuire 150 € a una o più atlete prima del confronto record per record.

## Causa accertata della possibile confusione «150 € da recuperare»

`routes_dashboard.py` aggrega:
```sql
SELECT COALESCE(SUM(amount),0)
FROM payment_requests
WHERE status IN ('pending','queued','requested')
  AND (deleted_at IS NULL OR deleted_at='')
```
Tale importo viene mostrato nel riquadro *Richieste da riconciliare*, distinto dal riquadro *Mensili da incassare*. La pagina `/pagamenti/da-recuperare` visualizza le richieste di pagamento aperte, non una certificazione di debito. Un link non chiuso può rimanere dopo un incasso manuale. **Non risolvere creando o cancellando pagamenti senza audit.**

## Configurazione economica già presente

- `/quote-incassi` contiene il **Listino** (standard, agonista, sorelle, personalizzata), persistito nella tabella `quote_listino`. L'importo standard **va verificato nel DB live prima di impostarlo a 70**: in `quote_engine.py` il default per una nuova installazione è 0 €, mentre alcuni componenti legacy riportano 70 hardcoded.
- `/quote-incassi/atleta/<id>` gestisce `quota_tipo`, `quota_personalizzata` e `quota_sconto_fisso`; sul singolo mese la route `/quote-incassi/variazione/<id>` modifica il dovuto con motivazione e `/quote-incassi/non-dovuto/<id>` registra un'esenzione con motivo.
- La logica `/quote-incassi/listino` aggiorna soltanto mensilità `non_configurato`, senza riscrivere quelle già configurate. Le modifiche al listino non devono retrodatare tariffe su ricevute già emesse.
- L'ingresso effettivo settembre/ottobre deve bloccare mesi precedenti; riclassificare la **coorte d'ingresso** non deve muovere data e metodo di un incasso storico.

## Guardrail da verificare prima del rilascio unico

1. Mostrare in dashboard **Debiti mensili verificati** e **Richieste/link da riconciliare** come categorie separate, sempre con conteggio record, elenco per atleta, periodo e causa.
2. Per ogni mese calcolare `dovuto=max(0,base-sconti)`; `residuo=max(0,dovuto-incassi_validi-crediti_applicabili)` solo se iscrizione attiva nel periodo e decisione non esente.
3. Acconti multipli rappresentano più movimenti ma **una mensilità**. Metodo contanti/bonifico/SumUp è proprietà di ogni incasso, non della mensilità.
4. Una richiesta pending `payment_requests` non aumenta il debito reale; al pagamento riconciliato va chiusa senza duplicare movimenti o ricevute.
5. Configurazione standard 70 € per il periodo desiderato, eccezione continuativa per atleta, variazione mensile motivata, esenzione; storicizzare la tariffa applicata al momento del mese, senza mutare progressivi PDF.
6. Dashboard, bilancio e cassa contanti devono riferirsi alla **stessa fonte canonica A237/A267B**; distinguere data dell'incasso, mese quota e inizio iscrizione.
7. Report nominativo Settembre/Ottobre: iscritti per data ingresso, incassato reale per data e competenza, raggruppamenti contanti/bonifico/carta, sconti ed esenzioni, importi residui con origine verificabile.
8. Non inviare solleciti se stato ambiguo, data ingresso sconosciuta, credito non riconciliato, ricevuta/pdf incoerente o riduzione da verificare.
9. QA autenticato su copia DB/media, conservare tutta l'A267B attiva, no merge diretto del repository pubblico che manca dei sorgenti runtime completi.

## Stato
La causa **del riquadro 150 €** è stata identificata nel codice, ma non la composizione precisa dei 150 €: serve audit read-only di `payment_requests` e comparazione per id atleta e periodo con `pagamenti`, `ricevute`, `quote_mensili`, date ingresso. PDF mancanti: A272 ha rilevato 87 ricevute attive senza PDF; A273 ha protetto l'archivio ma non li ha recuperati. Nessun dato modificato da questo rapporto.
