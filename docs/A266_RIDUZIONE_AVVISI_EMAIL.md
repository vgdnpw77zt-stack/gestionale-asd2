# A266 — Riduzione degli avvisi inutili

**STAGING, NON PUBBLICATO.**

Il generatore `get_operational_alerts` nel sorgente reale BodyMind crea una segnalazione di scheda incompleta quando manca il campo `email`. L'ASD usa principalmente cellulari e WhatsApp; l'email non è disponibile per tutte le famiglie e **non deve produrre da sola un avviso amministrativo quotidiano**.

La patch `A266_optional_email_alert.py` rimuove esclusivamente `email` dall'elenco dei campi verificati come obbligatori nell'avviso generico. Restano gli avvisi per telefono, corso, data di nascita, certificati, tutela minori e pagamenti. L'email rimane consultabile e inseribile nella scheda.

QA isolato A265 → A266: patch applicabile una volta e idempotente; AST valido; differenza esatta di una riga; nessuna scrittura DB. Non toccare il database di produzione. Non attivare nuovi invii WhatsApp/email.

Il Cuore Operativo è nascosto dalle UI ordinarie in A263/A264; i dati di audit non vanno eliminati. Il rumore dei vecchi contatori non è ancora dichiarato completamente risolto: verificare la dashboard effettiva su un clone con dati reali, e solo poi considerare il deploy.
