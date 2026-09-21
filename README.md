# ASD Pro Goldclass — deployment package

Questa è la versione completa del gestionale originale ripulita per repository GitHub + frontend Netlify + backend FastAPI/MongoDB.

## Cosa è stato corretto
- rimosso `node_modules`, cache, `.git`, file locali e archivi enormi;
- rimosso il vecchio layer CRACO/Emergent dal build di produzione;
- mantenuto React con build standard `react-scripts`;
- risolti gli import `@/` rendendoli compatibili con CRA senza alias CRACO;
- aggiunto `_redirects` SPA per evitare i 404 di Netlify;
- `netlify.toml` già configurato con base `frontend` e publish `build`;
- proxy Netlify `/api/*` verso il backend FastAPI tramite la variabile `BACKEND_URL`;
- nessuna chiave segreta inclusa nel repository;
- backend predisposto per container e deploy separato;
- requirements di produzione separati da quelli di sviluppo;
- service worker aggiornato per evitare cache del vecchio frontend.

## Architettura online

GitHub contiene tutto il codice sorgente.

Netlify pubblica il frontend React.

Il backend FastAPI deve essere eseguito su un servizio server/container con MongoDB (ad esempio un servizio Docker compatibile). Netlify non esegue direttamente il server FastAPI persistente: il proxy incluso nel progetto collega `/api/*` del sito al backend.

## Netlify

Collega il repository GitHub a Netlify. Il `netlify.toml` configura automaticamente:

- Base directory: `frontend`
- Build command: `npm run build`
- Publish directory: `build`
- Node: 20
- SPA fallback
- Functions directory: `netlify/functions`

Imposta in Netlify la variabile:

`BACKEND_URL=https://URL-PUBBLICO-DEL-BACKEND`

Non impostare qui password MongoDB, JWT o chiavi Stripe: quelle restano esclusivamente nel backend.

## Backend

Usa `backend/Dockerfile` e `backend/requirements.txt`.

Variabili obbligatorie: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `CORS_ORIGINS`.

Per `CORS_ORIGINS` inserisci il dominio Netlify del frontend.

Le integrazioni Stripe, Resend e AI sono mantenute nel codice e diventano operative quando vengono configurate le rispettive variabili; non sono più presenti credenziali nel pacchetto.

## Verifica

Il backend è stato verificato con `py_compile`.

Non è stato possibile eseguire una build React completa in questo ambiente perché il progetto originale non contiene una installazione `node_modules` utilizzabile e l'ambiente di esecuzione non ha completato `npm install`. Netlify installerà le dipendenze pulite durante il build.
