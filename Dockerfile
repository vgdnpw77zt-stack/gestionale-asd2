FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ASDPRO_RUNTIME_DIR=/data ASD_PRO_DATA_DIR=/data ASD_MAX_UPLOAD_MB=500
WORKDIR /opt/bodymind-migration
COPY migration_upload.py /opt/bodymind-migration/migration_upload.py
EXPOSE 8080
CMD ["python","/opt/bodymind-migration/migration_upload.py"]
