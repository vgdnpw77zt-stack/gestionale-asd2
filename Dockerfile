FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends unzip libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY ASD_PRO_GOLDCLASS_ONLINE_READY.zip /tmp/asd-pro.zip
RUN unzip -q /tmp/asd-pro.zip -d /tmp/asd-pro-src \
 && cp -a /tmp/asd-pro-src/ASD_PRO_GOLDCLASS_ONLINE_READY/. /app/ \
 && rm -rf /tmp/asd-pro.zip /tmp/asd-pro-src
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /var/data/asd-pro
EXPOSE 10000
CMD ["sh","-c","gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 wsgi:application"]
