FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-rus \
    fonts-dejavu \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY docdiffops /app/docdiffops
COPY samples /app/samples

ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "docdiffops.main:app", "--host", "0.0.0.0", "--port", "8000"]
