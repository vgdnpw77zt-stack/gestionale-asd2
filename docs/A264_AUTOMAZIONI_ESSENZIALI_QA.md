# A264 — Automazioni più semplici, senza perdere regole

**Solo STAGING: non è un deploy e non abilita nuovi invii automatici.**

Intervento su `routes_automation_pro.py`, usando la route già esistente `/motore-automazioni` e senza modificarne la logica POST:

- Hero compatto «Automazioni» e collegamento immediato allo storico invii, senza link al Cuore Operativo.
- Cinque sezioni native espandibili: Pagamenti; Certificati e documenti; Campi Estivi; Eventi, saggi e gare; Canali e livello di autonomia. Solo Pagamenti aperta inizialmente.
- Tutti i 16 checkbox e i relativi 16 livelli `auto / preview / manual` restano nel medesimo form; collassare una sezione non disabilita né cancella i valori.
- Eliminate dalla UI le tre grandi tappe Motore/Risolvi/Cuore, sostituite dalle azioni concrete «Esegui ora», «Storico invii», «Salva».
- Ridotte ombre, dimensione delle card, gradienti e spazi vuoti; preferiti colori sobri, contrasto e focus visibile.

## QA di staging

Test basato sulla funzione GET reale estratta dall'AST, eseguita con `load_config` e CSRF sintetici, **senza DB né Flask**. Verificati 5 `details`, 16 checkbox, 16 select e un unico POST form. Playwright su **375, 390, 428, 768, 1024, 1152, 1366, 1440 px**: nessun overflow; 3 schede visibili all'apertura, 7 dopo espansione di Certificati. Nessun errore JavaScript. È stato corretto un conflitto CSS che inizialmente mostrava sezioni chiuse.

Non modifica scheduler, provider, invii, SumUp, ricevute, quote, documenti o notifiche reali.

## Ulteriori decisioni tecniche, NON ancora realizzate

- Regole di promemoria con giorni configurabili (5/7/10 prima, ripetizione 3 giorni dopo) e stop su pagamento verificato: da sviluppare con migrazione DB e test anti-duplicati, non sono operative in A264.
- WhatsApp Business ordinario non equivale a invio programmato via API ufficiale: richiede provider/Meta, consenso e gestione template. Con integrazione mancante, preparare solo messaggi manuali, senza segnalare invii effettuati.
- Il link SumUp potrà essere mostrato nei promemoria e nell'app Famiglie dopo configurazione; un click non deve cambiare lo stato a pagato senza conferma affidabile.
- Restano numerosi collegamenti legacy a `/cuore-operativo` in moduli storici. A263/A264 alleggeriscono le superfici principali, ma la migrazione completa degli accessi va collaudata in un clone integrale.
- Validare il rendering finale con autenticazione, CSS completo e flussi amministrativi. Tenere A253 in produzione fino a quel momento.

**A253 online e inalterata — zero deploy, zero scritture DB, zero eliminazione storici.**
