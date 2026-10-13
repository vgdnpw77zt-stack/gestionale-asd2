# BODYMIND AERIAL STUDIO ASD — MANDATO DI STABILIZZAZIONE PRODUZIONE
## Recovery + audit documentale + contabilità + interfacce + collaudo end-to-end

### Identità del progetto: vincolo assoluto
Lavora SOLO su BodyMind:
- GitHub: \`vgdnpw77zt-stack/gestionale-asd2\`.
- Railway: progetto \`86e0ffee-cf06-4da9-97e2-c3571b669f2a\`, servizio \`bodymind-app\` \`9dfa6991-ce53-4ad3-a118-dfd605c55548\`, ambiente production \`d29c5580-4964-422c-af70-d72b3ed47aa0\`.
- Dominio: \`https://app.bodymindaerialstudio.life\`.
- SQLite persistente: \`/data/tenants/default/asd.db\`; dati e file persistenti sotto \`/data\`.
- Codice di riparazione NON online sul branch \`bodymind-accounting-repair-20261013\`, PR #4 in DRAFT. Non fare merge automatico.
- Ultimo deployment online verificato \`b6b78a15-3ea2-49f7-9765-5aae8a429c3c\`, build SHA \`64c9a2163313f5b82f9c3f27b4476133a90409db\`.
- **MAI** modificare altri progetti, in particolare Stair & Steel.

### Ruolo unico e responsabilità
Agisci come team coordinato di: Staff Engineer Python/Flask/SQLite, Database Reliability Engineer, archivista documentale ASD, QA Engineer end-to-end, Security Engineer, disaster recovery/backup engineer, UX/UI designer desktop e mobile, Railway/GitHub release engineer. Un solo responsabile dei rilasci. Le metriche infrastrutturali SUCCESS NON equivalgono a comportamento applicativo corretto.

### PRIORITÀ ZERO — INTEGRITÀ E BACKUP (BLOCCANTE)
1. Inventaria integralmente e in SOLA LETTURA tutto il volume: DB, documenti, documenti inbound, modulo unico, certificati medici, tutela minori, firme, verbali, ricevute, materiali associati e file orfani. Esplora anche radici inattese, non soltanto i percorsi già conosciuti.
2. Registra ID, tipo, path, esistenza fisica, dimensione, SHA-256, associazione tesserata/pratica, stato visibilità; NON divulgare contenuti personali nei log. Confronta i conteggi storici disponibili: all'ultimo avvio riuscito risultavano 44 tesserate, 162 record documenti, 168 inbound, 384 media, 18 onboarding, 3 signatures, 24 user_static, 126 pagamenti, 118 ricevute; sono SOLO una baseline, non una prova che tutti i file siano integri.
3. Usa backup SQLite ONLINE API per ottenere un'istantanea coerente, anche in WAL. NON copiare ingenuamente il solo \`asd.db\` mentre sono attivi i writer. Evita snapshot multirecord e trasferimenti durante mutazioni dei file non sospese o riconciliate.
4. Prepara un backup **esterno al volume** (download o storage autorizzato), contenente database e TUTTI i dati utente; file manifest firmabile con SHA-256 per ogni file, conteggi e versione del formato. Nessuna copia valida senza verifica di lettura, ZIP integrity, PRAGMA integrity_check/fk e controllo degli allegati. I vecchi backup sono sullo stesso volume e non sono disaster recovery indipendente.
5. Implementa nel gestionale un Centro Backup riservato all'amministratore: stato/inventario, Genera, Scarica, Verifica file scaricato, Importa in area di staging, Anteprima differenze, Avvia ripristino guidato SOLO in manutenzione con ulteriore conferma. Proteggi contro traversal, ZIP bomb, CSRF, accessi non-admin, doppia attivazione e file alterati.
6. PROVA realmente export -> download -> upload -> verifica -> restore su volume/ambiente temporaneo VUOTO -> confronto conteggi e impronte -> riapertura di PDF, certificati, moduli e verbali. Il restore non deve mai sostituire automaticamente il volume live, sovrascrivere ricevute o cancellare documenti.
7. Stop al rilascio se una categoria, anche archivio invisibile, risulta mancante, irraggiungibile o ambiguamente associata. Non cancellare backup esistenti. Le routine di startup non devono eliminare backups o ripristinare DB antichi autonomamente.
8. \`bodymind_archive_guard.py\` e relativi test sono già preparati sul branch di riparazione per inventario/backup/verify/ripristino offline. Non confondere questi test isolati con l'esistenza di un Centro Backup UI già operativo.

### PAGAMENTI: UNICA VERITÀ CONTABILE E RICEVUTE
1. Caso riproducibile: GIORGIA BAFFONI, tesserata ID 14, mensile ottobre 2026, richiesta €50 contanti. Form 'Salva pagamento' fallisce con \`IntegrityError UNIQUE constraint failed: pagamenti.tesserato_id, pagamenti.mese, pagamenti.anno, pagamenti.causale\`. Sul gestionale appare 'DA PAGARE', e in una visualizzazione era presente movimento €50. Non dedurre \`stato\`, causale e ricevuta dal solo screenshot: leggerli dal DB con query in SOLA LETTURA.
2. Rebecca Picchi: l'utente riferisce che la registrazione è riuscita. Verificare senza alterarla, non supporre che il risultato generico HTTP 303 equivalga a pagamento contabile.
3. Normalizza TUTTE le causali compatibili (mensile, quota_mensile, quota, varianti storiche); prima di inserire, controlla collisioni contabili, movimentazioni emesse, ricevute e stati contraddittori.
4. Una riga \`unpaid\` senza ricevuta può essere completata in modo autorizzato e tracciato se inequivocabile; mai sovrascrivere righe già saldate, annullate, esentate, con ricevuta collegata o con dati conflittuali. Per anomalie mostra messaggio amministrativo chiaro, senza SQL grezzo né duplicazione.
5. Se una quota è ridotta, esente, sospesa o non dovuta, la decisione va registrata separatamente dall'incasso con autore/motivo/data; zero euro non è una ricevuta di pagamento; preserva numero progressivo e tutte le ricevute storiche. Pagamenti parziali non devono trasformare indebitamente l'intero dovuto in pagato.
6. UI modulo: tipo di pagamento e ID movimento devono essere congruenti, 'Apri pagamento' deve aprire la riga corretta (non trasformare mensile in iscrizione), pulsanti 'Registra', 'Correggi' e 'Aggiorna' devono avere comportamenti distinti.
7. Usa una singola funzione canonica read-only per il conteggio degli incassi e dei dovuti su desktop/mobile/centro operativo/dashboard/segreteria. Esegui test reali su route POST in DB SQLite sintetico e verifica inserimenti/rollback/ricevute/UNIQUE.

### ALERT E VERITÀ AMMINISTRATIVA
1. Caso ALICE ILARE ID 26: nei log storico \`onboarding_status=waiting_payment\` e \`onboarding_blocked_reason=1 pagamenti da verificare\`. Utente segnala falso alert solo su PC nel Cuore/Centro operativo mentre su mobile è già risolto. Lo stato storico non è automaticamente la verità corrente.
2. Risali alla sorgente di OGNI alert desktop (smart_alerts, operational tasks, onboarding stored flags e view) e incrociala con gli effettivi movimenti, quote mensili, decisioni non-dovuto, stagioni/periodi e documenti.
3. Non nascondere segnali per sola condizione grafica! Correggi la fonte; reindicizza/chiudi eventi obsoleti soltanto dopo verifica e audit trail; non cancellare lo storico. Un caso aperto valido deve rimanere visibile ovunque.
4. Test su 3 stati: debito reale rosso; pagato verde; non dovuto/sospeso 'non dovuto' neutro. Conferma stesso stato su PC e mobile, centro operativo e scheda atleta, anche dopo refresh/login.

### DOCUMENTI ASD E CICLO DI VITA
Per OGNI tesserata e categoria: modulo unico firmato, consenso genitore, certificato medico, scadenze, caricamenti hub, assegnazioni, preview/download, verbali, ricevute, file inbound, allegati collaborazione. Verifica che associazione da hub aggiorni realmente la scheda, non richieda doppie registrazioni, non crei duplicati e non segni come valido un certificato solo caricato ma non controllato. Verifica HTTP download 200, MIME, integrità SHA e autorizzazione. NESSUN purge automatico o detach di file senza backup esterno e confronto approvato.

### GRAFICA E RESPONSIVE DESKTOP 12–13"
Collauda tutte le route principali a 1024x768, 1152x720, 1280x800, 1366x768, 1440x900 e iPhone 390x844; includi Safari Mac/iOS e Chromium. Controlla barra laterale, tabelle, pulsanti, banner, form, operatore, modali, sticky navigation, tastiera virtuale e contrasto. Nessuna sovrapposizione o scroll orizzontale globale. Gli elenchi amministrativi devono rimanere azionabili senza zoom. Usa screenshot **prima/dopo** ed esegui test funzionali, non solo verifica CSS sorgente. Nessun redesign gratuito.

### PROCESSO DI RILASCIO
1. Identifica con certezza l'ultima base Railway funzionante. Diff a livello commit tra base online, branch di produzione e branch repair: nessun cherry-pick cieco sulla PR divergente; unifica solo patch necessarie.
2. Prima un ambiente/staging con database e media COPIATI, dati sensibili privati, nessun SMS/e-mail reali, nessuna migrazione distruttiva. Backup export verificato e piano rollback operativo provato.
3. Test automatici: unit, integrazione route HTTP reali, DB con UNIQUE e WAL, ricevute numerate, upload/download/import, permessi, regressioni desktop/mobile, checksum e restore. Testa anche failure modes: storage pieno, upload interrotto, cookie sessione scaduto, doppio tap e due richieste concorrenti.
4. Rilascio Railway controllato SOLO dopo gate superati, con un'unica distribuzione e monitoraggio. A deploy ultimato testa in produzione senza creare incassi fittizi: Giorgia con un pagamento REALE già incassato e autorizzato, Alice senza falsi alert; documenti, moduli e certificati apribili; backup esportato e verificato.
5. Non modificare programmi esterni, non ruotare credenziali, non toccare service volume, non acquistare piani, non inviare SMS, non effettuare restore né cancellazioni senza esplicito consenso.
6. In ogni rapporto separa: ANALIZZATO, PATCHATO, TESTATO IN ISOLAMENTO, TESTATO IN STAGING, PUBBLICATO, VERIFICATO IN PRODUZIONE. Non dichiarare "risolto" se il sito reale non è stato verificato.

### Criterio di completamento obbligatorio
Il lavoro è concluso SOLO se: backup esterno completo scaricabile/importabile e restore testato; zero documenti presenti nel riferimento baseline persi; assenza di file visibili senza percorso valido; pagamenti sicuri e coerenti con ricevute e dashboard; alert desktop/mobile identici alla situazione amministrativa; interfaccia pienamente utilizzabile a 12–13"; test automatici ed end-to-end superati; rollback verificabile. Consegnare checklist con prove e link a CI/deployment, mai dichiarazioni generiche.
