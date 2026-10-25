FROM python:3.11-slim
# BodyMind A301 immutable source + SQLite read-only guard, no historic release scripts.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ASDPRO_RUNTIME_DIR=/data ASD_PRO_DATA_DIR=/data ASD_MAX_UPLOAD_MB=500
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tesseract-ocr tesseract-ocr-ita poppler-utils libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/bodymind
COPY requirements_runtime.txt /opt/bodymind/requirements_runtime.txt
RUN pip install --no-cache-dir -r /opt/bodymind/requirements_runtime.txt
COPY bootstrap/clean_runtime_launcher.py /opt/bodymind/clean_runtime_launcher.py
COPY bootstrap/family_a337.css.zlib.base64 /opt/bodymind/family_a337.css.zlib.base64
COPY bootstrap/family_a340.css.zlib.base64 /opt/bodymind/family_a340.css.zlib.base64
COPY bootstrap/family_a341.css /opt/bodymind/family_a341.css
COPY bootstrap/family_a341.js /opt/bodymind/family_a341.js
COPY bootstrap/family_a342_motion.css /opt/bodymind/family_a342_motion.css
COPY bootstrap/family_a343_visible_waves.css /opt/bodymind/family_a343_visible_waves.css
COPY bootstrap/family_a344_luxury.css /opt/bodymind/family_a344_luxury.css
# Existing Railway startCommand remains compatible, but now executes this CLEAN code only.
RUN mkdir -p /opt/bodymind-migration && cp /opt/bodymind/clean_runtime_launcher.py /opt/bodymind-migration/migration_upload.py
EXPOSE 8080
CMD ["python","/opt/bodymind/clean_runtime_launcher.py","start"]
