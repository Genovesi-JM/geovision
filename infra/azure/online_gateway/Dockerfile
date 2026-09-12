# Reuse only the already reviewed, secret-free GeoVision runtime and libraries.
FROM geovisionpilothcwka3w.azurecr.io/geovision-backend@sha256:37e0280a688c9ae8915c4adec00c83b9ff2895f28c11a0a18d986f0f4dc1de00

WORKDIR /gateway
ENV PORT=8080 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --chown=10001:10001 gateway.py /gateway/gateway.py
COPY --chown=10001:10001 manifest.json /gateway/manifest.json
COPY --chown=10001:10001 public/ /gateway/public/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/_gateway/health', timeout=4).read()"]
ENTRYPOINT ["python", "/gateway/gateway.py"]
CMD []
