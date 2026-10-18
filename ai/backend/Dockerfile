FROM python:3.12-slim

# LibreOffice headless (hwp/hwpx/docx/xlsx/doc -> PDF), Korean fonts, Tesseract kor (OCR baseline, CPU)
# shortcut: HWP 5.x layout needs the H2Orestart extension; without it hwp falls back to the native text parser
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer libreoffice-calc fonts-nanum tesseract-ocr tesseract-ocr-kor libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY ai ./ai

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
