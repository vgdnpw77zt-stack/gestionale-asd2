# BodyMind A269 — Release candidate unica (STAGING, NON PUBBLICATA)

**Scopo:** chiudere in un unico rilascio stabile la richiesta di semplificazione e affidabilità: A253 pagamenti/ricevute, A267B contabilità/mobile, A259 operatore e incassi mobile, A260–A264 dashboard/Automazioni/Cuore invisibile, A266 falsi avvisi, nuovo modello solleciti e integrazioni SumUp/WhatsApp.

## Correzione anti-downgrade emersa nel test integrato
Nel clone integrato la UI aveva **reintrodotto** un filtro bonifici *dopo* `ORDER BY ... LIMIT 300`, che poteva nascondere proprio l'uscita storica al presidente. Il clone è stato riparato per conservare **esattamente** la query A267B: filtro SQL `WHERE LOWER(TRIM(COALESCE(metodo,''))) IN (...)` prima di LIMIT 300. Corretti anche gli escape CSS del template mobile. `routes_contabilita.py` e `bodymind_a265_cashbook.py` del clone ora coincidono byte per byte con il payload A267B originale. **Non sovrascrivere queste versioni con una patch più vecchia.**

## Nuovo modello promemoria (A269, isolato)
- Regole configurabili nella UI Automazioni: giorno effettivo di scadenza **obbligatorio**, giorni di anticipo (es. 7), ripetizione dopo 3 giorni, numero massimo, link SumUp HTTPS, abilitazione anteprime.
- Lettura SQL `query_only` delle `quote_mensili`, delle decisioni formali, dei pagamenti con stato valido, delle ricevute e degli eventuali crediti di periodi precedenti. Quota inesistente/non configurata, esente, pagata, ambigua o con credito non riconciliato: **nessuna richiesta automatica di pagamento**.
- Rate parziali: importo residuo; mensilità distinta dai singoli movimenti; anticipo e calendario derivano da scadenza esplicita e non dall'assenza di `paid_at`.
- Anti-duplicazione: solo messaggi effettivamente inviati e confermati dal provider contano come tentativi; una bozza o una coda non è un invio. Nessun secondo sollecito prima dell'intervallo impostato.
- Fino a connessione ufficiale WhatsApp Business API e template approvato, solo anteprima `wa.me`, mai falso “inviato”. Il link SumUp NON registra automaticamente un pagamento.
- Non alterare i documenti, PDF, progressivi, incassi A253, ricevute, stati certificati e dati di tesserati.

## QA svolto adesso
- **28 test** di logica, SQLite sintetico in sola lettura, scadenze, sconti/esenzioni, acconti e configurazione UI superati.
- Layout Automazioni a **375, 390, 428, 768, 1024, 1152, 1366, 1920 px** senza overflow nel rendering isolato.
- **184 moduli Python** del clone integrato passati nel controllo AST.
- Regole A264 e 16 checkbox preservate.
- Nessuna richiesta esterna, nessun invio, nessuna scrittura sul DB reale, nessun deploy.

## Gate obbligatori prima dell'UNICO rilascio
1. Acquisire il vero giorno di scadenza della quota e il link SumUp che il proprietario intende usare, senza indovinarli.
2. Collegare e convalidare WhatsApp Cloud API/fornitore con le credenziali e consensi effettivi; per messaggi business iniziati dall'ASD, usare template autorizzati. In assenza, rilasciare solo bozze manuali e stato «non configurato», senza promesse di automaticità.
3. Implementare verifica provider SumUp tramite conferma attendibile, preferibilmente webhook autenticato o verifica operativa esplicita; nessuno stato «pagato» alla semplice apertura del link.
4. Test autentico, prima su clone isolato di **DB e media** (non sui dati reali): pagamento/rettifica, ricevute, contabilità, bonifico al presidente mobile, riepilogo per metodo, sconti, esenzioni, operatore, avvisi medici, minorenni, dashboard, documenti, app Famiglie e upload/download; no regressione su 12–13 pollici e iPhone.
5. Preparare un'unica build riproducibile **privata**, consolidando i sorgenti /data reali, con hash di A253/A267B verificati contro il live. Non fare merge diretto del branch pubblico: mancano i sorgenti runtime completi.
6. Backup DB/media con manifest/hash + prova di restore; disinnescare in staging le 131 vecchie procedure di startup senza perdere migrazioni ancora necessarie; avvio a freddo su clone.
7. **Un solo** passaggio controllato in produzione, dopo approvazione, con QA post deploy e rollback dei soli sorgenti. Non modificare automaticamente dati/receipt PDF.
   
La codebase A269 è disponibile nel pacchetto di test privato della sessione; non riversare interi sorgenti live o credenziali nel repository GitHub pubblico.

**Stato reale:** produzione A267B online, ulteriori semplificazioni/test A259–A269 in staging. Non dichiarare tutto completato o invii automatici attivi prima dei gate.
