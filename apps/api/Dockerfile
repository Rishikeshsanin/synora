FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 app
COPY synora ./synora
USER app
ENV PYTHONUNBUFFERED=1
CMD ["sh","-c","exec uvicorn synora.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
