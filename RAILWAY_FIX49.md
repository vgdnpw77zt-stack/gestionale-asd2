# BodyMind FIX49 — Railway production

This branch reconstructs the sanitized Railway payload derived from the exact FIX49 application.

Functional application parity check:
- 301 application files are byte-for-byte identical to FIX49.
- 0 application files changed.
- Only static/app_icon.icns is omitted because it is a macOS desktop icon and is not used on Railway.
- Legacy macOS launchers containing the old ngrok credential are not included.

Railway payload SHA-256:
7b9c5a7a9e26d5369abffc8391f2563b27178e9053e350cb66db5e1e85a0e62e

Original FIX49 SHA-256:
0d9cff6215eb5582801f2f648bd414dd38567521a8c11725483f0130f4f86a1f

Persistent runtime directory:
/data
