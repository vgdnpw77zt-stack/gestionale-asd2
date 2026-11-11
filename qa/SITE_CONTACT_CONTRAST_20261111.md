# BodyMind — contrasto Contatti — 11 novembre 2026

## Stato: testata, NON PUBBLICATA
Ramo: bodymind-site-a351-contact-contrast-20261111.
Commit candidato verificato: 2fa28e849108e7e70ab4bf7422e3f013ccf58ec3.
Sito attualmente pubblicato: bdc69283dda179715d4c2d18e49b44e6950d68af, deployment faed3e4f-c605-4dc9-b75c-1fb574089fb6.
Il tentativo di accept-deploy è stato bloccato dal sistema di approvazione:
"Cancelled — the user did not approve this action. No changes were made."
Nessun nuovo deployment è stato avviato.

## Modifica
Due regole di colore in site/static/sunrise.css: la section-label dei Contatti eredita il colore chiaro delle sezioni scure; le etichette dei collegamenti diventano #D8EBE7. Aggiornato parametro versione CSS nel template.
Nessuna modifica a layout, foto, crop, video, JavaScript, Flask, contenuti o funzioni.
Nessuna operazione sul servizio bodymind-app o sui dati del gestionale.

## Test eseguiti
WebKit su pagina pubblica reale con sostituzione della sola risposta sunrise.css per la candidata.
Viewport 375×667, 390×844, 430×932 e 1440×1000.
Run superata: https://github.com/vgdnpw77zt-stack/gestionale-asd2/actions/runs/43030612744
Artefatto: contact-contrast-webkit, conservazione 14 giorni.
Test verificano HTTP200, nessun errore pageerror JS, nessun overflow orizzontale, scritta Home separata da medaglie e titolo, apertura menu e navigazione a Contatti, href dei collegamenti e geometria delle etichette identici prima/dopo.
Il contrasto è misurato tra il colore CSS del testo e i pixel del fondo reso da WebKit nascondendo temporaneamente l'etichetta, centrata nel viewport per evitare la barra fissa.
Il primo run 43030328944 era fallito perché il campionamento includeva il pulsante fisso: corretto il test, non la grafica.
Il runtime locale non disponeva delle dipendenze WebKit: test reali eseguiti su GitHub Actions.
Nessuna prova su iPhone fisico né certificazione globale di accessibilità.

| Testo, 390 px | Prima | Candidata |
|---|---:|---:|
| INIZIA DA QUI | 3,18:1 | 13,89:1 |
| Instagram | 4,53:1 | 14,73:1 |
| Già con noi? | 4,44:1 | 14,43:1 |

Screenshot prima/candidata, non dopo produzione:
https://chatgpt.com/library?file_id=libfile_c7d69ea932108191b0d6548b54d0b2df&account_id=personal

## Punto di ripresa
Patch Railway pendente: 674477a5-6540-4e5b-98bf-d8eed9196f21.
Due sole modifiche staged: branch e commitSha di bodymind-site.
Project 86e0ffee-cf06-4da9-97e2-c3571b669f2a, environment d29c5580-4964-422c-af70-d72b3ed47aa0, service cc7189e7-4f22-41a5-b7b4-108564701542.
Serve sbloccare l'approvazione della pubblicazione, rileggere le modifiche pendenti e applicare solo quelle autorizzate.
Poi attendere SUCCESS e replica online e rieseguire qa/contact_contrast_qa.py online (senza sostituzione CSS), aggiornando il workflow sul ramo; verificare screenshot e rapporto.
Non dichiarare completato prima della verifica reale online. Nessun'altra attività avviata.

## Rollback dopo eventuale pubblicazione
Ripuntare esclusivamente bodymind-site al commit bdc69283dda179715d4c2d18e49b44e6950d68af del ramo bodymind-site-a351-kicker-qa-20261110; applicare e verificare health e pagina pubblica.
Prima della pubblicazione non è necessario rollback: la produzione è ancora a quel commit.
