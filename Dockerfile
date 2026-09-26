FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ASDPRO_RUNTIME_DIR=/data ASD_PRO_DATA_DIR=/data ASD_MAX_UPLOAD_MB=500
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tesseract-ocr tesseract-ocr-ita poppler-utils libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/bodymind
COPY requirements_runtime.txt /opt/bodymind/requirements_runtime.txt
RUN pip install --no-cache-dir -r /opt/bodymind/requirements_runtime.txt
COPY release_apply.py /opt/bodymind/release_apply.py
COPY release_autopilot_r3.py /opt/bodymind/release_autopilot_r3.py
COPY release_autopilot_r4.py /opt/bodymind/release_autopilot_r4.py
COPY release_autopilot_r5.py /opt/bodymind/release_autopilot_r5.py
COPY release_cleanup_r2.py /opt/bodymind/release_cleanup_r2.py
COPY runtime_launcher.py /opt/bodymind/runtime_launcher.py
RUN mkdir -p /opt/bodymind-migration && cp /opt/bodymind/runtime_launcher.py /opt/bodymind-migration/migration_upload.py
EXPOSE 8080
CMD ["python","/opt/bodymind-migration/migration_upload.py"]
