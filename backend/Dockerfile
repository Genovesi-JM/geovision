FROM python:3.12-slim AS wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.deploy.txt ./
RUN python -m pip wheel --wheel-dir /wheels --requirement requirements.deploy.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8010

RUN groupadd --gid 10001 geovision \
    && useradd --uid 10001 --gid geovision --home-dir /app --no-create-home \
        --shell /usr/sbin/nologin geovision \
    && mkdir -p /app /app/data/object-storage /runtime \
    && chown -R 10001:10001 /app /runtime

WORKDIR /app
COPY --from=wheels /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels
COPY --chown=10001:10001 . .

USER 10001:10001
EXPOSE 8010
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8010') + '/health', timeout=4).read()"]

CMD ["python", "start.py", "serve"]
