FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASDPRO_RUNTIME_DIR=/data \
    ASD_PRO_DATA_DIR=/data \
    ASD_MAX_UPLOAD_MB=500

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      unzip \
      tesseract-ocr \
      tesseract-ocr-ita \
      poppler-utils \
      libgl1 \
      libglib2.0-0 \
      fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/bodymind
COPY railway_fix49_parts/ /tmp/source_parts/

RUN cat /tmp/source_parts/FIX49_PAYLOAD.b64.part* \
    | tr -d '\n\r\t ' \
    | base64 -d > /tmp/bodymind_runtime.zip \
 && echo "7b9c5a7a9e26d5369abffc8391f2563b27178e9053e350cb66db5e1e85a0e62e  /tmp/bodymind_runtime.zip" | sha256sum -c - \
 && unzip -q /tmp/bodymind_runtime.zip -d /opt/bodymind \
 && rm -rf /tmp/bodymind_runtime.zip /tmp/source_parts

WORKDIR /opt/bodymind/fix49_railway_payload

# Top2 runtime corrections: overwrite the affected modules after unpacking the legacy payload.
COPY top2_overlay/routes_backup.py /opt/bodymind/fix49_railway_payload/asd_app/routes_backup.py
COPY top2_overlay/routes_bodymind_fix10.py /opt/bodymind/fix49_railway_payload/asd_app/routes_bodymind_fix10.py

RUN python -m py_compile asd_app/routes_backup.py asd_app/routes_bodymind_fix10.py \
 && pip install --no-cache-dir -r requirements_runtime.txt \
 && pip install --no-cache-dir "gunicorn>=22,<24"

COPY migration_upload.py /opt/migration_upload.py

EXPOSE 8080

CMD ["sh","-c","python -c 'from asd_app.core import init_db; init_db()' && exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 300 --access-logfile - --error-logfile - app:app"]
