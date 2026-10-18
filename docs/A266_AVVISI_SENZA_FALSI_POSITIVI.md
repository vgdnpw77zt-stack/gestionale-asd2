# A266 — Avvisi affidabili e dashboard più leggera

**STAGING, NON IN PRODUZIONE**. La modifica è nella patch `staging_patches/A266_filtra_falsi_avvisi.py`, applicabile al clone dei sorgenti A253/A259–A265. Non rimuove nessun dato o registro dello storico.

## Errore reale individuato
Il wrapper A229 in `core.py` tentava di filtrare avvisi di pagamento già saldati cercando `alert['tesserato_id']`, mentre gli avvisi generati dal motore conservano comunemente l'identificativo in `alert['meta']['tesserato_id']`. Il filtro saltava così casi di quote già pagate o non dovute. Anche contatori e liste di task rimanevano gonfiati.

## Fix
- Cercare prima l'ID esplicito, poi `meta.tesserato_id`.
- Confrontare lo stato della quota con il read model canonico: `pagato`, `non_dovuto`, `da_definire` non diventano nuovi mancati pagamenti.
- Applicare lo stesso criterio all'elenco task di dashboard; ricalcolare numero task aperti, bloccanti e atlete coinvolte **dopo** il filtro.
- Non silenziare certificati medici scaduti/mancanti e tutela minori (non sono filtrati per pagamento).
- Nella categoria anagrafica un recapito utilizzabile è sufficiente: email assente con telefono presente non genera un alert secondario, e viceversa. Questa scelta non rimuove documenti né modifica anagrafiche.

## QA isolato
Sorgente A266 applicato su clone A263/A265 e compilato (181 moduli Python, 0 errori). Test AST con stati fittizi: quote pagate e non dovute spariscono dagli avvisi; quota dovuta e certificato critico rimangono; contatori e lista di task vengono corretti. **Nessuna connessione alla produzione.**

## Vincoli di rilascio
1. Backup verificato DB/media e mantenimento della A253 attiva.
2. Collaudo dei casi reali senza creare false richieste di pagamento; verifiche certificati e tutela.
3. Analisi delle vecchie route del Cuore: eliminare gli elementi di navigazione, non la tracciabilità delle pratiche.
4. No Railway redeploy non controllato. Non applicare A265/A266 separatamente da A259–A264 senza collaudo complessivo.

**Produzione inalterata.**
