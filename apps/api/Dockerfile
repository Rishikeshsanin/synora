# Build with repository root as context: docker build -f apps/api/Dockerfile .
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* && useradd -m -u 10001 app
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api/synora ./synora
COPY engines/music ./engines/music
USER app
ENV PYTHONUNBUFFERED=1
CMD ["sh","-c","exec uvicorn synora.api:app --no-access-log --host 0.0.0.0 --port ${PORT:-8000}"]
