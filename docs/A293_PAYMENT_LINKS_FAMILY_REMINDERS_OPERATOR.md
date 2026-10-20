# BodyMind A293 — pagamento famiglie, promemoria accesso e layout operatore

**STAGING, NON INSTALLATO IN PRODUZIONE.** A292 installata sul volume resta invariata.

## Audit live di sola lettura (20/10/2026)
- Le impostazioni pagamenti esistono già: `/impostazioni/pagamenti` in `routes_bodymind_fix25.py`.
- Esistono `/pagamenti/provider-links` e `bodymind_a291_family_methods.family_payment_options(conn, athlete_id, month, year, config)`. La soluzione deve integrare questi punti, non replicare il motore contabile.
- PIN famiglia già presente: `tesserati.family_pin`, sistema accessi in `routes_bodymind_fix10.py`; promemoria in `routes_promemoria.py` e `bodymind_a269_reminders.py`.
- L'operatore è in `routes_operator_bodymind.py`; R155 presente ma CSS del composer stratificato in più blocchi.

## Funzionalità A293 richieste
1. Amministratore: inserimento/link SumUp manuale per singola atleta, periodo, tipologia e importo; abilitazione/disabilitazione con audit. Stripe/PayPal solo se effettivamente configurati e testati.
2. App Famiglie: mostrare «Paga» solo per la stessa atleta autenticata e solo con importo residuo confermato dal sistema contabile; nascondere per quota pagata, annullata o non dovuta.
3. Promemoria: usare il PIN già attivo e inviare il relativo URL personale al contatto autorizzato (genitore per minori); mai inviare automaticamente senza consenso/canale abilitato.
4. Layout operatore: consolidare CSS del composer (R154/R155), verificare PC 12–13 pollici, Safari iPhone e tastiera.

## Verifica di dettaglio live (20/10/2026)
- `routes_bodymind_fix25.py` e `routes_bodymind_fix20.py`: presenza di Stripe/PayPal, **SumUp non presente** nella relativa configurazione.
- `routes_bodymind_final.py`: contiene già logica `family_payment_options` e riferimento a SumUp.
- `bodymind_a269_reminders.py`: contiene SumUp, `payment_url` e riferimenti al consenso, ma **non** `family_pin`, `family_code` o `/famiglia/`.
- Operatore: test di trasformazione su sorgente live A292 (senza scritture) superato; SHA sorgente `7caf27e1f22692c0d3e90149857f1c5d3d3ed2379189f9545bc11d295c9c7e21` e SHA candidato `0cdd4569ba01a8cd328295bc09e4e5cb0a90069f3be78ed2d7f0ab55f90941ad`.
- GitHub Actions A293 test Python + Flask: superati. Prova UI autenticata reale ancora da eseguire.

**Nota d'integrazione:** il nuovo registro A293 è ausiliario per link manuali; prima del rilascio occorre definirne la relazione con `payment_requests` e `family_payment_options` esistenti, evitando doppi link e doppie richieste contabili. Nessun automatismo di invio o riconciliazione è attivo.

## Protezioni
- Aprire un link **non equivale a incassare**; nessuna ricevuta prima di conferma transazione verificata.
- Non modificare o eliminare `pagamenti`, `ricevute`, `quote_mensili`, documenti o credenziali.
- Non pubblicare token di accesso o link personali nei log, GitHub o output diagnostici.
- I moduli A293 sono preparati in pacchetto isolato e con test locali core; il test Flask completo e l'integrazione con la copia live sono ancora da eseguire.
- Non fare merge o redeploy Railway: launcher storico potenzialmente mutativo.

## Stato QA
Audit GitHub Actions remoto di sola lettura riuscito; 5 test unitari locali puri superati. Il test della schermata Flask è ancora sospeso per dipendenze Flask non presenti nell'ambiente locale. Nessun invio automatico è stato attivato e nessuna modifica A293 è stata applicata al volume live.
