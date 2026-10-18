# BodyMind A265 — Contabilità e uscite leggibili su mobile

**Stato: STAGING. Non è stato eseguito alcun deploy; A253 in produzione resta invariata.**

## Difetto strutturale accertato nel sorgente A256
In `core.py`, la funzione `_bodymind_expense_entry_v11` intercetta in `before_request` GET e POST di `/contabilita` e restituisce `_bodymind_uscite_v11_impl()`, oscurando la route corretta della contabilità A253. L'elenco `/pagamenti/uscite` è una tabella `min-width:900px` anche su iPhone: le colonne di dettaglio possono rimanere fuori schermo. La segnalazione dell'utente specifica che il bonifico al presidente esiste nel registro desktop ma non compare correttamente sul telefono. **Non generare un movimento nuovo.**

## Correzione sviluppata nel workspace di test A265
- `core.py`: eliminare `/contabilita` dall'intercettazione `before_request` (restano `/uscite`, `/pagamenti/uscite`); il GET/POST contabilità rientra così nella route A253 originale, con CRUD manuale e riconciliazione.
- Render della tabella uscite: celle con etichette accessibili; su mobile righe-card verticali; data, causale, importo, metodo, giustificativo, modifica, senza necessità di scorrere 900px.
- Filtro lettura `metodo=bonifico` sulle ultime 300 uscite, più collegamento «Tutte le uscite». Non altera i totali né le registrazioni.
- `routes_contabilita.py`: metodo visibile nel registro operativo, link «Apri uscita» ai movimenti di `bodymind_uscite`, righe responsive.
- `bodymind_a265_cashbook.py`: pannello in sola lettura; numero versamenti e mensilità distinte per contanti/bonifico/carta-SumUp; iscrizioni e quote mensili; riduzioni ed esenzioni documentate; uscite per metodo con singole causali bonifico e collegamento alla registrazione.
- Tutti i riepiloghi devono quadrare con il canonico A237/A253. Incassi annullati/non pagati esclusi; metodi sconosciuti mai imputati automaticamente ai contanti. La **cassa contanti teorica** è entrate contanti meno uscite contanti: non costituisce attestazione della giacenza fisica custodita dalla presidente in assenza di saldo iniziale e trasferimenti interni.
- Riduzioni ricavate da `quote_mensili` e `bodymind_quota_decisioni`, conteggiate per atleta/mese/anno una sola volta; valori indicativi in mancanza di tariffari storici immutabili. Un'esenzione non è un incasso.

## QA isolato completato
Patch applicata solo a copia A256/A253 (senza accesso DB reale). Sorgenti `core.py` e `routes_contabilita.py` compilati, modulo A265 compilato; test con fixture SQLite: entrate, uscite, mese frazionato in due tranche, bonifico al presidente fittizio, sconti, esenzioni, metodo di pagamento, filtro annullati e incompatibilità canoniche. Snapshot prima/dopo il test in sola lettura identico. Browser Chromium: **375, 390, 428, 768, 1024, 1152, 1280, 1366 px**, nessun overflow orizzontale, bonifico e causale visibili in mobile.

SHA-256 sorgenti staging:
- `bodymind_a265_cashbook.py`: `1ba2799f1ff64be0582c57639dc5e124e5562846e9a7f4bb8ca92`
- `patch_a265.py`: `21866e2a9b9d1e36240498ac49f27013d50076d061b76373c7ccf6776e796b4c`
- `test_a265.py`: `a51b10b5d90e0da114527ea5fa43f837b8476e3fd361bf4e29f65603cba90bb8`
- `test_a265_layout.py`: `5edb8f447bb57925e25b00a055a85b7390afccefbe830587c608349e5e34bea0`

I sorgenti e i test completi sono custoditi nell'artefatto locale `BodyMind_A265_Fix_Cassa_Mobile_STAGING.zip`. Non sono stati integrati come file applicativi su GitHub né pubblicati su Railway in questa fase: il repo pubblico non include ancora tutto il codice live e il deploy del branch causerebbe regressioni.

## Prima di dichiarare il fix concluso
1. Riconciliare il caso **reale** del bonifico al presidente direttamente dal DB production **in sola lettura**, verificando che sia presente in `bodymind_uscite` o nel movimento manuale A253, senza duplicarlo.
2. Collaudare autenticazione/CSRF e route effettive con clone di DB e media; verificare `/contabilita` e `/pagamenti/uscite` su iPhone e portatile, con ricevute, sconti, allegati, permessi, dashboard, app Famiglie.
3. Verificare regressioni A259–A264, il launcher di deployment e il rollback dei soli sorgenti; non riavviare Railway tramite launcher storico, che può riprocessare vecchie migrazioni.
4. Ottenere approvazione per il rilascio controllato. Conservare backup documento/DB/progressivi.

**Cuore Operativo:** mantenerne i registri di audit e le route necessarie ai flussi, ma toglierne gli avvisi duplicati dalla dashboard. Evitare di cancellare dati o disabilitare certificati e scadenze reali.
