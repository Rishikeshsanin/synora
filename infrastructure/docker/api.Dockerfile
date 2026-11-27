FROM python:3.12-slim AS build
WORKDIR /build
COPY apps/api/requirements.lock .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock
FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 synora && useradd --uid 10001 --gid 10001 --create-home synora
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=10001:10001 apps/api/synora ./synora
COPY --chown=10001:10001 engines/music ./engines/music
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health',timeout=3)"
CMD ["sh","-c","exec uvicorn synora.api:app --no-access-log --host 0.0.0.0 --port ${PORT:-8000}"]
