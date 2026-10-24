FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=4010 \
    HOST=0.0.0.0 \
    DATABASE_PATH=/data/rfp_assistant.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data /app/data/uploads /app/logs

EXPOSE 4010

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4010/api/health').status==200 else 1)"

CMD ["python", "run.py"]
