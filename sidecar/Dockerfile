FROM python:3.12-alpine

LABEL maintainer="LanSentry"
LABEL description="Sidecar de automação de bloqueio de dispositivos no Pi-hole via PostgreSQL"

WORKDIR /app

# Instala sqlite e dependências mínimas do Alpine
RUN apk add --no-cache sqlite bash tzdata

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sidecar.py .

CMD ["python", "-u", "sidecar.py"]
