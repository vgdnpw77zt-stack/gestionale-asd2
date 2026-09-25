FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASDPRO_RUNTIME_DIR=/data \
    ASD_PRO_DATA_DIR=/data \
    ASD_MAX_UPLOAD_MB=50

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
COPY railway_fix49_parts/ /tmp/fix49_parts/

RUN cat /tmp/fix49_parts/FIX49_PAYLOAD.b64.part* \
    | tr -d '\n\r\t ' \
    | base64 -d > /tmp/bodymind_fix49_railway.zip \
 && echo "7b9c5a7a9e26d5369abffc8391f2563b27178e9053e350cb66db5e1e85a0e62e  /tmp/bodymind_fix49_railway.zip" | sha256sum -c - \
 && unzip -q /tmp/bodymind_fix49_railway.zip -d /opt/bodymind \
 && rm -rf /tmp/bodymind_fix49_railway.zip /tmp/fix49_parts

WORKDIR /opt/bodymind/fix49_railway_payload

RUN pip install --no-cache-dir -r requirements_runtime.txt \
 && pip install --no-cache-dir "gunicorn>=22,<24"

EXPOSE 8080

CMD ["sh","-c","python -c 'from asd_app.core import init_db; init_db()' && exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 180 --access-logfile - --error-logfile - app:app"]
