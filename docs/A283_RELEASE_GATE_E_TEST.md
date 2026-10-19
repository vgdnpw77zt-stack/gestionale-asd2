# A283 — candidato tecnico; NON pubblicato

Data: 2026-10-19. Correzione dei promemoria che potrebbero richiedere settembre ad atlete con ingresso ottobre confermato. La lettura A269 richiedeva fino a qui solo un record `quote_mensili` esistente: ora usa `before_start` + `start_date` A276; salta i mesi precedenti all'ingresso verificato e trattiene per revisione qualunque data d'ingresso non confermata.

Dati reali A279 (in versione privata, **non pubblicati**): 112 incassi per €6.120: contanti €3.295, bonifici €2.590, carta €235. Le 9 nuove iscritte ottobre hanno €385 di quote di iscrizione (incluse €35 di Giammei, valore confermato dall'utente) e €590 di mensilità. Coorti 34 settembre / 9 ottobre nel manifesto privato A281.

QA locale: **54 test passati, 1 saltato**, AST di **191 moduli Python**. Mancante test completo di bootstrap Flask e test autenticati su replica DB+media.

**BLOCCO RELEASE**: il collegamento Railway disponibile non consente la lettura/esecuzione shell sul volume live. A273 ha protetto l'archivio; A279 indicava **86 ricevute attive prive di PDF**, non recuperate nell'archivio compressi visionato. Non falsificare originali PDF né prometterne il recupero. Il vecchio cold-start Railway esegue 131 script storici: vietato restart/redeploy cieco. Prima di singolo rilascio: snapshot sicuro DB/media su supporto esterno, prova restore clone, test avvio Flask e auth, verifiche comparate PDF, autorizzazione sul volume.

Il codice patch A283 è separato dai dati personali e NON deve essere applicato direttamente alla produzione senza gli altri moduli A274–A281 testati in modo coordinato. Le notifiche WhatsApp effettive richiedono provider, consensi e template; SumUp richiede conferma provider per segnare pagato.
