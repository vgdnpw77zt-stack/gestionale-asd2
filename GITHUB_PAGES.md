# GitHub Pages — ASD Pro Goldclass

Questo pacchetto è predisposto per GitHub Pages tramite GitHub Actions.

IMPORTANTE: `index.html` sorgente è in `frontend/public/index.html`. Non deve essere nella root: il workflow compila React e genera automaticamente `frontend/build/index.html`, che viene pubblicato su Pages.

## Pubblicazione
1. Estrai questo ZIP sul computer.
2. Carica TUTTO il contenuto estratto nella root del repository GitHub (non caricare lo ZIP come singolo file).
3. In Settings → Pages scegli Source: GitHub Actions.
4. Fai commit/push su `main`.
5. Il workflow `.github/workflows/static.yml` installa le dipendenze, compila `frontend` e pubblica `frontend/build`.

## Backend
GitHub Pages ospita soltanto il frontend. Login, dati, pagamenti e altre funzioni server richiedono il backend FastAPI/MongoDB pubblico.
Imposta nel repository GitHub la variabile Actions `REACT_APP_BACKEND_URL` con l'URL HTTPS del backend prima del build, se vuoi usare le funzioni collegate al server.
