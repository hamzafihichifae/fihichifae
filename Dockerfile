# syntax=docker/dockerfile:1.6
# Backend service: the Python API only (pages and images are served by the
# frontend service, data lives in MySQL and the object storage).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2 \
    FIHI_ENV=production \
    FIHI_TRUST_PROXY=1 \
    FIHI_HOST=:: \
    PORT=8000

# security updates + unprivileged runtime user
RUN apt-get update && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY server.py docker-entrypoint.py ./
# images shipped with the code: copied into the bucket at start-up when missing
COPY seed ./seed

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/v1/ping' % os.environ.get('PORT','8000'), timeout=3).getcode()==200 else 1)"

EXPOSE 8000

USER appuser
CMD ["python", "docker-entrypoint.py"]
