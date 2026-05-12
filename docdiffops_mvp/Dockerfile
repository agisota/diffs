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

# Bundle pdf.js (legacy IIFE build) locally — Cloudflare CDN versions are
# unreliable and the prod app cannot depend on uncontrolled third-party
# CDNs. We pin to 3.11.174 (the last legacy-IIFE-first release that works
# without ES modules and a separate worker bundle).
RUN mkdir -p /app/docdiffops/static/pdfjs && \
    curl -fsSL https://unpkg.com/pdfjs-dist@3.11.174/legacy/build/pdf.min.js \
        -o /app/docdiffops/static/pdfjs/pdf.min.js && \
    curl -fsSL https://unpkg.com/pdfjs-dist@3.11.174/legacy/build/pdf.worker.min.js \
        -o /app/docdiffops/static/pdfjs/pdf.worker.min.js && \
    test -s /app/docdiffops/static/pdfjs/pdf.min.js && \
    test -s /app/docdiffops/static/pdfjs/pdf.worker.min.js

ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "docdiffops.main:app", "--host", "0.0.0.0", "--port", "8000"]
